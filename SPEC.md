# SPEC: Webhook Messenger — Auto-Resend

| Field | Value |
|---|---|
| Status | Active |
| Owner | Daron |
| Created | 2026-07-16 |
| Last updated | 2026-07-16 |
| Repo | `/home/daron/spark-dev-workspace/Webhook` (branch `Auto-Resend`, off `main`) |
| Target environment | Developed and verified on DGX Spark, aarch64, Ubuntu 24.04. Stdlib-only, so expected to run on Windows/macOS — untested (see Open Questions). |
| Permission overrides | None — global `~/.claude/settings.json` applies |

---

## 1. Goal & Motivation

**What:** Add opt-in auto-resend to the existing Discord webhook messenger. When enabled, the app repeatedly reposts the current message on a fixed interval (the existing cooldown field) until the user stops it. Available in both the GUI and the CLI, and it composes with the already-merged auto-delete feature.

**Why:** The app can only send one message per manual action. Users who want a message repeated on a cadence — a recurring reminder, a heartbeat, a bump — must click or retype every time. Auto-resend automates the repeat while keeping the send-once default untouched.

**Definition of overall success:** With auto-resend enabled and an interval of N seconds, the app reposts the current message content approximately every N seconds — firing immediately in the GUI when toggled On — and stops on user command (GUI Off / CLI Ctrl+C) or after an optional max-count, provided the app stays running. Demonstrated by an automated `unittest` suite against a mock Discord server, and confirmed once by hand against a real channel.

---

## 2. Scope

### In scope
- A display-free resend core that performs one send (delegating to the existing `send_and_schedule()` so auto-delete composes), tracks a send count, and enforces an optional max-count.
- GUI: an **Auto-resend** live checkbox that swaps the **Send message** button into an **On/Off** toggle and back.
- GUI scheduling via `root.after()`; On fires immediately, then repeats every interval.
- CLI: a startup y/N prompt that enables auto-resend, driven by a daemon background thread that reposts the current content every interval.
- Reuse of the existing **Cooldown between sends** field as the resend interval, re-read each fire.
- An optional **max-count** field ("stop after N sends"; blank/0 = unlimited).
- Live re-read of message content (and ping) at each fire.
- `unittest` coverage against the existing localhost mock Discord server.
- README documenting the feature, its interaction with auto-delete, the rate-limit note, and the app-must-stay-open limitation.

### Out of scope (non-goals)
- **Persistence of an active resend loop across restarts.** No state file. Closing the app stops all resending immediately.
- **A live on/off toggle in the CLI.** The CLI has no pause control; content is changed by typing, and the loop is ended with Ctrl+C.
- **Scheduling sends at absolute times / cron-style triggers.** The interval is a fixed relative delay only.
- **Retrying failed sends or deletes.** One attempt each, report the outcome, drop it (inherited contract).
- **A distinct interval field.** Auto-resend reuses the existing cooldown field, not a new one.
- **Raising the interval floor.** The GUI minimum stays 1s; rate-limit responses are reported and dropped, not prevented.
- **Per-message resend history / send log UI.**

### Future work (explicitly deferred)
- A persisted, resumable resend schedule (survives restart). Deferred deliberately; do not design current code around it.
- A CLI pause/resume control.
- Absolute-time or cron-style scheduling.
- An adaptive interval that backs off on 429s.

---

## 3. Requirements

