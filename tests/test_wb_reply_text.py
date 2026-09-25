"""Unit-тесты на чистые функции WB-сервиса (wb/app/core/postprocess.py). Без сети."""
import re

from app.core.postprocess import SIGNATURE, finalize_reply, make_short_reply

REVIEW = {
    "id": "fb-1",
    "createdDate": "2025-09-24T10:15:00Z",  # 10:15 -> «Добрый день»
    "userName": "Мария",
    "productValuation": 5,
}


def test_finalize_reply_adds_greeting_capitalizes_you_and_signs_once():
    raw = "спасибо, что вы выбрали нас, ваш заказ мы собирали с заботой"
    out = finalize_reply(raw, REVIEW)

    assert out.startswith("Добрый день, Мария!")
    assert re.search(r"\bвы\b", out) is None and "Вы " in out
    assert re.search(r"\bваш\b", out) is None and "Ваш " in out
    assert out.endswith(SIGNATURE)
    assert out.count(SIGNATURE) == 1

    # Если модель уже поздоровалась и подписалась — ничего не дублируется.
    pre = f"Добрый вечер, Мария! Спасибо за отзыв.\n\n{SIGNATURE}"
    out2 = finalize_reply(pre, REVIEW)
    assert out2.startswith("Добрый вечер, Мария!")
    assert out2.count("Добр") == 1
    assert out2.count(SIGNATURE) == 1


def test_finalize_reply_trims_long_text_and_keeps_signature():
    raw = "Спасибо за подробный отзыв, нам важно Ваше мнение. " * 40  # ~2000 символов
    out = finalize_reply(raw, REVIEW)

    # trim_length режет по границе слова до 900 символов, ставит «…» и заново подписывает
    assert len(out) <= 900 + 4 + len(SIGNATURE)
    assert "…" in out
    assert out.endswith(SIGNATURE)
    assert out.count(SIGNATURE) == 1


def test_make_short_reply_is_deterministic_and_well_formed():
    a = make_short_reply(REVIEW)
    b = make_short_reply(REVIEW)

    assert a == b  # вариант благодарности выбирается по хэшу id отзыва
    assert a.startswith("Добрый день, Мария!")
    assert a.endswith(SIGNATURE)
    assert re.search(r"\bвы\b", a) is None

    # Без имени — приветствие без обращения
    anon = make_short_reply({**REVIEW, "userName": ""})
    assert anon.startswith("Добрый день!")
