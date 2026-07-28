#!/usr/bin/env python3
"""Fetch latest WTI/Brent crude oil prices from Yahoo Finance and regenerate index.html.

No AI involved — pure data fetch + template fill. Meant to be run on a schedule
(see .github/workflows/update.yml) by GitHub Actions.
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "scripts" / "template.html"
OUTPUT_PATH = ROOT / "index.html"

USER_AGENT = "Mozilla/5.0 (compatible; oil-price-chart-bot/1.0)"

SYMBOLS = {"wti": "CL=F", "brent": "BZ=F"}


def fetch_json(url: str) -> dict:
    # Shell out to curl (system CA store) instead of urllib — avoids Python's
    # own cert store being out of date on some platforms/runners.
    result = subprocess.run(
        ["curl", "-sL", "-A", USER_AGENT, "--max-time", "30", url],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def fetch_history(symbol: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5y&interval=1d"
    data = fetch_json(url)
    result = data["chart"]["result"][0]
    timestamps = result["timestamp"]
    closes = result["indicators"]["quote"][0]["close"]
    by_date = {}
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        date = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        by_date[date] = round(close, 2)
    return by_date


def fetch_live(symbol: str) -> tuple[float, float]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
    data = fetch_json(url)
    meta = data["chart"]["result"][0]["meta"]
    price = meta["regularMarketPrice"]
    prev_close = meta["chartPreviousClose"]
    delta_pct = (price - prev_close) / prev_close * 100
    return round(price, 2), round(delta_pct, 2)


def merge_series(wti: dict, brent: dict) -> list:
    all_dates = sorted(set(wti) | set(brent))
    merged = []
    last_w = last_b = None
    for d in all_dates:
        if d in wti:
            last_w = wti[d]
        if d in brent:
            last_b = brent[d]
        if last_w is not None and last_b is not None:
            merged.append([d, last_w, last_b])
    return merged


def build_note(as_of_date: str, chart_end_date: str, wti_delta: float, brent_delta: float) -> str:
    note = (
        "数据来源:Yahoo Finance(WTI/布伦特原油期货连续合约,近似现货价)。"
        f"图表历史数据截至 {chart_end_date}。"
        f"上方两个统计卡片为 {as_of_date} 最新报价,由 GitHub Actions 每日自动抓取更新,过程不经过 AI。"
    )
    big_move = max(abs(wti_delta), abs(brent_delta))
    if big_move > 3:
        note += " 今日价格波动较大,具体驱动因素请参考财经新闻,本页面不做归因分析。"
    return note


def main():
    wti_hist = fetch_history(SYMBOLS["wti"])
    brent_hist = fetch_history(SYMBOLS["brent"])
    merged = merge_series(wti_hist, brent_hist)

    wti_live, wti_delta = fetch_live(SYMBOLS["wti"])
    brent_live, brent_delta = fetch_live(SYMBOLS["brent"])

    date_range = f"{merged[0][0]} 至 {merged[-1][0]}"
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    note = build_note(as_of, merged[-1][0], wti_delta, brent_delta)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = (
        template
        .replace("__DATE_RANGE__", date_range)
        .replace("__DATA_JSON__", json.dumps(merged, separators=(",", ":")))
        .replace("__WTI_LIVE__", str(wti_live))
        .replace("__WTI_DELTA_PCT__", str(wti_delta))
        .replace("__BRENT_LIVE__", str(brent_live))
        .replace("__BRENT_DELTA_PCT__", str(brent_delta))
        .replace("__NOTE_TEXT__", note)
        .replace("__UPDATED_AT__", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    )

    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} — WTI ${wti_live} ({wti_delta:+.2f}%), Brent ${brent_live} ({brent_delta:+.2f}%)")


if __name__ == "__main__":
    main()
