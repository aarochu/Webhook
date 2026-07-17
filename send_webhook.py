#!/usr/bin/env python3
"""
D4zr + Prototype
Send one message at a time (with optional user ping) through a Discord webhook.
Cooldown prevents accidental double-sends.
"""

from __future__ import annotations

import json
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, NamedTuple

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    tk = None

# Leave empty — paste your webhook in the app when you run it. Never commit real webhooks.
DEFAULT_WEBHOOK = ""

# Tests patch this to point at a local mock server.
WEBHOOK_PREFIXES = (
    "https://discord.com/api/webhooks/",
    "https://discordapp.com/api/webhooks/",
)

# Auto-delete delay bounds, in seconds. 0 means delete as soon as the send confirms.
MIN_DELAY = 0
MAX_DELAY = 3600
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_IMAGE_BYTES = 25 * 1024 * 1024


class ImageAttachment(NamedTuple):
    """A local image file to upload with a webhook message."""

    filename: str
    data: bytes
    content_type: str


def attachment_from_bytes(
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> tuple[ImageAttachment | None, str | None]:
    ext = Path(filename).suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        return None, "Image must be png, jpg, gif, or webp."
    if len(data) > MAX_IMAGE_BYTES:
        return None, "Image must be under 25 MB."
    ctype = content_type or {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "application/octet-stream")
    return ImageAttachment(filename, data, ctype), None


def attachment_from_path(path: str) -> tuple[ImageAttachment | None, str | None]:
    file_path = Path(path)
    try:
        data = file_path.read_bytes()
    except OSError as exc:
        return None, f"Could not read file: {exc}"
    return attachment_from_bytes(file_path.name, data)


def _build_payload(
    content: str,
    username: str | None,
    avatar_url: str | None,
) -> tuple[dict | None, str | None]:
    payload: dict = {
        "content": content,
        "allowed_mentions": {"parse": ["users", "roles", "everyone"]},
    }
    if username and username.strip():
        payload["username"] = username.strip()
    if avatar_url and avatar_url.strip():
        url = avatar_url.strip()
        if not url.startswith(("http://", "https://")):
            return None, "Avatar URL must start with http:// or https://"
        payload["avatar_url"] = url
    return payload, None


def _encode_multipart(boundary: str, payload: dict, attachment: ImageAttachment) -> bytes:
    crlf = b"\r\n"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="payload_json"\r\n')
    body.extend(b"Content-Type: application/json\r\n\r\n")
    body.extend(json.dumps(payload).encode("utf-8"))
    body.extend(crlf)
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="files[0]"; filename="{attachment.filename}"\r\n'.encode()
    )
    body.extend(f"Content-Type: {attachment.content_type}\r\n\r\n".encode())
    body.extend(attachment.data)
    body.extend(crlf)
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body)


def _with_wait(webhook_url: str) -> str:
    """Discord only returns the created message (and its id) when wait=true."""
    sep = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{sep}wait=true"


