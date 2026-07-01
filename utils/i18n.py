import json
import os
from typing import Any

_LOCALES: dict[str, dict] = {}
_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales")
SUPPORTED = {"fr", "en"}
DEFAULT = "fr"


def _load(lang: str) -> dict:
    if lang not in _LOCALES:
        path = os.path.join(_DIR, f"{lang}.json")
        with open(path, encoding="utf-8") as f:
            _LOCALES[lang] = json.load(f)
    return _LOCALES[lang]


def t(lang: str, key: str, **kwargs: Any) -> str:
    if lang not in SUPPORTED:
        lang = DEFAULT
    data = _load(lang)
    text = data.get(key) or _load(DEFAULT).get(key) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return text
