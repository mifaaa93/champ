from app.telegram import build_hourly_message, render_template


def test_render_keeps_unknown_placeholder():
    assert "{foo}" in render_template("hi {name} {foo}", name="Ann")


def test_hourly_uses_custom_row_template():
    cfg = {
        "tg_hourly_header": "DAY {day} {time}",
        "tg_yield_title": "YIELD",
        "tg_yield_row": "#{place} uid={uid} {pct}",
        "tg_loss_title": "LOSS",
        "tg_loss_empty": "none",
        "tg_footer": "",
    }
    text = build_hourly_message(
        "2026-09-20",
        "23:00",
        [{"uid": 1, "nickname": "a", "return_pct": 12.5, "pnl": 10}],
        [],
        cfg,
    )
    assert "DAY 2026-09-20 23:00" in text
    assert "#1 uid=1 +12.50%" in text
    assert "none" in text
