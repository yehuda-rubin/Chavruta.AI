"""LLM query planner (Phase 5, spec 002-query-understanding) — OPTIONAL, flag-gated.

The heuristic router is fast, offline, and deterministic, but it cannot resolve every
indirect phrasing. When `CHAVRUTA_QUERY_PLANNER=llm`, this planner runs as a *fallback*
(only when the heuristics found no explicit ref): one cheap LLM call extracts structured
hints — refs, commentators, intent — as JSON, which the router merges in. Default off, so
the offline/deterministic path (Principle II) is unchanged unless explicitly enabled.
"""

from __future__ import annotations

import json
import re

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_SYSTEM = (
    "You extract structured retrieval hints from a Jewish-texts study question. "
    "Return ONLY a JSON object with keys: "
    '"refs" (list of canonical Sefaria refs in dotted form, e.g. "Genesis.1.1", '
    '"Bava_Metzia.2a"; resolve indirect references like "the first verse of the Torah" '
    '→ "Genesis.1.1"), "commentators" (list of ids from: rashi, ramban, ibn_ezra, radak, '
    "sforno, rashbam, or_hachaim, malbim, onkelos), and "
    '"intent" (one of: qa, explain, compare, lesson). Use [] when unsure. No prose.'
)


class LLMQueryPlanner:
    def __init__(self, model_id: str, base_url: str, api_key: str):
        self.model_id = model_id
        self.base_url = base_url
        self.api_key = api_key
        self._client = None  # lazy

    def _client_(self):
        if self._client is None:
            from openai import OpenAI  # lazy
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def plan(self, text: str) -> dict:
        """Return {"refs": [...], "commentators": [...], "intent": str|None}.

        Never raises — on any failure returns empty hints so the request falls back to
        the heuristic result.
        """
        try:
            resp = self._client_().chat.completions.create(
                model=self.model_id,
                messages=[{"role": "system", "content": _SYSTEM},
                          {"role": "user", "content": text}],
                temperature=0.0,
                max_tokens=256,
            )
            return _parse(resp.choices[0].message.content or "")
        except Exception:
            return {"refs": [], "commentators": [], "intent": None}


def _parse(raw: str) -> dict:
    m = _JSON_RE.search(raw)
    if not m:
        return {"refs": [], "commentators": [], "intent": None}
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return {"refs": [], "commentators": [], "intent": None}
    refs = [str(r) for r in data.get("refs", []) if isinstance(r, str)]
    comms = [str(c) for c in data.get("commentators", []) if isinstance(c, str)]
    intent = data.get("intent") if isinstance(data.get("intent"), str) else None
    return {"refs": refs, "commentators": comms, "intent": intent}


from dataclasses import dataclass, field


@dataclass
class DistillerResult:
    action: str  # "chitchat" | "study"
    answer: str = ""  # direct answer if chitchat (codes stripped)
    distilled_query: str = ""  # cleaned search query if study (codes stripped)
    requested_files: list[str] = field(default_factory=list)  # e.g. ["sources", "flow"]
    raw: str = ""  # raw model output


DISTILLER_MODEL = "google/gemma-3-27b-it"

_CONTROL_CODES_MAP = {
    "ZZZ": ["sources", "flow", "full"],
    "XXX": ["sources"],
    "YYY": ["flow"],
    "WWW": ["full"],
    "PPP": ["pdf"],
    "NNN": [],
}

_ALL_CONTROL_CODES = ("HHH", "ZZZ", "XXX", "YYY", "WWW", "PPP", "NNN")

_CONTROL_CODES_PREFIX_RE = re.compile(
    r"^(?:\[?(?:HHH|ZZZ|XXX|YYY|WWW|PPP|NNN)\]?[\s:\-]*)+",
    re.IGNORECASE,
)


def strip_control_codes(text: str) -> str:
    """Completely hide/strip internal routing and file control codes from user-facing text."""
    if not text:
        return ""
    clean = _CONTROL_CODES_PREFIX_RE.sub("", text.strip()).strip()
    return clean


_HALACHIC_INTERROGATIVE_KEYWORDS = {
    "מותר", "אסור", "הלכה", "הלכתי", "הלכתית", "דין", "דינים", "חזיר", "כיפור", "פסח", "שבת",
    "כשר", "כשרות", "תפילה", "ברכה", "ברכות", "מצווה", "מצוות", "חג", "חגים", "צדק", "טעה",
    "שאלתי", "הרב", "רב", "פוסק", "פוסקים", "גמרא", "משנה", "תורה", "רש\"י", "רמב\"ם", "שו\"ע",
}


