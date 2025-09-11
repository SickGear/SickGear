import contextlib
from .logger import logger as logger
from _typeshed import Incomplete
from collections.abc import Generator

GETTEXT_LOADED: bool

class AppriseLocale:
    _domain: str
    _locale_dir: Incomplete
    _local_re: Incomplete
    _default_encoding: str
    _fn: str
    _default_language: str
    _gtobjs: Incomplete
    lang: Incomplete
    __fn_map: Incomplete
    def __init__(self, language=None) -> None: ...
    def add(self, lang=None, set_default: bool = True): ...
    @contextlib.contextmanager
    def lang_at(self, lang, mapto=...) -> Generator[Incomplete]: ...
    @property
    def gettext(self): ...
    @staticmethod
    def detect_language(lang=None, detect_fallback: bool = True): ...
    def __getstate__(self): ...
    def __setstate__(self, state) -> None: ...

LOCALE: Incomplete

class LazyTranslation:
    text: Incomplete
    def __init__(self, text, *args, **kwargs) -> None: ...
    def __str__(self) -> str: ...

def gettext_lazy(text): ...
Translatable = str | LazyTranslation
