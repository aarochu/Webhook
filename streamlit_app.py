#!/usr/bin/env python3
"""Streamlit front end for D4zr + Prototype."""

from __future__ import annotations

import time
from datetime import timedelta

import streamlit as st

from send_webhook import (
    DEFAULT_WEBHOOK,
    MAX_DELAY,
    MIN_DELAY,
    DeleteRequest,
    ResendSettings,
    arm_delete_timer,
    build_gui_content,
    clamp_delay,
    clamp_max_count,
    delete_message,
    edit_message,
    forget_sent,
    gui_after_fire,
    remember_sent,
    resend_step,
    send_and_schedule,
    update_sent_content,
)

# ---------------------------------------------------------------------------
# Page + theme
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="D4zr + Prototype",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=Rajdhani:wght@400;500;600&display=swap');

:root {
    --bg-deep: #050810;
    --bg-panel: rgba(12, 18, 36, 0.72);
    --border-glow: rgba(0, 240, 255, 0.35);
    --accent-cyan: #00f0ff;
    --accent-violet: #a855f7;
    --accent-magenta: #ec4899;
    --text-dim: #94a3b8;
    --text-bright: #e2e8f0;
    --success: #34d399;
    --danger: #f87171;
}

.stApp {
    background:
        radial-gradient(ellipse 80% 50% at 50% -20%, rgba(0, 240, 255, 0.12), transparent),
        radial-gradient(ellipse 60% 40% at 100% 50%, rgba(168, 85, 247, 0.1), transparent),
        radial-gradient(ellipse 50% 30% at 0% 80%, rgba(236, 72, 153, 0.08), transparent),
        linear-gradient(180deg, #050810 0%, #0a0f1e 50%, #050810 100%);
    color: var(--text-bright);
    font-family: 'Rajdhani', sans-serif;
}

#MainMenu, footer, header { visibility: hidden; }

.nexus-hero {
    text-align: center;
    padding: 1.5rem 0 2rem;
    margin-bottom: 0.5rem;
}
.nexus-hero h1 {
    font-family: 'Orbitron', sans-serif;
    font-size: 2.4rem;
    font-weight: 700;
    letter-spacing: 0.18em;
    margin: 0;
    background: linear-gradient(90deg, var(--accent-cyan), var(--accent-violet), var(--accent-magenta));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    filter: drop-shadow(0 0 24px rgba(0, 240, 255, 0.35));
}
.nexus-hero p {
    color: var(--text-dim);
    font-size: 1.05rem;
    letter-spacing: 0.35em;
    text-transform: uppercase;
    margin: 0.4rem 0 0;
}

.glass-panel {
    background: var(--bg-panel);
    border: 1px solid var(--border-glow);
    border-radius: 14px;
    padding: 1.25rem 1.5rem;
    margin-bottom: 1rem;
    box-shadow:
        0 0 30px rgba(0, 240, 255, 0.06),
        inset 0 1px 0 rgba(255, 255, 255, 0.04);
    backdrop-filter: blur(12px);
}
.panel-title {
    font-family: 'Orbitron', sans-serif;
    font-size: 0.75rem;
    letter-spacing: 0.2em;
    color: var(--accent-cyan);
    text-transform: uppercase;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(0, 240, 255, 0.15);
}

.status-pill {
    display: inline-block;
    padding: 0.35rem 0.9rem;
    border-radius: 999px;
    font-size: 0.9rem;
    letter-spacing: 0.05em;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: rgba(15, 23, 42, 0.6);
}
.status-pill.ok { border-color: rgba(52, 211, 153, 0.5); color: var(--success); }
.status-pill.err { border-color: rgba(248, 113, 113, 0.5); color: var(--danger); }
.status-pill.wait { border-color: rgba(0, 240, 255, 0.4); color: var(--accent-cyan); }

div[data-testid="stMetric"] {
    background: rgba(15, 23, 42, 0.5);
    border: 1px solid rgba(0, 240, 255, 0.12);
    border-radius: 10px;
    padding: 0.5rem;
}
div[data-testid="stMetric"] label { color: var(--text-dim) !important; }
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: 'Orbitron', sans-serif;
    color: var(--accent-cyan) !important;
}

