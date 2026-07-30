"""Live language switching.

Widgets never store translated text.  They implement ``retranslate()``, call
:func:`tr` inside it to (re)fill their labels, and connect that method to
:data:`translator`'s ``language_changed`` signal.  Switching language then costs
one signal emission and no restart.
"""

from __future__ import annotations

from PySide6.QtCore import QLocale, QObject, Signal

from .translations import CATALOGS, DEFAULT_LANGUAGE, LANGUAGE_NAMES


class Translator(QObject):
    """Holds the active language and notifies the interface when it changes."""

    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._language = DEFAULT_LANGUAGE

    @property
    def language(self) -> str:
        return self._language

    def available(self) -> list[tuple[str, str]]:
        """``[(code, display name)]`` for the language selector."""
        return [(code, LANGUAGE_NAMES[code]) for code in CATALOGS]

    def set_language(self, code: str) -> None:
        if code not in CATALOGS or code == self._language:
            return
        self._language = code
        self.language_changed.emit(code)

    def detect_system_language(self) -> str:
        """The OS language when we support it, Italian otherwise."""
        code = QLocale.system().name().split("_")[0].lower()
        return code if code in CATALOGS else DEFAULT_LANGUAGE

    def translate(self, key: str, **kwargs: object) -> str:
        """Look ``key`` up in the active catalog.

        Falls back to the default language, then to the key itself, so a missing
        translation degrades to something readable rather than crashing.
        """
        catalog = CATALOGS.get(self._language, {})
        text = catalog.get(key)
        if text is None:
            text = CATALOGS[DEFAULT_LANGUAGE].get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError):
                return text
        return text


#: The single translator instance the whole interface shares.
translator = Translator()


def tr(key: str, **kwargs: object) -> str:
    """Shorthand for ``translator.translate``."""
    return translator.translate(key, **kwargs)
