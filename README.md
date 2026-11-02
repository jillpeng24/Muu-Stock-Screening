# Muu 選股機器人 v2

以「投信買超」為核心的每日選股，加上大盤紅綠燈、風險過濾與模擬帳戶成績單。
每天收盤後自動執行，用 LINE 群發給所有加機器人好友的人。

## 每天做的事

1. 更新證交所法人買賣超與收盤行情
2. 判斷大盤紅綠燈（0050 的 20 週均線＋美股 200 日均線）
3. 篩選：投信有買（外資同步買的加註）→ 避雷（近 4 季 EPS、營業現金流、處置股、注意股、KY 股）→ 風險（離均線、融資）
4. 依「投信 5 日買超佔成交量」排序，推薦前 5 名，其餘列觀察名單
5. 記錄所有候選股、更新模擬帳戶（推薦隔天買、持有 20 個交易日）
6. LINE 群發：今日推薦、到期提醒、成績單

規則參數都在 `core/config.py`，想調整只要改那個檔案。

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `run_daily.py` | 主程式 |
| `core/config.py` | 所有規則參數 |
| `core/data_twse.py` | 證交所：法人、行情、融資、處置股 |
| `core/data_finmind.py` | FinMind：月營收、EPS、現金流（有快取） |
| `core/data_price.py` | 股價（Yahoo，備援用證交所） |
| `core/market.py` | 大盤紅綠燈 |
| `core/screener.py` | 篩選與排序 |
| `core/tracker.py` | 紀錄與模擬帳戶 |
| `core/notify.py` | LINE 群發 |
| `data/` | 所有資料與紀錄（自動產生，不要手動刪除） |

## 第一次設定

### 1. 建立新的 GitHub 專案
- 在 GitHub 按右上角「＋」→「New repository」，名稱例如 `muu-stock-v2`
- 把這個資料夾的所有檔案上傳，**包含 `.github` 資料夾**
  - Mac 的 Finder 預設會隱藏 `.github`，按 `Command + Shift + .` 就會顯示

### 2. 設定密鑰（跟舊系統用同一組）
專案頁面 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**：

| 名稱 | 內容 |
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE 機器人的 Channel access token |
| `FINMIND_TOKEN` | FinMind 的 API token |

（網站完成後，再到同一頁的 **Variables** 新增 `WEBSITE_URL`，推播最後一行就會附上網址。）

### 3. 先用「預覽模式」測試
- 專案頁面 → **Actions** → 左邊點「每日選股」→ 右邊「Run workflow」
- `dry_run` 填 `1`（預設就是 1），按綠色按鈕執行
- 執行完點進去看紀錄，「執行每日選股」那一段最後會印出 LINE 訊息預覽，**不會真的發送**
- 第一次執行會補抓約 30 個交易日的資料，大約需要 3～5 分鐘

### 4. 確認沒問題後
- 之後每個交易日 14:32 會自動執行一次
- GitHub 免費排程常會延遲幾個小時，屬於正常現象
- 如果執行時證交所資料還沒公布，程式會每 10 分鐘再檢查一次，最多等到 17:00；休市日會直接結束
- 想手動正式發送一次：Run workflow，`dry_run` 填 `0`

## 注意事項

- LINE 群發會送給所有加機器人好友的人。免費方案每月有訊息則數上限（依人數計算），可到 LINE Official Account Manager 查看用量。
- 模擬帳戶的報酬優先用 Yahoo 還原股價（含除權息）計算。
- 本系統的規則依 2026/2～10 的歷史資料測試訂定，未來不一定有相同表現。推播內容僅供參考，不構成投資建議。
