from enum import Enum


class ReviewCategory(str, Enum):
    POSITIVE_NO_ISSUE = "positive_no_issue"
    POSITIVE_WITH_NOTE = "positive_with_note"
    NEUTRAL = "neutral"
    NEGATIVE_QUALITY = "negative_quality"
    NEGATIVE_SIZE = "negative_size"
    NEGATIVE_PACKAGING = "negative_packaging"
    NEGATIVE_DELIVERY_CONDITION = "negative_delivery_condition"
    EXPECTATION_MISMATCH = "expectation_mismatch"
    EMPTY_REVIEW = "empty_review"
    SHORT_NONSPECIFIC = "short_nonspecific"
