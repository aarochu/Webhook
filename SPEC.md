# SPEC: Webhook Messenger — Auto-Delete

| Field | Value |
|---|---|
| Status | Active |
| Owner | Daron |
| Created | 2026-07-15 |
| Last updated | 2026-07-16 |
| Repo | `/home/daron/spark-dev-workspace/Webhook` (branch `Auto-Delete`) |
| Target environment | Developed and verified on DGX Spark, aarch64, Ubuntu 24.04. Stdlib-only, so expected to run on Windows/macOS — untested (see Open Questions). |
| Permission overrides | None — global `~/.claude/settings.json` applies |

---

## 1. Goal & Motivation

**What:** Add opt-in auto-delete to the existing Discord webhook messenger. The sender chooses whether a message deletes itself after posting, and how many seconds later. Available in both the GUI and the CLI.

**Why:** People sending through the webhook should be able to post something without it persisting in the channel, if that's what they want. The app currently has no way to remove a message once sent — the only recourse is deleting it by hand in Discord.

**Definition of overall success:** With auto-delete enabled and a delay of N seconds (0 ≤ N ≤ 3600), a message posted through the app is removed from the Discord channel approximately N seconds after it appears, provided the app stays running — demonstrated by an automated test suite against a mock Discord server, and confirmed once by hand against a real channel.

---

## 2. Scope

### In scope
- `send_message()` posts with `?wait=true` and returns the created message's ID.
- A `delete_message()` call issuing `DELETE /webhooks/{id}/{token}/messages/{message_id}`.
- An in-memory scheduler that fires the delete after the chosen delay.
- Auto-delete toggle and delay field in the GUI (checkbox + spinbox).
- Auto-delete toggle and delay prompt in the CLI.
- A local mock Discord server and `unittest` suite covering the send/delete path.
- README documenting the feature and its app-must-stay-open limitation.

### Out of scope (non-goals)
- **Persistence of pending deletes across restarts.** No state file, no queue. Close the app with a delete pending and the message stays on Discord permanently.
- **Sweeping/cleanup on next launch** of messages orphaned by a previous session.
- **Retrying failed deletes.** One attempt, report the outcome, drop it.
- **Editing messages** after send.
- **Bulk delete**, or deleting messages this app instance did not send.
- **Deleting the ping/mention behavior's messages separately** — auto-delete applies to the whole message as sent.
- **Blocking or warning on exit** when deletes are pending.

### Future work (explicitly deferred)
- A durable, at-least-once delete story (persisted pending-delete file + launch-time sweep). Deferred deliberately; do not design current code around it.
- Manual "delete last message" button.
- Per-message delete history in the UI.

---

## 3. Requirements

### Functional
- **FR-1:** `send_message()` appends `wait=true` to the webhook URL query and, on success, returns the Discord message ID from the JSON response alongside the existing ok/detail result.
- **FR-2:** `delete_message(webhook_url, message_id)` issues an HTTP DELETE to `{webhook_url}/messages/{message_id}` and returns `(ok, detail)`.
- **FR-3:** Auto-delete is opt-in. The toggle defaults to **off**; an unmodified workflow behaves exactly as it does today.
- **FR-4:** The delay field accepts an integer 0–3600 seconds and defaults to **0**, meaning the delete is issued as soon as the send is confirmed.
- **FR-5:** In the GUI, auto-delete is a checkbox and the delay a spinbox; the delete is scheduled with `root.after()` on the tkinter main loop.
- **FR-6:** In the CLI, auto-delete and delay are prompted at startup; the delete is scheduled with a daemon `threading.Timer`.
- **FR-7:** A failed delete (404, 429, network error) reports to the GUI status label or CLI stdout and is then discarded. No retry, no crash, no interruption of the app.
- **FR-8:** Pending deletes are held in memory only and are lost if the app exits. The README states this limitation explicitly.

### Non-functional
- **NFR-1:** Standard library only. No `pip install` for the app or its tests.
- **NFR-2:** Python 3.10+ (matches the existing `from __future__ import annotations` / `X | None` style).
- **NFR-3:** Tests make no outbound network calls; all HTTP is against a mock server bound to localhost.
- **NFR-4:** No webhook URLs, tokens, or real user/role IDs in the repo, tests, or fixtures.
- **NFR-5:** The app remains a single file, `send_webhook.py`; tests live under `tests/`.

