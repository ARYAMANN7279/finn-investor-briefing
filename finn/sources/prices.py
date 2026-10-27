"""End-of-day price and volume from Yahoo Finance's public chart endpoint (the same data yfinance reads)."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

from .. import net


@dataclass
class Bar:
    date: str
    close: float
    volume: int


def parse_chart(payload: dict) -> list[Bar]:
    res = payload["chart"]["result"][0]
    ts = res.get("timestamp") or []
    q = res["indicators"]["quote"][0]
    bars = []
    for t, c, v in zip(ts, q["close"], q["volume"]):
        if c is None or v is None:
            continue
        day = dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=5, minutes=30))).date().isoformat()
        bars.append(Bar(day, float(c), int(v)))
    return bars


def fetch(symbol: str, range_: str = "6mo", ttl: float = 3 * 3600) -> list[Bar]:
    sym = symbol.upper()
    if not sym.endswith((".NS", ".BO")):
        sym += ".NS"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={range_}&interval=1d"
    return parse_chart(json.loads(net.get(url, ttl=ttl)))


IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def completed(bars: list[Bar], now: dt.datetime | None = None) -> list[Bar]:
    """End-of-day data only: drop today's bar while the NSE session is still open (it closes 15:30 IST), because
    a half-day volume would look like a collapse."""
    now = (now or dt.datetime.now(IST)).astimezone(IST)
    if bars and bars[-1].date == now.date().isoformat() and (now.hour, now.minute) < (15, 45):
        return bars[:-1]
    return bars


def unusual(bars: list[Bar], vol_mult: float = 2.0, move_pct: float = 4.0, lookback: int = 20) -> dict:
    """Latest day versus the previous `lookback` days: volume multiple of the average, and the one-day price change."""
    if len(bars) < lookback + 2:
        raise ValueError("not enough history")
    last, prev = bars[-1], bars[-2]
    window = bars[-lookback - 1:-1]
    avg = sum(b.volume for b in window) / len(window)
    mult = last.volume / avg if avg else 0.0
    move = (last.close / prev.close - 1) * 100
    return {"date": last.date, "close": last.close, "move_pct": round(move, 2), "volume": last.volume,
            "avg_volume": round(avg), "vol_multiple": round(mult, 2),
            "volume_alert": mult >= vol_mult, "move_alert": abs(move) >= move_pct}


def daily_stats(bars: list[Bar], days: int = 20, lookback: int = 20) -> list[dict]:
    """For each of the last `days` completed sessions: close, one-day move and volume as a multiple of the previous `lookback`
    sessions' average. The app uses this to re-evaluate any threshold the user sets without asking a server."""
    out = []
    for i in range(max(lookback + 1, len(bars) - days), len(bars)):
        window = bars[i - lookback:i]
        avg = sum(b.volume for b in window) / lookback
        out.append({"date": bars[i].date, "close": round(bars[i].close, 2),
                    "move_pct": round((bars[i].close / bars[i - 1].close - 1) * 100, 2),
                    "vol_multiple": round(bars[i].volume / avg, 2) if avg else 0.0})
    return out
