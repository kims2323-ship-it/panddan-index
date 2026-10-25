#!/usr/bin/env python3
"""사용법:
  python3 main.py                # 수집 → 차트 → 텔레그램 전송
  python3 main.py --dry-run      # 전송 없이 메시지만 출력 (차트는 output/ 에 생성)
  python3 main.py ecos-find 키워드   # ECOS 통계표/항목 코드 찾기 (ECOS_API_KEY 필요)
"""
from __future__ import annotations

import datetime as dt
import sys

import requests

from tracker import charts, env, metrics, report, sources


def ecos_find(word: str) -> None:
    key = env.get("ECOS_API_KEY")
    if not key:
        sys.exit("ECOS_API_KEY 가 .env 에 필요합니다")
    j = requests.get(f"https://ecos.bok.or.kr/api/StatisticTableList/{key}/json/kr/1/2000/", timeout=60).json()
    for r in (j.get("StatisticTableList") or {}).get("row", []):
        if word in r["STAT_NAME"] and r["SRCH_YN"] == "Y":
            print(r["STAT_CODE"], r["CYCLE"], r["STAT_NAME"])


def main() -> int:
    if len(sys.argv) > 2 and sys.argv[1] == "ecos-find":
        ecos_find(sys.argv[2]); return 0
    dry = "--dry-run" in sys.argv
    today = dt.date.today()
    daily, monthly = metrics.build(sources.collect())
    stamp = f"{today:%Y-%m-%d}"
    imgs = [charts.daily(daily, stamp), charts.monthly(monthly, stamp)]
    text = report.compose(daily, monthly, today)
    if dry:
        print(text); print("\n차트:", *imgs)
        return 0
    report.send(text, imgs)
    print("텔레그램 전송 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
