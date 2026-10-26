"""The crisis gate: screens a MINOR's message before any generation, records an alert and tells the
people responsible (spec 009 US2, FR-011..FR-015, research R6/R7).

`app/crisis.py` decides WHETHER a message is a crisis (pure functions, no I/O). This module is the
wiring: who gets screened, which model may read a minor's text, what is stored, who is emailed.

Rules this module holds:
  * Adults are never touched: `screen_message` returns None before reading the text.
  * A minor's text goes to no LLM provider unless the operator named one for minors in
    CHAVRUTA_MINOR_LLM_PRESET (+ CHAVRUTA_MINOR_LLM_API_KEY). Unset, unknown, keyless, or hosted on
    Nebius (not approved for minors, Services Agreement 4.1.6) means the phrase layer ONLY. It never
    falls back to the default backend.
  * A classifier failure means "answer normally" (the answer path is gated separately) and a log line
    that carries no message text.
  * The alert row and the emails never contain the message or the student's age. Delivery runs in a
    background thread with retries and never raises into the request.
"""

from __future__ import annotations

import html
import logging
import os
import threading
import time
from typing import Any, Callable, Optional

import app.db as db
from app import crisis, minors, orgs

_log = logging.getLogger("chavruta.crisis")

# Text appended to the typed question by api._augment_question: the student's own words end before it.
_ATTACHMENT_MARKERS = ("\n\n## מקורות שצירף המשתמש", "\n\n## Sources the user attached")

_RETRY_DELAYS_S = (0.0, 5.0, 30.0)     # three attempts per recipient; patched to zero in tests
_NOT_APPROVED_HOSTS = ("nebius",)       # providers that must never read a minor's text
_classifier_note_logged = False


def typed_part(text: str) -> str:
    """Only what the student typed: attached sources are other people's text, not a disclosure."""
    cut = len(text)
    for marker in _ATTACHMENT_MARKERS:
        i = text.find(marker)
        if i != -1:
            cut = min(cut, i)
    return text[:cut]


# ── the classifier model (optional, minor-approved only) ──────────────────────────
def _note_classifier_disabled(reason: str) -> None:
    global _classifier_note_logged
    if not _classifier_note_logged:
        _classifier_note_logged = True
        _log.info("crisis classifier disabled (%s): minors are screened by the phrase layer only", reason)


def _classifier_call() -> Optional[Callable[[str], str]]:
    """`llm_call(prompt) -> str` for the minors-approved preset, or None for phrase-layer-only."""
    name = os.environ.get("CHAVRUTA_MINOR_LLM_PRESET", "").strip()
    if not name:
        _note_classifier_disabled("CHAVRUTA_MINOR_LLM_PRESET not set")
        return None
    try:
        from chavruta.llm.cloud import CloudLLM
        from chavruta.llm.presets import resolve

        preset = resolve(name)
        key = os.environ.get("CHAVRUTA_MINOR_LLM_API_KEY", "").strip()
        if preset is None or not key:
            _note_classifier_disabled("preset unknown or no CHAVRUTA_MINOR_LLM_API_KEY")
            return None
        if any(h in preset.base_url.lower() for h in _NOT_APPROVED_HOSTS):
            _note_classifier_disabled("preset is hosted by a provider not approved for minors")
            return None
        llm = CloudLLM(preset.model, preset.base_url, key, timeout_s=10.0, max_retries=0,
                       min_output_tokens=preset.min_output_tokens)

        def call(prompt: str) -> str:
            choice, _usage = llm._complete([{"role": "user", "content": prompt}], max_tokens=200,
                                           temperature=0.0, what="crisis_screen")
            return (choice.message.content or "") if choice and choice.message else ""

        return call
    except Exception:
        _note_classifier_disabled("preset could not be built")
        return None


# ── the gate ──────────────────────────────────────────────────────────────────────
def screen_message(owner_id: str, text: str, lang: str = "he") -> Optional[dict[str, Any]]:
    """The crisis payload to return INSTEAD of an answer, or None to proceed normally.

    Never raises. For a positive screen it also stores the alert row and queues the emails."""
    try:
        if not owner_id or not minors.is_minor(owner_id):
            return None
        said = typed_part(text or "")
        if not said.strip():
            return None
        outcome = crisis.check(said, _classifier_call())
        if outcome is crisis.SCREEN_UNAVAILABLE:
            _log.warning("%s owner=%s", crisis.SCREEN_UNAVAILABLE_TAG, owner_id)   # no text, ever
            return None
        if not outcome:
            return None
        _record_and_dispatch(owner_id, outcome)
        return crisis.crisis_reply(outcome, lang)
    except Exception:
        _log.exception("crisis gate failed; proceeding without a screen result")
        return None


