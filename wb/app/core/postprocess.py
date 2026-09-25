import hashlib
import re
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict

from dateutil import parser

SIGNATURE = "С уважением, команда JE LA PECHE."

SHORT_THANKS_VARIANTS = [
    "Спасибо за высокую оценку! Нам очень приятно, что Вы остались довольны покупкой.",
    "Благодарим за Вашу отличную оценку. Рады, что товар оправдал ожидания!",
    "Спасибо за 5★! Будем рады видеть Вас снова.",
    "Спасибо, что поделились впечатлением! Для нас очень ценно Ваше доверие.",
    "Благодарим за выбор нашего бренда и Вашу поддержку!"
]


class RepetitionGuard:
    def __init__(self, max_items: int = 200):
        self._recent: Deque[str] = deque(maxlen=max_items)

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def is_too_similar(self, text: str) -> bool:
        norm = self._normalize(text)
        if not norm:
            return False
        for prev in self._recent:
            # простой и быстрый анти-дубль: полный матч или почти полный префикс
            if norm == prev or norm[:120] == prev[:120]:
                return True
        return False

    def remember(self, text: str):
        norm = self._normalize(text)
        if norm:
            self._recent.append(norm)


def greeting_only(dt_str: str) -> str:
    try:
        hour = parser.parse(dt_str).hour
    except Exception:
        hour = datetime.utcnow().hour
    if 1 <= hour <= 8:
        return "Доброе утро!"
    if 9 <= hour <= 14:
        return "Добрый день!"
    if 15 <= hour <= 20:
        return "Добрый вечер!"
    return "Доброй ночи!"


def greeting_with_name(dt_str: str, user_name: str) -> str:
    try:
        hour = parser.parse(dt_str).hour
    except Exception:
        hour = datetime.utcnow().hour
    if 1 <= hour <= 8:
        prefix = "Доброе утро"
    elif 9 <= hour <= 14:
        prefix = "Добрый день"
    elif 15 <= hour <= 20:
        prefix = "Добрый вечер"
    else:
        prefix = "Доброй ночи"
    return f"{prefix}, {user_name}!"


def compose_greeting(created_date: str, raw_name: str) -> str:
    raw_name = (raw_name or "").strip()
    return greeting_with_name(created_date, raw_name) if raw_name else greeting_only(created_date)


def capitalize_formal_you(text: str) -> str:
    repl = {
        r"\bвы\b": "Вы",
        r"\bвам\b": "Вам",
        r"\bвас\b": "Вас",
        r"\bваш\b": "Ваш",
        r"\bваша\b": "Ваша",
        r"\bваши\b": "Ваши",
        r"\bвашем\b": "Вашем",
        r"\bвашим\b": "Вашим",
        r"\bвашей\b": "Вашей",
    }
    out = text
    for pat, to in repl.items():
        out = re.sub(pat, to, out, flags=re.IGNORECASE)
    return out


def ensure_greeting_prefix(text: str, created: str, user_name: str) -> str:
    s = (text or "").strip()
    if re.match(r"^(Доброе утро|Добрый день|Добрый вечер|Доброй ночи)[,! ]", s, flags=re.IGNORECASE):
        return s
    return f"{compose_greeting(created, user_name)}\n\n{s}"


def ensure_signature(text: str) -> str:
    s = (text or "").rstrip()
    s = re.sub(r"С уважением, команда JE LA PECHE\.?\s*$", "", s, flags=re.IGNORECASE).rstrip()
    if s and not s.endswith("."):
        s += "."
    return f"{s}\n\n{SIGNATURE}".strip()


def remove_over_transport_blame(text: str) -> str:
    # Убираем категоричные формулировки в духе "это только из-за доставки"
    patterns = [
        r"это\s+только\s+из-за\s+доставки",
        r"виновата\s+только\s+доставка",
        r"исключительно\s+доставка",
    ]
    out = text
    for p in patterns:
        out = re.sub(p, "это могло произойти на одном из этапов обработки заказа", out, flags=re.IGNORECASE)
    return out


def trim_length(text: str, max_len: int = 900) -> str:
    if len(text) <= max_len:
        return text
    s = text[:max_len].rstrip()
    s = re.sub(r"\s+\S*$", "", s)
    return ensure_signature(s + "…")


def pick_short_thanks(feedback_id: str) -> str:
    h = hashlib.sha1((feedback_id or "").encode("utf-8")).hexdigest()
    idx = int(h[:2], 16) % len(SHORT_THANKS_VARIANTS)
    return SHORT_THANKS_VARIANTS[idx]


def make_short_reply(review: Dict[str, Any]) -> str:
    created = review.get("createdDate") or review.get("createdTs") or review.get("createdAt") or datetime.utcnow().isoformat()
    raw_name = (review.get("userName") or "").strip()
    fid = review.get("id") or review.get("feedbackId") or ""
    greet = compose_greeting(created, raw_name)
    return f"{greet}\n\n{pick_short_thanks(str(fid))}\n\n{SIGNATURE}"


def finalize_reply(raw_text: str, review: Dict[str, Any]) -> str:
    created = review.get("createdDate") or review.get("createdTs") or review.get("createdAt") or datetime.utcnow().isoformat()
    raw_name = (review.get("userName") or "").strip()

    text = ensure_greeting_prefix(raw_text, created, raw_name)
    text = capitalize_formal_you(text)
    text = remove_over_transport_blame(text)
    text = ensure_signature(text)
    text = trim_length(text)
    return text
