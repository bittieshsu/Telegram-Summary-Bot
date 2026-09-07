# Telegram 群組定期摘要機器人

收集**已授權** Telegram 群組的文字訊息，依排程或指令產生摘要。群組 owner 可管理設定；成員可訂閱排程摘要，或在啟用額度後私訊要求摘要。

![Telegram 群組摘要範例](example.jpg)

## 功能

- 以 5 欄 cron 排程發佈群組摘要，或用 `/summary` 立即產生。
- 可依時間範圍或主題摘要，例如「這兩週以來討論到露營的事情」。
- `/preview` 僅私訊 owner 預覽，不發佈也不更新摘要進度。
- 提供 `normal`、`funny`、`roast` 三種摘要風格。
- 僅接受 owner 加入的群組；owner 或 Bot 離群後會撤銷授權。
- 可私訊訂閱自己仍在其中的群組之**排程**摘要。
- SQLite 保存訊息、群組設定與摘要進度；摘要可附 Telegram 原始訊息連結。

Bot 保存所有帳號的文字訊息與 caption，包括其他 Bot 的內容，讓回覆可保留完整脈絡。訊息含公開 HTTP(S) 連結時，Bot 會保存網頁的 Open Graph 標題與描述；貼圖、純圖片、影片、語音、音訊、video note 與動畫不會保存。

## 前置需求與快速啟動

- Docker Compose
- BotFather 建立的 Telegram Bot token
- OpenAI API key
- owner 的 Telegram user ID
- Python 3.14（僅本機執行舊訊息補回工具時需要）

容器使用官方 `python:3.14-alpine` 映像；執行時入口為 `python -m app.main`。

### 1. 建立設定檔

```bash
cp .env.example .env
```

至少填入：

```dotenv
TELEGRAM_BOT_TOKEN=<BotFather token>
OPENAI_API_KEY=<OpenAI API key>
OWNER_TELEGRAM_USER_ID=<owner 的 Telegram user ID>
```

### 2. 啟動

```bash
docker compose up -d --build
docker compose logs -f telegram-summary-bot
```

更新程式後使用相同指令重新建置。資料庫位於主機的 `./data/bot.db`，映射到容器的 `/app/data/bot.db`。

## Telegram 與 BotFather 權限

1. 在 BotFather 建立 Bot，取得 `TELEGRAM_BOT_TOKEN`。
2. 對 Bot 執行 `/setprivacy` 並選擇 **Disable**，否則通常只能收到指令，無法取得完整群組訊息。
3. 由 `OWNER_TELEGRAM_USER_ID` 對應帳號將 Bot 加入群組，並將 Bot 設為管理員。管理員權限讓 Bot 能收到成員狀態變更，並確認訂閱者資格。
4. owner 與訂閱者都要先私訊 Bot 一次（可輸入 `/start`）；Telegram 不允許 Bot 主動開啟未互動過的私訊。

owner 加入的群組會自動授權。非 owner 加入時，Bot 會通知 owner 後離群，不保存該群組訊息。owner 離群時，Bot 會撤銷授權並離開；owner 重新加入後，須重新加入 Bot。指令選單會自動同步，不必在 BotFather 逐一設定。

## 設定

所有設定都在 `.env`；前 3 項必填，其餘可省略並採用預設值。