def parse_distiller_output(raw: str, original_query: str) -> DistillerResult:
    """Parse the distiller output into action, answer, query, and requested files."""
    clean = (raw or "").strip()
    if not clean:
        return DistillerResult(action="study", distilled_query=original_query, raw=raw)

    orig_clean = " ".join((original_query or "").strip().split())
    orig_words = [w.strip("?!.,;:-\"'״`()").lower() for w in orig_clean.split()]

    # Check for HHH (Chitchat / Idle / Greeting / Thanks)
    first_token = clean.split()[0].strip("[]:-,. ").upper() if clean.split() else ""
    if first_token == "HHH":
        # SAFETY NET: Only override HHH to study if the user's input actually contains
        # explicit halachic/Torah inquiry keywords (e.g. מותר, אסור, חזיר, כיפור, שבת, כשר, הלכה, דין, רב...).
        # Casual non-Torah questions (e.g. "אתה אוהב שוקולד?", "מה שלומך?", "איך קוראים לך?") remain HHH!
        has_halachic_kw = any(w in _HALACHIC_INTERROGATIVE_KEYWORDS for w in orig_words)
        if has_halachic_kw:
            return DistillerResult(action="study", distilled_query=original_query, raw=raw)

        answer = strip_control_codes(clean)
        return DistillerResult(action="chitchat", answer=answer, raw=raw)

    # Check for file codes (single or multiple space-separated, e.g. "XXX YYY")
    words = clean.split()
    requested_files: list[str] = []
    idx = 0
    while idx < len(words):
        token = words[idx].strip("[]:-,. ").upper()
        if token in _CONTROL_CODES_MAP:
            for f in _CONTROL_CODES_MAP[token]:
                if f not in requested_files:
                    requested_files.append(f)
            idx += 1
        else:
            break

    remaining_query = " ".join(words[idx:]).strip()
    distilled = strip_control_codes(remaining_query) if remaining_query else original_query
    return DistillerResult(
        action="study",
        distilled_query=distilled if distilled else original_query,
        requested_files=requested_files,
        raw=raw,
    )


_DISTILL_SYSTEM = (
    "You are the query classifier, router, and distiller for Chavruta (Torah study partner).\n"
    "Analyze the user's input (and conversation history if present) and output strictly in this protocol:\n\n"
    "1. IDLE / CHITCHAT / GREETING / THANKS (שאלת סרק, תודה, ברכה, פרידה):\n"
    "CRITICAL: Use HHH ONLY for pure greetings ('שלום', 'מה נשמע'), pure thanks ('תודה רבה לך', 'יישר כוח'), or casual pleasantries that contain NO question about Torah, Halacha, mitzvot, or Jewish practice.\n"
    "NEVER use HHH if the user asks a halachic or Torah question, asks whether something is permitted/forbidden (מותר/אסור), asks if someone was right/wrong (צדק/טעה) about a religious matter, or tells a personal story/memory that ends in a question.\n"
    "Start with code HHH followed by a short, warm, polite response in Hebrew.\n\n"
    "2. TORAH / HALACHA / STUDY QUERY:\n"
    "Start with the file generation code(s):\n"
    "- NNN: ללא קבצים (תשובה טקסטואלית רגילה)\n"
    "- ZZZ: כל הקבצים (שיעור מלא: דף מקורות + מהלך השיעור + שיעור מלא)\n"
    "- XXX: דף מקורות בלבד\n"
    "- YYY: מהלך השיעור בלבד\n"
    "- WWW: השיעור המלא בלבד\n"
    "- PPP: חוברת ליווי להדפסה ו-PDF\n"
    "If the user asks for a combination of two or more files, write their codes separated by space (e.g. 'XXX YYY').\n"
    "After the file code(s), write the single distilled core question/topic in Hebrew in 1 concise sentence.\n\n"
    "Examples:\n"
    "- 'תודה רבה לך' -> HHH בשמחה רבה! תמיד כאן לכל שאלה ולימוד.\n"
    "- 'שלום מה נשמע?' -> HHH שלום וברכה! הכול מצוין, ברוך השם. במה נוכל להעמיק היום?\n"
    "- 'לפני כמה שנים שהייתי ילד שאלתי את הרב האם מותר לי לאכול ביום כיפור בשר חזיר והוא ענה לי לא הוא צדק?' -> NNN איסור אכילת חזיר ואיסור אכילה ביום כיפור\n"
    "- 'האם מותר לאכול חזיר בפסח?' -> NNN איסור אכילת חזיר בפסח\n"
    "- 'תכין לי רק דף מקורות על הלכות שבת' -> XXX הלכות שבת\n"
    "- 'אני רוצה דף מקורות ומהלך שיעור על תפילה' -> XXX YYY סוגיית תפילה\n"
    "- 'תכין לי שיעור שלם על תנורו של עכנאי' -> ZZZ סוגיית תנורו של עכנאי\n"
    "- 'תודה, אבל מה המקור לדין הזה?' -> NNN מקור להלכה שנדונה\n"
)