.stTextInput input, .stTextArea textarea, .stNumberInput input {
    background: rgba(8, 12, 24, 0.9) !important;
    border: 1px solid rgba(0, 240, 255, 0.2) !important;
    border-radius: 8px !important;
    color: var(--text-bright) !important;
    font-family: 'Rajdhani', sans-serif !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--accent-cyan) !important;
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.2) !important;
}

.stButton > button {
    font-family: 'Orbitron', sans-serif !important;
    letter-spacing: 0.08em !important;
    border-radius: 8px !important;
    border: 1px solid rgba(0, 240, 255, 0.4) !important;
    background: linear-gradient(135deg, rgba(0, 240, 255, 0.15), rgba(168, 85, 247, 0.15)) !important;
    color: var(--text-bright) !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    border-color: var(--accent-cyan) !important;
    box-shadow: 0 0 20px rgba(0, 240, 255, 0.3) !important;
    transform: translateY(-1px);
}
.stButton > button:disabled {
    opacity: 0.45 !important;
    transform: none !important;
    box-shadow: none !important;
}

div[data-testid="stCheckbox"] label span { color: var(--text-bright) !important; }

.log-line {
    font-family: 'Rajdhani', monospace;
    font-size: 0.85rem;
    color: var(--text-dim);
    padding: 0.2rem 0;
    border-left: 2px solid rgba(0, 240, 255, 0.2);
    padding-left: 0.6rem;
    margin: 0.15rem 0;
}
.log-line.ok { border-left-color: var(--success); color: #a7f3d0; }
.log-line.err { border-left-color: var(--danger); color: #fecaca; }
</style>
""",
    unsafe_allow_html=True,
)


def _init_state() -> None:
    defaults = {
        "cooldown_until": 0.0,
        "resend_active": False,
        "resend_count": 0,
        "next_fire": 0.0,
        "status": "Ready",
        "status_ok": None,
        "log": [],
        "message": "hey",
        "sent_messages": [],
        "editing_id": None,
        "edit_draft": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _log(msg: str, ok: bool | None = None) -> None:
    stamp = time.strftime("%H:%M:%S")
    st.session_state.log.insert(0, (stamp, msg, ok))
    st.session_state.log = st.session_state.log[:20]


def _schedule_delete(request: DeleteRequest) -> None:
    def on_done(ok: bool, detail: str) -> None:
        _log(detail, ok)
        if ok:
            forget_sent(st.session_state.sent_messages, request.message_id)

    arm_delete_timer(request, on_done=on_done)


def _note_sent(message_id: str | None, webhook_url: str, content: str) -> None:
    remember_sent(st.session_state.sent_messages, message_id, webhook_url, content)


def _settings() -> ResendSettings:
    return ResendSettings(
        webhook_url=st.session_state.get("webhook_url", DEFAULT_WEBHOOK),
        username=st.session_state.get("display_name") or None,
        avatar_url=st.session_state.get("avatar_url") or None,
        auto_delete=st.session_state.get("auto_delete", False),
        delay=clamp_delay(st.session_state.get("delete_delay", MIN_DELAY)),
        max_count=clamp_max_count(st.session_state.get("max_count", 0)),
    )


def _cooldown_seconds() -> int:
    try:
        return max(1, int(st.session_state.get("cooldown", 5)))
    except (TypeError, ValueError):
        return 5


def _build_content() -> tuple[str | None, str | None]:
    return build_gui_content(
        st.session_state.get("message", ""),
        st.session_state.get("include_ping", True),
        st.session_state.get("user_id", ""),
    )


def _do_send() -> None:
    content, err = _build_content()
    if err:
        st.session_state.status = err
        st.session_state.status_ok = False
        _log(err, False)
        return

    ok, detail, message_id, request = send_and_schedule(
        st.session_state.get("webhook_url", ""),
        content,
        st.session_state.get("display_name") or None,
        st.session_state.get("avatar_url") or None,
        st.session_state.get("auto_delete", False),
        st.session_state.get("delete_delay", MIN_DELAY),
    )
    st.session_state.status = detail
    st.session_state.status_ok = ok
    _log(detail, ok)
    if ok:
        _note_sent(message_id, st.session_state.get("webhook_url", ""), content)
        st.session_state.cooldown_until = time.monotonic() + _cooldown_seconds()
        if request:
            _schedule_delete(request)
            _log(f"Auto-delete armed ({request.delay}s)", True)


def _do_resend_fire() -> None:
    content, err = _build_content()
    if err:
        st.session_state.status = err
        st.session_state.status_ok = False
        st.session_state.resend_active = False
        _log(err, False)
        return

    settings = _settings()
    (ok, detail), request, keep_going, message_id = resend_step(
        lambda: content, settings, st.session_state.resend_count
    )
    if ok:
        st.session_state.resend_count += 1
        _note_sent(message_id, settings.webhook_url, content)
    st.session_state.status = detail
    st.session_state.status_ok = ok
    _log(f"[resend #{st.session_state.resend_count}] {detail}", ok)
    if request:
        _schedule_delete(request)

    _active, decision = gui_after_fire(keep_going)
    if decision == "stop":
        st.session_state.resend_active = False
        _log("Auto-resend stopped (max count reached)", True)
    elif st.session_state.resend_active:
        st.session_state.next_fire = time.monotonic() + _cooldown_seconds()


def _append_to_message(text: str) -> None:
    current = st.session_state.get("message", "")
    st.session_state.message = f"{current}{text} " if current else f"{text} "


@st.fragment(run_every=timedelta(seconds=1))
def _resend_tick() -> None:
    if not st.session_state.resend_active:
        return
    if time.monotonic() >= st.session_state.next_fire:
        _do_resend_fire()


def _cooldown_remaining() -> int:
    return max(0, int(st.session_state.cooldown_until - time.monotonic()))


def _status_class() -> str:
    if st.session_state.resend_active:
        return "wait"
    if _cooldown_remaining() > 0:
        return "wait"
    if st.session_state.status_ok is True:
        return "ok"
    if st.session_state.status_ok is False:
        return "err"
    return ""


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

_init_state()

st.markdown(
    """
<div class="nexus-hero">
  <h1>D4zr + Prototype</h1>
  <p>Discord transmission console</p>
</div>
""",
    unsafe_allow_html=True,
)

left, right = st.columns(2, gap="large")

with left:
    st.markdown('<div class="panel-title">Connection</div>', unsafe_allow_html=True)
    st.text_input("Webhook URL", value=DEFAULT_WEBHOOK, key="webhook_url", placeholder="Paste webhook URL…")
    st.text_input("Display name", key="display_name", placeholder="Optional bot name")
    st.text_input("Profile picture URL", key="avatar_url", placeholder="Direct image link (png/jpg/gif/webp)")

    st.markdown('<div class="panel-title" style="margin-top:1.5rem">Target</div>', unsafe_allow_html=True)
    uid_col, ping_col = st.columns([2, 1])
    with uid_col:
        st.text_input("User ID to ping", key="user_id", placeholder="Numeric snowflake")
    with ping_col:
        st.markdown("<br>", unsafe_allow_html=True)
        st.checkbox("Include ping", key="include_ping", value=True)
    st.text_input("Role ID (for @role button)", key="role_id", placeholder="Optional numeric role ID")
    st.caption("Developer Mode → right-click user/role → Copy ID")

with right:
    st.markdown('<div class="panel-title">Compose</div>', unsafe_allow_html=True)
    st.text_area("Message", key="message", height=180, placeholder="Transmission payload…")

    st.markdown("**Insert mention**")
    p1, p2, p3, p4 = st.columns(4)
    with p1:
        if st.button("@user", use_container_width=True):
            uid = st.session_state.get("user_id", "").strip()
            if uid.isdigit():
                _append_to_message(f"<@{uid}>")
            else:
                st.session_state.status = "Enter a numeric user ID first."
                st.session_state.status_ok = False
    with p2:
        if st.button("@role", use_container_width=True):
            rid = st.session_state.get("role_id", "").strip()
            if rid.isdigit():
                _append_to_message(f"<@&{rid}>")
            else:
                st.session_state.status = "Enter a numeric role ID first."
                st.session_state.status_ok = False
    with p3:
        if st.button("@everyone", use_container_width=True):
            _append_to_message("@everyone")
    with p4:
        if st.button("@here", use_container_width=True):
            _append_to_message("@here")

st.markdown('<div class="panel-title" style="margin-top:0.5rem">Automation</div>', unsafe_allow_html=True)
a1, a2, a3, a4 = st.columns(4)
with a1:
    st.number_input("Cooldown (sec)", min_value=1, max_value=3600, value=5, key="cooldown")
with a2:
    st.checkbox("Auto-delete", key="auto_delete", value=False)
with a3:
    st.number_input("Delete after (sec)", min_value=MIN_DELAY, max_value=MAX_DELAY, value=MIN_DELAY, key="delete_delay")
with a4:
    st.number_input("Resend cap (0=∞)", min_value=0, max_value=100000, value=0, key="max_count")

st.caption(
    "Auto-delete only works while this tab is open. "
    "Auto-resend reposts every cooldown; failed sends don't count toward the cap."
)

# Metrics + status
m1, m2, m3 = st.columns(3)
with m1:
    remaining = _cooldown_remaining()
    st.metric("Cooldown", f"{remaining}s" if remaining else "Ready")
with m2:
    st.metric("Resend count", st.session_state.resend_count if st.session_state.resend_active else "—")
with m3:
    pill_class = _status_class()
    st.markdown(
        f'<div class="status-pill {pill_class}">{st.session_state.status}</div>',
        unsafe_allow_html=True,
    )

# Actions
btn1, btn2, btn3 = st.columns([2, 2, 3])
can_send = _cooldown_remaining() == 0 and not st.session_state.resend_active

with btn1:
    if st.button("⚡ Transmit", disabled=not can_send, use_container_width=True, type="primary"):
        _do_send()

with btn2:
    if st.session_state.resend_active:
        if st.button("■ Stop loop", use_container_width=True):
            st.session_state.resend_active = False
            _log("Auto-resend stopped by user", True)
    else:
        if st.button("↻ Start auto-resend", use_container_width=True):
            st.session_state.resend_active = True
            st.session_state.resend_count = 0
            st.session_state.next_fire = 0.0
            _log("Auto-resend started", True)

with btn3:
    if st.button("Clear log", use_container_width=True):
        st.session_state.log = []

_resend_tick()

# Sent message history (this session only — webhooks cannot read channel history)
with st.expander("Sent messages", expanded=True):
    st.caption("Messages sent through this app in the current session. Edit or delete webhook posts.")
    if not st.session_state.sent_messages:
        st.markdown('<div class="log-line">No messages yet.</div>', unsafe_allow_html=True)
    else:
        for rec in st.session_state.sent_messages:
            preview = rec.content if len(rec.content) <= 120 else rec.content[:120] + "…"
            st.markdown(f"**[{rec.sent_at}]** {preview}")
            c1, c2, c3 = st.columns([1, 1, 6])
            with c1:
                if st.button("Edit", key=f"edit_{rec.message_id}", use_container_width=True):
                    st.session_state.editing_id = rec.message_id
                    st.session_state.edit_draft = rec.content
            with c2:
                if st.button("Delete", key=f"del_{rec.message_id}", use_container_width=True):
                    ok, detail = delete_message(rec.webhook_url, rec.message_id)
                    st.session_state.status = detail
                    st.session_state.status_ok = ok
                    _log(detail, ok)
                    if ok:
                        forget_sent(st.session_state.sent_messages, rec.message_id)
            st.divider()

        if st.session_state.editing_id:
            editing = next(
                (m for m in st.session_state.sent_messages if m.message_id == st.session_state.editing_id),
                None,
            )
            if editing:
                st.markdown("**Edit message**")
                draft = st.text_area(
                    "New content",
                    value=st.session_state.edit_draft,
                    key="edit_draft_area",
                    height=100,
                )
                s1, s2 = st.columns(2)
                with s1:
                    if st.button("Save edit", use_container_width=True):
                        ok, detail = edit_message(editing.webhook_url, editing.message_id, draft)
                        st.session_state.status = detail
                        st.session_state.status_ok = ok
                        _log(detail, ok)
                        if ok:
                            update_sent_content(st.session_state.sent_messages, editing.message_id, draft)
                            st.session_state.editing_id = None
                with s2:
                    if st.button("Cancel edit", use_container_width=True):
                        st.session_state.editing_id = None

# Activity log
with st.expander("Transmission log", expanded=False):
    if not st.session_state.log:
        st.markdown('<div class="log-line">No events yet.</div>', unsafe_allow_html=True)
    else:
        for stamp, line, ok in st.session_state.log:
            css = "ok" if ok is True else "err" if ok is False else ""
            st.markdown(f'<div class="log-line {css}">[{stamp}] {line}</div>', unsafe_allow_html=True)
