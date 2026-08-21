#!/usr/bin/env python3
"""ดึงราคาล่าสุด + คำนวณสัญญาณเทคนิค (SMA20, RSI14, เทรนด์) จาก Yahoo Finance
แล้วเขียนลง docs/data.json — รันโดย GitHub Actions ทุกชั่วโมง
"""
import json
import time
import urllib.request
from datetime import datetime, timezone, timedelta

SYMBOLS = [
    "BDMS.BK", "KKP.BK", "DELTA.BK", "AWC.BK", "BANPU.BK", "DOHOME.BK",
    "EPG.BK", "CPAXT.BK", "COCOCO.BK", "KTC.BK", "BBGI.BK",
    "AAPL80.BK", "TSLA80.BK", "BABA80.BK",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (dashboard price updater)"}


def fetch_json(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def sma(values, n):
    if len(values) < n:
        return None
    return round(sum(values[-n:]) / n, 4)


def rsi(values, n=14):
    """RSI14 แบบง่าย (Wilder's smoothing แบบเรียบง่าย ไม่ compound หลายรอบ)"""
    if len(values) < n + 1:
        return None
    gains, losses = [], []
    for i in range(-n, 0):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / n
    avg_loss = sum(losses) / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def trend_label(price, sma20):
    if sma20 is None:
        return "ข้อมูลไม่พอคำนวณ"
    diff_pct = (price - sma20) / sma20 * 100
    if diff_pct >= 2:
        return f"ขาขึ้น (เหนือ SMA20 +{diff_pct:.1f}%)"
    if diff_pct <= -2:
        return f"ขาลง (ต่ำกว่า SMA20 {diff_pct:.1f}%)"
    return f"แกว่งตัว (ใกล้ SMA20 {diff_pct:+.1f}%)"


def rsi_label(rsi_val):
    if rsi_val is None:
        return "ข้อมูลไม่พอคำนวณ"
    if rsi_val >= 70:
        return f"RSI {rsi_val} · โซนซื้อมากไป (Overbought)"
    if rsi_val <= 30:
        return f"RSI {rsi_val} · โซนขายมากไป (Oversold)"
    return f"RSI {rsi_val} · ปกติ"


def signal_label(price, sma20, rsi_val):
    """สัญญาณรวมแบบง่าย — อ้างอิงจากราคาจริงล้วน ๆ ไม่ใช่คำแนะนำการลงทุน"""
    if sma20 is None or rsi_val is None:
        return "ข้อมูลไม่พอวิเคราะห์"
    if rsi_val <= 30 and price <= sma20:
        return "จับตาโซนสะสม (Oversold + ต่ำกว่าเส้นค่าเฉลี่ย)"
    if rsi_val >= 70 and price >= sma20:
        return "ระวังไล่ราคา (Overbought + เหนือเส้นค่าเฉลี่ย)"
    if price > sma20:
        return "โมเมนตัมเป็นบวก"
    if price < sma20:
        return "โมเมนตัมเป็นลบ"
    return "ไม่มีสัญญาณสุดโต่ง"


def fetch(symbol: str):
    # ราคาล่าสุด
    meta_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
    meta = fetch_json(meta_url)["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    chg = round(price - prev, 4) if price is not None and prev else None
    chg_pct = round(chg / prev * 100, 2) if chg is not None and prev else None

    # ราคาย้อนหลัง 3 เดือน สำหรับคำนวณ SMA/RSI
    sma20 = rsi14 = None
    trend = rsi_txt = signal = "ข้อมูลไม่พอคำนวณ"
    try:
        hist_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=3mo&interval=1d"
        hist = fetch_json(hist_url)["chart"]["result"][0]
        closes = hist["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        if closes:
            ref_price = price if price is not None else closes[-1]
            sma20 = sma(closes, 20)
            rsi14 = rsi(closes, 14)
            trend = trend_label(ref_price, sma20)
            rsi_txt = rsi_label(rsi14)
            signal = signal_label(ref_price, sma20, rsi14)
    except Exception as e:
        print(f"tech-indicator skip {symbol}: {e}")

    return {
        "price": price, "chg": chg, "chgPct": chg_pct,
        "sma20": sma20, "rsi14": rsi14,
        "trend": trend, "rsiLabel": rsi_txt, "signal": signal,
    }


def main():
    quotes = {}
    for sym in SYMBOLS:
        key = sym.replace(".BK", "")
        try:
            quotes[key] = fetch(sym)
        except Exception as e:  # ตัวไหนดึงไม่ได้ ข้ามไป ไม่ให้ทั้งไฟล์พัง
            print(f"skip {sym}: {e}")
        time.sleep(1)  # สุภาพกับ API

    bkk = timezone(timedelta(hours=7))
    now = datetime.now(bkk)
    thai_days = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
    thai_str = (
        f"{thai_days[now.weekday()]} {now.day:02d}/{now.month:02d}/{now.year + 543} "
        f"{now.strftime('%H:%M')} น. (เวลาไทย)"
    )
    out = {
        "updated": thai_str,
        "updated_iso": datetime.now(timezone.utc).isoformat(),
        "quotes": quotes,
    }
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"wrote {len(quotes)} quotes with technical indicators")


if __name__ == "__main__":
    main()

