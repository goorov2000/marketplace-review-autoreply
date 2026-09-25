"""Unit-тесты на чистые функции Ozon-сервиса (ozon/ozon_reviews_reply.py). Без сети."""
import pytest

import ozon_reviews_reply as ozon


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Пахнет химией, пришлось проветривать", "запах"),
        ("Пришло совсем другое платье, не та модель", "ошибка при отгрузке"),
        ("Платье маломерит, не подошло по размеру", "размер"),
        ("Упаковка помята, коробка порвана", "упаковка"),
        ("Цвет не соответствует фото", "несоответствие фото"),
        ("Ткань скатывается, торчат нитки", "качество ткани"),
        ("Отличное платье, спасибо!", "прочее"),
    ],
)
def test_classify_detects_review_topic(text, expected):
    assert ozon.classify(text) == expected


def test_size_complaint_skips_local_template_and_fix_response_rewrites_cliche():
    raw_text = "Платье маломерит, не подошло по размеру"

    # Локальный шаблон — только для чистых 5★ без замечаний
    assert ozon.local_template("", 5, "Всё отлично, спасибо!") is not None
    assert ozon.local_template("", 5, raw_text) is None
    assert ozon.local_template("", 4, "Всё отлично, спасибо!") is None

    # Ответ модели с позитивным клише при жалобе на размер правится
    model_reply = f"Добрый день! Мы рады, что Вы остались довольны покупкой. Спасибо за отзыв.\n{ozon.SIGN}"
    out = ozon.fix_response(model_reply, 3, ozon.classify(raw_text), raw_text)

    assert "остались довольны" not in out
    assert "размерной сетке" in out
    assert "вы " not in out  # обращения только с заглавной
    assert out.endswith(ozon.SIGN)
    assert out.count(ozon.SIGN) == 1
