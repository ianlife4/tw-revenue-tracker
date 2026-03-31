"""
快速補抓上個月營收，用於計算月增率 (MoM)
只針對已篩選出的新高股票抓取，不需重跑全部 3006 檔
"""

import os
import sys
import time
import random
import logging
import pandas as pd

from config import DATA_DIR
from scraper import fetch_stock_revenue
from analyzer import find_revenue_new_highs, format_revenue
from html_generator import generate_html, save_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def patch_prev_month(year: int = 2026, month: int = 2, years_back: int = 5):
    """補抓上個月營收並重新生成報表"""

    # 計算上個月
    if month == 1:
        prev_month = 12
        prev_month_year = year - 1
    else:
        prev_month = month - 1
        prev_month_year = year

    logger.info(f"目標: {year}/{month:02d}，上個月: {prev_month_year}/{prev_month:02d}")

    # 讀取已有的目標月快取
    csv_path = os.path.join(DATA_DIR, f"all_revenue_m{month:02d}.csv")
    if not os.path.exists(csv_path):
        logger.error(f"找不到快取: {csv_path}，請先執行 main.py")
        return

    result_df = pd.read_csv(csv_path, dtype={"stock_id": str})
    logger.info(f"已載入目標月快取: {len(result_df)} 筆")

    # 重建 history
    history = {}
    for y in range(year - years_back, year + 1):
        year_df = result_df[result_df["revenue_year"] == y].copy()
        if not year_df.empty:
            year_df["year"] = y
            year_df["month"] = month
            history[y] = year_df

    # 先跑一次分析找出新高股票清單
    new_highs_temp = find_revenue_new_highs(history, year)
    if new_highs_temp.empty:
        logger.info("無新高股票，不需補抓")
        return

    stock_ids = new_highs_temp["stock_id"].tolist()
    logger.info(f"需要補抓 {len(stock_ids)} 檔上月營收...")

    # 只抓這些股票的上個月營收
    prev_month_records = []
    for i, sid in enumerate(stock_ids):
        start_date = f"{prev_month_year}-01-01"
        end_date = f"{prev_month_year}-12-31"
        df = fetch_stock_revenue(sid, start_date, end_date)
        if not df.empty:
            pm_df = df[
                (df["revenue_month"] == prev_month) &
                (df["revenue_year"] == prev_month_year)
            ].copy()
            if not pm_df.empty:
                prev_month_records.append(pm_df)
                rev = pm_df.iloc[0]["revenue"]
                logger.info(f"  [{i+1}/{len(stock_ids)}] {sid}: 上月營收 = {format_revenue(rev)}")
            else:
                logger.info(f"  [{i+1}/{len(stock_ids)}] {sid}: 無上月資料")
        else:
            logger.info(f"  [{i+1}/{len(stock_ids)}] {sid}: 查詢失敗")
        time.sleep(random.uniform(0.3, 0.6))

    if prev_month_records:
        prev_month_df = pd.concat(prev_month_records, ignore_index=True)
        prev_month_df = prev_month_df.drop_duplicates(subset=["stock_id"], keep="first")
        history["prev_month"] = prev_month_df
        logger.info(f"成功取得 {len(prev_month_df)} 檔上月營收")
    else:
        logger.warning("未取得任何上月營收資料")

    # 重新分析 (這次有 prev_month 資料了)
    new_highs = find_revenue_new_highs(history, year)
    logger.info(f"共 {len(new_highs)} 檔營收創同期新高")

    if "mom_pct" in new_highs.columns:
        has_mom = new_highs["mom_pct"].notna().sum()
        logger.info(f"其中 {has_mom} 檔有月增率資料")

    # 重新生成 HTML
    html = generate_html(new_highs, year, month, years_back)
    output_path = save_html(html)
    logger.info(f"報表已更新: {output_path}")
    logger.info("===== 完成 =====")


if __name__ == "__main__":
    y = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    m = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    patch_prev_month(y, m)