def _record_and_dispatch(owner_id: str, result: crisis.CrisisResult) -> None:
    try:
        m = orgs.membership(owner_id)
        org_id = m["org_id"] if m else None
        with db._tx(db.get_conn()) as conn:
            alert_id = conn.execute(
                "INSERT INTO crisis_alerts (owner_id, org_id, category, immediate_danger, detector, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (owner_id, org_id, result.category, int(result.immediate_danger), result.detector,
                 db._now())).lastrowid
    except Exception:
        _log.exception("could not store crisis alert (category=%s)", result.category)
        return
    _spawn(lambda: _deliver(alert_id, owner_id, org_id, result.category,
                            result.immediate_danger))


def _spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="crisis-alert", daemon=True).start()


# ── delivery ──────────────────────────────────────────────────────────────────────
def _operator_ids() -> list[str]:
    raw = os.environ.get("CHAVRUTA_ADMIN_OWNERS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]


def _email_for(owner_id: str) -> Optional[str]:
    """The account's address, from Supabase's admin API (same credentials marketing.py uses)."""
    from app import marketing

    admin = marketing._admin_headers()
    if admin is None:
        return None
    import json
    import urllib.request

    url, headers = admin
    req = urllib.request.Request(f"{url}/auth/v1/admin/users/{owner_id}", headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        email = (json.loads(resp.read()).get("email") or "").strip()
    return email if "@" in email else None


def _send(to: str, subject: str, body_html: str, body_text: str) -> bool:
    from app.email_pool import pool

    ok, _provider = pool.send(to, subject, body_html, body_text)
    return ok


def _site_url() -> str:
    return os.environ.get("CHAVRUTA_PUBLIC_URL", "https://chavrutaai.org").rstrip("/")


_CATEGORY_HE = {"suicide": "מחשבות אובדניות", "self_harm": "פגיעה עצמית",
                "abuse": "פגיעה או התעללות", "danger": "סכנה"}


def _compose(owner_id: str, category: str, immediate: bool, created_at: str, link: str) -> tuple[str, str, str]:
    cat = _CATEGORY_HE.get(category, category)
    urgent = "כן - לפנות מיד" if immediate else "לא"
    subject = "התראת בטיחות בחברותא" + (" (דחוף)" if immediate else "")
    lines = [
        "זוהתה פנייה של תלמיד/ה שדורשת תשומת לב.",
        f"תלמיד/ה: {owner_id}",
        f"זמן: {created_at}",
        f"סוג: {cat}",
        f"סכנה מיידית: {urgent}",
        f"לצפייה ולאישור קבלה: {link}",
        "ההודעה עצמה אינה נשמרת ואינה נשלחת במייל. התלמיד/ה קיבל/ה הודעת תמיכה ומספרי סיוע.",
    ]
    text = "\n".join(lines)
    body_html = ('<div dir="rtl" style="font-family:Arial,sans-serif">'
                 + "".join(f"<p>{html.escape(line)}</p>" for line in lines[:-2])
                 + f'<p><a href="{html.escape(link)}">{html.escape(lines[-2].split(": ", 1)[0])}</a></p>'
                 + f"<p>{html.escape(lines[-1])}</p></div>")
    return subject, body_html, text


def _deliver(alert_id: int, owner_id: str, org_id: Optional[str], category: str, immediate: bool) -> None:
    """Email the school's safety contacts (if linked) and the operator. Never raises."""
    try:
        recipients: dict[str, str] = {}      # owner_id -> link
        if org_id:
            for o in orgs.safety_contacts(org_id):
                recipients[o] = f"{_site_url()}/school"
        for o in _operator_ids():
            recipients.setdefault(o, f"{_site_url()}/admin")
        created_at = db._now()
        pending = dict(recipients)
        delivered = 0
        for delay in _RETRY_DELAYS_S:
            if not pending:
                break
            if delay:
                time.sleep(delay)
            for rid, link in list(pending.items()):
                try:
                    to = _email_for(rid)
                    if not to:
                        _log.warning("crisis alert %s: no email for recipient %s", alert_id, rid)
                        pending.pop(rid)       # retrying cannot create an address
                        continue
                    if _send(to, *_compose(owner_id, category, immediate, created_at, link)):
                        pending.pop(rid)
                        delivered += 1
                except Exception as exc:       # noqa: BLE001 - delivery must never raise
                    _log.warning("crisis alert %s: send to %s failed (%s)", alert_id, rid, type(exc).__name__)
        if delivered:
            with db._tx(db.get_conn()) as conn:
                conn.execute("UPDATE crisis_alerts SET delivered_at=? WHERE id=?", (db._now(), alert_id))
        else:
            _log.error("crisis alert %s was NOT delivered to anyone", alert_id)
    except Exception:
        _log.exception("crisis alert %s delivery crashed", alert_id)
