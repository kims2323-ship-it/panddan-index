"""데이터 수집. 원천별 fetch → data/*.csv 캐시. 실패 시 캐시로 대체하고 상태를 기록한다."""
from __future__ import annotations

import datetime as dt
import io
import re
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

import pandas as pd
import requests

from . import env

START = "2020-01-01"
DATA = env.ROOT / "data"
TIMEOUT = 40

# ECOS 코드: (통계표코드, 주기, 항목코드). `python3 main.py ecos-find <키워드>` 로 찾는다.
ECOS_CODES = {
    "kr_m2": ("101Y004", "M", "BBHA00"),   # M2(광의통화) 평잔 원계열, 십억원 — ECOS_API_KEY 필요
}


class SourceError(Exception):
    pass


def _get(url: str, **kw) -> requests.Response:
    last = None
    for i in range(3):
        try:
            r = requests.get(url, timeout=TIMEOUT, **kw)
        except requests.RequestException as e:
            last = f"{type(e).__name__}"
        else:
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        time.sleep(3 * (i + 1))
    raise SourceError(f"{last} ({url.split('?')[0]})")


def fred(series_id: str, start: str = START) -> pd.Series:
    r = _get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series_id, "cosd": start})
    df = pd.read_csv(io.StringIO(r.text), na_values=".")
    return pd.Series(df.iloc[:, 1].values, index=pd.to_datetime(df.iloc[:, 0]), name=series_id).dropna()


def cnn_fng() -> pd.Series:
    # CNN 은 봇 트래픽을 막는 경우가 있다(HTTP 418). 우회하지 않고 실패 시 캐시를 쓴다.
    r = _get(f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{START}")
    pts = r.json()["fear_and_greed_historical"]["data"]
    s = pd.Series({pd.to_datetime(p["x"], unit="ms").normalize(): float(p["y"]) for p in pts})
    return s.sort_index()


def shiller_pe_us() -> pd.Series:
    html = _get("https://www.multpl.com/shiller-pe/table/by-month").text
    rows = re.findall(r"<td>([A-Z][a-z]{2} \d{1,2}, \d{4})</td>\s*<td>\s*(?:&#x2002;)?\s*([\d.]+)", html)
    if not rows:
        raise SourceError("multpl 파싱 실패")
    s = pd.Series({pd.to_datetime(d, format="%b %d, %Y"): float(v) for d, v in rows}).sort_index()
    return s[s.index >= START]


def ecos(key_name: str) -> pd.Series:
    code = ECOS_CODES.get(key_name)
    if code is None:
        raise SourceError("ECOS 코드 미설정")
    key = env.get("ECOS_API_KEY")
    if not key:
        raise SourceError("ECOS_API_KEY 미설정")
    stat, cycle, item = code
    today = dt.date.today()
    s0, e0 = pd.Timestamp(START), pd.Timestamp(today)
    fmt = {"D": lambda t: t.strftime("%Y%m%d"), "M": lambda t: t.strftime("%Y%m"),
           "Q": lambda t: f"{t.year}Q{(t.month - 1) // 3 + 1}"}[cycle]
    url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/100000/"
           f"{stat}/{cycle}/{fmt(s0)}/{fmt(e0)}/{item}")
    j = _get(url).json()
    rows = (j.get("StatisticSearch") or {}).get("row")
    if not rows:
        raise SourceError("ECOS: " + (j.get("RESULT") or {}).get("MESSAGE", "빈 응답").strip())

    def parse(t: str) -> pd.Timestamp:
        if cycle == "D":
            return pd.to_datetime(t, format="%Y%m%d")
        if cycle == "M":
            return pd.to_datetime(t, format="%Y%m")
        return pd.Period(t, freq="Q").start_time

    return pd.Series({parse(r["TIME"]): float(r["DATA_VALUE"]) for r in rows if r.get("DATA_VALUE")}).sort_index()


def naver_kospi() -> pd.Series:
    """네이버 금융 공개 시세 엔드포인트 (키 불필요). 한국 CAPE 대용 계산용으로 2010년부터."""
    import ast
    r = _get("https://api.finance.naver.com/siseJson.naver",
             params={"symbol": "KOSPI", "requestType": 1, "startTime": "20100101",
                     "endTime": dt.date.today().strftime("%Y%m%d"), "timeframe": "day"})
    try:
        rows = ast.literal_eval(r.text.strip())[1:]
        return pd.Series({pd.to_datetime(x[0], format="%Y%m%d"): float(x[4]) for x in rows}).sort_index()
    except (ValueError, SyntaxError, IndexError):
        raise SourceError("네이버 KOSPI 파싱 실패")


