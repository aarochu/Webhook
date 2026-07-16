#!/usr/bin/env python3
"""
Discord Webhook Messenger
Send one message at a time (with optional user ping) through a Discord webhook.
Cooldown prevents accidental double-sends.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Callable, NamedTuple

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
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


def _with_wait(webhook_url: str) -> str:
    """Discord only returns the created message (and its id) when wait=true."""
    sep = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{sep}wait=true"


def send_message(
    webhook_url: str,
    content: str,
    username: str | None = None,
    avatar_url: str | None = None,
) -> tuple[bool, str, str | None]:
    """POST a message to a Discord webhook. Returns (ok, detail, message_id)."""
    webhook_url = webhook_url.strip()
    if not webhook_url.startswith(WEBHOOK_PREFIXES):
        return False, "URL must be a Discord webhook link.", None

    if not content.strip():
        return False, "Message cannot be empty.", None

    payload: dict = {
        "content": content,
        "allowed_mentions": {
            "parse": ["users", "roles", "everyone"],
        },
    }
    if username and username.strip():
        payload["username"] = username.strip()
    if avatar_url and avatar_url.strip():
        url = avatar_url.strip()
        if not url.startswith(("http://", "https://")):
            return False, "Avatar URL must start with http:// or https://", None
        payload["avatar_url"] = url

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _with_wait(webhook_url),
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "WebhookMessenger/1.0"},
        method="POST",
    )

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


def send_and_schedule(
    webhook_url: str,
    content: str,
    username: str | None = None,
    avatar_url: str | None = None,
    auto_delete: bool = False,
    delay: object = MIN_DELAY,
) -> tuple[bool, str, DeleteRequest | None]:
    """Send, and decide whether a delete should follow.

    Display-free so both front ends share it: the GUI arms the returned request
    with root.after(), the CLI with a daemon threading.Timer.
    """
    ok, detail, message_id = send_message(webhook_url, content, username, avatar_url)
    if not ok or not auto_delete:
        return ok, detail, None

    if not message_id:
        return ok, f"{detail} (No message ID returned — cannot auto-delete.)", None

    return ok, detail, DeleteRequest(webhook_url.strip(), message_id, clamp_delay(delay))


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
    root.title("Discord Webhook Messenger")
    root.minsize(520, 540)
    root.geometry("580x600")

    pad = {"padx": 12, "pady": 6}
    cooldown_until = {"t": 0.0}

    ttk.Label(root, text="Webhook URL").pack(anchor="w", **pad)
    url_var = tk.StringVar(value=DEFAULT_WEBHOOK)
    ttk.Entry(root, textvariable=url_var).pack(fill="x", padx=12)

    ttk.Label(root, text="Display name (optional)").pack(anchor="w", **pad)
    name_var = tk.StringVar()
    ttk.Entry(root, textvariable=name_var).pack(fill="x", padx=12)

    ttk.Label(root, text="Profile picture URL (optional)").pack(anchor="w", **pad)
    avatar_var = tk.StringVar()
    ttk.Entry(root, textvariable=avatar_var).pack(fill="x", padx=12)
    ttk.Label(
        root,
        text="Direct image link (png/jpg/gif/webp). Hosted online, not a local file.",
        foreground="#666",
    ).pack(anchor="w", padx=12)

    user_row = ttk.Frame(root)
    user_row.pack(fill="x", padx=12, pady=6)
    ttk.Label(user_row, text="User ID to ping").pack(side=tk.LEFT)
    user_id_var = tk.StringVar()
    ttk.Entry(user_row, textvariable=user_id_var, width=28).pack(side=tk.LEFT, padx=8)
    ping_user_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(user_row, text="Include ping", variable=ping_user_var).pack(side=tk.LEFT)

    ttk.Label(
        root,
        text="Numeric ID only (Developer Mode → right-click user → Copy ID)",
        foreground="#666",
    ).pack(anchor="w", padx=12)

    cd_row = ttk.Frame(root)
    cd_row.pack(fill="x", padx=12, pady=6)
    ttk.Label(cd_row, text="Cooldown between sends (seconds)").pack(side=tk.LEFT)
    cooldown_var = tk.IntVar(value=5)
    ttk.Spinbox(cd_row, from_=1, to=3600, textvariable=cooldown_var, width=8).pack(side=tk.LEFT, padx=8)

    ad_row = ttk.Frame(root)
    ad_row.pack(fill="x", padx=12, pady=6)
    auto_delete_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(ad_row, text="Auto-delete after sending", variable=auto_delete_var).pack(side=tk.LEFT)
    ttk.Label(ad_row, text="after (seconds)").pack(side=tk.LEFT, padx=(12, 4))
    delay_var = tk.IntVar(value=MIN_DELAY)
    ttk.Spinbox(ad_row, from_=MIN_DELAY, to=MAX_DELAY, textvariable=delay_var, width=8).pack(side=tk.LEFT)

    ttk.Label(
        root,
        text="0 = delete immediately. Only works while this app is running — closing it cancels pending deletes.",
        foreground="#666",
        wraplength=540,
    ).pack(anchor="w", padx=12)

    ttk.Label(root, text="Message").pack(anchor="w", **pad)
    msg = tk.Text(root, height=10, wrap="word", font=("Segoe UI", 10))
    msg.pack(fill="both", expand=True, padx=12, pady=(0, 6))
    msg.insert("1.0", "hey")

    ping_row = ttk.Frame(root)
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

    status = ttk.Label(root, text="Ready", foreground="#555")
    status.pack(anchor="w", padx=12, pady=(4, 0))

    send_btn = ttk.Button(root, text="Send message")
    send_btn.pack(pady=12)

    def tick_cooldown() -> None:
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

    def on_send() -> None:
        now = time.monotonic()
        if now < cooldown_until["t"]:
            return

        content = msg.get("1.0", "end-1c").strip()
        uid = user_id_var.get().strip()

        if ping_user_var.get():
            if not uid.isdigit():
                messagebox.showerror(
                    "User ID required",
                    "Paste a numeric Discord user ID, or turn off “Include ping”.",
                )
                return
            mention = f"<@{uid}>"
            if mention not in content:
                content = f"{mention} {content}".strip()

        try:
            delay_value = delay_var.get()
        except tk.TclError:
            delay_value = MIN_DELAY

        ok, detail, request = send_and_schedule(
            url_var.get(),
            content,
            name_var.get(),
            avatar_var.get(),
            auto_delete_var.get(),
            delay_value,
        )
        status.config(text=detail, foreground="#1a7f37" if ok else "#c42b2b")
        if ok:
            try:
                seconds = max(1, int(cooldown_var.get()))
            except (TypeError, ValueError):
                seconds = 5
            cooldown_until["t"] = time.monotonic() + seconds
            tick_cooldown()
            if request:
                # after() runs the delete on the main loop; a timer thread must
                # never touch these widgets.
                root.after(request.delay * 1000, lambda: fire_delete(request))
        else:
            messagebox.showerror("Send failed", detail)

    send_btn.config(command=on_send)
    root.mainloop()


def run_cli() -> None:
    print("Discord Webhook Messenger")
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

    print()
    if auto_delete:
        print(f"Auto-delete ON — {delay}s after each send. Only works while this app is running.")
    print("Type your message. Empty line + Enter sends. Ctrl+C to quit.")
    print("-" * 40)
    last_sent = 0.0

    while True:
        try:
            lines: list[str] = []
            while True:
                line = input("> " if not lines else "  ")
                if line == "" and lines:
                    break
                if line == "" and not lines:
                    continue
                lines.append(line)
            content = "\n".join(lines)
            if user_id.isdigit():
                mention = f"<@{user_id}>"
                if mention not in content:
                    content = f"{mention} {content}"

            wait = cooldown - (time.monotonic() - last_sent)
            if wait > 0:
                print(f"Cooldown: wait {int(wait) + 1}s…")
                time.sleep(wait)

            ok, detail, request = send_and_schedule(
                webhook, content, username, avatar_url, auto_delete, delay
            )
            print(("✓ " if ok else "✗ ") + detail)
            if ok:
                last_sent = time.monotonic()
            if request:
                print(f"  auto-delete in {request.delay}s")
                arm_delete_timer(
                    request,
                    on_done=lambda deleted, note: print(("  ✓ " if deleted else "  ✗ ") + note),
                )
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