def send_message(
    webhook_url: str,
    content: str,
    username: str | None = None,
    avatar_url: str | None = None,
    attachment: ImageAttachment | None = None,
) -> tuple[bool, str, str | None]:
    """POST a message to a Discord webhook. Returns (ok, detail, message_id)."""
    webhook_url = webhook_url.strip()
    if not webhook_url.startswith(WEBHOOK_PREFIXES):
        return False, "URL must be a Discord webhook link.", None

    if not content.strip() and not attachment:
        return False, "Message or image attachment is required.", None

    payload, err = _build_payload(content, username, avatar_url)
    if err:
        return False, err, None

    if attachment:
        boundary = secrets.token_hex(16)
        data = _encode_multipart(boundary, payload, attachment)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "WebhookMessenger/1.0",
        }
    else:
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "WebhookMessenger/1.0"}

    req = urllib.request.Request(_with_wait(webhook_url), data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status not in (200, 204):
                return False, f"Unexpected status: {resp.status}", None
            body = resp.read().decode("utf-8", errors="replace")
            message_id = None
            if body:
                try:
                    message_id = json.loads(body).get("id")
                except json.JSONDecodeError:
                    pass
            return True, "Message sent.", message_id
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return False, f"HTTP {e.code}: {body}", None
    except urllib.error.URLError as e:
        return False, f"Network error: {e.reason}", None


def delete_message(webhook_url: str, message_id: str) -> tuple[bool, str]:
    """DELETE a message this webhook posted. Returns (ok, detail)."""
    webhook_url = webhook_url.strip()
    if not webhook_url.startswith(WEBHOOK_PREFIXES):
        return False, "URL must be a Discord webhook link."

    req = urllib.request.Request(
        f"{webhook_url}/messages/{message_id}",
        headers={"User-Agent": "WebhookMessenger/1.0"},
        method="DELETE",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 204):
                return True, "Message deleted."
            return False, f"Unexpected status: {resp.status}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return False, f"HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        return False, f"Network error: {e.reason}"


def edit_message(webhook_url: str, message_id: str, content: str) -> tuple[bool, str]:
    """PATCH a message this webhook posted. Returns (ok, detail)."""
    webhook_url = webhook_url.strip()
    if not webhook_url.startswith(WEBHOOK_PREFIXES):
        return False, "URL must be a Discord webhook link."

    if not content.strip():
        return False, "Message cannot be empty."

    payload = json.dumps(
        {
            "content": content,
            "allowed_mentions": {"parse": ["users", "roles", "everyone"]},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{webhook_url}/messages/{message_id}",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "WebhookMessenger/1.0"},
        method="PATCH",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 204):
                return True, "Message updated."
            return False, f"Unexpected status: {resp.status}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return False, f"HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        return False, f"Network error: {e.reason}"


def clamp_delay(value: object) -> int:
    """Coerce a delay to a whole number of seconds inside the allowed bounds."""
    try:
        seconds = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        seconds = MIN_DELAY
    return max(MIN_DELAY, min(MAX_DELAY, seconds))


class DeleteRequest(NamedTuple):
    """A delete the caller should arm. The caller owns the timer, not this module."""

    webhook_url: str
    message_id: str
    delay: int


class SentMessage(NamedTuple):
    """A webhook message sent during this app session (for edit/delete UI)."""

    message_id: str
    webhook_url: str
    content: str
    sent_at: str


def remember_sent(
    history: list[SentMessage],
    message_id: str | None,
    webhook_url: str,
    content: str,
) -> None:
    """Record a landed message so the UI can edit or delete it later."""
    if message_id:
        history.insert(
            0,
            SentMessage(message_id, webhook_url.strip(), content, time.strftime("%H:%M:%S")),
        )


def forget_sent(history: list[SentMessage], message_id: str) -> None:
    history[:] = [m for m in history if m.message_id != message_id]


def update_sent_content(history: list[SentMessage], message_id: str, content: str) -> None:
    history[:] = [
        m._replace(content=content) if m.message_id == message_id else m for m in history
    ]


def format_sent_label(content: str, attachment: ImageAttachment | None = None) -> str:
    if attachment:
        prefix = f"[image: {attachment.filename}]"
        return f"{prefix} {content}".strip()
    return content.strip()


def send_and_schedule(
    webhook_url: str,
    content: str,
    username: str | None = None,
    avatar_url: str | None = None,
    auto_delete: bool = False,
    delay: object = MIN_DELAY,
    attachment: ImageAttachment | None = None,
) -> tuple[bool, str, str | None, DeleteRequest | None]:
    """Send, and decide whether a delete should follow.

    Returns (ok, detail, message_id, delete_request). Display-free so both front
    ends share it: the GUI arms the returned request with root.after(), the CLI
    with a daemon threading.Timer.
    """
    ok, detail, message_id = send_message(
        webhook_url, content, username, avatar_url, attachment
    )
    if not ok:
        return ok, detail, None, None
    if not auto_delete:
        return ok, detail, message_id, None

    if not message_id:
        return ok, f"{detail} (No message ID returned — cannot auto-delete.)", None, None

    return ok, detail, message_id, DeleteRequest(webhook_url.strip(), message_id, clamp_delay(delay))


def arm_delete_timer(
    request: DeleteRequest,
    on_done: Callable[[bool, str], None] | None = None,
) -> threading.Timer:
    """Arm a delete on a daemon timer (CLI only — tkinter needs root.after instead).

    Daemon by design: a pending delete dies with the process. Auto-delete is
    best-effort and only holds while the app runs.
    """

    def fire() -> None:
        ok, detail = delete_message(request.webhook_url, request.message_id)
        if on_done:
            on_done(ok, detail)

    timer = threading.Timer(request.delay, fire)
    timer.daemon = True
    timer.start()
    return timer


class ResendSettings(NamedTuple):
    """Everything resend_step needs for one send. Content is read separately,
    at fire time, via a callback so mid-run edits take effect."""

    webhook_url: str
    username: str | None = None
    avatar_url: str | None = None
    auto_delete: bool = False
    delay: int = MIN_DELAY
    max_count: int = 0  # 0 (or blank) means unlimited
    attachment: ImageAttachment | None = None


def clamp_max_count(value: object) -> int:
    """Coerce a max-count to a non-negative integer. Blank/junk/negative -> 0 (unlimited).

    A decimal like "3.5" truncates to 3 rather than silently becoming unlimited — a
    bounded intent must never invert into an unbounded flood.
    """
    try:
        count = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        try:
            count = int(float(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0
    return max(0, count)


def resend_step(
    get_content: Callable[[], str],
    settings: ResendSettings,
    count: int,
) -> tuple[tuple[bool, str], DeleteRequest | None, bool, str | None]:
    """Perform one auto-resend send. Display-free so both front ends share it.

    `get_content` is called now, at fire time, so edits between fires change what
    is sent. The send is delegated to send_and_schedule() so auto-delete composes:
    each resent copy carries its own DeleteRequest when auto-delete is on.

    `count` is the number of *successful* sends already made before this one.
    Returns ((ok, detail), delete_request_or_none, keep_going). keep_going is
    False once max_count successful sends have landed (max_count of 0 means never
    stop on count). A failed fire does NOT advance toward the cap — only posts
    that actually land count — so a persistently failing send keeps trying rather
    than silently exhausting the cap. The caller arms the next fire (GUI
    root.after, CLI daemon thread) while keep_going, and increments its own count
    only when ok.
    """
    content = get_content()
    ok, detail, message_id, request = send_and_schedule(
        settings.webhook_url,
        content,
        settings.username,
        settings.avatar_url,
        settings.auto_delete,
        settings.delay,
        settings.attachment,
    )
    successes = count + 1 if ok else count
    max_count = clamp_max_count(settings.max_count)
    keep_going = not (max_count > 0 and successes >= max_count)
    return (ok, detail), request, keep_going, message_id


def build_gui_content(message: str, ping_user: bool, user_id: str) -> tuple[str | None, str | None]:
    """Assemble the message + optional user ping the GUI would send. Display-free.

    Returns (content, error): a ready-to-send string, or (None, reason) when the
    ping is requested but the user ID isn't numeric. Mirrors the single-send path
    so a resent copy carries the same mention.
    """
    content = message.strip()
    if ping_user:
        uid = user_id.strip()
        if not uid.isdigit():
            return None, "Paste a numeric Discord user ID, or turn off “Include ping”."
        mention = f"<@{uid}>"
        if mention not in content:
            content = f"{mention} {content}".strip()
    return content, None


def gui_after_fire(keep_going: bool) -> tuple[bool, str]:
    """Decide what the GUI does after one resend fire. Display-free.

    Returns (loop_still_active, decision): ("continue" -> re-arm the next
    root.after; "stop" -> max-count reached, flip the toggle back to Off).
    """
    if keep_going:
        return True, "continue"
    return False, "stop"


def resend_button_label(auto_resend_on: bool, loop_active: bool) -> str:
    """Text for the multi-purpose send button given the checkbox and loop state."""
    if not auto_resend_on:
        return "Send message"
    return "Auto-resend: ON (click to stop)" if loop_active else "Auto-resend: OFF (click to start)"


def insert_ping(entry: "tk.Text", kind: str, default_user_id: str = "") -> None:
    """Prompt for an ID and insert a Discord mention into the message box."""
    if kind in ("everyone", "here"):
        entry.insert(tk.INSERT, f"@{kind} ")
        return

    if kind == "user" and default_user_id.strip().isdigit():
        entry.insert(tk.INSERT, f"<@{default_user_id.strip()}> ")
        return

    dialog = tk.Toplevel(entry.winfo_toplevel())
    dialog.title(f"Ping {kind}")
    dialog.resizable(False, False)
    dialog.grab_set()

    label_text = "User ID" if kind == "user" else "Role ID"
    ttk.Label(dialog, text=f"Paste the Discord {label_text}:").pack(padx=12, pady=(12, 4))
    id_var = tk.StringVar(value=default_user_id if kind == "user" else "")
    id_entry = ttk.Entry(dialog, textvariable=id_var, width=36)
    id_entry.pack(padx=12, pady=4)
    id_entry.focus_set()

    ttk.Label(
        dialog,
        text="Developer Mode → right-click user/role → Copy ID",
        foreground="#666",
        wraplength=320,
    ).pack(padx=12, pady=(0, 8))

    def confirm() -> None:
        raw = id_var.get().strip()
        if not raw.isdigit():
            messagebox.showerror("Invalid ID", "Discord IDs are numbers only.", parent=dialog)
            return
        mention = f"<@{raw}>" if kind == "user" else f"<@&{raw}>"
        entry.insert(tk.INSERT, mention + " ")
        dialog.destroy()

    btn_row = ttk.Frame(dialog)
    btn_row.pack(padx=12, pady=(0, 12))
    ttk.Button(btn_row, text="Insert", command=confirm).pack(side=tk.LEFT, padx=4)
    ttk.Button(btn_row, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=4)
    dialog.bind("<Return>", lambda _e: confirm())


def run_gui() -> None:
    root = tk.Tk()
    root.title("D4zr + Prototype")
    root.minsize(520, 400)

    # Keep send + status visible above the Windows taskbar.
    footer = ttk.Frame(root)
    footer.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(4, 12))

    status = ttk.Label(footer, text="Ready", foreground="#555")
    status.pack(anchor="w", pady=(0, 6))

    send_btn = ttk.Button(footer, text="Send message")
    send_btn.pack(fill=tk.X)

    canvas_frame = ttk.Frame(root)
    canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    canvas = tk.Canvas(canvas_frame, highlightthickness=0)
    scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
    body = ttk.Frame(canvas)
    canvas_window = canvas.create_window((0, 0), window=body, anchor="nw")

    def _on_body_configure(_event: tk.Event) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(event: tk.Event) -> None:
        canvas.itemconfig(canvas_window, width=event.width)

    def _on_mousewheel(event: tk.Event) -> None:
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    body.bind("<Configure>", _on_body_configure)
    canvas.bind("<Configure>", _on_canvas_configure)
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.bind_all("<MouseWheel>", _on_mousewheel)
    root.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>") if e.widget is root else None)

    screen_h = root.winfo_screenheight()
    win_h = min(640, max(400, screen_h - 100))
    root.geometry(f"580x{win_h}")

    pad = {"padx": 12, "pady": 6}
    cooldown_until = {"t": 0.0}

    ttk.Label(body, text="Webhook URL").pack(anchor="w", **pad)
    url_var = tk.StringVar(value=DEFAULT_WEBHOOK)
    ttk.Entry(body, textvariable=url_var).pack(fill="x", padx=12)

    ttk.Label(body, text="Display name (optional)").pack(anchor="w", **pad)
    name_var = tk.StringVar()
    ttk.Entry(body, textvariable=name_var).pack(fill="x", padx=12)

    ttk.Label(body, text="Profile picture URL (optional)").pack(anchor="w", **pad)
    avatar_var = tk.StringVar()
    ttk.Entry(body, textvariable=avatar_var).pack(fill="x", padx=12)
    ttk.Label(
        body,
        text="Direct image link (png/jpg/gif/webp). Hosted online, not a local file.",
        foreground="#666",
    ).pack(anchor="w", padx=12)

    user_row = ttk.Frame(body)
    user_row.pack(fill="x", padx=12, pady=6)
    ttk.Label(user_row, text="User ID to ping").pack(side=tk.LEFT)
    user_id_var = tk.StringVar()
    ttk.Entry(user_row, textvariable=user_id_var, width=28).pack(side=tk.LEFT, padx=8)
    ping_user_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(user_row, text="Include ping", variable=ping_user_var).pack(side=tk.LEFT)

    ttk.Label(
        body,
        text="Numeric ID only (Developer Mode → right-click user → Copy ID)",
        foreground="#666",
    ).pack(anchor="w", padx=12)

    cd_row = ttk.Frame(body)
    cd_row.pack(fill="x", padx=12, pady=6)
    ttk.Label(cd_row, text="Cooldown between sends (seconds)").pack(side=tk.LEFT)
    cooldown_var = tk.IntVar(value=5)
    ttk.Spinbox(cd_row, from_=1, to=3600, textvariable=cooldown_var, width=8).pack(side=tk.LEFT, padx=8)

    ad_row = ttk.Frame(body)
    ad_row.pack(fill="x", padx=12, pady=6)
    auto_delete_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(ad_row, text="Auto-delete after sending", variable=auto_delete_var).pack(side=tk.LEFT)
    ttk.Label(ad_row, text="after (seconds)").pack(side=tk.LEFT, padx=(12, 4))
    delay_var = tk.IntVar(value=MIN_DELAY)
    ttk.Spinbox(ad_row, from_=MIN_DELAY, to=MAX_DELAY, textvariable=delay_var, width=8).pack(side=tk.LEFT)

    ttk.Label(
        body,
        text="0 = delete immediately. Only works while this app is running — closing it cancels pending deletes.",
        foreground="#666",
        wraplength=540,
    ).pack(anchor="w", padx=12)

    ar_row = ttk.Frame(body)
    ar_row.pack(fill="x", padx=12, pady=6)
    auto_resend_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(ar_row, text="Auto-resend on a loop", variable=auto_resend_var).pack(side=tk.LEFT)
    ttk.Label(ar_row, text="stop after (sends, 0 = unlimited)").pack(side=tk.LEFT, padx=(12, 4))
    max_count_var = tk.IntVar(value=0)
    ttk.Spinbox(ar_row, from_=0, to=100000, textvariable=max_count_var, width=8).pack(side=tk.LEFT)

    ttk.Label(
        body,
        text="Reposts the current message every cooldown. Turning it On sends now, then repeats. "
        "Stops at the send cap, when you turn it Off, or when you close the app.",
        foreground="#666",
        wraplength=540,
    ).pack(anchor="w", padx=12)

    ttk.Label(body, text="Message").pack(anchor="w", **pad)
    msg = tk.Text(body, height=6, wrap="word", font=("Segoe UI", 10))
    msg.pack(fill="x", padx=12, pady=(0, 6))
    msg.insert("1.0", "hey")

    image_state: dict[str, ImageAttachment | None] = {"value": None}
    img_row = ttk.Frame(body)
    img_row.pack(fill="x", padx=12, pady=4)
    image_label = ttk.Label(img_row, text="No image selected", foreground="#666")
    image_label.pack(side=tk.LEFT, fill="x", expand=True)

    def pick_image() -> None:
        if filedialog is None:
            return
        path = filedialog.askopenfilename(
            title="Choose an image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.webp")],
        )
        if not path:
            return
        att, err = attachment_from_path(path)
        if err:
            messagebox.showerror("Invalid image", err)
            return
        image_state["value"] = att
        image_label.config(text=att.filename)

    def clear_image() -> None:
        image_state["value"] = None
        image_label.config(text="No image selected")

    ttk.Button(img_row, text="Choose image", command=pick_image).pack(side=tk.RIGHT, padx=2)
    ttk.Button(img_row, text="Clear", command=clear_image).pack(side=tk.RIGHT)

    ping_row = ttk.Frame(body)
    ping_row.pack(fill="x", padx=12, pady=4)
    ttk.Label(ping_row, text="Insert ping:").pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(
        ping_row, text="@user", command=lambda: insert_ping(msg, "user", user_id_var.get())
    ).pack(side=tk.LEFT, padx=2)
    ttk.Button(ping_row, text="@role", command=lambda: insert_ping(msg, "role")).pack(side=tk.LEFT, padx=2)
    ttk.Button(ping_row, text="@everyone", command=lambda: insert_ping(msg, "everyone")).pack(
        side=tk.LEFT, padx=2
    )
    ttk.Button(ping_row, text="@here", command=lambda: insert_ping(msg, "here")).pack(side=tk.LEFT, padx=2)

    sent_messages: list[SentMessage] = []
    history_box = ttk.LabelFrame(body, text="Sent messages (this session)")
    history_box.pack(fill="x", padx=12, pady=(8, 4))
    history_list = ttk.Frame(history_box)
    history_list.pack(fill="x", padx=8, pady=6)
    ttk.Label(
        history_box,
        text="Only messages sent through this app appear here. Webhooks cannot read channel history.",
        foreground="#666",
        wraplength=520,
    ).pack(anchor="w", padx=8, pady=(0, 6))

    def refresh_history() -> None:
        for child in history_list.winfo_children():
            child.destroy()
        if not sent_messages:
            ttk.Label(history_list, text="No messages yet.", foreground="#666").pack(anchor="w")
            return
        for rec in sent_messages[:20]:
            row = ttk.Frame(history_list)
            row.pack(fill="x", pady=2)
            preview = rec.content if len(rec.content) <= 72 else rec.content[:72] + "…"
            ttk.Label(row, text=f"[{rec.sent_at}] {preview}", wraplength=360).pack(
                side=tk.LEFT, fill="x", expand=True
            )

            def open_edit(message_id: str = rec.message_id, webhook: str = rec.webhook_url, text: str = rec.content) -> None:
                dialog = tk.Toplevel(root)
                dialog.title("Edit message")
                dialog.resizable(True, False)
                dialog.grab_set()
                ttk.Label(dialog, text="New content:").pack(anchor="w", padx=12, pady=(12, 4))
                edit_box = tk.Text(dialog, height=5, width=48, wrap="word", font=("Segoe UI", 10))
                edit_box.pack(padx=12, pady=4)
                edit_box.insert("1.0", text)

                def save() -> None:
                    new_text = edit_box.get("1.0", "end-1c").strip()
                    if not new_text:
                        messagebox.showerror("Empty message", "Message cannot be empty.", parent=dialog)
                        return
                    ok, detail = edit_message(webhook, message_id, new_text)
                    status.config(text=detail, foreground="#1a7f37" if ok else "#c42b2b")
                    if ok:
                        update_sent_content(sent_messages, message_id, new_text)
                        refresh_history()
                        dialog.destroy()
                    else:
                        messagebox.showerror("Edit failed", detail, parent=dialog)

                btn_row = ttk.Frame(dialog)
                btn_row.pack(padx=12, pady=(0, 12))
                ttk.Button(btn_row, text="Save", command=save).pack(side=tk.LEFT, padx=4)
                ttk.Button(btn_row, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=4)

            def do_delete(message_id: str = rec.message_id, webhook: str = rec.webhook_url) -> None:
                ok, detail = delete_message(webhook, message_id)
                status.config(text=detail, foreground="#1a7f37" if ok else "#c42b2b")
                if ok:
                    forget_sent(sent_messages, message_id)
                    refresh_history()
                else:
                    messagebox.showerror("Delete failed", detail)

            ttk.Button(row, text="Edit", width=6, command=open_edit).pack(side=tk.RIGHT, padx=2)
            ttk.Button(row, text="Delete", width=7, command=do_delete).pack(side=tk.RIGHT)

    refresh_history()

    def note_sent(webhook: str, message_id: str | None, content: str) -> None:
        remember_sent(sent_messages, message_id, webhook, content)
        refresh_history()

    def tick_cooldown() -> None:
        if auto_resend_var.get():
            # The checkbox was ticked mid-cooldown: auto-resend owns the button now,
            # so drop the single-send cooldown lock instead of clobbering the toggle.
            send_btn.config(state="normal")
            refresh_send_button()
            if status.cget("text").startswith("Wait "):
                status.config(text="Ready", foreground="#555")
            return
        remaining = int(cooldown_until["t"] - time.monotonic())
        if remaining > 0:
            send_btn.config(state="disabled", text=f"Cooldown ({remaining}s)")
            status.config(text=f"Wait {remaining}s before sending again.", foreground="#555")
            root.after(250, tick_cooldown)
        else:
            send_btn.config(state="normal", text="Send message")
            if status.cget("text").startswith("Wait "):
                status.config(text="Ready", foreground="#555")

    def fire_delete(request: DeleteRequest) -> None:
        ok, detail = delete_message(request.webhook_url, request.message_id)
        status.config(text=detail, foreground="#1a7f37" if ok else "#c42b2b")
        if ok:
            forget_sent(sent_messages, request.message_id)
            refresh_history()

    def read_delay() -> object:
        try:
            return delay_var.get()
        except tk.TclError:
            return MIN_DELAY

    def read_interval_ms() -> int:
        try:
            return max(1, int(cooldown_var.get())) * 1000
        except (TypeError, ValueError, tk.TclError):
            return 5000

    def on_send() -> None:
        now = time.monotonic()
        if now < cooldown_until["t"]:
            return

        content, err = build_gui_content(
            msg.get("1.0", "end-1c"), ping_user_var.get(), user_id_var.get()
        )
        if err:
            messagebox.showerror("User ID required", err)
            return
        attachment = image_state["value"]
        if not content.strip() and not attachment:
            messagebox.showerror("Nothing to send", "Enter a message or attach an image.")
            return

        ok, detail, message_id, request = send_and_schedule(
            url_var.get(),
            content,
            name_var.get(),
            avatar_var.get(),
            auto_delete_var.get(),
            read_delay(),
            attachment,
        )
        status.config(text=detail, foreground="#1a7f37" if ok else "#c42b2b")
        if ok:
            note_sent(url_var.get(), message_id, format_sent_label(content, attachment))
            cooldown_until["t"] = time.monotonic() + read_interval_ms() / 1000
            tick_cooldown()
            if request:
                # after() runs the delete on the main loop; a timer thread must
                # never touch these widgets.
                root.after(request.delay * 1000, lambda: fire_delete(request))
        else:
            messagebox.showerror("Send failed", detail)

    # --- Auto-resend loop (driven entirely by root.after — no timer thread) ---
    resend_state = {"active": False, "count": 0, "after_id": None}

    def refresh_send_button() -> None:
        send_btn.config(text=resend_button_label(auto_resend_var.get(), resend_state["active"]))

    def stop_resend() -> None:
        if resend_state["after_id"] is not None:
            root.after_cancel(resend_state["after_id"])
            resend_state["after_id"] = None
        resend_state["active"] = False
        refresh_send_button()

    def fire_resend() -> None:
        if not resend_state["active"]:
            return
        resend_state["after_id"] = None

        content, err = build_gui_content(
            msg.get("1.0", "end-1c"), ping_user_var.get(), user_id_var.get()
        )
        if err:
            status.config(text=err, foreground="#c42b2b")
            stop_resend()
            return
        attachment = image_state["value"]
        if not content.strip() and not attachment:
            status.config(text="Enter a message or attach an image.", foreground="#c42b2b")
            stop_resend()
            return

        try:
            max_count = clamp_max_count(max_count_var.get())
        except tk.TclError:
            max_count = 0
        settings = ResendSettings(
            url_var.get(), name_var.get(), avatar_var.get(),
            auto_delete_var.get(), read_delay(), max_count, attachment,
        )
        (ok, detail), request, keep_going, message_id = resend_step(
            lambda: content, settings, resend_state["count"]
        )
        if ok:
            resend_state["count"] += 1  # only landed posts count toward max-count
            note_sent(settings.webhook_url, message_id, format_sent_label(content, attachment))
        status.config(text=detail, foreground="#1a7f37" if ok else "#c42b2b")
        if request:
            root.after(request.delay * 1000, lambda: fire_delete(request))

        _active, decision = gui_after_fire(keep_going)
        if decision == "stop":
            stop_resend()  # reached max-count — flip the toggle back to Off
        elif resend_state["active"]:
            resend_state["after_id"] = root.after(read_interval_ms(), fire_resend)

    def start_resend() -> None:
        resend_state["active"] = True
        resend_state["count"] = 0
        refresh_send_button()
        fire_resend()  # On fires immediately, then repeats every interval

    def toggle_resend() -> None:
        if resend_state["active"]:
            stop_resend()
        else:
            start_resend()

    def on_button() -> None:
        # One button, two jobs: single send when the checkbox is off, On/Off toggle when on.
        if auto_resend_var.get():
            toggle_resend()
        else:
            on_send()

    def on_auto_resend_toggled() -> None:
        # Unticking mid-run stops the loop; either way, restore the right button label.
        if not auto_resend_var.get():
            stop_resend()
        else:
            refresh_send_button()

    auto_resend_var.trace_add("write", lambda *_: on_auto_resend_toggled())
    send_btn.config(command=on_button)
    root.mainloop()


def _apply_mention(content: str, user_id: str) -> str:
    """Prefix a user mention if a numeric ID was given and it isn't already present."""
    if user_id.isdigit():
        mention = f"<@{user_id}>"
        if mention not in content:
            return f"{mention} {content}"
    return content


def _read_message(first_prompt: str = "> ", cont_prompt: str = "  ") -> str:
    """Read a multi-line message; a blank line after content sends it."""
    lines: list[str] = []
    while True:
        line = input(first_prompt if not lines else cont_prompt)
        if line == "" and lines:
            break
        if line == "" and not lines:
            continue
        lines.append(line)
    return "\n".join(lines)


def _print_send_result(ok: bool, detail: str, request: DeleteRequest | None) -> None:
    print(("✓ " if ok else "✗ ") + detail)
    if request:
        print(f"  auto-delete in {request.delay}s")
        arm_delete_timer(
            request,
            on_done=lambda deleted, note: print(("  ✓ " if deleted else "  ✗ ") + note),
        )


def _cli_resend_loop(
    settings: ResendSettings,
    user_id: str,
    cooldown: int,
) -> None:
    """Repost the current message every `cooldown` seconds on a daemon thread.

    tkinter's thread rule doesn't apply here — the CLI has no widgets — so a
    background thread is the only way to keep reposting while input() blocks.
    A lock guards the shared content; a generation counter starts a fresh
    max-count batch whenever the user types a new message.
    """
    # content: str | None; gen: which message the worker should be sending;
    # done_gen: the highest gen whose bounded batch has fully completed.
    state = {"content": None, "gen": 0, "done_gen": -1}
    cond = threading.Condition()  # guards state and signals batch completion
    stop_event = threading.Event()
    max_count = settings.max_count

    def get_content() -> str:
        with cond:
            return state["content"] or ""

    def mark_done(gen: int) -> None:
        with cond:
            if gen > state["done_gen"]:
                state["done_gen"] = gen
                cond.notify_all()

    def worker() -> None:
        seen_gen = -1
        count = 0
        while not stop_event.is_set():
            with cond:
                content = state["content"]
                gen = state["gen"]
            if gen != seen_gen:
                seen_gen = gen
                count = 0
            if content is None:
                stop_event.wait(0.1)
                continue
            if max_count and count >= max_count:
                stop_event.wait(0.1)  # batch already drained; idle until new content
                continue
            (ok, _detail), request, keep_going, _message_id = resend_step(get_content, settings, count)
            if ok:
                count += 1  # only landed posts count toward max-count
            _print_send_result(ok, _detail, request)
            if not keep_going:
                mark_done(seen_gen)  # this fire hit max_count — the batch for `gen` is done
            stop_event.wait(cooldown)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        while True:
            content = _apply_mention(_read_message(), user_id)
            with cond:
                state["content"] = content
                state["gen"] += 1  # fresh max-count batch
    except EOFError:
        # Piped/scripted input ended — let the last message's bounded batch finish
        # what was asked. wait_for returns the instant that gen completes, so the
        # timeout is only a safety cap (per-send latency included), never the norm.
        print("\nBye.")
        if max_count:
            with cond:
                target = state["gen"]
                if state["content"] is not None:
                    cond.wait_for(
                        lambda: state["done_gen"] >= target,
                        timeout=max_count * (cooldown + 16) + 5,
                    )
    except KeyboardInterrupt:
        # Interactive quit — stop immediately, don't drain.
        print("\nBye.")
    finally:
        stop_event.set()
        thread.join(timeout=5)
    sys.exit(0)


def run_cli() -> None:
    print("D4zr + Prototype")
    print("-" * 40)
    webhook = input("Webhook URL: ").strip() or DEFAULT_WEBHOOK
    if not webhook:
        print("A webhook URL is required.")
        sys.exit(1)
    username = input("Display name (optional, Enter to skip): ").strip() or None
    avatar_url = input("Profile picture URL (optional): ").strip() or None
    user_id = input("User ID to ping (optional): ").strip()
    try:
        cooldown = max(1, int(input("Cooldown seconds [5]: ").strip() or "5"))
    except ValueError:
        cooldown = 5

    auto_delete = input("Auto-delete messages after sending? [y/N]: ").strip().lower() in ("y", "yes")
    delay = 0
    if auto_delete:
        delay = clamp_delay(
            input(f"Delete after how many seconds? [0 = immediately, max {MAX_DELAY}]: ").strip() or "0"
        )

    auto_resend = input("Auto-resend the same message on a loop? [y/N]: ").strip().lower() in ("y", "yes")
    max_count = 0
    if auto_resend:
        max_count = clamp_max_count(
            input("Stop after how many sends? [blank/0 = unlimited]: ").strip()
        )

    print()
    if auto_delete:
        print(f"Auto-delete ON — {delay}s after each send. Only works while this app is running.")

    if auto_resend:
        cap = f"until it reaches {max_count} sends" if max_count else "until you press Ctrl+C"
        print(f"Auto-resend ON — reposts every {cooldown}s {cap}. Stops when you close the app.")
        print("Type a message + Enter to (re)start the loop with new text. Ctrl+C to quit.")
        print("-" * 40)
        settings = ResendSettings(
            webhook, username, avatar_url, auto_delete, delay, max_count
        )
        _cli_resend_loop(settings, user_id, cooldown)
        return

    print("Type your message. Empty line + Enter sends. Ctrl+C to quit.")
    print("-" * 40)
    last_sent = 0.0

    while True:
        try:
            content = _apply_mention(_read_message(), user_id)

            wait = cooldown - (time.monotonic() - last_sent)
            if wait > 0:
                print(f"Cooldown: wait {int(wait) + 1}s…")
                time.sleep(wait)

            ok, detail, _message_id, request = send_and_schedule(
                webhook, content, username, avatar_url, auto_delete, delay
            )
            _print_send_result(ok, detail, request)
            if ok:
                last_sent = time.monotonic()
            print()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            sys.exit(0)


def main() -> None:
    if "--cli" in sys.argv or tk is None:
        if tk is None and "--cli" not in sys.argv:
            print("tkinter not available; using CLI mode.")
        run_cli()
    else:
        run_gui()


if __name__ == "__main__":
    main()