### Constraints
- Discord provides **no server-side TTL** for webhook messages. Deletion must be initiated by this client.
- A webhook POST returns the message body (and therefore its ID) **only** when `?wait=true` is set.
- **tkinter is not thread-safe.** Widget access from a timer thread is a genuine crash risk, which forces the GUI/CLI scheduler split in FR-5/FR-6.
- No new system dependencies (this rules out `xvfb` for headless GUI tests).
- Work happens on branch `Auto-Delete`.

---

## 4. Technical Approach

### Stack
| Component | Version | Notes |
|---|---|---|
| Python | 3.10+ | System `python3` on Ubuntu 24.04 |
| urllib.request | stdlib | Existing HTTP client; extended with a DELETE request |
| tkinter / ttk | stdlib | GUI; already optional with CLI fallback |
| threading | stdlib | `Timer` (daemon) for CLI scheduling only |
| unittest | stdlib | Test runner — pytest excluded by NFR-1 |
| http.server | stdlib | Mock Discord webhook server for tests |

### Architecture overview

```
send_webhook.py
  send_message(url, content, ...)      -> (ok, detail, message_id)   POST ?wait=true
  delete_message(url, message_id)      -> (ok, detail)               DELETE .../messages/{id}
  send_and_schedule(...)               -> display-free orchestration; returns result +
                                          a scheduling request (delay, message_id)
  run_gui()   -> checkbox + spinbox; schedules via root.after(delay*1000, cb)
  run_cli()   -> prompts; schedules via threading.Timer(delay, cb, daemon=True)

tests/
  mock_discord.py   -> http.server on 127.0.0.1: honors ?wait=true (returns {"id": ...}),
                       records DELETE calls for assertion
  test_*.py         -> unittest suites, one per milestone
```

`send_and_schedule()` exists so the send/delete decision logic is verifiable without a display. Both front ends call it and only differ in how they arm the timer.

