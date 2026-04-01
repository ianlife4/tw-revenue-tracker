"""
營收即時監控系統
每次執行時：
1. 從 MOPS 下載當期營收 CSV（上市/上櫃/興櫃）
2. 比對已知的申報名單，找出新增的公司
3. 記錄每家公司的首次偵測時間（first_seen）
4. 生成即時 HTML 頁面
5. 推送到 GitHub Pages

設計參考：chengwaye.com/realtime-rev
"""

import os
import io
import json
import time
import random
import logging
import urllib3
from datetime import datetime

import requests
import pandas as pd

from config import DATA_DIR, OUTPUT_DIR, HEADERS, HISTORY_YEARS, get_current_period
from analyzer import format_revenue
from html_generator import save_html

urllib3.disable_warnings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

MOPS_DL_URL = "https://mopsov.twse.com.tw/server-java/FileDownLoad"
MARKETS = ["sii", "otc", "rotc"]
STATE_FILE = os.path.join(DATA_DIR, "monitor_state.json")
CACHE_FILE = os.path.join(DATA_DIR, "all_revenue_mops.csv")

COL_MAP = {
    "公司代號": "stock_id",
    "公司名稱": "stock_name",
    "產業別": "industry",
    "營業收入-當月營收": "revenue",
    "營業收入-上月營收": "prev_month_revenue",
    "營業收入-去年當月營收": "prev_year_revenue",
    "營業收入-上月比較增減(%)": "mom_pct",
    "營業收入-去年同月增減(%)": "yoy_pct",
    "累計營業收入-前期比較增減(%)": "ytd_yoy_pct",
    "出表日期": "publish_date",
    "資料年月": "period",
    "備註": "remark",
}


