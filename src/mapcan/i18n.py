"""Сообщения утилиты: CLI, проверки карты, веб-редактора и окна приложения.

Интерфейс — только на английском. Строки в коде пишутся по-русски и служат ключами;
английские переводы — в :mod:`mapcan.locale.en`.

Язык генерируемых документов и кода сюда не относится — он задаётся ``document.language``
или выбирается при экспорте.
"""

from __future__ import annotations

import re

# Языки, для которых есть подписи документов (заголовки таблиц и т. п.); для других — английские
DOC_LANGUAGES = ("ru", "en")
LANGUAGE_CODE = re.compile(r"[a-z]{2}")


def normalize_language(value: str | None) -> str | None:
    """Код языка документа (ISO 639-1: ru, en, de…) или None, если он не распознан."""
    v = (value or "").strip().lower()
    v = v.split("-")[0].split("_")[0]      # en-US, pt_BR → en, pt
    return v if LANGUAGE_CODE.fullmatch(v) else None


def _(msg: str, /, **kw) -> str:
    """Перевести сообщение на английский и подставить параметры (синтаксис str.format)."""
    from .locale.en import EN

    msg = EN.get(msg, msg)
    return msg.format(**kw) if kw else msg


def N_(msg: str) -> str:
    """Пометить строку для перевода, не переводя её сейчас (переводится при выводе через ``_``)."""
    return msg