| 環境變數 | 預設值 | 說明 |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | 無 | BotFather 提供的 token |
| `OPENAI_API_KEY` | 無 | OpenAI API key |
| `OWNER_TELEGRAM_USER_ID` | 無 | 唯一可管理群組設定的 Telegram user ID |
| `DEFAULT_TIMEZONE` | `UTC+8` | 新群組時區，例如 `UTC+8`、`Asia/Taipei` |
| `DEFAULT_CRON_EXPR` | `0 9 * * *` | 新群組的 5 欄 cron 排程 |
| `DEFAULT_MODEL` | `gpt-5.6-luna` | 新群組的 OpenAI Responses API 模型 |
| `DEFAULT_REASONING_EFFORT` | `default` | `default`、`none`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max` |
| `SQLITE_PATH` | `/app/data/bot.db` | SQLite 路徑；Docker 改動時也要調整 volume |
| `MAX_MESSAGES_PER_SUMMARY` | `10000` | 單次傳給模型的最新訊息上限；仍會顯示完整訊息總數 |
| `MIN_MESSAGES_TO_SUMMARY` | `8` | 自動摘要的最低訊息數 |
| `MAX_SUMMARY_GAP_HOURS` | `24` | 訊息不足時，最長累積多久仍強制自動摘要 |
| `MESSAGE_RETENTION_DAYS` | `180` | 原始訊息保存天數，也限制條件摘要的可查詢範圍 |
| `PREVIEW_WINDOW_HOURS` | `24` | `/preview` 預覽的最近訊息時數 |
| `DAILY_USER_SUMMARY_LIMIT` | `0` | 一般使用者每日、每群組的私訊摘要額度；`0` 為停用 |
| `OPENAI_MAX_OUTPUT_TOKENS` | `25000` | 摘要與條件解析的輸出 token 上限 |

`default` 不會傳送 reasoning 參數；模型不支援指定程度時，Bot 會改以模型預設值重試。

## 指令與存取權

### owner（群組內）

所有下列指令都必須在已授權的群組使用，除非另有註記。

| 指令 | 說明 |
| --- | --- |
| `/start`、`/help` | 顯示指令說明 |
| `/authorize_group` | 授權既有群組；由 owner 在該群組執行 |
| `/summary` | 摘要上次摘要後的訊息 |
| `/summary <條件>` | 依自然語言時間或主題摘要，例如 `/summary 這兩週以來討論到露營的事情` |
| `/preview` | 私訊 owner 預覽最近 24 小時摘要 |
| `/status` | 顯示群組設定、摘要進度與下次執行時間 |
| `/set_schedule <cron>` | 設定排程；省略值時依提示輸入 |
| `/set_timezone <tz>` | 設定時區；省略值時依提示輸入 |
| `/set_model <model>` | 設定模型；省略值時依提示輸入 |
| `/set_reasoning <level>` | 設定 reasoning 程度；省略值時依提示輸入 |
| `/set_style <normal\|funny\|roast>` | 設定摘要風格；省略值時依提示輸入 |
| `/set_auto <on\|off>` | 開啟或關閉自動摘要；省略值時依提示輸入 |
| `/cancel` | 取消進行中的設定問答 |

owner 可在私訊使用 `/summary <條件>`，不限額；也可用 `/user_summary_history` 查看最近 20 筆一般使用者摘要請求。

手動 `/summary` 只要有文字訊息就會執行，不受 `MIN_MESSAGES_TO_SUMMARY` 限制。帶條件的摘要不會更新群組摘要進度。

### 一般使用者（私訊 Bot）

| 指令 | 說明 |
| --- | --- |
| `/subscribe` | 選擇要訂閱的已授權群組 |
| `/unsubscribe` | 取消群組摘要訂閱 |
| `/summary <條件>` | 選擇自己仍在其中的已授權群組，取得私訊摘要 |

訂閱與私訊摘要清單只會顯示 Bot 能確認使用者仍在其中的群組；無法確認時不會建立訂閱或提供摘要。一般使用者的 `/summary` 須將 `DAILY_USER_SUMMARY_LIMIT` 設為正整數。額度按使用者與群組分開計算，於該群組時區的午夜重置；結果僅私訊請求者，不發佈至群組，也不更新摘要進度。

只有排程自動摘要會通知訂閱者。Bot 會重用已產生的 HTML 摘要，不增加 OpenAI API 呼叫；傳送前會再次確認訂閱者仍是群組成員，離群者會自動取消訂閱。

## 排程、摘要與資料

### 排程與時區

`/set_schedule` 使用標準 5 欄 cron：

```text
分鐘 小時 日 月 星期
```

| cron | 執行時間 |
| --- | --- |
| `0 9 * * *` | 每天 09:00 |
| `0 */6 * * *` | 每 6 小時 |
| `30 9 * * 1` | 每週一 09:30 |

排程依群組時區計算；`/status` 的下次執行時間為 UTC。自動摘要若未達 `MIN_MESSAGES_TO_SUMMARY`，會繼續累積且不更新摘要進度；最早未摘要訊息累積至 `MAX_SUMMARY_GAP_HOURS` 時仍會產生摘要。

### 摘要風格

| 風格 | 說明 |
| --- | --- |
| `normal` | 中性精簡，保留決策、結論、重要事實、待辦事項與分歧 |
| `funny` | 輕快有梗，但不犧牲重點或取笑個人 |
| `roast` | 台式垃圾話與吐槽，適合群組自願開啟的娛樂模式 |

所有風格都只根據對話內容，不杜撰事實，保留重要數字與專有名詞，清楚區分發言者，且只使用對話紀錄提供的 Telegram 討論連結。`roast` 可吐槽真實對話行為，但不得攻擊種族、性別、性向、宗教或身心障礙等身分特徵。

### 保存與升級

- 原始訊息預設保留 180 天；過期後會清除，手動條件摘要也不能查詢該時段。
- `messages` 僅保存 `user_id`，顯示名稱位於 `users` table；改名後歷史訊息會顯示最新名稱。
- 保存同群組內的回覆關係，供摘要辨識不同討論串。
- 公開群組與超級群組可產生「回到討論」連結；一般私人群組沒有 Telegram 永久訊息連結。
- 舊版資料庫會在啟動時自動 migration：舊的 `messages.user_name` 會移至 `users` table，訊息保留；舊訊息沒有回覆關係。

## 補回加入前的訊息

Bot API 無法讀取加入前的群組歷史。可用自己的 Telegram 帳號與一次性的 MTProto session 補回；該帳號必須仍在目標群組，且目標群組必須已由 Bot 授權。

1. 在 [my.telegram.org](https://my.telegram.org) 建立 API ID/hash。
2. 安裝相依套件並執行：

```bash
python3.14 -m pip install -r requirements.txt
export TELEGRAM_API_ID=123456
export TELEGRAM_API_HASH=your_api_hash
python3.14 -m app.backfill \
  --chat @group_username \
  --from 2025-01-01T00:00:00Z \
  --to 2025-02-01T00:00:00Z \
  --session ~/.local/share/telegram-summary-backfill
