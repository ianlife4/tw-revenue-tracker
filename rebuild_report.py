"""
快速重建報表 (使用既有快取資料)
不重新爬蟲，只合併資料 + 分析 + 生成 HTML
"""

import os
import sys
import logging
import pandas as pd

from config import DATA_DIR
from analyzer import find_revenue_new_highs
from html_generator import generate_html, save_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def rebuild(year: int = 2026, month: int = 2, years_back: int = 5):
    """用快取資料重建報表"""

    csv_path = os.path.join(DATA_DIR, f"all_revenue_m{month:02d}.csv")
    emerging_csv = os.path.join(DATA_DIR, f"emerging_revenue_m{month:02d}.csv")
    prev_month_csv_pattern = os.path.join(DATA_DIR, f"prev_month_m*_y{year}.csv")

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

        # 轉換為 FinMind 格式
        em_converted = pd.DataFrame({
            "stock_id": em_df["stock_id"],
            "stock_name": em_df["stock_name"],
            "revenue": em_df["revenue_k"] * 1000,  # 千元 → 元
            "revenue_month": month,
            "revenue_year": year,
            "market": "emerging",
            "industry": "興櫃",  # 預設產業
            "date": f"{year}-{month+1:02d}-01" if month < 12 else f"{year+1}-01-01",
            "country": "Taiwan",
        })

        # 用 stock_list 的 industry_category 更新興櫃產業
        sl_path = os.path.join(DATA_DIR, "stock_list.csv")
        if os.path.exists(sl_path):
            sl = pd.read_csv(sl_path, dtype={"stock_id": str})
            # 過濾 emerging 的產業分類
            em_industry = sl[sl["type"] == "emerging"][["stock_id", "industry_category"]].drop_duplicates("stock_id")
            em_industry.columns = ["stock_id", "industry_from_sl"]
            em_converted = em_converted.merge(em_industry, on="stock_id", how="left")
            mask = em_converted["industry_from_sl"].notna() & (em_converted["industry_from_sl"] != "")
            em_converted.loc[mask, "industry"] = em_converted.loc[mask, "industry_from_sl"]
            em_converted = em_converted.drop(columns=["industry_from_sl"])
            has_industry = mask.sum()
            logger.info(f"興櫃產業分類: {has_industry}/{len(em_converted)} 檔有 FinMind 產業分類")

        # 只保留今年興櫃資料 (興櫃無歷史比較)
        # MoneyDJ 只有當月數據，放入 history[year] 中
        # 但我們只取 yoy > 20% 的作為近似「創同期新高」
        em_converted["yoy_pct_raw"] = em_df["yoy_pct"].str.rstrip("%").astype(float, errors="ignore")
        em_converted["mom_pct_raw"] = em_df["mom_pct"].str.rstrip("%").astype(float, errors="ignore")

        # 合併到主快取 (只合併當年)
        # 移除主快取中的興櫃重複
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

    # 載入上月資料 (如果有)
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
        # 興櫃特殊處理: MoneyDJ 沒有歷史同期資料，用 yoy > 20% 近似
        # 把 MoneyDJ 的 yoy/mom 填入
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

        # 產業分佈
        logger.info(f"產業數: {new_highs['industry'].nunique()}")

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