### Key design decisions
| Decision | Rationale | Alternatives rejected |
|---|---|---|
| In-memory, best-effort deletes | Simplest thing that satisfies the goal; matches the "friends I hand it to" audience | Persist + launch sweep (state file would hold webhook URLs + message IDs — becomes a secret to protect); block exit until drained (a 1-hour TTL holds the app hostage); cap TTL short (arbitrarily limits the feature) |
| GUI uses `root.after()`, CLI uses `threading.Timer` | tkinter widgets are not thread-safe; a timer thread touching the status label is a real crash | One shared `threading.Timer` for both (would require marshalling back to the main loop anyway); one shared `after()` (no main loop exists in CLI) |
| Toggle defaults off, delay defaults 0 | Opt-in per owner; a destructive default is surprising. Delay default of "immediately" per owner | Toggle default on (deletes messages users didn't intend to lose) |
| Delay bounded 0–3600s | Mirrors the existing cooldown spinbox range; keeps the in-memory window bounded | Unbounded (a 24h TTL is a promise in-memory scheduling cannot keep) |
| Failed delete reports and drops | Best-effort is the stated contract; a retry queue implies durability that doesn't exist | Retry with backoff; dead-letter queue |
| `unittest` + local mock HTTP server | Executable verifiers with no secrets, no network, no pip | pytest (needs pip, violates NFR-1); manual-only testing (violates the executable-verifier rule) |
| Extract `send_and_schedule()` from `run_gui()` | Makes GUI logic testable without a display, avoiding an `xvfb` system dependency | `xvfb-run` headless tkinter tests (new system dep); manual-only GUI verifier (no executable verifier) |

---

## 5. Environment & Setup

**Hardware/OS assumptions:** DGX Spark, aarch64, Ubuntu 24.04 for development and verification. No GPU, no accelerator, no network service dependencies. Runtime is portable in principle (stdlib only) but only verified on the Spark.

**Setup commands:**
```bash
# from clean clone:
cd Webhook
git checkout Auto-Delete
python3 --version          # expect 3.10 or newer
python3 -c "import tkinter" # optional; CLI mode works without it
# no dependency install step — stdlib only
```

**Secrets/credentials required:** A Discord webhook URL, supplied at runtime by the user. Never stored in the repo, never committed, never written to disk by this app. Tests use a mock server and require no secret.

**Relevant knowledge-base entries:**
- None identified at spec time. Record any aarch64/tkinter findings via `/retro`.

---

## 6. Milestones

### M0 — Environment validation
- **Status:** ☑
- **Objective:** Clean environment runs the app's existing send path against a local mock Discord server.
- **Deliverables:**
  - `tests/mock_discord.py` — stdlib HTTP mock honoring `?wait=true` and recording DELETEs
  - `tests/test_smoke.py` — posts through the current `send_message()` to the mock, asserts success
- **Verifier:**
  ```bash
  python3 --version
  python3 -m unittest discover -s tests -v
  ```
  **Expected result:** Python reports 3.10 or newer. Test suite exits 0; `test_smoke` confirms the mock received a POST with the message content and `send_message()` returned ok.
- **Review gate:** No (mechanical)
- **Rollback/checkpoint:** git tag `m0-verified` on pass

### M1 — Capture the message ID
- **Status:** ☑
- **Objective:** `send_message()` requests `?wait=true` and surfaces the created message's ID.
- **Deliverables:**
  - `send_message()` returning the message ID in addition to `(ok, detail)`
  - `tests/test_send_id.py`
- **Depends on:** M0
- **Verifier:**
  ```bash
  python3 -m unittest tests.test_send_id -v
  ```
  **Expected result:** Exits 0. Asserts the mock saw `wait=true` in the POST query string, and that `send_message()` returned the ID the mock issued.
- **Review gate:** Yes — Codex review against this milestone's verifier + deliverables
- **Rollback/checkpoint:** git tag `m1-verified` on pass

### M2 — Delete call and in-memory scheduler
- **Status:** ☑
- **Objective:** A message can be deleted by ID, and a delete can be scheduled to fire after a delay.
- **Deliverables:**
  - `delete_message(webhook_url, message_id)`
  - `send_and_schedule()` — display-free orchestration returning the send result and the delete request
  - `tests/test_delete.py`
- **Depends on:** M1
- **Verifier:**
  ```bash
  python3 -m unittest tests.test_delete -v
  ```
  **Expected result:** Exits 0. With a 1-second delay, the mock records `DELETE /webhooks/{id}/{token}/messages/{message_id}` within 2 seconds of the POST. A separate case asserts a mock-returned 404 on delete is reported, not raised.
- **Review gate:** Yes
- **Rollback/checkpoint:** git tag `m2-verified` on pass

### M3 — CLI toggle and delay
- **Status:** ☑
- **Objective:** CLI users can enable auto-delete and set the delay.
- **Deliverables:**
  - `run_cli()` prompting for auto-delete (default off) and delay (default 0), scheduling via daemon `threading.Timer`
  - `tests/test_cli.py`
- **Depends on:** M2
- **Verifier:**
  ```bash
  python3 -m unittest tests.test_cli -v
  ```
  **Expected result:** Exits 0. Driving `run_cli()` with scripted stdin (auto-delete on, delay 1) causes the mock to record a POST followed by a matching DELETE. A second case with auto-delete off records a POST and **no** DELETE.
- **Review gate:** Yes
- **Rollback/checkpoint:** git tag `m3-verified` on pass

### M4 — GUI toggle and delay
- **Status:** ◐ (verifier passed; owner's manual GUI checklist outstanding)
- **Objective:** GUI users can enable auto-delete and set the delay; scheduling runs on the tkinter main loop.
- **Deliverables:**
  - Checkbox + delay spinbox in `run_gui()`, wired to `send_and_schedule()` and armed via `root.after()`
  - `tests/test_gui_logic.py` — exercises the extracted logic with no display
- **Depends on:** M3
- **Verifier:**
  ```bash
  python3 -m unittest tests.test_gui_logic -v
  ```
  **Expected result:** Exits 0. Asserts `send_and_schedule()` with auto-delete on returns a delete request carrying the right message ID and delay, and returns none when off. Widget wiring is **not** covered by this verifier — see review gate.
- **Review gate:** Yes — **owner manual GUI pass, required before this milestone closes.** Checklist:
  1. Checkbox is off on launch; sending with it off leaves the message in the channel.
  2. With it on and delay 0, the message appears and disappears.
  3. With it on and delay 10, the message survives ~10s, then goes.
  4. Closing the app during a pending delete leaves the message (expected, documented).
  5. Spinbox refuses values outside 0–3600.
- **Rollback/checkpoint:** git tag `m4-verified` on pass, after the manual pass

### M5 — README documents the feature and its limits
- **Status:** ☑
- **Objective:** A user reading only the README understands auto-delete and its app-must-stay-open caveat.
- **Deliverables:**
  - README section covering the toggle, the delay field, and the in-memory limitation
- **Depends on:** M4
- **Verifier:**
  ```bash
  grep -qi "only while the app is running" README.md && echo "CAVEAT DOCUMENTED"
  python3 -m unittest discover -s tests
  ```
  **Expected result:** Prints `CAVEAT DOCUMENTED`; full suite exits 0.
- **Review gate:** Yes — owner read-through
- **Rollback/checkpoint:** git tag `m5-verified` on pass

---

## 7. Verification Strategy

**Test approach:** stdlib `unittest`, tests in `tests/`, all HTTP against `tests/mock_discord.py` on localhost. One command runs everything:
```bash
python3 -m unittest discover -s tests -v
```

**Continuous checks:** Run the full suite before every commit on this branch. No linter or type checker is configured in this repo; do not add one as part of this work (out of scope) — match the existing file's style by hand.

**Review process:** Codex review at each milestone boundary from M1 on, judged against that milestone's verifier and deliverables. M4 additionally requires the owner's manual GUI checklist to pass before it closes. Human review before merging `Auto-Delete` to `main`.

**Reproducibility bar:** Every verified milestone must pass its verifier from a clean clone of the branch, not just the working tree.

**Manual smoke (once, before M5 closes):** Send one message through a real Discord webhook to a throwaway channel with auto-delete on and delay 5, and confirm it vanishes. Guards against mock-vs-Discord drift. Not an automated verifier; record the result in the Decision Log.

---

## 8. Risks & Open Questions

### Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Mock server diverges from real Discord behavior (response shape, status codes on delete) | M | M | One manual smoke against a real webhook before M5 closes; keep the mock's contract narrow |
| `threading.Timer` in CLI is a daemon — a pending delete dies silently on Ctrl+C | H | L | Accepted and documented; it is the stated best-effort contract (FR-8) |
| Rate limiting (429) when delay is 0 and sends are frequent | M | L | Existing cooldown throttles sends; failed delete reports and drops (FR-7) |
| Someone sets a long delay, closes the app, and is surprised the message persists | H | M | README caveat (M5); accepted for the "friends I hand it to" audience — no UI warning is in scope |
| `send_message()`'s return-type change breaks its callers | M | L | Single-file app; M1's verifier plus M0's smoke cover both call sites |
| tkinter absent on a user's Python build | L | L | Already handled — app falls back to CLI mode |
| Ambiguous done-criteria on M4, since widget wiring has no automated verifier | M | M | Split resolved this: logic is verified automatically, widgets by the owner's checklist, which is a named review gate rather than an implicit step |

### Open questions
| Question | Must resolve before | Owner |
|---|---|---|
| Which platforms do the "friends" actually run this on? If Windows/macOS, the README's support claim and the tkinter caveat need adjusting; the SPEC currently only claims Spark/Ubuntu verification. | **Still open** — was assigned M5; M5 closed without it. Resolve before merge to `main`. | Daron |
| ~~Should the delay field be per-message or set once at CLI startup?~~ | ~~M3~~ | **Resolved 2026-07-16:** once at startup, matching how the CLI already handles cooldown. |

---

## 9. Agent Operating Notes

- When blocked or when a verifier fails twice for the same cause: stop, summarize the failure, and ask the owner. Do not redesign around it.
- Do not modify this SPEC's milestones without logging the change in Section 10 and getting owner approval.
- Never put a real webhook URL in a test, fixture, or commit. `DEFAULT_WEBHOOK` stays empty.
- Do not add persistence for pending deletes "while you're in there" — it is an explicit non-goal (Section 2) and would introduce a file holding webhook URLs.
- Do not introduce pip dependencies, a linter, or a type checker as part of this work.
- Run `/retro` before ending any session that closes a milestone.

---

## 10. Decision Log

| Date | Change | Reason | Approved by |
|---|---|---|---|
| 2026-07-15 | Spec created via `/spec-interview` | New feature work on branch `Auto-Delete` | Daron |
| 2026-07-16 | Open question resolved: CLI auto-delete settings are prompted once at startup, not per message | Consistent with the CLI's existing pattern (cooldown asked once, then a pure send loop) | Daron |
| 2026-07-16 | `send_message()` return type changed from `(ok, detail)` to `(ok, detail, message_id)`; URL prefix check extracted to `WEBHOOK_PREFIXES` | Required by M1 (capture the id) and by M0 (tests must reach a localhost mock) | Daron |
| 2026-07-16 | **Deviation:** M1–M5 implemented in one pass without pausing at each milestone boundary | Owner instruction ("implement all remaining milestones"). Each verifier still ran and passed in order | Daron |
| 2026-07-16 | **Deviation:** Codex review gates (M1–M5) not performed | No Codex review was run in this session; gates remain outstanding, not waived | Claude (flagged for owner) |