_INDIRECT_PREFIXES = (
    "שלום", "היי", "בוקר טוב", "ערב טוב", "שלום עליכם", "תגיד", "תגידי",
    "רציתי לשאול", "יש לי שאלה", "שלום רב", "שלום כבוד הרב",
    "אני רוצה לדעת", "אני רוצה", "רציתי לדעת", "אשמח לדעת", "תוכל להסביר", "תוכל לומר",
    "תוכל", "תוכלי", "אפשר לשאול", "תעזור לי", "בבקשה תסביר",
    "hello", "hi", "hey", "can you tell me", "i have a question", "please tell me",
    "i want to know", "could you explain",
)


def _is_short_and_direct(text: str, history=None) -> bool:
    from chavruta.intents.router import is_conversational_acknowledgement
    clean = text.strip()
    if is_conversational_acknowledgement(clean):
        return True
    words = clean.split()
    if not words or len(words) > 10:
        return False
    low = clean.lower()
    for prefix in _INDIRECT_PREFIXES:
        if low.startswith(prefix):
            return False
    if history and len(words) <= 6:
        return False
    return True


def classify_and_distill(
    text: str, history=None, intent=None, *, client=None, model: str = DISTILLER_MODEL
) -> DistillerResult:
    """Classify user intent, determine file generation codes, and distill question in Hebrew."""
    if not text or not text.strip():
        return DistillerResult(action="study", distilled_query="", raw="")
    clean = text.strip()

    from chavruta.intents.router import is_pure_greeting, is_conversational_acknowledgement
    if is_pure_greeting(clean):
        return DistillerResult(
            action="chitchat",
            answer="שלום וברכה! אני חברותא — שותף הלימוד שלך. במה נוכל להעמיק היום? אפשר לעיין בסוגיה, ללמוד משנה או גמרא עם מפרשים, או לברר שאלה הלכתית.",
            raw="HHH",
        )
    if is_conversational_acknowledgement(clean):
        if any(w in clean for w in ("צדק", "צדקתי", "אגיד לו", "אומר לו", "אספר לו", "אעדכן")):
            ack = "בשמחה רבה! שמחתי לעזור ולברר את הדברים. שיהיה בהצלחה בדיון! תמיד כאן בשמחה לכל שאלה, לימוד סוגיה או בירור הלכתי נוסף."
        else:
            ack = "בשמחה רבה! תמיד כאן לעזרתך לכל שאלה, לימוד סוגיה או בירור הלכתי נוסף."
        return DistillerResult(action="chitchat", answer=ack, raw="HHH")

    if _is_short_and_direct(clean, history=history):
        return DistillerResult(action="study", distilled_query=clean, raw=clean)

    from chavruta.llm import metering

    messages = [{"role": "system", "content": _DISTILL_SYSTEM}]
    if history:
        prior_lines = []
        for h in history[-4:]:
            role = getattr(h, "role", "user")
            t = (getattr(h, "text", "") or "").strip()
            if t:
                prior_lines.append(f"{role}: {t}")
        if prior_lines:
            messages.append({
                "role": "user",
                "content": f"הקשר מהשיחה הקודמת:\n" + "\n".join(prior_lines) + f"\n\nבקשת המשתמש:\n{clean}"
            })
        else:
            messages.append({"role": "user", "content": clean})
    else:
        messages.append({"role": "user", "content": clean})

    try:
        if client is None:
            import os
            from openai import OpenAI
            api_key = os.environ.get("CHAVRUTA_LLM_API_KEY") or os.environ.get("NEBIUS_API_KEY") or ""
            if not api_key:
                return DistillerResult(action="study", distilled_query=clean, raw=clean)
            base_url = (os.environ.get("CHAVRUTA_LLM_BASE_URL") or
                        os.environ.get("NEBIUS_BASE_URL") or
                        "https://api.studio.nebius.ai/v1")
            client = OpenAI(base_url=base_url, api_key=api_key, timeout=15.0, max_retries=1)

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=80,
        )
        usage = getattr(resp, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        metering.record(prompt_tokens, completion_tokens, model=model)
        content = (resp.choices[0].message.content or "").strip()
        return parse_distiller_output(content, original_query=clean)
    except Exception:
        return DistillerResult(action="study", distilled_query=clean, raw=clean)


def distill_query(
    text: str, history=None, intent=None, *, client=None, model: str = DISTILLER_MODEL
) -> str:
    res = classify_and_distill(text, history=history, intent=intent, client=client, model=model)
    return res.distilled_query if res.action == "study" else text


# ── Lesson Follow-up Intent & File Edit Classifier ───────────────────────────

from typing import Literal
from pydantic import BaseModel


class LessonFollowupDecision(BaseModel):
    action: Literal["chat", "edit_file", "rebuild_all"]
    target_file: Literal["flow", "full", "sources"] | None = None
    topic: str = ""
    instruction: str = ""


_FOLLOWUP_CLASSIFIER_SYSTEM = (
    "You are an expert Torah lesson assistant that classifies user follow-up requests after a lesson was generated.\n"
    "The lesson has 3 files:\n"
    "- 'flow': מהלך השיעור (Lesson Flow / outline / stages / schedule / time breakdown)\n"
    "- 'full': השיעור המלא (Full Lesson text / complete shiur in depth)\n"
    "- 'sources': דף המקורות (Source Sheet)\n\n"
    "Analyze the user's message in the context of the previous lesson and classify into JSON:\n"
    "1. action: 'chat' (if asking a discussion/explanatory/clarifying question about the lesson or topic),\n"
    "          'edit_file' (if asking to change, update, add, shorten, or modify a specific file or part of the lesson),\n"
    "          'rebuild_all' (if asking to rebuild the whole lesson from scratch, e.g. 'תכין את השיעור מחדש', 'שיעור חדש', 'בנה שיעור אחר').\n"
    "2. target_file: 'flow' | 'full' | 'sources' | null (only when action is 'edit_file', else null).\n"
    "3. topic: The core Torah topic of the lesson recovered from context (e.g. 'דיני ממונות בשלושה', 'הלכות סוכה'). Do NOT put 'תכין מחדש' or commands as topic.\n"
    "4. instruction: The user's specific edit instruction or question in concise Hebrew.\n\n"
    "Return ONLY valid JSON matching this schema with no extra prose:\n"
    '{"action": "chat"|"edit_file"|"rebuild_all", "target_file": "flow"|"full"|"sources"|null, "topic": "...", "instruction": "..."}'
)


def _heuristic_fallback_classify(
    question: str, history=None, last_lesson_topic: str = ""
) -> LessonFollowupDecision:
    """Deterministic fallback classifier when LLM is offline or unavailable."""
    q_low = (question or "").lower().strip()
    
    # Check for target file keywords
    target_file = None
    if any(k in q_low for k in ["מהלך", "מערך", "flow", "שלב", "לוח זמנים", "פתיחה", "סיום", "זמנים"]):
        target_file = "flow"
    elif any(k in q_low for k in ["שיעור מלא", "השיעור המלא", "שיעור המלא", "גוף השיעור", "full lesson", "full_lesson", "פרוזה"]):
        target_file = "full"
    elif any(k in q_low for k in ["מקורות", "דף מקורות", "דף המקורות", "source sheet", "sourcesheet"]):
        target_file = "sources"

    # Action detection
    rebuild_keywords = ["מחדש", "שיעור חדש", "שיעור נוסף", "בנה מחדש", "הכן מחדש", "new lesson", "redo"]
    edit_keywords = ["שנה", "תשנה", "עדכן", "תעדכן", "הוסף", "תוסיף", "תקצר", "קצר", "תרחיב", "הרחב", "ערוך", "תערוך", "change", "shorten", "expand", "edit", "update"]

    # Recover topic
    topic = last_lesson_topic.strip()
    if not topic and history:
        for h in history:
            txt = (getattr(h, "text", "") or "").strip()
            if txt and len(txt.split()) > 2 and not any(cmd in txt for cmd in ["תכין", "שנה", "שיעור"]):
                topic = txt
                break
    if not topic:
        topic = question.strip()

    if target_file and any(k in q_low for k in edit_keywords):
        return LessonFollowupDecision(action="edit_file", target_file=target_file, topic=topic, instruction=question)
    if any(k in q_low for k in rebuild_keywords):
        return LessonFollowupDecision(action="rebuild_all", target_file=None, topic=topic, instruction=question)
    if target_file:
        return LessonFollowupDecision(action="edit_file", target_file=target_file, topic=topic, instruction=question)

    return LessonFollowupDecision(action="chat", target_file=None, topic=topic, instruction=question)


def classify_lesson_followup(
    question: str,
    history=None,
    last_lesson_topic: str = "",
    *,
    client=None,
    model: str = DISTILLER_MODEL,
) -> LessonFollowupDecision:
    """Classify a user follow-up turn in a lesson session using google/gemma-3-27b-it.

    Decides between:
    - 'chat': Question or discussion about the current lesson -> route to Chavruta chat
    - 'edit_file': Request to update a specific file ('flow'|'full'|'sources') -> single-file edit
    - 'rebuild_all': Request to regenerate the lesson from scratch -> rebuild with recovered topic
    """
    if not question or not question.strip():
        return LessonFollowupDecision(action="chat", target_file=None, topic=last_lesson_topic, instruction="")

    clean = question.strip()

    # Build context from history
    context_lines = []
    if last_lesson_topic:
        context_lines.append(f"נושא השיעור שנבנה: {last_lesson_topic}")
    if history:
        for h in history[-4:]:
            role = getattr(h, "role", "user")
            t = (getattr(h, "text", "") or "").strip()
            if t:
                # Truncate long lesson texts for classification efficiency
                snippet = t[:200] + "..." if len(t) > 200 else t
                context_lines.append(f"{role}: {snippet}")

    user_prompt = f"הקשר מהשיחה:\n" + "\n".join(context_lines) + f"\n\nבקשת המשתמש הנוכחית:\n{clean}"
    messages = [
        {"role": "system", "content": _FOLLOWUP_CLASSIFIER_SYSTEM},
        {"role": "user", "content": user_prompt},
    ]

    try:
        if client is None:
            import os
            from openai import OpenAI
            api_key = os.environ.get("CHAVRUTA_LLM_API_KEY") or os.environ.get("NEBIUS_API_KEY") or ""
            if not api_key:
                return _heuristic_fallback_classify(clean, history=history, last_lesson_topic=last_lesson_topic)
            base_url = (os.environ.get("CHAVRUTA_LLM_BASE_URL") or
                        os.environ.get("NEBIUS_BASE_URL") or
                        "https://api.studio.nebius.ai/v1")
            client = OpenAI(base_url=base_url, api_key=api_key, timeout=15.0, max_retries=1)

        from chavruta.llm import metering

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=128,
        )
        usage = getattr(resp, "usage", None)
        p_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        c_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        metering.record(p_tokens, c_tokens, model=model)

        raw = (resp.choices[0].message.content or "").strip()
        # Parse JSON
        m = _JSON_RE.search(raw)
        if m:
            data = json.loads(m.group(0))
            action = data.get("action")
            if action in ("chat", "edit_file", "rebuild_all"):
                tf = data.get("target_file")
                if tf not in ("flow", "full", "sources"):
                    tf = None
                topic = (data.get("topic") or "").strip() or last_lesson_topic or clean
                instruction = (data.get("instruction") or "").strip() or clean
                return LessonFollowupDecision(
                    action=action,
                    target_file=tf,
                    topic=topic,
                    instruction=instruction,
                )
        return _heuristic_fallback_classify(clean, history=history, last_lesson_topic=last_lesson_topic)
    except Exception:
        return _heuristic_fallback_classify(clean, history=history, last_lesson_topic=last_lesson_topic)
