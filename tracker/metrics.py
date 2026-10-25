"""원천 시리즈 → 보고용 지표 (일간 3종, 월간 6종)와 전일/전월 대비 값."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class Metric:
    key: str
    label: str
    series: Optional[pd.Series]   # 일간: 일 단위, 월간: 월초 타임스탬프 인덱스
    unit: str = ""
    decimals: int = 2
    note: str = ""                # 수집 상태/주석
    monthly: bool = False

    @property
    def ok(self) -> bool:
        return self.series is not None and len(self.series.dropna()) >= 1

    def latest(self):
        s = self.series.dropna()
        return s.index[-1], float(s.iloc[-1])

    def change(self):
        """(기준일, 직전 기준일, 차이, 퍼센트) — 직전 관측이 없으면 None."""
        s = self.series.dropna()
        if len(s) < 2:
            return None
        cur, prev = float(s.iloc[-1]), float(s.iloc[-2])
        return s.index[-1], s.index[-2], cur - prev, (cur / prev - 1) * 100 if prev else None


def to_monthly(s: pd.Series) -> pd.Series:
    """월별 마지막 관측값, 인덱스는 월초."""
    g = s.groupby(s.index.to_period("M")).last()
    g.index = g.index.to_timestamp()
    return g


def buffett_us(equities: pd.Series, gdp: pd.Series, sp500: pd.Series) -> pd.Series:
    """미국 버핏지수(%) = 기업주식 시가총액(Z.1) / 명목 GDP.
    Z.1 은 분기 후 3개월 가량 늦게 공표되므로, 가장 가까운 분기말 값을 S&P500 변화율로 월별 보정(nowcast)한다."""
    sp_m = sp500.groupby(sp500.index.to_period("M")).last()
    sp_m.index = sp_m.index.to_timestamp()
    q_end = equities.copy()
    q_end.index = equities.index + pd.offsets.QuarterEnd(0)          # 분기 시작일 → 분기말
    anchors = pd.Series(q_end.values, index=q_end.index)
    anchors = anchors[(anchors.index >= sp500.index[0]) & (anchors.index <= sp500.index[-1])]
    gdp_m = gdp.resample("MS").ffill().reindex(sp_m.index, method="ffill")
    out = {}
    for m, px in sp_m.items():
        m_end = m + pd.offsets.MonthEnd(0)
        a = anchors.index[abs(anchors.index - m_end).argmin()]       # 가장 가까운 분기말
        a_px = sp500[:a].iloc[-1]
        mcap = anchors[a] * px / a_px / 1000                          # 백만달러 → 십억달러
        out[m] = mcap / gdp_m[m] * 100
    return pd.Series(out)


def buffett_kr(wb: pd.Series, kospi: pd.Series) -> pd.Series:
    """한국 버핏지수(%) = 세계은행 연말 시가총액/GDP 를 가장 가까운 연말 KOSPI 대비 변화율로 월 보정한 추정치."""
    k_m = to_monthly(kospi)
    anchors = wb[(wb.index >= kospi.index[0]) & (wb.index <= kospi.index[-1])]
    out = {}
    for m, px in k_m.items():
        m_end = m + pd.offsets.MonthEnd(0)
        a = anchors.index[abs(anchors.index - m_end).argmin()]
        out[m] = anchors[a] * px / kospi[:a].iloc[-1]
    return pd.Series(out)


def kr_cape_proxy(kospi: pd.Series) -> pd.Series:
    """한국 CAPE 대용: 월말 KOSPI(명목) ÷ 직전 10년(120개월) 평균. 이익 데이터가 아니라 가격 기준 장기 과열도."""
    k = to_monthly(kospi)
    return (k / k.rolling(120, min_periods=120).mean()).dropna()


def _trim(s, start="2020-01-01"):
    return None if s is None else s[s.index >= start]


def build(raw: dict) -> tuple[list[Metric], list[Metric]]:
    g = lambda k: raw[k][0]
    st = lambda k: raw[k][1]

    # 공포탐욕: CNN 이 정상이면 CNN, 아니면 자체산출 대체
    if g("fng") is not None and st("fng") == "ok":
        fng = Metric("fng", "공포탐욕지수", _trim(g("fng")), "", 1, "ok")
    elif g("fng_proxy") is not None:
        fng = Metric("fng", "공포탐욕지수", _trim(g("fng_proxy")), "", 1,
                     "자체산출(CNN 차단 → VIX·모멘텀·52주고점·안전자산 4요소)")
    else:
        fng = Metric("fng", "공포탐욕지수", None, "", 1, st("fng"))
    daily = [
        fng,
        Metric("sp500", "S&P500", _trim(g("sp500")), "", 2, st("sp500")),
        Metric("kospi", "KOSPI", _trim(g("kospi")), "", 2, st("kospi")),
    ]

    def monthly_of(k, scale=1.0):
        s = g(k)
        return None if s is None else _trim(to_monthly(s) * scale)

    # 한국 M2: ECOS(최신) 우선, 없으면 IMF(지연) 대체
    if g("kr_m2") is not None and st("kr_m2") == "ok":
        kr_m2 = Metric("kr_m2", "한국 M2", monthly_of("kr_m2", 1 / 1000), "조원", 1, "ok", True)
    else:
        kr_m2 = Metric("kr_m2", "한국 M2", monthly_of("kr_m2_imf", 1 / 1000), "조원", 1,
                       "대체: IMF 데이터(공표 지연). ECOS_API_KEY 설정 시 최신화", True)

    fed = g("fed_assets")
    bf_us = None
    note_bf = "추정: Z.1 분기값을 S&P500으로 월 보정"
    if all(g(k) is not None for k in ("us_equities", "us_gdp", "sp500")):
        bf_us = _trim(buffett_us(g("us_equities"), g("us_gdp"), g("sp500")))
    else:
        note_bf = "원천 데이터 없음"

    bf_kr = None
    note_bf_kr = "원천 데이터 없음"
    if g("kr_mcap_gdp") is not None and g("kospi") is not None:
        bf_kr = _trim(buffett_kr(g("kr_mcap_gdp"), g("kospi")))
        note_bf_kr = "추정: 세계은행 연말값을 KOSPI로 월 보정"

    kr_pe = _trim(kr_cape_proxy(g("kospi"))) if g("kospi") is not None else None

    monthly = [
        Metric("us_m2", "미국 M2", monthly_of("us_m2", 1 / 1000), "조$", 2, st("us_m2"), True),
        kr_m2,
        Metric("fed", "연준 자산", None if fed is None else _trim(to_monthly(fed) / 1e6), "조$", 3, st("fed_assets"), True),
        Metric("us_pe", "미국 Shiller PE", monthly_of("us_pe"), "배", 2, st("us_pe"), True),
        Metric("kr_pe", "한국 장기과열도(CAPE 대용)", kr_pe, "배", 2,
               "대용: KOSPI÷10년평균(이익 기준 Shiller PE 아님)", True),
        Metric("bf_us", "미국 버핏지수", bf_us, "%", 1, note_bf, True),
        Metric("bf_kr", "한국 버핏지수", bf_kr, "%", 1, note_bf_kr, True),
    ]
    return daily, monthly