### Functional
- **FR-1:** Auto-resend is opt-in. Both front ends default to **off**; an unmodified workflow behaves exactly as it does today (GUI single-send button, CLI blank-line send loop).
- **FR-2:** The existing **Cooldown between sends** field is reused as the resend interval and is re-read at each fire. The GUI spinbox floor remains **1s**.
- **FR-3:** An optional **max-count** field accepts a non-negative integer; blank or 0 means unlimited. When set to N, auto-resend stops after N **successful** sends; a failed fire (e.g. a 429) does not count toward the cap.
- **FR-4:** Each auto-send re-reads the current content at fire time — the GUI message box plus its ping/mention, the CLI's current content — so edits mid-run change subsequent sends.
- **FR-5:** Auto-resend composes with auto-delete: when auto-delete is also enabled, each resent message schedules its own delete per the existing delay.
- **FR-6 (GUI):** Ticking the **Auto-resend** checkbox swaps the **Send message** button into an **On/Off** toggle; unticking swaps it back. Turning it **On** fires immediately and then repeats every interval, scheduled via `root.after()`. Reaching max-count flips the toggle back to **Off**. Unticking the checkbox mid-run stops the loop and restores the plain Send button.
- **FR-7 (CLI):** A startup **y/N** prompt enables auto-resend. When on, a daemon `threading.Timer`/thread reposts the current content every interval; typing a new message + Enter swaps the content (guarded by a lock) and starts a fresh max-count batch. There is no live on/off toggle; Ctrl+C quits.
- **FR-8:** A failed send or delete (404, 429, network error) reports to the GUI status label or CLI stdout and is then discarded. No retry, no crash, no interruption of the loop (inherited contract).
- **FR-9:** An active resend loop and any composed pending deletes are held in memory only and stop when the app exits. The README states this explicitly.

### Non-functional
- **NFR-1:** Standard library only. No `pip install` for the app or its tests.
- **NFR-2:** Python 3.10+ (matches the existing `from __future__ import annotations` / `X | None` style).
- **NFR-3:** Tests make no outbound network calls; all HTTP is against the existing mock server bound to localhost.
- **NFR-4:** No webhook URLs, tokens, or real user/role IDs in the repo, tests, or fixtures.
- **NFR-5:** The app remains a single file, `send_webhook.py`; tests live under `tests/`.
- **NFR-6:** No regression — the existing send and auto-delete test suites stay green.

### Constraints
- **tkinter is not thread-safe.** The GUI resend loop must be driven by `root.after()` on the main loop; no timer thread may touch a widget. This mirrors the auto-delete GUI/CLI scheduler split.
- Discord tolerates roughly **30 posts/minute per webhook**. A 1s interval will draw 429s; those are reported and dropped (FR-8), not prevented.
- The CLI must repost while `input()` is blocking, which forces a background thread plus a lock over the shared current-content string.
- No new system dependencies (this rules out `xvfb` for headless GUI tests).
- Work happens on branch `Auto-Resend`, branched from `main` (which must contain the merged auto-delete feature — see Open Questions).

---

## 4. Technical Approach

### Stack
| Component | Version | Notes |
|---|---|---|
| Python | 3.10+ | System `python3` on Ubuntu 24.04 |
| urllib.request | stdlib | Existing HTTP client (POST + DELETE) |
| tkinter / ttk | stdlib | GUI; already optional with CLI fallback |
| threading | stdlib | Daemon thread + `Lock` for the CLI resend loop |
| unittest | stdlib | Test runner — pytest excluded by NFR-1 |
| http.server | stdlib | Existing mock Discord webhook server for tests |

### Architecture overview

```
send_webhook.py
  send_message(url, content, ...)      -> (ok, detail, message_id)   [existing]
  delete_message(url, message_id)      -> (ok, detail)               [existing]
  send_and_schedule(...)               -> (ok, detail, DeleteRequest|None)  [existing]

  resend_step(get_content, settings, count) -> (result, DeleteRequest|None, keep_going)
        # display-free: reads current content via callback, delegates the send to
        # send_and_schedule (so auto-delete composes), returns whether to continue
        # given the optional max-count.

  run_gui()  -> Auto-resend checkbox swaps Send <-> On/Off toggle; On fires immediately,
                repeats via root.after(interval*1000, ...); max-count flips Off.
  run_cli()  -> startup y/N prompt; daemon thread calls resend_step() every interval,
                reading a lock-guarded current-content string the input loop updates.

tests/
  mock_discord.py         -> existing localhost mock (POST ?wait=true, records DELETEs)
  test_resend_core.py     -> resend_step: count, max-count stop, live content re-read, delete composition
  test_cli_resend.py      -> threaded CLI loop bounded by max-count; off-path unchanged
  test_gui_resend_logic.py-> display-free GUI helper logic (button-state / stop decisions)
```

