import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable

from app.config.categories import ReviewCategory


@dataclass
class ClassificationResult:
    category: ReviewCategory
    reasons: list[str]


class ReviewClassifier:
    def __init__(self, rules_path: str):
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        with self.rules_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _norm(value: Any) -> str:
        return (value or "").strip().lower()

    @staticmethod
    def _contains_any(text: str, patterns: Iterable[str]) -> bool:
        return any(re.search(re.escape(p), text, re.IGNORECASE) for p in patterns)

    def classify(self, review: Dict[str, Any]) -> ClassificationResult:
        text = self._norm(review.get("text"))
        stars = int(review.get("productValuation") or review.get("valuation") or 0)
        bables = review.get("bables") or review.get("aspects") or review.get("tags") or []
        bables_text = self._norm(" ".join(map(str, bables)))
        full_text = f"{text} {bables_text}".strip()

        rules = self.rules
        kw = rules["keywords"]
        short_max = int(rules.get("short_review_max_len", 18))

        # 1) empty
        if not text:
            return ClassificationResult(ReviewCategory.EMPTY_REVIEW, ["empty_text"])

        # 2) short nonspecific
        if len(text) <= short_max and not any(
            self._contains_any(full_text, kw[k])
            for k in ("quality", "size", "packaging", "delivery_condition", "expectation_mismatch")
        ):
            return ClassificationResult(ReviewCategory.SHORT_NONSPECIFIC, ["short_without_specific_issue"])

        # 3) specific negatives by topic
        if self._contains_any(full_text, kw["size"]):
            return ClassificationResult(ReviewCategory.NEGATIVE_SIZE, ["size_keywords"])

        if self._contains_any(full_text, kw["quality"]):
            return ClassificationResult(ReviewCategory.NEGATIVE_QUALITY, ["quality_keywords"])

        if self._contains_any(full_text, kw["packaging"]):
            return ClassificationResult(ReviewCategory.NEGATIVE_PACKAGING, ["packaging_keywords"])

        if self._contains_any(full_text, kw["delivery_condition"]):
            return ClassificationResult(ReviewCategory.NEGATIVE_DELIVERY_CONDITION, ["delivery_condition_keywords"])

        if self._contains_any(full_text, kw["expectation_mismatch"]):
            return ClassificationResult(ReviewCategory.EXPECTATION_MISMATCH, ["expectation_mismatch_keywords"])

        # 4) sentiment-ish fallback by stars + generic signals
        has_negative_signal = self._contains_any(full_text, kw["negative_signal"])
        has_positive_signal = self._contains_any(full_text, kw["positive_signal"])

        if stars in rules.get("negative_stars", [1, 2]) or has_negative_signal:
            return ClassificationResult(ReviewCategory.NEUTRAL, ["negative_or_low_star_without_topic"])

        if stars == 5 and not has_negative_signal:
            return ClassificationResult(ReviewCategory.POSITIVE_NO_ISSUE, ["high_star_no_issue_keywords"])

        if stars == 4 and has_positive_signal:
            return ClassificationResult(ReviewCategory.POSITIVE_WITH_NOTE, ["4_star_positive_signal"])

        if stars in rules.get("neutral_stars", [3]):
            return ClassificationResult(ReviewCategory.NEUTRAL, ["neutral_star"])

        # default
        return ClassificationResult(ReviewCategory.POSITIVE_WITH_NOTE, ["fallback"])