def load_state() -> dict:
    """載入監控狀態"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "period_year": 0,
        "period_month": 0,
        "stocks": {},  # {stock_id: {"first_seen": "2026-04-01 20:04", "market": "sii"}}
        "last_check": "",
        "last_new_filing": "",
        "total_filed": 0,
    }


def save_state(state: dict):
    """儲存監控狀態"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_current_month(roc_year: int, month: int, market: str) -> pd.DataFrame:
    """下載當月某市場的營收 CSV"""
    fpath = f"/t21/{market}/"
    fname = f"t21sc03_{roc_year}_{month}.csv"

    payload = {
        "step": "9",
        "functionName": "show_file2",
        "filePath": fpath,
        "fileName": fname,
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                MOPS_DL_URL, data=payload, headers=HEADERS,
                verify=False, timeout=30,
            )
            if resp.status_code == 200 and len(resp.content) >= 600:
                resp.encoding = "utf-8-sig"
                df = pd.read_csv(io.StringIO(resp.text))

                # 重命名欄位
                rename = {}
                for orig, new in COL_MAP.items():
                    for col in df.columns:
                        if orig in col:
                            rename[col] = new
                            break
                df = df.rename(columns=rename)

                western_year = roc_year + 1911
                df["revenue_year"] = western_year
                df["revenue_month"] = month
                market_internal = "emerging" if market == "rotc" else market
                df["market"] = market_internal
                df["stock_id"] = df["stock_id"].astype(str).str.strip()

                # 營收轉數值 (千元 → 元)
                for col in ["revenue", "prev_month_revenue", "prev_year_revenue"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(
                            df[col].astype(str).str.replace(",", ""), errors="coerce"
                        ) * 1000

                for col in ["yoy_pct", "mom_pct", "ytd_yoy_pct"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(
                            df[col].astype(str).str.replace(",", ""), errors="coerce"
                        )

                df = df[df["stock_id"].str.match(r"^\d{4}$", na=False)].copy()
                return df

            if attempt < max_retries - 1:
                time.sleep(random.uniform(1.5, 3.0))

        except Exception as e:
            logger.warning(f"  {market} {roc_year}/{month}: 錯誤 {e}")
            if attempt < max_retries - 1:
                time.sleep(random.uniform(1.5, 3.0))

    return pd.DataFrame()


def check_filings():
    """主偵測邏輯：檢查 MOPS 新申報"""
    now = datetime.now()
    rev_year, rev_month = get_current_period()
    roc_year = rev_year - 1911

    logger.info(f"=== 偵測營收申報：{rev_year}/{rev_month:02d} (民國 {roc_year}/{rev_month}) ===")

    # 載入狀態
    state = load_state()

    # 如果營收期間變了，重置狀態
    if state["period_year"] != rev_year or state["period_month"] != rev_month:
        logger.info(f"新營收期間 {rev_year}/{rev_month:02d}，重置監控狀態")
        state = {
            "period_year": rev_year,
            "period_month": rev_month,
            "stocks": {},
            "last_check": "",
            "last_new_filing": "",
            "total_filed": 0,
        }

    # 下載三個市場的當月 CSV
    all_dfs = []
    for market in MARKETS:
        df = fetch_current_month(roc_year, rev_month, market)
        if not df.empty:
            logger.info(f"  {market}: {len(df)} 筆")
            all_dfs.append(df)
        else:
            logger.info(f"  {market}: 尚無資料")

    if not all_dfs:
        logger.info("MOPS 尚無當期資料")
        state["last_check"] = now.strftime("%m-%d %H:%M:%S")
        save_state(state)
        return state, pd.DataFrame()

    current_df = pd.concat(all_dfs, ignore_index=True)
    current_ids = set(current_df["stock_id"].unique())
    known_ids = set(state["stocks"].keys())

    # 找出新增的申報
    new_ids = current_ids - known_ids
    if new_ids:
        logger.info(f"🆕 新偵測到 {len(new_ids)} 家申報！")
        for sid in new_ids:
            row = current_df[current_df["stock_id"] == sid].iloc[0]
            state["stocks"][sid] = {
                "first_seen": now.strftime("%m-%d %H:%M"),
                "market": row.get("market", ""),
                "stock_name": row.get("stock_name", ""),
            }
        state["last_new_filing"] = now.strftime("%m-%d %H:%M:%S")
    else:
        logger.info("無新增申報")

    state["last_check"] = now.strftime("%m-%d %H:%M:%S")
    state["total_filed"] = len(current_ids)

    save_state(state)

    # 將 first_seen 加入 DataFrame
    current_df["first_seen"] = current_df["stock_id"].map(
        lambda sid: state["stocks"].get(sid, {}).get("first_seen", "")
    )

    return state, current_df


def generate_realtime_html(state: dict, current_df: pd.DataFrame, full_df: pd.DataFrame = None):
    """生成即時營收頁面"""
    from html_realtime import generate_realtime_page
    rev_year = state["period_year"]
    rev_month = state["period_month"]

    # 載入歷史資料 (用於比對新高和圖表)
    if full_df is None and os.path.exists(CACHE_FILE):
        full_df = pd.read_csv(CACHE_FILE, dtype={"stock_id": str})

    html = generate_realtime_page(state, current_df, full_df, rev_year, rev_month)
    path = save_html(html, "index.html")
    logger.info(f"即時頁面已更新: {path}")
    return path


def run_once():
    """執行一次偵測"""
    state, current_df = check_filings()
    if not current_df.empty:
        generate_realtime_html(state, current_df)
    else:
        logger.info("無資料，跳過生成 HTML")
    return state


def run_loop(interval_sec: int = 300):
    """持續監控 (每 interval_sec 秒執行一次)"""
    logger.info(f"啟動營收即時監控，每 {interval_sec} 秒偵測一次")
    while True:
        try:
            run_once()
        except Exception as e:
            logger.error(f"偵測錯誤: {e}", exc_info=True)
        logger.info(f"下次偵測: {interval_sec} 秒後\n")
        time.sleep(interval_sec)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "loop":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        run_loop(interval)
    else:
        run_once()