The resend core is display-free so the send/count/stop decision is verifiable without a display or a running loop. Both front ends call it and differ only in how they arm the next fire (GUI `root.after`, CLI daemon thread).

### Key design decisions
| Decision | Rationale | Alternatives rejected |
|---|---|---|
| Reuse the cooldown field as the resend interval | Owner directive; avoids a second interval field and matches the "cooldown between messages" framing | A separate interval field (redundant control) |
| GUI: live checkbox swaps Send into an On/Off toggle | Owner directive; consistent with the existing auto-delete checkbox pattern | Startup-fixed mode (less flexible); a separate always-present Start/Stop button (more clutter) |
| On fires immediately, then every interval | Owner choice; "On" reads as "go now" | Wait one interval before the first send (feels unresponsive) |
| Compose with auto-delete (each copy deletes per its delay) | Owner choice; the two features are orthogonal and combine cleanly | Make them mutually exclusive (arbitrary limitation); ignore the interaction (surprising effects) |
| CLI: daemon background thread + lock-guarded content | Only way to keep reposting while `input()` blocks; matches the existing daemon-timer best-effort pattern | Non-blocking stdin via `select` (not portable to Windows); prompt-between-sends (cannot repost while waiting for input) |
| Optional max-count (blank/0 = unlimited) | Owner choice; a safety cap against runaway spam without limiting legitimate use | No cap (runaway risk); a mandatory hard cap (limits legitimate long runs) |
| Keep the 1s interval floor | Owner choice; failed sends already report and drop (FR-8) | Raise the floor (unnecessary given existing failure handling) |
| GUI max-count flips the toggle Off; CLI new message resets the batch | Sensible, owner-confirmed stop/restart semantics for each front end | Silently idle at max (looks hung); exit the app at max (too aggressive) |
| Display-free `resend_step()` shared by both front ends | Testable without a display or timers; mirrors the existing `send_and_schedule()` extraction | Duplicate the loop logic per front end (untestable, drift-prone) |

---

## 5. Environment & Setup

**Hardware/OS assumptions:** DGX Spark, aarch64, Ubuntu 24.04 for development and verification. No GPU, no accelerator, no network service dependencies. Runtime is portable in principle (stdlib only) but only verified on the Spark.

**Setup commands:**
```bash
# from clean clone:
cd Webhook
git checkout Auto-Resend
python3 --version          # expect 3.10 or newer
python3 -c "import tkinter" # optional; CLI mode works without it
# no dependency install step — stdlib only
```

**Secrets/credentials required:** A Discord webhook URL, supplied at runtime by the user. Never stored in the repo, never committed, never written to disk by this app. Tests use the mock server and require no secret.

**Relevant knowledge-base entries:**
- None identified at spec time. Record any aarch64/tkinter/threading findings via `/retro`.

---

## 6. Milestones

### M0 — Environment / regression baseline
- **Status:** ☑ (verifier passed; tag `resend-m0-verified`)
- **Objective:** The `Auto-Resend` branch, cut from a `main` that contains auto-delete, runs the full existing suite green.
- **Deliverables:**
  - Branch `Auto-Resend` created off `main`.
  - No code change beyond confirming the baseline.
- **Verifier:**
  ```bash
  python3 --version
  git grep -q "def delete_message" -- send_webhook.py && echo "AUTO-DELETE PRESENT"
  python3 -m unittest discover -s tests -v
  ```
  **Expected result:** Python reports 3.10 or newer. Prints `AUTO-DELETE PRESENT` (confirms the branch base carried auto-delete). Existing suite exits 0.
- **Review gate:** No (mechanical)
- **Rollback/checkpoint:** git tag `resend-m0-verified` on pass

### M1 — Display-free resend core
- **Status:** ☑ (verifier passed; workflow code review done, one correctness fix applied — see Decision Log; awaiting owner sign-off + tag)
- **Objective:** A `resend_step()` performs one send by delegating to `send_and_schedule()`, tracks the send count, re-reads content each call, and reports whether to continue given an optional max-count.
- **Deliverables:**
  - `resend_step()` (or an equivalent small controller) in `send_webhook.py`.
  - `tests/test_resend_core.py`.
