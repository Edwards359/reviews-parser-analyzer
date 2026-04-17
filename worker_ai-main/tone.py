from __future__ import annotations

import re

from models import ReviewTone

POSITIVE_MARKERS: tuple[str, ...] = (
    "спасибо",
    "отлично",
    "супер",
    "класс",
    "хорош",
    "понрав",
    "рекоменд",
    "быстро",
    "удобно",
    "прекрас",
    "идеально",
    "love",
    "great",
    "awesome",
    "лучш",
    "восторг",
    "доволен",
)
NEGATIVE_MARKERS: tuple[str, ...] = (
    "плохо",
    "ужас",
    "отврат",
    "проблем",
    "не работает",
    "ошибка",
    "долго",
    "медленно",
    "разочар",
    "сломал",
    "недоволен",
    "bad",
    "terrible",
    "awful",
    "обман",
    "возврат",
    "жал",
)
NEGATION_EXACT: frozenset[str] = frozenset({"не", "нет", "без", "not", "no", "never"})
NEGATION_PREFIXES: tuple[str, ...] = (
    "никак",
    "никог",
    "никто",
    "никаких",
    "никакой",
    "никакая",
    "никакое",
)

# Многословные оценочные паттерны — считаются как +1 к соответствующей стороне.
# Проверяются как подстроки в нормализованном тексте (с одинарными пробелами).
NEGATIVE_PHRASES: tuple[str, ...] = (
    "никакой товар",
    "никакое качество",
    "никакая поддержка",
    "никакой сервис",
    "никакое обслуживание",
    "никакая доставка",
    "так себе",
    "ни о чем",
    "ни о чём",
    "полный провал",
    "полное разочарование",
    "зря потратил",
    "зря потратила",
    "зря купил",
    "зря купила",
    "деньги на ветер",
    "мимо денег",
    "хуже не бывает",
    "на троечку",
    "не стоит своих денег",
    "не стоит денег",
    "не рекомендую",
    "не советую",
    "waste of money",
    "do not recommend",
)
POSITIVE_PHRASES: tuple[str, ...] = (
    "всё супер",
    "все супер",
    "всё отлично",
    "все отлично",
    "очень доволен",
    "очень довольна",
    "остался доволен",
    "остались довольны",
    "буду заказывать снова",
    "обязательно вернусь",
    "рекомендую к покупке",
    "стоит своих денег",
    "highly recommend",
)

# "никакой <X>" и "<X> — никакой" — оценочные отрицания, считаем сигналом негатива.
# Формы окончаний: "никак(ой|ая|ое|ие|их|ому|ими|ом)".
_NIKAKOI_SUFFIX = r"никак(?:ой|ая|ое|ие|их|ому|ими|ом)"
_NIKAKOI_BEFORE_RE = re.compile(
    rf"\b{_NIKAKOI_SUFFIX}\s+([а-я]{{3,}})",
    flags=re.IGNORECASE | re.UNICODE,
)
_NIKAKOI_AFTER_RE = re.compile(
    rf"\b([а-я]{{3,}})\s*[\-\u2014\u2013]?\s*{_NIKAKOI_SUFFIX}\b",
    flags=re.IGNORECASE | re.UNICODE,
)

_STOP_WORDS_AROUND_NIKAKOI: frozenset[str] = frozenset(
    {
        "и", "а", "но", "же", "ли", "бы", "не", "нет",
        "так", "там", "тут", "это", "том", "тем",
        "все", "всё", "что", "как", "еще", "ещё",
    }
)


_clause_split_re = re.compile(r"[.!?;,:\-\u2014\u2013\n\r]+", flags=re.UNICODE)
_word_re = re.compile(r"[\w']+", flags=re.UNICODE)
_whitespace_re = re.compile(r"\s+", flags=re.UNICODE)


def _is_negation_token(token: str) -> bool:
    if token in NEGATION_EXACT:
        return True
    return any(token.startswith(prefix) for prefix in NEGATION_PREFIXES)


def _normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    return _whitespace_re.sub(" ", text).strip()


def _clauses(text: str) -> list[list[str]]:
    parts: list[list[str]] = []
    for chunk in _clause_split_re.split(text):
        tokens = [token.lower() for token in _word_re.findall(chunk)]
        if tokens:
            parts.append(tokens)
    return parts


def _hits_in(tokens: list[str], marker: str) -> list[int]:
    return [idx for idx, token in enumerate(tokens) if marker in token]


def _is_negated(tokens: list[str], position: int, window: int = 3) -> bool:
    start = max(0, position - window)
    return any(_is_negation_token(token) for token in tokens[start:position])


def _count_phrase_hits(text: str, phrases: tuple[str, ...]) -> int:
    hits = 0
    for phrase in phrases:
        normalized = phrase.replace("ё", "е")
        if normalized in text:
            hits += 1
    return hits


def _count_nikakoi_noun(text: str) -> int:
    hits = 0
    for match in _NIKAKOI_BEFORE_RE.finditer(text):
        noun = match.group(1).lower()
        if noun not in _STOP_WORDS_AROUND_NIKAKOI:
            hits += 1
    for match in _NIKAKOI_AFTER_RE.finditer(text):
        noun = match.group(1).lower()
        if noun not in _STOP_WORDS_AROUND_NIKAKOI:
            hits += 1
    return hits


def detect_tone(review_text: str) -> ReviewTone:
    if not review_text or not review_text.strip():
        return ReviewTone.NEUTRAL

    normalized = _normalize(review_text)
    positive_score = _count_phrase_hits(normalized, POSITIVE_PHRASES)
    negative_score = _count_phrase_hits(normalized, NEGATIVE_PHRASES)
    negative_score += _count_nikakoi_noun(normalized)

    for tokens in _clauses(review_text):
        for marker in POSITIVE_MARKERS:
            for idx in _hits_in(tokens, marker):
                if _is_negated(tokens, idx):
                    negative_score += 1
                else:
                    positive_score += 1

        for marker in NEGATIVE_MARKERS:
            for idx in _hits_in(tokens, marker):
                if _is_negated(tokens, idx):
                    positive_score += 1
                else:
                    negative_score += 1

    if negative_score > positive_score:
        return ReviewTone.NEGATIVE
    if positive_score > negative_score:
        return ReviewTone.POSITIVE
    return ReviewTone.NEUTRAL


def build_fallback_reply(review_text: str) -> str:
    tone = detect_tone(review_text)
    if tone == ReviewTone.NEGATIVE:
        return (
            "Нам жаль, что у вас остались негативные впечатления. "
            "Спасибо, что сообщили об этом, мы постараемся помочь и разобраться в ситуации."
        )
    if tone == ReviewTone.POSITIVE:
        return (
            "Спасибо за добрые слова и за то, что поделились впечатлениями. "
            "Нам приятно, что у вас всё получилось."
        )
    return (
        "Спасибо за отзыв. Мы учтём ваши замечания; "
        "если захотите, поделитесь деталями — так мы сможем отреагировать точнее."
    )
