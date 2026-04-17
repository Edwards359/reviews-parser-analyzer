from models import ReviewTone
from providers.base import parse_llm_response


def test_parse_valid_json():
    raw = '{"tone":"positive","reply":"Спасибо!"}'
    result = parse_llm_response(raw, "Отлично")
    assert result.tone == ReviewTone.POSITIVE
    assert result.reply == "Спасибо!"


def test_parse_with_surrounding_text():
    raw = 'Вот ответ: {"tone": "negative", "reply": "Извините"} конец.'
    result = parse_llm_response(raw, "Ужасно")
    assert result.tone == ReviewTone.NEGATIVE
    assert result.reply == "Извините"


def test_parse_invalid_falls_back():
    result = parse_llm_response("совсем не JSON", "Всё отлично, спасибо")
    assert result.tone == ReviewTone.POSITIVE
    assert result.reply
