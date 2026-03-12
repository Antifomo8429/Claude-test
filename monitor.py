#!/usr/bin/env python3
"""
MOPS 公告關鍵字追蹤器
監控台灣公開資訊觀測站 (https://mopsov.twse.com.tw/mops/web/ezsearch)，
當搜尋結果出現新公告時透過 Discord Webhook、Telegram 或 LINE Notify 發送通知。

用法:
  python monitor.py           # 持續輪詢
  python monitor.py --once    # 單次執行後結束
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import urllib3
import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── 路徑設定 ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"
SEEN_FILE = BASE_DIR / "seen_announcements.json"

# ── 瀏覽器 Headers（避免 403）────────────────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://mopsov.twse.com.tw/mops/web/ezsearch",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ── 設定 ─────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        log.error("找不到 config.json，請參考 README 建立設定檔")
        sys.exit(1)
    with CONFIG_FILE.open(encoding="utf-8") as f:
        return json.load(f)


# ── 已見公告狀態 ──────────────────────────────────────────────────────────────

def load_seen() -> set:
    if not SEEN_FILE.exists():
        return set()
    with SEEN_FILE.open(encoding="utf-8") as f:
        return set(json.load(f))


def save_seen(seen: set) -> None:
    with SEEN_FILE.open("w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=2)


# ── MOPS 爬取 ─────────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    session.verify = False  # MOPS 憑證缺少 Subject Key Identifier，需略過驗證
    return session


def fetch_search_results(session: requests.Session, base_url: str, keyword: str) -> str | None:
    """
    對 MOPS ezsearch 發出搜尋請求，回傳 HTML。
    先 GET 頁面（取得 session cookies），再 POST 帶關鍵字。
    若失敗回傳 None。
    """
    try:
        # Step 1: GET 頁面取得 session / CSRF cookies
        get_resp = session.get(base_url, timeout=15)
        get_resp.raise_for_status()

        # Step 2: POST 搜尋表單
        # MOPS ezsearch 常見的表單欄位名稱，依實際頁面 HTML 調整
        form_data = {
            "encodeURIComponent": "1",
            "step": "1",
            "firstin": "1",
            "off": "1",
            "keyword": keyword,
            "co_id": "",
            "TYPEK": "all",
        }
        post_resp = session.post(base_url, data=form_data, timeout=20)
        post_resp.raise_for_status()
        return post_resp.text

    except requests.RequestException as e:
        log.warning("無法取得 MOPS 頁面（關鍵字：%s）：%s", keyword, e)
        return None


def parse_announcements(html: str, keyword: str) -> list[dict]:
    """
    解析 HTML，從結果表格中擷取公告資訊。
    回傳公告 dict 列表，每筆包含 id、company、title、date、url。
    """
    soup = BeautifulSoup(html, "lxml")
    results = []

    # MOPS ezsearch 結果通常放在 <table> 內
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            # 嘗試從各欄取出資料（欄位順序依實際頁面而定）
            try:
                # 常見欄位排列：序號 | 公司代號 | 公司名稱 | 公告標題 | 日期 | ...
                link_tag = row.find("a", href=True)
                title_cell = cells[3] if len(cells) > 3 else cells[-1]
                date_cell = cells[-1]

                title = title_cell.get_text(strip=True)
                date = date_cell.get_text(strip=True)
                company = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                co_id = cells[1].get_text(strip=True) if len(cells) > 1 else ""

                if not title:
                    continue

                href = ""
                if link_tag:
                    href = link_tag["href"]
                    if href.startswith("/"):
                        href = "https://mopsov.twse.com.tw" + href

                # 以「公司代號 + 日期 + 標題前20字」作為唯一 ID
                ann_id = f"{co_id}_{date}_{title[:20]}"

                results.append({
                    "id": ann_id,
                    "company": company,
                    "title": title,
                    "date": date,
                    "url": href,
                    "keyword": keyword,
                })
            except (IndexError, AttributeError):
                continue

    log.info("關鍵字「%s」：解析到 %d 筆公告", keyword, len(results))
    return results


def filter_new(announcements: list[dict], seen: set) -> list[dict]:
    return [a for a in announcements if a["id"] not in seen]


# ── 通知 ──────────────────────────────────────────────────────────────────────

def format_message(matches: list[dict], keyword: str) -> str:
    header = f"🔔 MOPS 公告提醒 — 關鍵字「{keyword}」\n共 {len(matches)} 則新公告\n"
    items = []
    for m in matches:
        item = (
            f"\n📋 {m['company']}\n"
            f"📝 {m['title']}\n"
            f"📅 {m['date']}\n"
        )
        if m["url"]:
            item += f"🔗 {m['url']}\n"
        items.append(item)
    return header + "\n".join(items)


def notify_telegram(matches: list[dict], keyword: str, cfg: dict) -> None:
    token = cfg.get("bot_token", "")
    chat_id = cfg.get("chat_id", "")
    if not token or not chat_id or token == "YOUR_BOT_TOKEN":
        log.warning("Telegram 設定未填寫，略過通知")
        return

    text = format_message(matches, keyword)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        resp.raise_for_status()
        log.info("Telegram 通知已發送（關鍵字：%s，%d 筆）", keyword, len(matches))
    except requests.RequestException as e:
        log.error("Telegram 通知失敗：%s", e)


def notify_discord(matches: list[dict], keyword: str, cfg: dict) -> None:
    webhook_url = cfg.get("webhook_url", "")
    if not webhook_url or webhook_url == "YOUR_DISCORD_WEBHOOK_URL":
        log.warning("Discord Webhook 設定未填寫，略過通知")
        return

    content = format_message(matches, keyword)
    # Discord 單則訊息上限 2000 字元
    for chunk in [content[i:i+2000] for i in range(0, len(content), 2000)]:
        try:
            resp = requests.post(webhook_url, json={"content": chunk}, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.error("Discord 通知失敗：%s", e)
            return
    log.info("Discord 通知已發送（關鍵字：%s，%d 筆）", keyword, len(matches))


def notify_line(matches: list[dict], keyword: str, cfg: dict) -> None:
    token = cfg.get("token", "")
    if not token or token == "YOUR_LINE_NOTIFY_TOKEN":
        log.warning("LINE Notify 設定未填寫，略過通知")
        return

    message = "\n" + format_message(matches, keyword)
    try:
        resp = requests.post(
            "https://notify-api.line.me/api/notify",
            headers={"Authorization": f"Bearer {token}"},
            data={"message": message},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("LINE 通知已發送（關鍵字：%s，%d 筆）", keyword, len(matches))
    except requests.RequestException as e:
        log.error("LINE Notify 通知失敗：%s", e)


def notify(matches: list[dict], keyword: str, config: dict) -> None:
    method = config.get("notify_method", "console")
    if method == "discord":
        notify_discord(matches, keyword, config.get("discord", {}))
    elif method == "telegram":
        notify_telegram(matches, keyword, config.get("telegram", {}))
    elif method == "line":
        notify_line(matches, keyword, config.get("line_notify", {}))
    else:
        # console fallback
        print(format_message(matches, keyword))


# ── 主流程 ────────────────────────────────────────────────────────────────────

def check_once(config: dict, session: requests.Session, seen: set) -> set:
    """執行一輪所有關鍵字的檢查，回傳更新後的 seen set。"""
    url = config.get("mops_url", "https://mopsov.twse.com.tw/mops/web/ezsearch")
    keywords = config.get("keywords", [])

    for keyword in keywords:
        log.info("檢查關鍵字：%s", keyword)
        html = fetch_search_results(session, url, keyword)
        if html is None:
            continue

        announcements = parse_announcements(html, keyword)
        new_matches = filter_new(announcements, seen)

        if new_matches:
            log.info("發現 %d 則新公告（關鍵字：%s），發送通知", len(new_matches), keyword)
            notify(new_matches, keyword, config)
            for m in new_matches:
                seen.add(m["id"])
        else:
            log.info("無新公告（關鍵字：%s）", keyword)

    save_seen(seen)
    return seen


def run_loop(config: dict) -> None:
    interval = config.get("check_interval_seconds", 300)
    session = make_session()
    seen = load_seen()
    log.info("開始持續監控，間隔 %d 秒。按 Ctrl+C 停止。", interval)
    while True:
        try:
            seen = check_once(config, session, seen)
        except Exception as e:
            log.error("輪詢過程發生錯誤：%s", e)
        log.info("等待 %d 秒後再次檢查...", interval)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="MOPS 公告關鍵字追蹤器")
    parser.add_argument(
        "--once",
        action="store_true",
        help="單次執行後結束（適合 cron 排程）",
    )
    args = parser.parse_args()

    config = load_config()
    session = make_session()
    seen = load_seen()

    if args.once:
        check_once(config, session, seen)
    else:
        run_loop(config)


if __name__ == "__main__":
    main()
