from app.core.classifier import ReviewClassifier
from app.core.pipeline import ReplyPipeline


class _DummyGenerator:
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return "Спасибо за отзыв! Нам очень жаль, что возникла такая ситуация."


def test_pipeline_artifacts_include_manual_review_flags():
    pipeline = ReplyPipeline(
        classifier=ReviewClassifier("app/config/classification_rules.json"),
        generator=_DummyGenerator(),
        scenarios_path="app/config/scenarios.json",
        system_prompt_path="app/prompts/system_ru.txt",
        user_template_path="app/prompts/user_template.txt",
    )

    review = {
        "id": "1",
        "text": "Это опасно, после использования появилась аллергия.",
        "productValuation": 1,
    }

    artifacts = pipeline.process(review)

    assert hasattr(artifacts, "needs_manual_review")
    assert hasattr(artifacts, "manual_reasons")
    assert artifacts.needs_manual_review is True
    assert artifacts.manual_reasons
