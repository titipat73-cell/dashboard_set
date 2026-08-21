#!/usr/bin/env python3
"""(ทางเลือก) ให้ Claude สรุปมุมมองสั้น ๆ ต่อหุ้นแต่ละตัว โดยใช้ราคา+สัญญาณเทคนิคที่คำนวณไว้แล้ว
รันเฉพาะเมื่อมี secret ชื่อ ANTHROPIC_API_KEY เท่านั้น (ดู .github/workflows/update-prices.yml)
มีค่าใช้จ่ายตามการเรียก API จริง — ใช้ Haiku (โมเดลเล็ก) เพื่อประหยัด
"""
import json
import os
import sys
import time
import urllib.request

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MODEL = "claude-haiku-4-5-20251001"
API_URL = "https://api.anthropic.com/v1/messages"


def ask_claude(prompt: str) -> str:
    body = json.dumps({
        "model": MODEL,
        "max_tokens": 120,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    return " ".join(parts).strip()


def main():
    if not API_KEY:
        print("ANTHROPIC_API_KEY not set — skip AI analysis (ปกติถ้ายังไม่ได้เปิดใช้ฟีเจอร์นี้)")
        return

    with open("docs/data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    quotes = data.get("quotes", {})
    for sym, q in quotes.items():
        price = q.get("price")
        chg_pct = q.get("chgPct")
        trend = q.get("trend")
        rsi_label = q.get("rsiLabel")
        if price is None:
            continue
        prompt = (
            f"หุ้น {sym} ราคาล่าสุด {price} บาท เปลี่ยนแปลง {chg_pct}% "
            f"เทรนด์ราคาเทียบเส้นค่าเฉลี่ย: {trend} · {rsi_label}\n"
            "สรุปมุมมองสั้น ๆ ไม่เกิน 2 ประโยคภาษาไทย เป็นข้อสังเกตเชิงข้อมูล ไม่ใช่คำแนะนำให้ซื้อขาย "
            "ห้ามใช้คำว่า 'แนะนำให้ซื้อ' หรือ 'แนะนำให้ขาย' โดยตรง"
        )
        try:
            note = ask_claude(prompt)
            quotes[sym]["aiNote"] = note
        except Exception as e:
            print(f"AI note failed for {sym}: {e}", file=sys.stderr)
        time.sleep(1)

    data["quotes"] = quotes
    data["aiNotesUpdated"] = True
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("wrote AI notes")


if __name__ == "__main__":
    main()
