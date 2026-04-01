"""
快速重建報表 (使用既有快取資料)
不重新爬蟲，只合併資料 + 分析 + 生成 HTML
抓新高股票近 12 個月營收供柱狀圖使用
"""

import os
import sys
import time
import json
import random
import logging
import pandas as pd

from config import DATA_DIR
from analyzer import find_revenue_new_highs, format_revenue
from scraper import fetch_stock_revenue
from html_generator import generate_html, save_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def fetch_monthly_revenue(stock_ids: list[str], year: int, month: int) -> dict[str, list]:
    """抓取股票近 12 個月 + 去年同期營收 (共 24 個月)

    Returns:
        {stock_id: [{"year": y, "month": m, "revenue": r}, ...]}
        涵蓋近兩年，供 MoM 雙柱圖使用 (本期 vs 前期)
    """
    cache_path = os.path.join(DATA_DIR, f"monthly_24m_y{year}_m{month:02d}.json")

    # 檢查快取
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        missing = [sid for sid in stock_ids if sid not in cached]
        if not missing:
            logger.info(f"24 個月營收快取命中: {len(cached)} 檔")
            return cached
        logger.info(f"快取部分命中，還需抓取 {len(missing)} 檔")
    else:
        cached = {}
        missing = stock_ids

    # 抓取近 24 個月: 例如 2026/02 → 需要 2024/03 ~ 2026/02
    start_date = f"{year - 2}-{month + 1:02d}-01" if month < 12 else f"{year - 2}-01-01"
    end_date = f"{year}-{month + 1:02d}-01" if month < 12 else f"{year + 1}-01-01"

    logger.info(f"抓取 {len(missing)} 檔近 24 個月營收 ({start_date} ~ {end_date})...")

    for i, sid in enumerate(missing):
        df = fetch_stock_revenue(sid, start_date, end_date)
        if not df.empty:
            df = df.sort_values(["revenue_year", "revenue_month"])
            records = []
            for _, row in df.iterrows():
                records.append({
                    "year": int(row["revenue_year"]),
                    "month": int(row["revenue_month"]),
                    "revenue": float(row["revenue"]),
                })
            cached[sid] = records[-24:]
            logger.info(f"  [{i+1}/{len(missing)}] {sid}: {len(cached[sid])} 個月")
        else:
            cached[sid] = []
            logger.info(f"  [{i+1}/{len(missing)}] {sid}: 無資料")

        time.sleep(random.uniform(0.3, 0.6))

    # 儲存快取
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cached, f, ensure_ascii=False)
    logger.info(f"已儲存 24 個月營收快取: {cache_path}")

    return cached


