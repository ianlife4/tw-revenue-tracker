"""
營收創同期新高追蹤系統 - 主程式
用法:
    python main.py                      # 自動查最近一期
    python main.py --year 2026 --month 2  # 指定年月
"""

import argparse
import logging
import os
import webbrowser

from config import get_current_period, HISTORY_YEARS
from scraper import scrape_history
from analyzer import find_revenue_new_highs
from html_generator import generate_html, save_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="營收創同期新高追蹤系統")
    parser.add_argument("--year", type=int, help="西元年 (預設: 自動判斷最近一期)")
    parser.add_argument("--month", type=int, help="月份 (預設: 自動判斷最近一期)")
    parser.add_argument("--years-back", type=int, default=HISTORY_YEARS, help="比對歷史年數 (預設: 5)")
    parser.add_argument("--no-open", action="store_true", help="不自動開啟瀏覽器")
    args = parser.parse_args()

    if args.year and args.month:
        year, month = args.year, args.month
    else:
        year, month = get_current_period()

    logger.info(f"===== 營收創同期新高追蹤 {year}/{month:02d} =====")
    logger.info(f"比對近 {args.years_back} 年同期資料")

    # Step 1: 爬取歷史資料
    logger.info("Step 1: 爬取營收資料...")
    history = scrape_history(month, year, args.years_back)

    if not history:
        logger.error("無法取得任何營收資料，請檢查網路連線或 MOPS 網站狀態")
        return

    year_keys = sorted([k for k in history.keys() if isinstance(k, int)])
    logger.info(f"已取得 {len(year_keys)} 年資料: {year_keys}")

    # Step 2: 分析營收創同期新高
    logger.info("Step 2: 分析營收創同期新高...")
    new_highs = find_revenue_new_highs(history, year)

    if new_highs.empty:
        logger.info("本期無營收創同期新高")
    else:
        logger.info(f"共 {len(new_highs)} 檔營收創同期新高")

    # Step 3: 生成 HTML 報表
    logger.info("Step 3: 生成 HTML 報表...")
    html = generate_html(new_highs, year, month, args.years_back)
    # 儲存為 index.html (最新) 和 {year}_{month}.html (歷史存檔)
    output_path = save_html(html, "index.html")
    archive_name = f"{year}_{month:02d}.html"
    save_html(html, archive_name)
    logger.info(f"報表已輸出: {output_path} + {archive_name}")

    # 自動開啟瀏覽器
    if not args.no_open:
        webbrowser.open(f"file:///{os.path.abspath(output_path)}")
        logger.info("已在瀏覽器開啟報表")

    logger.info("===== 完成 =====")


if __name__ == "__main__":
    main()
