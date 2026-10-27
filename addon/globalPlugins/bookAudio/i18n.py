"""Russian source messages with English fallback for every non-Russian locale.

The wrapper resolves the translator at call time, including after worker bootstrap.
Missing or invalid English catalogs deliberately raise, never silently use Russian.
"""
import gettext
from pathlib import Path

LOCALE_DIR = Path(__file__).resolve().parents[2] / 'locale'
_translator = gettext.NullTranslations()


def set_language(language):
    global _translator
    base = str(language or 'en').replace('-', '_').split('_', 1)[0].lower()
    translator = gettext.NullTranslations() if base == 'ru' else gettext.translation(
        'nvda', localedir=str(LOCALE_DIR), languages=['en'], fallback=False,
    )
    _translator = translator


def _(message):
    return _translator.gettext(message)


try:
    import languageHandler
except ImportError:
    set_language('ru')
else:
    set_language(languageHandler.getLanguage())
