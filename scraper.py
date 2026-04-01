"""
台灣股票每月營收爬蟲
資料來源: FinMind API (免費) + Playwright 備援 MOPS
"""

import os
import time
import random
import logging
import urllib3

import requests
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import (
    DATA_DIR,
    HEADERS,
    REQUEST_DELAY_MIN,
    REQUEST_DELAY_MAX,
)

logger = logging.getLogger(__name__)

FINMIND_API = "https://api.finmindtrade.com/api/v4/data"


def get_stock_list() -> pd.DataFrame:
    """取得所有上市、上櫃、興櫃股票清單 (從 FinMind)
    自動識別創新板股票 (industry_category == '創新板股票' 或名稱以 -創 結尾)
    """
    cache_path = os.path.join(DATA_DIR, "stock_list.csv")

    # 快取一天
    if os.path.exists(cache_path):
        mtime = os.path.getmtime(cache_path)
        if time.time() - mtime < 86400:
            return pd.read_csv(cache_path, dtype={"stock_id": str})

    logger.info("從 FinMind 取得股票清單...")
    params = {"dataset": "TaiwanStockInfo"}
    resp = requests.get(FINMIND_API, params=params, verify=False, timeout=30)
    data = resp.json()

    if data.get("status") != 200 or not data.get("data"):
        logger.error(f"取得股票清單失敗: {data.get('msg', 'unknown error')}")
        return pd.DataFrame()

    df = pd.DataFrame(data["data"])
    # 保留上市 (twse)、上櫃 (tpex)、興櫃 (emerging)
    df = df[df["type"].isin(["twse", "tpex", "emerging"])].copy()
    # 只保留純數字代號 (排除 ETF 等)
    df = df[df["stock_id"].str.match(r"^\d{4}$")].copy()

    # --- 識別創新板股票 ---
    # 方法1: industry_category 為 "創新板股票"
    tib_ids_cat = set(df[df["industry_category"] == "創新板股票"]["stock_id"].unique())
    # 方法2: 名稱以「創」結尾 (e.g. 鴻華先進-創, 錼創科技-KY創)
    tib_ids_name = set(df[df["stock_name"].str.endswith("創", na=False)]["stock_id"].unique())
    tib_ids = tib_ids_cat | tib_ids_name
    logger.info(f"偵測到 {len(tib_ids)} 檔創新板股票: {sorted(tib_ids)}")

    # 去除 industry_category == "創新板股票" 的重複列 (保留實際產業分類的那列)
    df_tib_rows = df[df["industry_category"] == "創新板股票"]
    df = df[df["industry_category"] != "創新板股票"].copy()

    # 如果有 TIB 股票只有 "創新板股票" 列沒有其他產業列，補回來
    missing_tib = tib_ids - set(df["stock_id"].unique())
    if missing_tib:
        df = pd.concat([df, df_tib_rows[df_tib_rows["stock_id"].isin(missing_tib)]], ignore_index=True)

    # 標記創新板
    df["is_tib"] = df["stock_id"].isin(tib_ids)

    # 去除重複 stock_id (保留最新日期的)
    df = df.sort_values("date", ascending=False).drop_duplicates("stock_id", keep="first")

    os.makedirs(DATA_DIR, exist_ok=True)
    df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    n_twse = len(df[(df['type'] == 'twse') & (~df['is_tib'])])
    n_tpex = len(df[df['type'] == 'tpex'])
    n_emerging = len(df[df['type'] == 'emerging'])
    n_tib = len(df[df['is_tib']])
    logger.info(f"股票清單: {len(df)} 檔 (上市 {n_twse}, 上櫃 {n_tpex}, 興櫃 {n_emerging}, 創新板 {n_tib})")
    return df