- **Depends on:** M0
- **Verifier:**
  ```bash
  python3 -m unittest tests.test_resend_core -v
  ```
  **Expected result:** Exits 0. Asserts: (a) calling the core K times against the mock records K POSTs; (b) changing the content callback's return value between calls changes the POSTed content (live re-read); (c) with max-count N, the core reports `keep_going=False` once N is reached; (d) with auto-delete on, each call returns a `DeleteRequest` carrying the mock-issued message ID (composition).
- **Review gate:** Yes — Codex review against this milestone's verifier + deliverables
- **Rollback/checkpoint:** git tag `resend-m1-verified` on pass

### M2 — CLI auto-resend
- **Status:** ☑ (verifier passed; workflow code review in progress; awaiting owner sign-off + tag)
- **Objective:** CLI users can enable auto-resend at startup; a daemon thread reposts the current content every interval, and typing a new message swaps it.
- **Deliverables:**
  - `run_cli()` with a startup y/N auto-resend prompt, a daemon resend thread over lock-guarded content, and a fresh max-count batch on new content.
  - `tests/test_cli_resend.py`.
- **Depends on:** M1
- **Verifier:**
  ```bash
  python3 -m unittest tests.test_cli_resend -v
  ```
  **Expected result:** Exits 0. Case A: auto-resend on, max-count 3, scripted stdin gives one message then EOF; the resend thread is joined and the mock records exactly 3 POSTs of that content. Case B: auto-resend **off** preserves today's behavior — one POST per blank-line send, no background thread started.
- **Review gate:** Yes
- **Rollback/checkpoint:** git tag `resend-m2-verified` on pass

### M3 — GUI auto-resend
- **Status:** ◐ (display-free verifier passed; workflow code review in progress. **Owner manual GUI checklist still required** — cannot run on the Spark: no tkinter/no display here.)
- **Objective:** GUI users can tick Auto-resend to swap the Send button into an On/Off toggle that fires immediately and repeats on the main loop.
- **Deliverables:**
  - `run_gui()`: Auto-resend checkbox that swaps Send ↔ On/Off, immediate-first-fire via `root.after()`, live re-read of the message box + ping, max-count flips Off, unticking restores Send.
  - `tests/test_gui_resend_logic.py` — exercises the extracted GUI decision logic with no display.
- **Depends on:** M2
- **Verifier:**
  ```bash
  python3 -m unittest tests.test_gui_resend_logic -v
  ```
  **Expected result:** Exits 0. Asserts the display-free GUI helpers: reaching max-count reports "stop" (toggle should flip Off), and a non-max state reports "continue". Widget wiring is **not** covered here — see the review gate.
- **Review gate:** Yes — **owner manual GUI pass, required before this milestone closes.** Checklist:
  1. Checkbox off at launch; button reads "Send message"; a single send works as today.
  2. Ticking the checkbox turns the button into an On/Off toggle (Off).
  3. Turning On fires immediately, then repeats every cooldown; editing the message box mid-run changes subsequent sends.
  4. Setting max-count N stops after N sends and flips the toggle back to Off.
  5. Unticking the checkbox mid-run stops the loop and restores the plain Send button.
  6. With auto-delete also on, each resent copy disappears after its delay.
- **Rollback/checkpoint:** git tag `resend-m3-verified` on pass, after the manual pass

### M4 — README documents the feature and its limits
- **Status:** ☑ (verifier passed: `CAVEAT DOCUMENTED`, full suite green; awaiting owner read-through)
- **Objective:** A user reading only the README understands auto-resend, its interaction with auto-delete, the rate-limit note, and the app-must-stay-open caveat.
- **Deliverables:**
  - README section covering the Auto-resend checkbox / CLI prompt, the reused cooldown interval, the max-count field, the resend+delete interaction, and the in-memory/rate-limit limitations.
- **Depends on:** M3
- **Verifier:**
  ```bash
  grep -qi "stops when you close the app" README.md && echo "CAVEAT DOCUMENTED"
  python3 -m unittest discover -s tests
  ```
  **Expected result:** Prints `CAVEAT DOCUMENTED`; full suite exits 0.
