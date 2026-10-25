"""텔레그램 메시지 작성/전송."""
from __future__ import annotations

import html
from typing import Optional

import requests

from . import env
from .metrics import Metric

WD = "월화수목금토일"


def fng_rating(v: float) -> str:
    for hi, name in ((25, "극도의 공포"), (45, "공포"), (55, "중립"), (75, "탐욕"), (101, "극도의 탐욕")):
        if v < hi:
            return name


def _arrow(d: float) -> str:
    return "▲" if d > 0 else "▼" if d < 0 else "–"


def _line(m: Metric) -> str:
    name = html.escape(m.label)
    if not m.ok:
        return f"• {name}: N/A — {html.escape(m.note)}"
    d, v = m.latest()
    unit = m.unit
    val = f"{v:,.{m.decimals}f}{unit}"
    if m.key == "fng":
        val += f" ({fng_rating(v)})"
    when = d.strftime("%Y-%m") if m.monthly else d.strftime("%m/%d")
    ch = m.change()
    if ch is None:
        diff = "대비 없음"
    else:
        _, _, dv, pct = ch
        base = "전월" if m.monthly else "전일"
        pct_s = f" ({pct:+.2f}%)" if pct is not None and m.key != "fng" else ""
        diff = f"{base}대비 {_arrow(dv)}{abs(dv):,.{m.decimals}f}{unit if m.key != 'fng' else ''}{pct_s}"
    warn = {"캐시": " ⚠캐시", "대체": " ⚠대체", "자체": " ⚠자체산출", "대용": " ⚠대용", "추정": " ※추정"}.get(m.note[:2], "")
    return f"• {name}: <b>{html.escape(val)}</b> · {diff} <i>[{when}]</i>{warn}"


def compose(daily: list[Metric], monthly: list[Metric], today) -> str:
    out = [f"📊 <b>시장 판단지수 리포트</b> — {today:%Y-%m-%d}({WD[today.weekday()]})", "", "<b>[일간]</b>"]
    out += [_line(m) for m in daily]
    out += ["", "<b>[월간]</b>"] + [_line(m) for m in monthly]
    notes = [f"{m.label}: {m.note}" for m in daily + monthly if m.note != "ok"]
    if notes:
        out += ["", "<i>주석</i>"] + [f"  – {html.escape(n)}" for n in notes]
    out += ["", "<i>[ ] 안은 해당 값의 기준일.</i>"]
    return "\n".join(out)


def _creds():
    tok, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 .env 에 설정되지 않았습니다")
    return tok, chat


def send(text: str, images: list) -> None:
    tok, chat = _creds()
    api = f"https://api.telegram.org/bot{tok}"
    r = requests.post(f"{api}/sendMessage", data={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                                  "disable_web_page_preview": True}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"sendMessage 실패: {r.status_code} {r.text[:200]}")
    for p in images:
        with open(p, "rb") as f:
            r = requests.post(f"{api}/sendPhoto", data={"chat_id": chat}, files={"photo": f}, timeout=60)
        if not r.ok:
            raise RuntimeError(f"sendPhoto 실패: {r.status_code} {r.text[:200]}")
