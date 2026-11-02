"""
所有規則參數集中在這裡。想調整規則，只要改這個檔案。
括號內是根據 2026/2～10 歷史資料測試的依據。
"""
import os

# ── 路徑 ──────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CHIPS_FILE = os.path.join(DATA_DIR, "chips_history.csv")        # 每日法人＋行情（全市場）
FUND_DIR = os.path.join(DATA_DIR, "fundamentals")               # 基本面快取
PICKS_LOG = os.path.join(DATA_DIR, "picks_log.csv")             # 每日候選紀錄（永久保存）
TRADES_FILE = os.path.join(DATA_DIR, "sim_trades.csv")          # 模擬帳戶交易紀錄
REPORT_DIR = os.path.join(DATA_DIR, "reports")                  # 每日報告（網站讀取）
MARKET_FILE = os.path.join(DATA_DIR, "market_light.csv")        # 大盤燈號紀錄

# ── 籌碼篩選 ─────────────────────────────────────
PATTERN_A_DAYS = 3        # A：外資＋投信同買連續天數
PATTERN_B_DAYS = 4        # B：投信連買天數
TRUST_WINDOW = 5          # 投信買超佔成交量的計算天數

# ── 排序與推播 ───────────────────────────────────
TOP_N = 5                 # 每天推薦幾檔（前 5 名上漲比例 61%→68%）
STRONG_TRUST_RATIO = 0.14 # 投信 5 日買超佔量 ≥ 14% → ⭐ 強訊號（跑贏 0050 比例 57%）
STRONG_TRUST_DAYS = 10    # 投信連買 ≥ 10 天 → ⭐ 強訊號（跑贏 0050 比例 53%）

# ── 風險條件（不進推薦，改列觀察名單）─────────────
MAX_BIAS = 0.10           # 離 20 日均線超過 10% 不推（中途大跌機會 24%→51%）
MARGIN_EXCLUDE = 20.0     # 融資使用率 ≥ 20% 不推（虧超過 10% 的比例 25%）
MARGIN_WARN = 10.0        # 融資使用率 ≥ 10% 加註「金額減半」
NOTICE_LOOKBACK_DAYS = 7  # 最近 7 天（日曆天）被列為注意股 → 不推
EXCLUDE_KY = True         # KY 股（外國公司來台上市）不推

# ── 持有規則 ─────────────────────────────────────
HOLD_DAYS = 20            # 持有 20 個交易日後檢視（看訊號提前賣出的結果都比較差）

# ── 大盤紅綠燈 ───────────────────────────────────
TW_TREND_WEEKS = 20       # 0050 週收盤 vs 20 週均線（大跌期間跌幅減少七成）
US_TREND_DAYS = 200       # S&P 500 vs 200 日均線

# ── 其他 ─────────────────────────────────────────
CHIPS_KEEP_DAYS = 260     # 法人資料保留約一年
BACKFILL_DAYS = 45        # 第一次執行時往前補抓的日曆天數（約 30 個交易日）
FUND_REFRESH_DAYS = 30    # EPS、現金流多久重新抓一次
TWSE_SLEEP = 3            # 證交所每次請求間隔秒數（避免被擋）
WEBSITE_URL = os.environ.get("WEBSITE_URL", "")   # 網站網址，推播最後一行會附上

# 環境變數（放在 GitHub Secrets）
FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"   # 1 = 只印出訊息、不實際發送
