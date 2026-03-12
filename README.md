# MOPS 公告關鍵字追蹤器

自動監控[台灣公開資訊觀測站 (MOPS)](https://mopsov.twse.com.tw/mops/web/ezsearch)，
當搜尋結果出現新公告時，透過 **Discord Webhook** 發送通知。

---

## 功能

- 支援多組關鍵字同時監控
- 自動記住已通知過的公告，不重複發送
- 支援 Discord Webhook / Telegram / LINE Notify
- 可設定輪詢間隔（預設 5 分鐘）
- 支援 cron 排程（`--once` 模式）

---

## 快速設定（Discord Webhook）

### 步驟 1：取得 Discord Webhook URL

1. 開啟 Discord，進入想接收通知的頻道
2. 右鍵頻道 → **Edit Channel（編輯頻道）**
3. 左側選 **Integrations → Webhooks**
4. 點 **New Webhook** → 命名後複製 URL

URL 格式：
```
https://discord.com/api/webhooks/123456789/xxxxxxxxxxxxxxxxx
```

### 步驟 2：下載專案

```bash
git clone https://github.com/你的帳號/你的Repo.git
cd 你的Repo
```

### 步驟 3：安裝依賴套件

```bash
pip install -r requirements.txt
```

> 建議使用虛擬環境：
> ```bash
> python -m venv venv
> source venv/bin/activate   # Windows: venv\Scripts\activate
> pip install -r requirements.txt
> ```

### 步驟 4：建立設定檔

```bash
cp config.example.json config.json
```

編輯 `config.json`：

```json
{
  "keywords": ["興達", "再生能源"],
  "check_interval_seconds": 300,
  "notify_method": "discord",
  "discord": {
    "webhook_url": "https://discord.com/api/webhooks/你的ID/你的Token"
  }
}
```

| 欄位 | 說明 |
|------|------|
| `keywords` | 要監控的關鍵字列表 |
| `check_interval_seconds` | 輪詢間隔秒數（預設 300 = 5 分鐘） |
| `notify_method` | 通知方式：`discord` / `telegram` / `line` / `console` |
| `discord.webhook_url` | 步驟 1 取得的 Webhook URL |

### 步驟 5：執行

```bash
# 持續監控（每 5 分鐘自動查詢）
python monitor.py

# 單次執行（適合 cron 排程）
python monitor.py --once
```

---

## 使用 cron 自動排程（Linux / macOS）

```bash
crontab -e
```

加入以下一行（每 5 分鐘執行一次）：

```
*/5 * * * * cd /你的專案路徑 && /你的python路徑/python monitor.py --once >> monitor.log 2>&1
```

查詢 Python 路徑：`which python` 或 `which python3`

---

## 其他通知方式

### Telegram

```json
{
  "notify_method": "telegram",
  "telegram": {
    "bot_token": "從 @BotFather 取得",
    "chat_id": "你的 Chat ID"
  }
}
```

### LINE Notify（LINE 官方通知服務即將停止，建議改用 Discord）

```json
{
  "notify_method": "line",
  "line_notify": {
    "token": "從 LINE Notify 官網申請"
  }
}
```

### Console（測試用）

```json
{
  "notify_method": "console"
}
```

---

## 檔案說明

| 檔案 | 說明 |
|------|------|
| `monitor.py` | 主程式 |
| `config.json` | 個人設定（**不會上傳 GitHub**） |
| `config.example.json` | 設定範本（可安全上傳） |
| `seen_announcements.json` | 已通知公告快取（自動產生） |
| `requirements.txt` | Python 依賴套件 |

> `config.json` 和 `seen_announcements.json` 已加入 `.gitignore`，不會不小心上傳 Token。

---

## 注意事項

- MOPS 網站結構若有異動，可能需要調整 `parse_announcements()` 的欄位解析邏輯
- 建議在台灣時區的主機執行，以確保日期比對正確
