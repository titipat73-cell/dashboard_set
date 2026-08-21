#!/usr/bin/env python3
"""ดึงราคาล่าสุดของหุ้น SET/DR จาก Yahoo Finance แล้วเขียนลง docs/data.json
รันโดย GitHub Actions ทุกชั่วโมง (ดู .github/workflows/update-prices.yml)
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


def fetch(symbol: str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    meta = data["chart"]["result"][0]["meta"]
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    chg = round(price - prev, 4) if price is not None and prev else None
    chg_pct = round(chg / prev * 100, 2) if chg is not None and prev else None
    return {"price": price, "chg": chg, "chgPct": chg_pct}


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
    print(f"wrote {len(quotes)} quotes")


if __name__ == "__main__":
    main()
