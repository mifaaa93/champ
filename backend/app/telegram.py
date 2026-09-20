from __future__ import annotations

import html
import logging

import httpx

from app.config import settings

log = logging.getLogger("champ.telegram")


def _fmt_pct(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _fmt_money(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}${value:.2f}"


def build_hourly_message(day: str, hour_label: str, yield_rows: list, loss_rows: list) -> str:
    lines = [
        f"<b>IB CUP</b> · {day} · {hour_label} Dubai",
        "",
        "<b>Доходность</b>",
    ]
    if not yield_rows:
        lines.append("пока пусто — ждут депозит и регистрацию")
    for i, r in enumerate(yield_rows, 1):
        name = html.escape(r.get("nickname") or str(r["uid"]))
        lines.append(
            f"{i}. <code>{r['uid']}</code> {name}  {_fmt_pct(r['return_pct'])}  ({_fmt_money(r['pnl'])})"
        )
    lines += ["", "<b>Просадка</b>"]
    if not loss_rows:
        lines.append("нет отрицательных результатов")
    for i, r in enumerate(loss_rows, 1):
        name = html.escape(r.get("nickname") or str(r["uid"]))
        lines.append(
            f"{i}. <code>{r['uid']}</code> {name}  {_fmt_money(r['pnl'])}  ({_fmt_pct(r['return_pct'])})"
        )
    if settings.site_public_url:
        lines += ["", f'<a href="{html.escape(settings.site_public_url)}">Рейтинг на сайте</a>']
    return "\n".join(lines)


def build_final_message(day: str, winners: dict) -> str:
    lines = [f"<b>Итоги дня</b> · {day} Dubai", "", "<b>Доходность</b>"]
    for item in winners.get("yield") or []:
        lines.append(
            f"{item['place']}. <code>{item['uid']}</code>  приз {_fmt_money(float(item['prize_amount']))}"
        )
    lines += ["", "<b>Компенсация просадки</b>"]
    for item in winners.get("loss") or []:
        lines.append(
            f"{item['place']}. <code>{item['uid']}</code>  {_fmt_money(float(item['prize_amount']))}"
        )
    if settings.site_public_url:
        lines += ["", f'<a href="{html.escape(settings.site_public_url)}/archive/{day}">Архив дня</a>']
    return "\n".join(lines)


async def send_message(text: str) -> bool:
    if not settings.tg_bot_token or not settings.tg_chat_id:
        log.info("telegram skipped: token or chat_id empty")
        return False
    url = f"https://api.telegram.org/bot{settings.tg_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            url,
            json={
                "chat_id": settings.tg_chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )
        if resp.status_code >= 400:
            log.error("telegram error %s %s", resp.status_code, resp.text)
            return False
    return True
