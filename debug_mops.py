#!/usr/bin/env python3
"""本機除錯用：直接測試 MOPS 頁面結構，不需要跑 GitHub Actions"""
import requests, urllib3
urllib3.disable_warnings()

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9",
    "Referer": "https://mopsov.twse.com.tw/mops/web/ezsearch",
}
s = requests.Session()
s.headers.update(headers)
s.verify = False
url = "https://mopsov.twse.com.tw/mops/web/ezsearch"

print("=== GET 頁面 ===")
r = s.get(url, timeout=15)
print(f"status: {r.status_code}, len: {len(r.text)}")

from bs4 import BeautifulSoup
soup = BeautifulSoup(r.text, "lxml")
print("\n--- form input 欄位 ---")
for inp in soup.find_all(["input", "select"]):
    print(f"  name={inp.get('name')!r:30} type={inp.get('type')!r:10} value={str(inp.get('value',''))[:40]!r}")

print("\n=== POST 搜尋（step=1）===")
for step_val in ["1", "2"]:
    form_data = {
        "step": step_val, "keyword": "發行", "co_id": "",
        "TYPEK": "all", "LEG": "TW", "RADIO_CM": "1", "AN": "1",
        "SDATE": "", "EDATE": "",
    }
    r2 = s.post(url, data=form_data, timeout=20)
    soup2 = BeautifulSoup(r2.text, "lxml")
    tables = soup2.find_all("table")
    print(f"\nstep={step_val} → status:{r2.status_code} len:{len(r2.text)} tables:{len(tables)}")
    body = soup2.find("body")
    text = (body.get_text(separator=" ", strip=True) if body else r2.text)[:1000]
    print("body 前1000字:", text)
    if tables:
        print("\n--- 第一個 table 結構 ---")
        for row in tables[0].find_all("tr")[:5]:
            cells = row.find_all(["td","th"])
            print("  ", [c.get_text(strip=True)[:25] for c in cells])
        break
