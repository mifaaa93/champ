from __future__ import annotations

import html
import logging
import re
from string import Formatter

import httpx

from app.config import settings

log = logging.getLogger("champ.telegram")

DEFAULT_TEMPLATES = {
    "tg_hourly_header": "<b>Чемпионат</b> · {day} · {time} UTC+2",
    "tg_yield_title": "<b>Доходность</b>",
    "tg_yield_row": "{place}. <code>{uid}</code> {name}  {pct}  ({pnl})",
    "tg_yield_empty": "пока пусто — ждут депозит и регистрацию",
    "tg_loss_title": "<b>Просадка</b>",
    "tg_loss_row": "{place}. <code>{uid}</code> {name}  {pnl}  ({pct})",
    "tg_loss_empty": "нет отрицательных результатов",
    "tg_footer": '<a href="{site}">Рейтинг на сайте</a>',
    "tg_final_header": "<b>Итоги дня</b> · {day} UTC+2",
    "tg_final_yield_row": "{place}. <code>{uid}</code>  приз {prize}",
    "tg_final_loss_row": "{place}. <code>{uid}</code>  {prize}",
}


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _fmt_pct(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def _fmt_money(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}${value:.2f}"


def render_template(template: str, **values: object) -> str:
    if not template:
        return ""
    try:
        return Formatter().vformat(template, (), _Safe(values))
    except Exception:
        return template


def _tpl(cfg: dict, key: str) -> str:
    value = (cfg or {}).get(key)
    if isinstance(value, str) and value.strip():
        return value
    return DEFAULT_TEMPLATES[key]


def _row_vars(place: int, row: dict) -> dict:
    uid = row.get("uid", "")
    name = html.escape(str(row.get("nickname") or uid))
    return {
        "place": place,
        "uid": uid,
        "name": name,
        "pct": _fmt_pct(float(row.get("return_pct") or 0)),
        "pnl": _fmt_money(float(row.get("pnl") or 0)),
        "prize": _fmt_money(float(row.get("prize_amount") or 0)),
    }


def build_hourly_message(
    day: str,
    hour_label: str,
    yield_rows: list,
    loss_rows: list,
    cfg: dict | None = None,
) -> str:
    cfg = cfg or {}
    site = settings.site_public_url or ""
    common = {"day": day, "time": hour_label, "site": html.escape(site)}
    lines = [render_template(_tpl(cfg, "tg_hourly_header"), **common), ""]
    lines.append(render_template(_tpl(cfg, "tg_yield_title"), **common))
    if not yield_rows:
        lines.append(render_template(_tpl(cfg, "tg_yield_empty"), **common))
    for i, r in enumerate(yield_rows, 1):
        lines.append(render_template(_tpl(cfg, "tg_yield_row"), **common, **_row_vars(i, r)))
    lines += ["", render_template(_tpl(cfg, "tg_loss_title"), **common)]
    if not loss_rows:
        lines.append(render_template(_tpl(cfg, "tg_loss_empty"), **common))
    for i, r in enumerate(loss_rows, 1):
        lines.append(render_template(_tpl(cfg, "tg_loss_row"), **common, **_row_vars(i, r)))
    footer = render_template(_tpl(cfg, "tg_footer"), **common)
    if footer.strip():
        lines += ["", footer]
    return "\n".join(lines)


def build_final_message(day: str, winners: dict, cfg: dict | None = None) -> str:
    cfg = cfg or {}
    site = settings.site_public_url or ""
    archive = f"{site}/archive/{day}" if site else ""
    common = {"day": day, "time": "", "site": html.escape(archive)}
    lines = [render_template(_tpl(cfg, "tg_final_header"), **common), ""]
    lines.append(render_template(_tpl(cfg, "tg_yield_title"), **common))
    for item in winners.get("yield") or []:
        lines.append(
            render_template(_tpl(cfg, "tg_final_yield_row"), **common, **_row_vars(item["place"], item))
        )
    lines += ["", render_template(_tpl(cfg, "tg_loss_title"), **common)]
    for item in winners.get("loss") or []:
        lines.append(
            render_template(_tpl(cfg, "tg_final_loss_row"), **common, **_row_vars(item["place"], item))
        )
    footer = render_template(_tpl(cfg, "tg_footer"), **common)
    if footer.strip():
        lines += ["", footer]
    return "\n".join(lines)


TG_TAGS = frozenset(
    {
        "b",
        "strong",
        "i",
        "em",
        "u",
        "ins",
        "s",
        "strike",
        "del",
        "code",
        "pre",
        "a",
        "span",
        "tg-spoiler",
        "blockquote",
    }
)
VOID_FORBIDDEN = frozenset({"br", "hr", "img", "input"})
TAG_RE = re.compile(r"(?s)<(/)?([a-zA-Z][a-zA-Z0-9-]*)(\s[^>]*)?>")
ATTR_RE = re.compile(r'([a-zA-Z_:][-a-zA-Z0-9_:]*)\s*=\s*("([^"]*)"|\'([^\']*)\')')
ENTITY_RE = re.compile(r"^&(?:#x[0-9a-fA-F]+|#\d+|[a-zA-Z][a-zA-Z0-9]+);")


class TelegramHtmlError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _attrs(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    out: dict[str, str] = {}
    for match in ATTR_RE.finditer(raw):
        out[match.group(1).lower()] = match.group(3) if match.group(3) is not None else match.group(4)
    return out


def validate_telegram_html(text: str) -> list[str]:
    errors: list[str] = []
    if len(text) > 4096:
        errors.append("Сообщение длиннее 4096 символов — Telegram его не примет")
    stack: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "&":
            ent = ENTITY_RE.match(text[i:])
            if not ent:
                errors.append("Символ & нужно писать как &amp;")
                i += 1
                continue
            i += len(ent.group(0))
            continue
        if ch == ">":
            errors.append("Символ > вне тега нужно писать как &gt;")
            i += 1
            continue
        if ch != "<":
            i += 1
            continue
        m = TAG_RE.match(text, i)
        if not m:
            errors.append("Символ < вне тега нужно писать как &lt;. Теги вроде <br> Telegram не понимает.")
            i += 1
            continue
        closing, raw_name, raw_attrs = m.group(1), m.group(2).lower(), m.group(3)
        i = m.end()
        if raw_name in VOID_FORBIDDEN:
            errors.append(f"Тег <{raw_name}> в Telegram нельзя. Для новой строки просто нажми Enter.")
            continue
        if raw_name not in TG_TAGS:
            errors.append(
                f"Тег <{raw_name}> Telegram не понимает. Можно: "
                f"b, i, u, s, code, pre, a, blockquote, tg-spoiler."
            )
            continue
        attrs = _attrs(raw_attrs)
        if closing:
            if not stack:
                errors.append(f"Лишний закрывающий </{raw_name}>")
            elif stack[-1] != raw_name:
                errors.append(f"Сначала закрой <{stack[-1]}>, а не </{raw_name}>")
            else:
                stack.pop()
            continue
        if raw_name == "a":
            href = attrs.get("href", "")
            if not href or not re.match(r"^(https?://|tg://|mailto:)", href, re.I):
                errors.append('Ссылка <a> должна быть с href="https://..." или tg://')
            extra = set(attrs) - {"href"}
            if extra:
                errors.append(f"У <a> лишние атрибуты: {', '.join(sorted(extra))}")
        elif raw_name == "span":
            if attrs.get("class") != "tg-spoiler":
                errors.append('Тег <span> в Telegram только как <span class="tg-spoiler">')
        elif raw_name == "blockquote":
            extra = set(attrs) - {"expandable"}
            if extra:
                errors.append("У <blockquote> допустим только атрибут expandable")
        elif attrs:
            errors.append(f"У <{raw_name}> не должно быть атрибутов")
        stack.append(raw_name)
    for open_tag in stack:
        errors.append(f"Не закрыт тег <{open_tag}>")
    # unique, keep order
    seen: set[str] = set()
    uniq: list[str] = []
    for err in errors:
        if err not in seen:
            seen.add(err)
            uniq.append(err)
    return uniq


def telegram_html_to_preview(text: str) -> str:
    """Browser HTML: keep Telegram tags, escape the rest."""
    parts: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            parts.append("<br>")
            i += 1
            continue
        m = TAG_RE.match(text, i) if ch == "<" else None
        if m:
            closing, raw_name, raw_attrs = m.group(1), m.group(2).lower(), m.group(3) or ""
            if raw_name in TG_TAGS:
                if closing:
                    parts.append(f"</{raw_name}>")
                elif raw_name == "a":
                    href = html.escape(_attrs(raw_attrs).get("href", ""), quote=True)
                    parts.append(f'<a href="{href}">')
                elif raw_name == "span":
                    parts.append('<span class="tg-spoiler">')
                else:
                    parts.append(f"<{raw_name}>")
                i = m.end()
                continue
        parts.append(html.escape(ch, quote=False))
        i += 1
    return "".join(parts)


async def send_message(text: str) -> bool:
    errors = validate_telegram_html(text)
    if errors:
        raise TelegramHtmlError(errors)
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
