"""Язык интерфейса утилиты: сообщения CLI, проверки карты, веб-редактора и окна приложения.

Строки в коде пишутся по-русски и служат ключами; английские переводы — в
:mod:`mapcan.locale.en`. Язык по умолчанию — английский; выбор хранится в
``~/.mapcan/config.json`` и переопределяется переменной окружения ``MAPCAN_LANG``.

Язык генерируемых документов и кода сюда не относится — он задаётся ``document.language``.
"""

from __future__ import annotations

import os

LANGUAGES = ("en", "ru")
DEFAULT_LANGUAGE = "en"

_lang: str | None = None


def normalize_language(value: str | None) -> str | None:
    v = (value or "").strip().lower()[:2]
    return v if v in LANGUAGES else None


def configured_language() -> str | None:
    """Язык из переменной окружения или настроек пользователя (None — ещё не выбран)."""
    env = normalize_language(os.environ.get("MAPCAN_LANG") or os.environ.get("CANMAP_LANG"))
    if env:
        return env
    from .userconfig import UserConfig  # здесь: userconfig сам использует перевод

    return normalize_language(UserConfig.load().language)


def get_language() -> str:
    global _lang
    if _lang is None:
        _lang = configured_language() or DEFAULT_LANGUAGE
    return _lang


def set_language(lang: str) -> None:
    global _lang
    _lang = normalize_language(lang) or DEFAULT_LANGUAGE


def _(msg: str, /, **kw) -> str:
    """Перевести сообщение на язык интерфейса и подставить параметры (синтаксис str.format)."""
    if get_language() != "ru":
        from .locale.en import EN

        msg = EN.get(msg, msg)
    return msg.format(**kw) if kw else msg


def N_(msg: str) -> str:
    """Пометить строку для перевода, не переводя её сейчас (переводится при выводе через ``_``)."""
    return msg
