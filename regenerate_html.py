"""
只重新產生 HTML（不爬資料），使用現有的 data/ 資料
用途：修改 html_generator.py 模板後，快速重建 HTML
"""
import os
import sys
import json
import logging
import pandas as pd

# 設定路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import DATA_DIR, OUTPUT_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(DATA_DIR, "all_revenue_mops.csv")
STATE_FILE = os.path.join(DATA_DIR, "monitor_state.json")


def main():
    # 載入 state
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    rev_year = state["period_year"]
    rev_month = state["period_month"]
    logger.info(f"重新產生 {rev_year} 年 {rev_month} 月報表")

    # 載入當月 MOPS 資料
    if not os.path.exists(CACHE_FILE):
        logger.error(f"找不到 {CACHE_FILE}")
        return

    mops_df = pd.read_csv(CACHE_FILE, dtype={"stock_id": str})
    logger.info(f"MOPS 資料: {len(mops_df)} 筆")

    # 載入歷史資料
    full_path = os.path.join(DATA_DIR, "all_revenue_full.csv")
    if os.path.exists(full_path):
        full_df = pd.read_csv(full_path, dtype={"stock_id": str})
        logger.info(f"歷史資料: {len(full_df)} 筆")
    else:
        full_df = None
        logger.warning("無歷史資料")

    # 用 monitor.py 的 generate_period_high_report 邏輯
    from analyzer import find_revenue_new_highs
    from html_generator import generate_html, save_html

    if full_df is None or full_df.empty:
        logger.error("缺少歷史資料，無法產生報表")
        return

    # 建立 history dict
    history = {}
    hist_month = full_df[full_df["revenue_month"] == rev_month]
    for y in hist_month["revenue_year"].unique():
        year_df = hist_month[hist_month["revenue_year"] == y].copy()
        if not year_df.empty:
            history[int(y)] = year_df

    # 加入當月即時資料
    cur = mops_df.copy()
    cur["revenue_year"] = rev_year
    cur["revenue_month"] = rev_month
    history[rev_year] = cur

    logger.info(f"比對年份: {sorted(history.keys())}")

    # 上月資料
    prev_m = rev_month - 1 if rev_month > 1 else 12
    prev_y = rev_year if rev_month > 1 else rev_year - 1
    prev_df = full_df[(full_df["revenue_year"] == prev_y) & (full_df["revenue_month"] == prev_m)]
    if not prev_df.empty:
        history["prev_month"] = prev_df

    # 分析營收創同期新高
    new_highs = find_revenue_new_highs(history, rev_year)
    logger.info(f"營收創同期新高: {len(new_highs)} 檔")

    if not new_highs.empty:
        # 注入 first_seen
        stocks_state = state.get("stocks", {})
        for idx, row in new_highs.iterrows():
            sid = str(row["stock_id"])
            fs = stocks_state.get(sid, {}).get("first_seen", "")
            new_highs.at[idx, "first_seen"] = fs

        # 歷史柱狀圖資料
        for idx, row in new_highs.iterrows():
            sid = row["stock_id"]
            stock_hist = full_df[full_df["stock_id"] == sid].copy()
            cur_row = mops_df[mops_df["stock_id"] == sid]
            if not cur_row.empty:
                stock_hist = pd.concat([stock_hist, cur_row], ignore_index=True)
            stock_hist = stock_hist.sort_values(["revenue_year", "revenue_month"])
            records = []
            for _, r in stock_hist.iterrows():
                if pd.notna(r.get("revenue")) and r["revenue"] > 0:
                    records.append({
                        "year": int(r["revenue_year"]),
                        "month": int(r["revenue_month"]),
                        "revenue": float(r["revenue"]),
                    })
            new_highs.at[idx, "monthly_json"] = json.dumps(records[-24:], ensure_ascii=False)

        # T+1 分析
        try:
            from t1_analysis import analyze_all_period_highs, generate_early_alerts
            logger.info("開始 T+1 歷史股價分析...")
            t1_results = analyze_all_period_highs(new_highs, full_df, state, rev_month)
            early_alerts = generate_early_alerts(t1_results)
            logger.info(f"T+1 分析完成: {sum(1 for r in t1_results if r.get('count',0)>0)} 檔有歷史資料")

            t1_map = {r["stock_id"]: r for r in t1_results}
            for idx, row in new_highs.iterrows():
                sid = row["stock_id"]
                t1 = t1_map.get(sid, {})
                new_highs.at[idx, "t1_avg"] = t1.get("avg_t1", None)
                new_highs.at[idx, "t1_hit_rate"] = t1.get("hit_rate", None)
                new_highs.at[idx, "t1_count"] = t1.get("count", 0)
                new_highs.at[idx, "t1_max"] = t1.get("max_t1", None)
                new_highs.at[idx, "t1_detail_json"] = json.dumps(
                    t1.get("historical_highs", []), ensure_ascii=False
                )
        except Exception as e:
            logger.warning(f"T+1 分析失敗（可能缺少股價資料）: {e}")
            early_alerts = []

    # 生成 HTML
    html = generate_html(new_highs, rev_year, rev_month, compare_years=5,
                         early_alerts=[])  # early_alerts 清空，不需要推播
    archive_name = f"{rev_year}_{rev_month:02d}.html"
    save_html(html, archive_name)
    logger.info(f"✅ 報表已重新產生: output/{archive_name}")


if __name__ == "__main__":
    main()
