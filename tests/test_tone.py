from models import ReviewTone
from tone import detect_tone


def test_positive_simple():
    assert detect_tone("Всё супер, спасибо большое!") == ReviewTone.POSITIVE


def test_negative_simple():
    assert detect_tone("Ужасно, товар сломался сразу") == ReviewTone.NEGATIVE


def test_negation_flips_positive():
    # "не понравилось" не должно засчитываться как положительный
    assert detect_tone("Мне совсем не понравилось, долго и неудобно") == ReviewTone.NEGATIVE


def test_negation_flips_negative():
    assert detect_tone("Никаких проблем не возникло, всё отлично") == ReviewTone.POSITIVE


def test_neutral_empty():
    assert detect_tone("") == ReviewTone.NEUTRAL


def test_neutral_factual():
    assert detect_tone("Доставили во вторник, пакет стандартный") == ReviewTone.NEUTRAL


def test_nikakoi_noun_is_negative():
    assert detect_tone("Никакой товар") == ReviewTone.NEGATIVE
    assert detect_tone("Никакая поддержка, одни отписки") == ReviewTone.NEGATIVE
    assert detect_tone("Качество — никакое, возьму в другом месте") == ReviewTone.NEGATIVE


def test_idioms_are_negative():
    assert detect_tone("Так себе, если честно") == ReviewTone.NEGATIVE
    assert detect_tone("Полный провал, зря потратил деньги") == ReviewTone.NEGATIVE
    assert detect_tone("Не рекомендую, хуже не бывает") == ReviewTone.NEGATIVE


def test_idioms_are_positive():
    assert detect_tone("Всё супер, обязательно вернусь") == ReviewTone.POSITIVE
    assert detect_tone("Стоит своих денег, рекомендую к покупке") == ReviewTone.POSITIVE
