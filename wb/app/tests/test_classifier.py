from app.config.categories import ReviewCategory
from app.core.classifier import ReviewClassifier


def test_empty_review():
    c = ReviewClassifier("app/config/classification_rules.json")
    r = c.classify({"text": "", "productValuation": 5})
    assert r.category == ReviewCategory.EMPTY_REVIEW


def test_negative_size_review():
    c = ReviewClassifier("app/config/classification_rules.json")
    r = c.classify({"text": "Размер не подошел, маломерит", "productValuation": 2})
    assert r.category == ReviewCategory.NEGATIVE_SIZE


def test_positive_no_issue():
    c = ReviewClassifier("app/config/classification_rules.json")
    r = c.classify({"text": "Все отлично, спасибо", "productValuation": 5})
    assert r.category == ReviewCategory.POSITIVE_NO_ISSUE
