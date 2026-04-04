"""
用現有的 all_revenue_full.csv 重新產生所有月份的 HTML
不需要爬蟲，只重建 HTML（套用最新模板）
"""
import os
import sys
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

import pandas as pd
from config import DATA_DIR, OUTPUT_DIR
from batch_scrape import generate_month_report

FULL_CSV = os.path.join(DATA_DIR, "all_revenue_full.csv")


def main():
    if not os.path.exists(FULL_CSV):
        logger.error(f"找不到 {FULL_CSV}")
        return

    full_df = pd.read_csv(FULL_CSV, dtype={"stock_id": str})
    logger.info(f"載入全量資料: {len(full_df)} 筆")

    # 找出 output/ 下所有已存在的月份檔案
    existing = []
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith(".html") and "_" in f and f != "index.html":
            parts = f.replace(".html", "").split("_")
            if len(parts) == 2:
                try:
                    y, m = int(parts[0]), int(parts[1])
                    existing.append((y, m))
                except ValueError:
                    pass

    if not existing:
        logger.error("output/ 下無月份檔案")
        return

    logger.info(f"將重建 {len(existing)} 個月份: {existing}")

    for y, m in existing:
        try:
            count = generate_month_report(full_df, y, m, years_back=5)
            logger.info(f"  {y}/{m:02d}: {count} 檔新高")
        except Exception as e:
            logger.error(f"  {y}/{m:02d} 失敗: {e}")

    # 複製最新一期為 index.html
    import shutil
    latest_y, latest_m = existing[-1]
    latest_file = os.path.join(OUTPUT_DIR, f"{latest_y}_{latest_m:02d}.html")
    index_file = os.path.join(OUTPUT_DIR, "index.html")
    if os.path.exists(latest_file):
        shutil.copy2(latest_file, index_file)
        logger.info(f"已複製 {latest_y}_{latest_m:02d}.html → index.html")

    logger.info("✅ 全部重建完成")


if __name__ == "__main__":
    main()
