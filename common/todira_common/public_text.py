"""What an ad's own text may show (2026-10-19, owner): the only way to reach a poster is through Todira (a trial or a
paid pass), so the text we show never carries who posted it, a phone number, a WhatsApp/e-mail contact or a link.
Used for every card (Telegram) and every listing on the site, whatever the source; the stored text is left as it was."""
from __future__ import annotations

import re

# 050-1234567, 0501234567, 054 748 2445, +972-54-..., 03-1234567, 972541234567
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?972[\s\-.]?|0)(?:[23489]|5\d|7\d)(?:[\s\-.]?\d){7}(?!\d)"
)
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.\-]+")
_LINK_RE = re.compile(r"(?:https?://|www\.)\S+|(?<![\w.])(?:wa\.me|m\.me|t\.me|fb\.me)/\S*", re.IGNORECASE)
# "(מפרסם/ת: ...)" - the poster's name we used to add to group posts.
_POSTER_RE = re.compile(r"\(\s*מפרסם/ת:[^)\n]*\)")
# A short line that only invites contact ("לפרטים נוספים:", "ליצירת קשר", "טלפון:") is left empty once the number is gone.
_CONTACT_PROMPT_RE = re.compile(
    r"^[\W_]*(?:ל?פרטים(?:\s+נוספים)?|ליצירת\s+קשר|לתיאום(?:\s+צפייה)?|לתאום(?:\s+צפייה)?|צרו\s+קשר|צור\s+קשר|"
    r"טל['׳]?|טלפון|נייד|פלאפון|וואטסאפ|ווטסאפ|ווצאפ|whatsapp|לשאלות|להתקשר|התקשרו|בטלפון|במספר)"
    r"(?:\s+(?:ו?ל?תיאום|בטלפון|ב?וואטסאפ|ב?ווטסאפ|צפייה|נוספים|ב?הודעה|בפרטי))*[\s:.\-–!]*$",
    re.IGNORECASE,
)
# A line that held a phone number and is short (a name next to the number, "נגה-", "📲 שליו אדרי") goes completely.
_SHORT_CONTACT_LINE = 40


def public_description(text: str | None) -> str:
    """`text` without the poster's name, phone numbers, e-mails, links and the lines that only carried them."""
    if not text:
        return ""
    text = _POSTER_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    kept: list[str] = []
    for line in text.split("\n"):
        had_contact = bool(_PHONE_RE.search(line) or _EMAIL_RE.search(line) or _LINK_RE.search(line))
        cleaned = _LINK_RE.sub("", _EMAIL_RE.sub("", _PHONE_RE.sub("", line)))
        if had_contact:
            rest = re.sub(r"[\W_]+", " ", cleaned).strip()
            if len(rest) <= _SHORT_CONTACT_LINE:
                continue
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        if _CONTACT_PROMPT_RE.match(cleaned.strip()):
            continue
        kept.append(cleaned.rstrip())
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


# "חדר בדירת שותפים", "מתפנה חדר בדירת 4 חדרים", "חדר להשכרה", "מחפשים שותפה": one room, not a whole flat.
_SHARED_ROOM_RE = re.compile(
    r"(?<![א-ת])(?:חדר\s+(?:פנוי\s+|יפה\s+|גדול\s+|מרווח\s+|מרוהט\s+)?(?:ב?דירת\s+שותפ|בדירה\s+משותפת|להשכרה\s+בדירה|"
    r"בדירה\s+של)|מתפנה\s+חדר|מתפנה\s+לי\s+חדר|מפנה\s+(?:את\s+)?(?:ה)?חדר|(?:מחפש|מחפשת|מחפשים|מחפשות)\s+"
    r"(?:שותף|שותפה|שותפים|שותפות|מחליף|מחליפה)|דירת\s+שותפים|דירת\s+שותפות)"
)


def is_room_in_shared_flat(text: str | None) -> bool:
    """True when an ad offers one room in a shared flat rather than a whole flat."""
    return bool(text) and bool(_SHARED_ROOM_RE.search(text[:600]))