def rebuild(year: int = 2026, month: int = 2, years_back: int = 5):
    """用快取資料重建報表"""

    csv_path = os.path.join(DATA_DIR, f"all_revenue_m{month:02d}.csv")
    emerging_csv = os.path.join(DATA_DIR, f"emerging_revenue_m{month:02d}.csv")

    # 載入主要營收快取 (FinMind: 上市+上櫃+創新板)
    if not os.path.exists(csv_path):
        logger.error(f"找不到快取: {csv_path}")
        return
    result_df = pd.read_csv(csv_path, dtype={"stock_id": str})
    logger.info(f"已載入主快取: {len(result_df)} 筆 (市場: {result_df.groupby('market').size().to_dict()})")

    # 載入興櫃營收快取 (MoneyDJ)
    if os.path.exists(emerging_csv):
        em_df = pd.read_csv(emerging_csv, dtype={"stock_id": str})
        logger.info(f"已載入興櫃快取: {len(em_df)} 筆")

        em_converted = pd.DataFrame({
            "stock_id": em_df["stock_id"],
            "stock_name": em_df["stock_name"],
            "revenue": em_df["revenue_k"] * 1000,
            "revenue_month": month,
            "revenue_year": year,
            "market": "emerging",
            "industry": "興櫃",
            "date": f"{year}-{month+1:02d}-01" if month < 12 else f"{year+1}-01-01",
            "country": "Taiwan",
        })

        # 用 stock_list 的 industry_category 更新興櫃產業
        sl_path = os.path.join(DATA_DIR, "stock_list.csv")
        if os.path.exists(sl_path):
            sl = pd.read_csv(sl_path, dtype={"stock_id": str})
            em_industry = sl[sl["type"] == "emerging"][["stock_id", "industry_category"]].drop_duplicates("stock_id")
            em_industry.columns = ["stock_id", "industry_from_sl"]
            em_converted = em_converted.merge(em_industry, on="stock_id", how="left")
            mask = em_converted["industry_from_sl"].notna() & (em_converted["industry_from_sl"] != "")
            em_converted.loc[mask, "industry"] = em_converted.loc[mask, "industry_from_sl"]
            em_converted = em_converted.drop(columns=["industry_from_sl"])
            logger.info(f"興櫃產業分類: {mask.sum()}/{len(em_converted)} 檔")

        em_converted["yoy_pct_raw"] = em_df["yoy_pct"].str.rstrip("%").astype(float, errors="ignore")
        em_converted["mom_pct_raw"] = em_df["mom_pct"].str.rstrip("%").astype(float, errors="ignore")

        result_df = result_df[result_df["market"] != "emerging"]
        result_df = pd.concat([result_df, em_converted], ignore_index=True)
        logger.info(f"合併後: {len(result_df)} 筆")
    else:
        logger.warning(f"無興櫃快取: {emerging_csv}")

    # 建 history dict
    history = {}
    for y in range(year - years_back, year + 1):
        year_df = result_df[result_df["revenue_year"] == y].copy()
        if not year_df.empty:
            year_df["year"] = y
            year_df["month"] = month
            history[y] = year_df

    logger.info(f"歷史年份: {sorted([k for k in history.keys() if isinstance(k, int)])}")

    # 載入上月資料
    import glob
    prev_csvs = glob.glob(os.path.join(DATA_DIR, f"prev_month_m*_y{year}.csv"))
    if prev_csvs:
        pm_df = pd.read_csv(prev_csvs[0], dtype={"stock_id": str})
        history["prev_month"] = pm_df
        logger.info(f"已載入上月資料: {len(pm_df)} 筆")

    # 分析
    new_highs = find_revenue_new_highs(history, year)
    logger.info(f"共 {len(new_highs)} 檔營收創同期新高")

    if not new_highs.empty:
        # 興櫃 MoneyDJ yoy/mom 回填
        if os.path.exists(emerging_csv):
            em_df = pd.read_csv(emerging_csv, dtype={"stock_id": str})
            em_yoy = dict(zip(em_df["stock_id"], em_df["yoy_pct"].str.rstrip("%")))
            em_mom = dict(zip(em_df["stock_id"], em_df["mom_pct"].str.rstrip("%")))
            for idx, row in new_highs.iterrows():
                if row["market"] == "emerging":
                    sid = row["stock_id"]
                    if sid in em_yoy and pd.isna(row.get("yoy_pct")):
                        try:
                            new_highs.at[idx, "yoy_pct"] = float(em_yoy[sid])
                        except (ValueError, TypeError):
                            pass
                    if sid in em_mom and pd.isna(row.get("mom_pct")):
                        try:
                            new_highs.at[idx, "mom_pct"] = float(em_mom[sid])
                        except (ValueError, TypeError):
                            pass

        for mkt in ["sii", "otc", "tib", "emerging"]:
            cnt = len(new_highs[new_highs["market"] == mkt])
            if cnt > 0:
                logger.info(f"  {mkt}: {cnt} 檔")
        logger.info(f"產業數: {new_highs['industry'].nunique()}")

        # --- 抓近 12 個月營收 (供柱狀圖) ---
        stock_ids = new_highs["stock_id"].tolist()
        monthly_data = fetch_monthly_revenue(stock_ids, year, month)

        # 寫入 DataFrame 的 monthly_json 欄位
        new_highs["monthly_json"] = new_highs["stock_id"].map(
            lambda sid: json.dumps(monthly_data.get(sid, []), ensure_ascii=False)
        )

    # 生成 HTML
    html = generate_html(new_highs, year, month, years_back)
    output_path = save_html(html, "index.html")
    archive_name = f"{year}_{month:02d}.html"
    save_html(html, archive_name)
    logger.info(f"報表已輸出: {output_path} + {archive_name}")
    logger.info("===== 完成 =====")


if __name__ == "__main__":
    y = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    m = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    rebuild(y, m)
