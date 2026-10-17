import pytest
from src.utils.language import detect_language, detect_and_translate, LanguageResult


def test_detect_language_english():
    text = "The quick brown fox jumps over the lazy dog."
    assert detect_language(text) == "en"


def test_detect_language_hindi():
    text = "भारत ने चंद्रयान मिशन को चंद्रमा पर सफलतापूर्वक उतारा।"
    assert detect_language(text) == "hi"


def test_detect_language_french():
    text = "La tour Eiffel est située à Paris en France."
    assert detect_language(text) == "fr"


def test_detect_language_fallback_on_empty():
    assert detect_language("") == "en"


def test_detect_and_translate_english_passthrough():
    text = "Scientists discovered a new species in the ocean."
    result = detect_and_translate(text)
    assert isinstance(result, LanguageResult)
    assert result.detected_language == "en"
    assert result.was_translated is False
    assert result.processed_text == text