- **Review gate:** Yes — owner read-through
- **Rollback/checkpoint:** git tag `resend-m4-verified` on pass

---

## 7. Verification Strategy

**Test approach:** stdlib `unittest`, tests in `tests/`, all HTTP against `tests/mock_discord.py` on localhost. One command runs everything:
```bash
python3 -m unittest discover -s tests -v
```

**Continuous checks:** Run the full suite before every commit on this branch. No linter or type checker is configured in this repo; do not add one as part of this work (out of scope) — match the existing file's style by hand.

**Review process:** Codex review at each milestone boundary from M1 on, judged against that milestone's verifier and deliverables. M3 additionally requires the owner's manual GUI checklist to pass before it closes. Human review before merging `Auto-Resend` to `main`.

**Reproducibility bar:** Every verified milestone must pass its verifier from a clean clone of the branch, not just the working tree.

**Manual smoke (once, before M4 closes):** Enable auto-resend against a real Discord webhook to a throwaway channel with a short interval and max-count 3, and confirm three posts arrive on cadence and it then stops. If auto-delete is also on, confirm each copy vanishes. Not an automated verifier; record the result in the Decision Log.

---

## 8. Risks & Open Questions

### Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Threaded CLI test is flaky (timing) | M | M | Bound the threaded test by max-count and join the thread; put the content-re-read assertion in the single-threaded core test (M1), not the threaded one |
| Race on the shared CLI current-content string between the input loop and the resend thread | M | M | Guard reads/writes with a `Lock`; the resend thread only reads a snapshot under the lock |
| A 1s interval draws sustained 429s and spams failures | M | L | Existing report-and-drop contract (FR-8); README rate-limit note; audience is "friends I hand it to" |
| Runaway resend floods a real channel | M | M | Optional max-count cap; feature is opt-in and off by default |
| tkinter widget touched from a non-main thread | L | H | GUI uses `root.after()` only — no thread in the GUI path; mirrors the auto-delete design |
| Branch base uncertainty — local `main` did not contain auto-delete and the remote could not be fetched | H | H | Resolve before M0: confirm `main` truly has auto-delete (Open Questions); M0's verifier prints `AUTO-DELETE PRESENT` as a gate |
| Resend + auto-delete at a low interval creates heavy send/delete churn | L | L | Accepted and documented; both features are opt-in |

### Open questions
| Question | Must resolve before | Owner |
|---|---|---|
| Does `main` actually contain the merged auto-delete feature? Local `main` was at the pre-auto-delete commit and `git fetch` could not authenticate (no SSH key). The branch base and the resend+delete composition depend on this. | **M0** — fix remote access, fetch, and branch `Auto-Resend` off the confirmed `main` | Daron |
| Which platforms do users actually run the CLI on? The background-thread + `input()` loop is only verified on Spark/Ubuntu; behavior on Windows/macOS is untested. | Merge to `main` | Daron |

---

## 9. Agent Operating Notes

- When blocked or when a verifier fails twice for the same cause: stop, summarize the failure, and ask the owner. Do not redesign around it.
- Do not modify this SPEC's milestones without logging the change in Section 10 and getting owner approval.
- Never put a real webhook URL in a test, fixture, or commit. `DEFAULT_WEBHOOK` stays empty.
- Do not add persistence for an active resend loop "while you're in there" — it is an explicit non-goal (Section 2).
- The GUI resend path must schedule via `root.after()` only; never touch a widget from a timer thread.
- Do not introduce pip dependencies, a linter, or a type checker as part of this work.
- Run `/retro` before ending any session that closes a milestone.

---

## 10. Decision Log

