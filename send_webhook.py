#!/usr/bin/env python3
"""
Discord Webhook Messenger
Send one message at a time (with optional user ping) through a Discord webhook.
Cooldown prevents accidental double-sends.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:
    tk = None

# Leave empty — paste your webhook in the app when you run it. Never commit real webhooks.
DEFAULT_WEBHOOK = ""


def send_message(
    webhook_url: str,
    content: str,
    username: str | None = None,
    avatar_url: str | None = None,
) -> tuple[bool, str]:
    """POST a message to a Discord webhook. Returns (ok, detail)."""
    webhook_url = webhook_url.strip()
    if not webhook_url.startswith("https://discord.com/api/webhooks/") and not webhook_url.startswith(
        "https://discordapp.com/api/webhooks/"
    ):
        return False, "URL must be a Discord webhook link."

    if not content.strip():
        return False, "Message cannot be empty."

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
            return False, "Avatar URL must start with http:// or https://"
        payload["avatar_url"] = url

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "WebhookMessenger/1.0"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 204):
                return True, "Message sent."
            return False, f"Unexpected status: {resp.status}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return False, f"HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        return False, f"Network error: {e.reason}"


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

        ok, detail = send_message(url_var.get(), content, name_var.get(), avatar_var.get())
        status.config(text=detail, foreground="#1a7f37" if ok else "#c42b2b")
        if ok:
            try:
                seconds = max(1, int(cooldown_var.get()))
            except (TypeError, ValueError):
                seconds = 5
            cooldown_until["t"] = time.monotonic() + seconds
            tick_cooldown()
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

    print()
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

            ok, detail = send_message(webhook, content, username, avatar_url)
            print(("✓ " if ok else "✗ ") + detail)
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