def fetch_stock_revenue(stock_id: str, start_date: str, end_date: str) -> pd.DataFrame:
    """從 FinMind 取得單一股票的營收歷史"""
    params = {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    try:
        resp = requests.get(FINMIND_API, params=params, verify=False, timeout=15)
        data = resp.json()
        if data.get("status") == 200 and data.get("data"):
            return pd.DataFrame(data["data"])
    except Exception as e:
        logger.debug(f"查詢 {stock_id} 失敗: {e}")
    return pd.DataFrame()


def scrape_all_revenue(target_month: int, current_year: int, years_back: int = 5) -> dict[int, pd.DataFrame]:
    """抓取所有股票指定月份的營收資料

    Returns:
        {year: DataFrame} 歷史同月資料
    """
    csv_path = os.path.join(DATA_DIR, f"all_revenue_m{target_month:02d}.csv")

    # 計算上個月 (用於月增率)
    if target_month == 1:
        prev_month = 12
        prev_month_year = current_year - 1
    else:
        prev_month = target_month - 1
        prev_month_year = current_year

    prev_month_csv = os.path.join(DATA_DIR, f"prev_month_m{prev_month:02d}_y{current_year}.csv")

    # 檢查快取 (當年資料每次重抓，歷史資料用快取)
    cached_df = None
    if os.path.exists(csv_path):
        cached_df = pd.read_csv(csv_path, dtype={"stock_id": str})
        cached_years = set(cached_df["revenue_year"].unique())
        need_years = set(range(current_year - years_back, current_year + 1))
        missing_years = need_years - cached_years

        if not missing_years or (missing_years == {current_year}):
            # 只需要更新當年資料
            logger.info(f"快取命中，只需更新 {current_year} 年資料")
        else:
            logger.info(f"缺少 {missing_years} 年資料，需要完整抓取")
            cached_df = None

    stock_list = get_stock_list()
    if stock_list.empty:
        logger.error("無法取得股票清單")
        return {}

    start_date = f"{current_year - years_back}-01-01"
    end_date = f"{current_year}-12-31"

    all_frames = []
    prev_month_frames = []
    total = len(stock_list)

    logger.info(f"開始抓取 {total} 檔股票營收 ({start_date} ~ {end_date})...")
    logger.info(f"同時抓取上月 ({prev_month_year}/{prev_month:02d}) 營收用於計算月增率")

    for count, (idx, row) in enumerate(stock_list.iterrows()):
        stock_id = row["stock_id"]

        if count % 50 == 0:
            logger.info(f"進度: {count}/{total} ({count/total*100:.0f}%)")

        df = fetch_stock_revenue(stock_id, start_date, end_date)
        if not df.empty:
            # 保留目標月份
            target_df = df[df["revenue_month"] == target_month].copy()
            if not target_df.empty:
                target_df["stock_name"] = row.get("stock_name", "")
                # 判斷市場別 (創新板優先)
                if row.get("is_tib", False):
                    target_df["market"] = "tib"
                else:
                    type_map = {"twse": "sii", "tpex": "otc", "emerging": "emerging"}
                    target_df["market"] = type_map.get(row.get("type", ""), "otc")
                target_df["industry"] = row.get("industry_category", "")
                all_frames.append(target_df)

            # 保留上個月 (只需要當年或前一年的)
            pm_df = df[
                (df["revenue_month"] == prev_month) &
                (df["revenue_year"] == prev_month_year)
            ].copy()
            if not pm_df.empty:
                pm_df["stock_name"] = row.get("stock_name", "")
                prev_month_frames.append(pm_df)

        # FinMind 免費版有速率限制
        time.sleep(random.uniform(0.3, 0.6))

    if not all_frames:
        logger.warning("未取得任何營收資料")
        return {}

    result_df = pd.concat(all_frames, ignore_index=True)
    # 去除重複 (同一股票同一年月只保留一筆)
    result_df = result_df.drop_duplicates(subset=["stock_id", "revenue_year", "revenue_month"], keep="first")

    # 儲存快取
    os.makedirs(DATA_DIR, exist_ok=True)
    result_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info(f"已儲存快取: {csv_path} ({len(result_df)} 筆)")

    # 儲存上個月快取
    prev_month_df = None
    if prev_month_frames:
        prev_month_df = pd.concat(prev_month_frames, ignore_index=True)
        prev_month_df = prev_month_df.drop_duplicates(subset=["stock_id"], keep="first")
        prev_month_df.to_csv(prev_month_csv, index=False, encoding="utf-8-sig")
        logger.info(f"已儲存上月快取: {prev_month_csv} ({len(prev_month_df)} 筆)")

    # 轉換為 {year: DataFrame} 格式
    history = {}
    for year in range(current_year - years_back, current_year + 1):
        year_df = result_df[result_df["revenue_year"] == year].copy()
        if not year_df.empty:
            year_df["year"] = year
            year_df["month"] = target_month
            history[year] = year_df

    # 把上個月資料附加到 history 中，用特殊 key
    if prev_month_df is not None and not prev_month_df.empty:
        history["prev_month"] = prev_month_df

    return history


def scrape_history(target_month: int, current_year: int, years_back: int = 5) -> dict[int, pd.DataFrame]:
    """主要入口: 抓取歷史同月份營收資料"""
    return scrape_all_revenue(target_month, current_year, years_back)
