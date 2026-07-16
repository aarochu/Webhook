# Discord Webhook Messenger

A small Python app that posts messages to a Discord channel webhook. You can set a display name, optional profile picture, ping users or roles, and enforce a cooldown between sends.

Requires Python 3.10+. Uses only the standard library (no pip install).

---

## Setup

1. In Discord, open **Server Settings → Integrations → Webhooks**.
2. Create a webhook (or edit an existing one) and copy its URL.
3. Keep that URL private. Anyone who has it can post to the channel as the webhook.
4. Save `send_webhook.py` somewhere on your computer.

If a webhook URL was ever shared or committed, delete it in Discord and create a new one.

---

## Run the app

**GUI (default)**

```
python send_webhook.py
```

**CLI**

```
python send_webhook.py --cli
```

---

## GUI fields

| Field | What it does |
|--------|----------------|
| **Webhook URL** | Paste the webhook you copied from Discord. Required. |
| **Display name** | Optional name shown on the message (overrides the webhook’s default name for that send). |
| **Profile picture URL** | Optional direct image address (png, jpg, gif, or webp hosted online). Local file paths will not work. |
| **User ID to ping** | Optional numeric Discord snowflake. Enable **Include ping** to mention that user once per send. |
| **Cooldown** | Seconds to wait after a successful send before you can send again (stops accidental double-sends). |
| **Message** | Text to post. |

### Ping buttons

- **@user** — inserts a user mention (uses the User ID field if filled, otherwise asks for one)
- **@role** — asks for a role ID and inserts a role mention
- **@everyone** / **@here** — inserts those mentions

### How to get a user or role ID

1. Discord **Settings → Advanced → Developer Mode** → turn on.
2. Right-click the user or role → **Copy ID**.
3. Paste the number into the app. Usernames alone will not work.

Mention formats (for reference if you type them yourself):

- User: `<@USER_ID>`
- Role: `<@&ROLE_ID>`
- Everyone / here: `@everyone` / `@here`

---

## Sending a message

1. Paste your webhook URL.
2. Optionally set display name and profile picture.
3. Optionally set a user ID and leave **Include ping** checked.
4. Type your message.
5. Click **Send message**.
6. Wait out the cooldown before sending again.

On success, status turns green. On failure, an error dialog shows Discord’s response (wrong URL, rate limit, etc.).

---

## CLI usage

1. Run with `--cli`.
2. Enter webhook URL, optional display name, optional avatar URL, optional user ID, and cooldown seconds.
3. Type your message. Press Enter on a blank line to send.
4. Ctrl+C to quit.

If a user ID was entered, that mention is prepended when it is not already in the message.

---

## Security notes

- Never share your webhook URL, commit it to git, or put it in screenshots.
- Do not hardcode webhooks, tokens, or real user IDs in this repo.
- Treat the webhook like a password: if it leaks, regenerate it in Discord immediately.
- Only use this on servers and channels you are allowed to post in. Follow Discord’s rules and your server’s rules.

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| “URL must be a Discord webhook link” | Paste the full webhook URL from Server Settings → Integrations → Webhooks. |
| Avatar does not show | Use a public direct image link, not a gallery page or a path on your PC. |
| Ping does nothing / wrong person | Confirm Developer Mode is on and you copied the numeric ID, not the username. |
| HTTP 429 | You are rate-limited; increase cooldown and wait. |
| HTTP 404 | Webhook was deleted or the URL is wrong — create a new webhook. |
| Window does not open | Run with `--cli`, or install a Python build that includes tkinter. |
