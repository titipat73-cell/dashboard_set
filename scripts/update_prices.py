#!/usr/bin/env python3
"""ดึงราคา + คำนวณ 'แผนเทคนิค' (Entry/TP/SL) จากกราฟราคาจริง ณ เวลานั้น ๆ
แผนเทคนิคเป็นตัวหลัก ส่วนเป้าหมายจากบทวิเคราะห์เป็นข้อมูลเสริม (อยู่ฝั่ง frontend)
รันโดย GitHub Actions ทุกชั่วโมง
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


def atr(highs, lows, closes, n=14):
    """Average True Range แบบง่าย (average ตรง ๆ ไม่ทำ Wilder smoothing หลายรอบ)"""
    if len(closes) < n + 1:
        return None
    trs = []
    for i in range(-n, 0):
        h, l, prev_c = highs[i], lows[i], closes[i - 1]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    return round(sum(trs) / n, 4)


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


def build_plan(price, atr14, high20, low20, r):
    """คำนวณแผน Entry/TP/SL จากกราฟราคาจริง — ใช้ ATR (ความผันผวนจริง) + แนวรับ-แนวต้าน (สูงสุด/ต่ำสุด 20 วัน)
    entry: ราคาปัจจุบัน ± ครึ่งหนึ่งของ ATR (โซนเข้าซื้อตามราคาตลาด)
    sl: แนวรับ 20 วัน ถ้าอยู่ใกล้ราคาไม่เกิน 2×ATR ไม่งั้นใช้ price - 2×ATR แทน (กันตัดขาดทุนเร็ว/ช้าเกินไป)
    tp1: แนวต้าน 20 วัน ถ้าอยู่ใกล้ ไม่งั้นใช้ price + r×ATR
    tp2: price + (r*1.7)×ATR เป็นเป้าขยายผล
    """
    if atr14 is None or atr14 <= 0:
        return None
    entry_low = round(price - atr14 * 0.5, 4)
    entry_high = round(price + atr14 * 0.5, 4)

    sl_candidate = low20 if low20 is not None else price - atr14 * 2
    sl = round(sl_candidate, 4) if (price - sl_candidate) <= atr14 * 2.2 else round(price - atr14 * 2, 4)

    tp1_candidate = high20 if high20 is not None else price + atr14 * r
    tp1 = round(tp1_candidate, 4) if (tp1_candidate - price) <= atr14 * (r + 1) and tp1_candidate > price else round(price + atr14 * r, 4)

    tp2 = round(price + atr14 * r * 1.7, 4)
    if tp2 <= tp1:
        tp2 = round(tp1 + atr14 * 0.8, 4)

    risk = max(price - sl, 0.0001)
    reward = tp1 - price
    rr = round(reward / risk, 2) if risk > 0 else None

    return {
        "entryLow": entry_low, "entryHigh": entry_high,
        "tp1": tp1, "tp2": tp2, "sl": sl, "rr": rr,
    }


def fetch(symbol: str):
    meta_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
    meta = fetch_json(meta_url)["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    chg = round(price - prev, 4) if price is not None and prev else None
    chg_pct = round(chg / prev * 100, 2) if chg is not None and prev else None

    sma20 = rsi14 = atr14 = high20 = low20 = None
    trend = rsi_txt = signal = "ข้อมูลไม่พอคำนวณ"
    plan = None
    try:
        hist_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=3mo&interval=1d"
        hist = fetch_json(hist_url)["chart"]["result"][0]
        q = hist["indicators"]["quote"][0]
        closes = q.get("close") or []
        highs = q.get("high") or []
        lows = q.get("low") or []
        # ตัดช่วงที่มีค่า None ทิ้ง (วันหยุดตลาด/ข้อมูลขาด) โดยจับคู่ index เดียวกัน
        rows = [(c, h, l) for c, h, l in zip(closes, highs, lows) if None not in (c, h, l)]
        if rows:
            closes = [x[0] for x in rows]
            highs = [x[1] for x in rows]
            lows = [x[2] for x in rows]
            ref_price = price if price is not None else closes[-1]
            sma20 = sma(closes, 20)
            rsi14 = rsi(closes, 14)
            atr14 = atr(highs, lows, closes, 14)
            high20 = max(highs[-20:]) if len(highs) >= 20 else max(highs)
            low20 = min(lows[-20:]) if len(lows) >= 20 else min(lows)
            trend = trend_label(ref_price, sma20)
            rsi_txt = rsi_label(rsi14)
            signal = signal_label(ref_price, sma20, rsi14)
            plan = build_plan(ref_price, atr14, high20, low20, r=1.5)
    except Exception as e:
        print(f"tech-indicator skip {symbol}: {e}")

    return {
        "price": price, "chg": chg, "chgPct": chg_pct,
        "sma20": sma20, "rsi14": rsi14, "atr14": atr14,
        "high20": high20, "low20": low20,
        "trend": trend, "rsiLabel": rsi_txt, "signal": signal,
        "plan": plan,
    }


def main():
    quotes = {}
    for sym in SYMBOLS:
        key = sym.replace(".BK", "")
        try:
            quotes[key] = fetch(sym)
        except Exception as e:
            print(f"skip {sym}: {e}")
        time.sleep(1)

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
    print(f"wrote {len(quotes)} quotes with technical plan")


if __name__ == "__main__":
    main()


