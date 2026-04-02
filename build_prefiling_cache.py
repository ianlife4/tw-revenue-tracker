"""
批次建立 T-1 預警快取

掃描歷史上在指定月份曾多次創同期新高且近期 (>=2023) 仍有新高的股票，
批次抓取股價並計算 T+1 表現，存入快取。

一次性執行，之後 monitor.py 即可從快取讀取預警清單。
"""

import json
import logging
import os
import sys
import time

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

from config import get_current_period
from t1_analysis import (
    T1_CACHE_FILE, DATA_DIR,
    find_historical_period_highs,
    analyze_stock_t1,
)


def build_cache(target_month: int = None, min_highs: int = 2,
                recent_year: int = 2023, max_stocks: int = 200):
    """批次建立 T+1 快取"""

    if target_month is None:
        _, target_month = get_current_period()

    logger.info(f"目標月份: {target_month}月, 最少新高: {min_highs}次, 近期門檻: >={recent_year}年")

    # 載入歷史營收
    cache_file = os.path.join(DATA_DIR, "all_revenue_mops.csv")
    if not os.path.exists(cache_file):
        logger.error(f"找不到 {cache_file}")
        return

    full_df = pd.read_csv(cache_file, dtype={"stock_id": str})
    month_data = full_df[full_df["revenue_month"] == target_month]
    stock_ids = month_data["stock_id"].unique()
    logger.info(f"共 {len(stock_ids)} 檔有 {target_month}月營收資料")

    # 載入既有快取
    cache = {}
    if os.path.exists(T1_CACHE_FILE):
        try:
            with open(T1_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    # 篩選候選股票
    candidates = []
    for sid in stock_ids:
        cache_key = f"{sid}_{target_month}"
        # 已在快取中且有結果的跳過
        if cache_key in cache and cache[cache_key].get("count", 0) > 0:
            continue

        highs = find_historical_period_highs(sid, full_df, target_month)
        if len(highs) < min_highs:
            continue

        # 必須近期有創新高
        if not any(h["year"] >= recent_year for h in highs):
            continue

        # 取得市場別
        stock_rows = month_data[month_data["stock_id"] == sid]
        latest = stock_rows.sort_values("revenue_year").iloc[-1]
        market = str(latest.get("market", "sii"))

        candidates.append({
            "stock_id": sid,
            "market": market,
            "high_count": len(highs),
            "last_high_year": max(h["year"] for h in highs),
        })

    # 依最近新高年份和次數排序
    candidates.sort(key=lambda x: (-x["last_high_year"], -x["high_count"]))

    # 限制數量
    if len(candidates) > max_stocks:
        candidates = candidates[:max_stocks]

    logger.info(f"候選股票: {len(candidates)} 檔 (快取已有 {len(cache)} 筆)")

    # 批次分析
    success = 0
    for i, c in enumerate(candidates, 1):
        sid = c["stock_id"]
        market = c["market"]
        logger.info(f"  [{i}/{len(candidates)}] {sid} (市場={market}, "
                    f"新高{c['high_count']}次, 最近{c['last_high_year']}年)")

        try:
            result = analyze_stock_t1(
                stock_id=sid, market=market, full_df=full_df,
                target_month=target_month, current_filing_date=None,
                cache=cache,
            )
            if result.get("count", 0) > 0:
                success += 1
                avg = result.get("avg_t1", 0)
                hit = result.get("hit_rate", 0)
                logger.info(f"    => count={result['count']}, avg_t1={avg:.1f}%, hit_rate={hit:.0f}%")
            else:
                logger.info(f"    => 無有效 T+1 資料")
        except Exception as e:
            logger.warning(f"    => 錯誤: {e}")

        # 每 10 筆存一次快取
        if i % 10 == 0:
            _save_cache(cache)
            logger.info(f"  --- 已存快取 ({success}/{i}) ---")

        # 避免 API 限速
        time.sleep(0.2)

    # 最終存檔
    _save_cache(cache)

    # 統計
    good = sum(1 for k, v in cache.items()
               if k.endswith(f"_{target_month}") and
               v.get("avg_t1", -999) >= 1.5 and
               v.get("hit_rate", 0) >= 50 and
               v.get("count", 0) >= 2)

    logger.info(f"\n完成! 成功分析: {success}/{len(candidates)}")
    logger.info(f"快取總計: {len(cache)} 筆")
    logger.info(f"符合預警條件 (avg>=1.5%, hit>=50%, count>=2): {good} 檔")


def _save_cache(cache):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(T1_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    month = None
    if len(sys.argv) > 1:
        month = int(sys.argv[1])
    build_cache(target_month=month, max_stocks=150)
