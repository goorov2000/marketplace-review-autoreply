import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict

from app.config.categories import ReviewCategory
from app.core.classifier import ReviewClassifier
from app.core.generator import OpenAIReplyGenerator
from app.core.manual_review import detect_manual_review_need
from app.core.postprocess import RepetitionGuard, finalize_reply, make_short_reply
from app.core.prompting import build_user_prompt, load_json, load_text


@dataclass
class PipelineArtifacts:
    category: ReviewCategory
    reasons: list[str]
    prompt: str
    raw_reply: str
    final_reply: str
    needs_manual_review: bool = False
    manual_reasons: list[str] = field(default_factory=list)


class ReplyPipeline:
    def __init__(
        self,
        classifier: ReviewClassifier,
        generator: OpenAIReplyGenerator,
        scenarios_path: str,
        system_prompt_path: str,
        user_template_path: str,
    ):
        self.classifier = classifier
        self.generator = generator
        self.scenarios = load_json(scenarios_path)
        self.system_prompt = load_text(system_prompt_path)
        self.user_template = load_text(user_template_path)
        self.repetition_guard = RepetitionGuard(max_items=300)

    def _can_use_local_short(self, category: ReviewCategory, review: Dict[str, Any]) -> bool:
        text = (review.get("text") or "").strip()
        stars = int(review.get("productValuation") or review.get("valuation") or 0)
        return category in {ReviewCategory.EMPTY_REVIEW, ReviewCategory.SHORT_NONSPECIFIC, ReviewCategory.POSITIVE_NO_ISSUE} and stars >= 5 and len(text) < 30

    def process(self, review: Dict[str, Any]) -> PipelineArtifacts:
        cls = self.classifier.classify(review)

        if self._can_use_local_short(cls.category, review):
            raw_reply = make_short_reply(review)
            prompt = "<local_short_reply>"
        else:
            scenario = self.scenarios[cls.category.value]
            prompt = build_user_prompt(self.user_template, scenario, review, cls.category.value)
            raw_reply = self.generator.generate(self.system_prompt, prompt)
            time.sleep(0.35)

        final_reply = finalize_reply(raw_reply, review)

        # анти-дубль: если ответ слишком похож на недавние, мягко перегенерируем
        if self.repetition_guard.is_too_similar(final_reply) and prompt != "<local_short_reply>":
            prompt2 = prompt + "\n\nСделайте формулировки заметно отличающимися от типовых, но без потери вежливости."
            raw2 = self.generator.generate(self.system_prompt, prompt2)
            final_reply = finalize_reply(raw2, review)
            logging.info("anti-repeat regenerate used for id=%s", review.get("id") or review.get("feedbackId"))

        self.repetition_guard.remember(final_reply)
        needs_manual_review, manual_reasons = detect_manual_review_need(cls.category, review)

        return PipelineArtifacts(
            category=cls.category,
            reasons=cls.reasons,
            prompt=prompt,
            raw_reply=raw_reply,
            final_reply=final_reply,
            needs_manual_review=needs_manual_review,
            manual_reasons=manual_reasons,
        )
