import re
from typing import Any, Dict, Tuple

from app.config.categories import ReviewCategory


SEVERE_PATTERNS = [
    r"опасно",
    r"аллерг",
    r"травм",
    r"порез",
    r"кров",
    r"в суд",
    r"претенз",
    r"жалоб",
    r"мошенн",
    r"подделк",
]


def detect_manual_review_need(category: ReviewCategory, review: Dict[str, Any]) -> Tuple[bool, list[str]]:
    text = (review.get("text") or "").strip().lower()
    stars = int(review.get("productValuation") or review.get("valuation") or 0)

    reasons: list[str] = []

    if stars <= 2 and category in {ReviewCategory.NEUTRAL, ReviewCategory.POSITIVE_WITH_NOTE}:
        reasons.append("низкая оценка без явной причины")

    if category in {
        ReviewCategory.NEGATIVE_QUALITY,
        ReviewCategory.NEGATIVE_DELIVERY_CONDITION,
        ReviewCategory.EXPECTATION_MISMATCH,
    } and len(text) > 350:
        reasons.append("длинная негативная претензия")

    for pattern in SEVERE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            reasons.append(f"обнаружено чувствительное слово: {pattern}")
            break

    return (len(reasons) > 0), reasons
