# Discord Webhook Messenger

A small Python app that posts messages to a Discord channel webhook. You can set a display name, optional profile picture, ping users or roles, enforce a cooldown between sends, auto-delete a message after it posts, and auto-resend a message on a loop.

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
| **Auto-delete after sending** | Off by default. When on, the message is deleted after it posts. |
| **after (seconds)** | How long to wait before deleting. 0 (the default) deletes as soon as the send goes through. Max 3600. |
| **Auto-resend on a loop** | Off by default. When ticked, the **Send message** button becomes an **On/Off** toggle that reposts the current message every cooldown. |
| **stop after (sends, 0 = unlimited)** | Optional cap. After this many *successful* posts the loop turns itself Off. A failed fire (e.g. a rate-limit 429) does not count, so the cap always delivers that many landed posts. `0` (the default) means no cap — the loop runs until you turn it Off or close the app. |
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

## Auto-delete

Messages can delete themselves after posting. Tick **Auto-delete after sending** (GUI) or answer `y` to the auto-delete prompt (CLI), then set how many seconds to wait. `0` means the message is removed as soon as it posts.

**The important limitation: auto-delete works only while the app is running.** Pending deletes are held in memory, nothing is written to disk, and there is no cleanup on the next launch. If you close the app — or it crashes, or the machine sleeps — before the timer fires, the message stays in the channel permanently. Delete it by hand in Discord.

What that means in practice:

- A delay of `0` is safe: the delete goes out immediately, while the app is still open.
- A long delay is a promise the app can only keep if you leave it open that whole time. Set 300 seconds and close the window a minute later, and the message survives.
- Nothing warns you on exit. Closing with deletes pending is silent.

Other things worth knowing:

- Only messages sent by this app, in this session, can be auto-deleted. It cannot remove anything sent earlier or by anyone else.
- A failed delete (the message was already removed, or Discord rate-limited the request) is reported in the status line and then dropped. It is not retried.
- The webhook must still exist when the timer fires. Delete the webhook in Discord and pending deletes will fail with a 404.

## Auto-resend

Auto-resend reposts the *same* message over and over on a timer, so you don't have to click or retype for a recurring reminder, a heartbeat, or a bump. It is off by default and never changes the normal single-send behaviour until you turn it on.

**GUI.** Tick **Auto-resend on a loop**. The **Send message** button turns into an **On/Off** toggle:

- Turning it **On** sends immediately, then reposts every **Cooldown** seconds.
- Editing the **Message** box (or the ping) mid-run changes what the *next* repost sends — the content is re-read each time.
- Set **stop after** to a number and the loop turns itself **Off** once it reaches that many *successful* posts — a failed fire (e.g. a 429) doesn't count against it. `0` means unlimited.
- Turning it **Off**, or unticking the checkbox, stops the loop and restores the plain **Send message** button.

**CLI.** Answer `y` to *Auto-resend the same message on a loop?* at startup, then optionally set a stop-after count. Type a message and press Enter on a blank line to start the loop; it reposts every cooldown. Typing a new message swaps the content and starts a fresh count. There is no live Off switch in the CLI — press **Ctrl+C** to stop.

**It works together with auto-delete.** Turn both on and every resent copy schedules its own delete: the message appears, then disappears after your delete delay, then the next copy posts on the next interval. A short cooldown with a short delete delay makes a message that keeps flashing in and out of the channel.

**Two limitations worth understanding:**

- **The interval is best-effort against Discord's rate limit.** Discord allows roughly 30 posts per minute per webhook. A 1-second cooldown *will* draw HTTP 429 responses; those are reported in the status line (GUI) or printed (CLI) and then dropped — they are not retried and do not stop the loop. If you want every repost to land, keep the cooldown at a few seconds. Because the **stop after** cap counts only *successful* posts, a webhook that keeps failing (wrong URL, deleted webhook) will keep trying and never hit the cap — turn it Off or close the app to stop it.
- **The loop lives only in the running app. It stops when you close the app.** Nothing is written to disk and nothing resumes on the next launch — closing the window, a crash, or the machine sleeping ends all resending immediately (and cancels any pending auto-deletes with it). There is no way to schedule a resend for later or across restarts.

## CLI usage

1. Run with `--cli`.
2. Enter webhook URL, optional display name, optional avatar URL, optional user ID, and cooldown seconds.
3. Answer the auto-delete prompt (`y`/`N`). If yes, enter the delay in seconds. Both apply to every message for the rest of the session.
4. Answer the auto-resend prompt (`y`/`N`). If yes, optionally set a stop-after count (blank or `0` = unlimited). See [Auto-resend](#auto-resend) above.
5. Type your message. Press Enter on a blank line to send (or, with auto-resend on, to start the loop).
6. Ctrl+C to quit. Note that quitting cancels any pending auto-deletes and stops any resend loop.

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