| Date | Change | Reason | Approved by |
|---|---|---|---|
| 2026-07-16 | Spec created via `/spec-interview` | New feature work on branch `Auto-Resend` | Daron |
| 2026-07-16 | Branch base correction: local `main` did not contain the auto-delete commit (only branch `Auto-Delete` did), and `git fetch` failed to authenticate. Branch creation deferred until the owner fixes remote access and confirms `main` has auto-delete. | Design assumes resend composes with auto-delete; branching off a main without it would silently drop FR-5. Flagged rather than branched off the wrong base. | Claude (flagged for owner) |
| 2026-07-16 | Open question resolved in practice: `Auto-Resend` sits on commit `1eb5851` ("Add opt-in auto-delete"), so **auto-delete is present in this branch** and FR-5 composition is satisfiable. M0 verifier printed `AUTO-DELETE PRESENT`. **Caveat for the owner:** `main` (and `origin/main`) still point at `6211513` (pre-auto-delete); auto-delete lives on branch `Auto-Delete`, never merged to `main`. So the SPEC's "branched off `main`" is not literally true, and **the merge order to land on `main` must fold in auto-delete first** (merge `Auto-Delete` → `main`, then `Auto-Resend` → `main`, or merge `Auto-Resend` which carries both). | Building resend on top of the auto-delete commit is correct and unblocks the work; only the eventual merge-to-main ordering needs care. | Claude (flagged for owner) |
| 2026-07-16 | **max-count counts send *attempts*, not successes** (FR-3 "stops after N sends" was ambiguous). A failed fire (e.g. a 429) still consumes one of the N. Consequence: on a transient failure the user may receive fewer than N posts, but the failure is surfaced (FR-8) and the cap always terminates. | FR-3's rationale is a *safety cap against runaway spam*; a cap that failures could bypass isn't a cap, and it would need a persistent-failure circuit-breaker, which is out of scope (FR-8: no retry). Flagged by the M1 code review; recorded here rather than silently chosen. | Claude (flagged for owner — say if you want N *successful* posts instead) |
| 2026-07-16 | M1 review fix: `clamp_max_count` treated a numeric decimal like `"3.5"` as junk → `0` (= unlimited), inverting a bounded intent into an unbounded flood. Now parses via `int(float(...))` so `"3.5"` → 3; truly non-numeric input still → 0. Regression test added. | Correctness fix inside new M1 code; a safety-cap field must never fail *open*. | Claude |
| 2026-07-16 | M0–M4 implemented in one session: M0/M1/M2/M4 verifiers green; M3 automated (display-free) verifier green. Tags beyond `resend-m0-verified` and any commit held for owner (global policy: commit/tag on owner's request). | Milestone work completed; front ends and README done. | Claude |
| 2026-07-16 | M2/M3 workflow code review (high effort, 19 agents): 10 findings. **Fixed:** (a) GUI `tick_cooldown` clobbered the auto-resend toggle label when the checkbox was ticked during a leftover single-send cooldown; (b) CLI EOF-drain used one `batch_done` Event shared across message generations (could return stale → truncate the final batch) and a latency-blind timeout — replaced with per-generation `done_gen` tracking via a `threading.Condition` (returns the instant the final batch completes; timeout now a safety cap that includes per-send latency). Added a swap-and-drain regression test. | Two genuine defects in the new resend code. | Claude |
| 2026-07-16 | **max-count now counts *successful* sends, reversing the earlier "counts attempts" decision** (see the 2026-07-16 row above). Owner chose N successful posts when asked. `resend_step` advances the count only when a fire lands; both front ends increment their own count only on `ok`. FR-3 updated. Trade-off accepted: a persistently failing webhook never reaches the cap and keeps trying until stopped (no circuit-breaker — out of scope per FR-8). Regression test `test_failed_send_does_not_consume_the_cap` added; README rate-limit note updated. | Owner directive (answered the pending flagged question). | Daron |
| 2026-07-16 | M2/M3 review — deliberately **not** changed (each is intended per an FR): piped multi-message sends only the latest (FR-7 swap semantics, no queue); GUI loop shows no blocking modal on a failed fire (FR-8 report-to-status, no interruption); GUI max-count doesn't reset when the message box is edited (FR-6 defines no GUI "commit" event). Cleanup deferred: blocking HTTP on the tkinter main loop (matches the existing single-send path; noted as future work), `build_gui_content`/`_apply_mention` strip divergence (each preserves merged behavior), `gui_after_fire` seam (kept — it is what the M3 verifier exercises). | Avoid "fixing" spec-mandated behavior or altering already-merged code; flagged for owner. | Claude (flagged for owner) |
