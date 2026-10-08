"""Messages of the tool: CLI, map validation, the web editor and the app window.

The interface is in English only. Messages are written in English in the code and wrapped in
``_()`` (or ``N_()`` for tables translated later); the English text is also the key of the Russian
translation in :mod:`mapcan.locale.ru`, which tests keep complete.

The language of generated documents and code is a different thing: it comes from
``document.language`` or is chosen on export.
"""

from __future__ import annotations

import re

# Languages with document labels (table headings etc.); other languages get the English ones
DOC_LANGUAGES = ("ru", "en")
LANGUAGE_CODE = re.compile(r"[a-z]{2}")


def normalize_language(value: str | None) -> str | None:
    """Document language code (ISO 639-1: ru, en, de…) or None if it is not recognized."""
    v = (value or "").strip().lower()
    v = v.split("-")[0].split("_")[0]      # en-US, pt_BR → en, pt
    return v if LANGUAGE_CODE.fullmatch(v) else None


def _(msg: str, /, **kw) -> str:
    """Interface message with its parameters filled in (str.format syntax)."""
    return msg.format(**kw) if kw else msg


def N_(msg: str) -> str:
    """Mark a message for translation without formatting it now (it is shown through ``_`` later)."""
    return msg
