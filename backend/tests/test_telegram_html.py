from app.telegram import telegram_html_to_preview, validate_telegram_html


def test_valid_default_markup():
    text = (
        "<b>Чемпионат</b> · 2026-09-21 · 12:00 UTC+2\n"
        "<code>114653273</code>  +10.00%\n"
        '<a href="https://example.com">Рейтинг на сайте</a>'
    )
    assert validate_telegram_html(text) == []


def test_rejects_br_and_unclosed():
    errors = validate_telegram_html("<b>hello<br>world")
    assert any("br" in e.lower() for e in errors)
    assert any("не закрыт" in e.lower() for e in errors)


def test_rejects_unknown_tag():
    errors = validate_telegram_html("<div>x</div>")
    assert any("div" in e for e in errors)


def test_preview_keeps_bold_and_breaks():
    html = telegram_html_to_preview("<b>A</b>\nB")
    assert "<b>A</b>" in html
    assert "<br>" in html
