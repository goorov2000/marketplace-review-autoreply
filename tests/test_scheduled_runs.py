"""Отказы API и меняющаяся очередь: без сети и настоящих секретов."""
import importlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import ozon_reviews_reply as ozon


@pytest.fixture
def wb(monkeypatch):
    monkeypatch.setenv("WB_TOKEN", "test-placeholder")
    module = importlib.import_module("wb_reviews_reply")
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    return module


def test_wb_failure_is_reported_and_attempts_are_bounded(wb, monkeypatch):
    client = Mock()
    client.list_feedbacks.return_value = {"feedbacks": [
        {"id": str(i), "productValuation": 5} for i in range(7)
    ]}
    pipeline = Mock()
    pipeline.process.side_effect = RuntimeError("API unavailable")
    monkeypatch.setattr(wb, "WBClient", lambda _: client)
    monkeypatch.setattr(wb, "build_pipeline", lambda: pipeline)
    monkeypatch.setattr(wb, "MAX_COUNT", 2)
    assert wb.main() == 1
    assert pipeline.process.call_count == 2
    client.answer.assert_not_called()


def test_wb_does_not_skip_reviews_when_published_items_leave_queue(wb, monkeypatch):
    pending = [{"id": str(i), "productValuation": 5} for i in range(200)]
    published = []

    class Client:
        def list_feedbacks(self, *, take, skip):
            return {"feedbacks": pending[skip:skip + take]}

        def answer(self, review_id, text):
            published.append(review_id)
            pending[:] = [r for r in pending if r["id"] != review_id]

    pipeline = Mock()
    pipeline.process.return_value = SimpleNamespace(final_reply="Спасибо!")
    monkeypatch.setattr(wb, "WBClient", lambda _: Client())
    monkeypatch.setattr(wb, "build_pipeline", lambda: pipeline)
    monkeypatch.setattr(wb, "MAX_COUNT", 150)
    monkeypatch.setattr(wb, "DRY_RUN", False)
    assert wb.main() == 0
    assert published == [str(i) for i in range(150)]
    assert len(pending) == 50


@pytest.fixture
def ozon_run(monkeypatch):
    monkeypatch.setattr(ozon.time, "sleep", lambda _: None)
    monkeypatch.setattr(ozon, "DRY_RUN", False)
    monkeypatch.setattr(ozon, "MAX_COUNT", 2)
    monkeypatch.setattr(ozon, "MARK_EMPTY_AS_PROCESSED", False)
    monkeypatch.setattr(ozon, "ONLY_UNANSWERED", True)
    monkeypatch.setattr(ozon, "SKIP_EMPTY", True)
    monkeypatch.setattr(ozon, "LOG_SHOW_LLM", False)
    publisher = Mock()
    monkeypatch.setattr(ozon, "create_comment", publisher)
    return publisher


def test_ozon_failure_is_reported_and_attempts_are_bounded(ozon_run, monkeypatch):
    monkeypatch.setattr(ozon, "list_reviews_unprocessed", lambda *_: [
        {"id": str(i), "rating": 5, "text": "Всё отлично"} for i in range(7)
    ])
    ozon_run.side_effect = RuntimeError("Ozon unavailable")
    assert ozon.main() == 1
    assert ozon_run.call_count == 2


def test_ozon_empty_review_with_comment_is_not_answered_again(ozon_run, monkeypatch):
    monkeypatch.setattr(ozon, "MARK_EMPTY_AS_PROCESSED", True)
    monkeypatch.setattr(ozon, "list_reviews_unprocessed", lambda *_: [
        {"id": "already-answered", "rating": 5, "text": "", "comments_amount": 1}
    ])
    comments = Mock(return_value=[{"id": "existing-comment"}])
    monkeypatch.setattr(ozon, "list_comments", comments)
    assert ozon.main() == 0
    comments.assert_called_once()
    ozon_run.assert_not_called()


def test_ozon_dry_run_previews_local_answer_without_publication(ozon_run, monkeypatch, caplog):
    monkeypatch.setattr(ozon, "DRY_RUN", True)
    monkeypatch.setattr(ozon, "list_reviews_unprocessed", lambda *_: [
        {"id": "preview", "rating": 5, "text": "Всё отлично"}
    ])
    with caplog.at_level("INFO"):
        assert ozon.main() == 0
    ozon_run.assert_not_called()
    assert "[DRY_RUN]" in caplog.text
    assert "Благодарим" in caplog.text or "благодарим" in caplog.text