def imf_kr_m2() -> pd.Series:
    """IMF IFS 한국 광의통화(월, 백만원) → 십억원. 공표 지연이 커서 ECOS 실패 시 대체용."""
    j = _get("https://api.db.nomics.world/v22/series/IMF/IFS/M.KR.FMB_XDC", params={"observations": 1}).json()
    docs = (j.get("series") or {}).get("docs") or []
    if not docs:
        raise SourceError("IMF 한국 M2 없음")
    d = docs[0]
    return pd.Series({pd.to_datetime(p): v / 1000 for p, v in zip(d["period"], d["value"]) if isinstance(v, (int, float))}).sort_index()


def wb_kr_mcap_gdp() -> pd.Series:
    """세계은행 한국 상장사 시가총액/GDP(%) 연간 → 연말(12-31) 인덱스."""
    j = _get("https://api.worldbank.org/v2/country/KOR/indicator/CM.MKT.LCAP.GD.ZS",
             params={"format": "json", "per_page": 30, "date": "2015:2030"}).json()
    rows = j[1] if isinstance(j, list) and len(j) > 1 and j[1] else []
    s = pd.Series({pd.Timestamp(int(r["date"]), 12, 31): float(r["value"]) for r in rows if r["value"] is not None})
    if s.empty:
        raise SourceError("세계은행 응답 없음")
    return s.sort_index()


def fng_proxy() -> pd.Series:
    """CNN 대체 자체산출 공포탐욕(0~100): VIX·모멘텀·52주고점 근접도·주식-채권 상대수익률의 1년 롤링 백분위 평균."""
    sp = pd.read_csv(DATA / "sp500.csv", index_col=0, parse_dates=True)["value"]
    vix = pd.read_csv(DATA / "vix.csv", index_col=0, parse_dates=True)["value"].reindex(sp.index).ffill()
    y10 = pd.read_csv(DATA / "dgs10.csv", index_col=0, parse_dates=True)["value"].reindex(sp.index).ffill()

    def rank(x: pd.Series) -> pd.Series:
        return x.rolling(252, min_periods=120).apply(lambda w: (w <= w[-1]).mean() * 100, raw=True)

    comps = [
        100 - rank(vix),                                    # 변동성: 낮을수록 탐욕
        rank(sp / sp.rolling(125).mean() - 1),              # 모멘텀: 125일선 대비
        rank(sp / sp.rolling(252, min_periods=120).max()),  # 52주 고점 근접도
        rank(sp.pct_change(20) + 8 * y10.diff(20) / 100),   # 안전자산 선호: 주식 − 채권(듀레이션 8 근사) 20일 수익률
    ]
    return pd.concat(comps, axis=1).mean(axis=1).rolling(5).mean().dropna().round(1)


def cached(name: str, fetch: Callable[[], pd.Series]) -> Tuple[Optional[pd.Series], str]:
    """(series, status). status: 'ok' 또는 사유 문자열(캐시 사용/없음)."""
    DATA.mkdir(exist_ok=True)
    path = DATA / f"{name}.csv"
    old = None
    if path.exists():
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        old = df.iloc[:, 0]
    try:
        new = fetch()
    except SourceError as e:
        return (old, f"캐시 사용: {e}") if old is not None else (None, str(e))
    merged = new if old is None else new.combine_first(old)
    merged = merged.sort_index()
    merged.to_csv(path, header=["value"], index_label="date")
    return merged, "ok"


def collect() -> dict:
    """원천 시리즈 전부 수집. {name: (series|None, status)}"""
    jobs = {
        "fng": cnn_fng,
        "sp500": lambda: fred("SP500", "2018-01-01"),
        "vix": lambda: fred("VIXCLS", "2018-01-01"),
        "dgs10": lambda: fred("DGS10", "2018-01-01"),
        "kospi": naver_kospi,
        "us_m2": lambda: fred("M2SL"),
        "fed_assets": lambda: fred("WALCL"),
        "us_pe": shiller_pe_us,
        "us_gdp": lambda: fred("GDP", "2019-01-01"),
        "us_equities": lambda: fred("BOGZ1LM893064105Q", "2019-10-01"),
        "kr_m2": lambda: ecos("kr_m2"),
        "kr_m2_imf": imf_kr_m2,
        "kr_mcap_gdp": wb_kr_mcap_gdp,
    }
    out = {}
    for name, fn in jobs.items():
        out[name] = cached(name, fn)
        time.sleep(0.5)
    out["fng_proxy"] = cached("fng_proxy", fng_proxy) if out["sp500"][0] is not None else (None, "S&P500 없음")
    return out