```

也可使用 `--api-id`、`--api-hash` 與 `--database` 指定值。首次執行會在終端登入；`--session` 的父目錄必須已存在。請勿提交或分享產生的 session 檔、API hash。

`--chat` 可填公開群組 username、invite-linked entity，或 `/status` 顯示的 `-100...` chat ID；私密群組 ID 會從該帳號的 dialogs 查找。工具只讀取指定 UTC 半開區間（`from <= date < to`）的文字與 caption；既有 `(chat_id, message_id)` 不會覆寫，不會啟動 Bot API。每 100 則訊息輸出一次進度。補回會將成員名稱、文字與回覆關係寫入 SQLite，並同樣受資料保存政策限制。僅在你有權存取及處理資料的群組執行。

## 常見問題

### Bot 看不到群組訊息

確認在 BotFather 對 Bot 執行 `/setprivacy` 並選擇 **Disable**，且 Bot 是由 owner 加入群組。

### Bot 無法私訊預覽或訂閱摘要

owner 或訂閱者需先私訊 Bot 並輸入 `/start`；Telegram 不允許 Bot 主動開啟未互動過的私訊。

### 訂閱清單是空的

使用者必須仍在已授權群組，且 Bot 必須有管理員權限以查詢成員資格。

## License

This project is licensed under the [MIT License](LICENSE).
