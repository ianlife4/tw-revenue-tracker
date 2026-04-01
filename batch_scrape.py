"""
批次爬取 + 生成報表
使用 MOPS 舊版 FileDownLoad 批次下載，一次取得全市場月營收
上市+上櫃: ~2 秒/月 (vs FinMind 逐檔: ~30 分鐘/月)
"""

import os
import sys
import time
import json
import random
import logging
import io

import requests
import urllib3
import pandas as pd

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import DATA_DIR, HEADERS
from analyzer import find_revenue_new_highs, format_revenue
from html_generator import generate_html, save_html

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

MOPS_DL_URL = "https://mopsov.twse.com.tw/server-java/FileDownLoad"

# 欄位對照 (MOPS CSV → 內部格式)
COL_MAP = {
    "公司代號": "stock_id",
    "公司名稱": "stock_name",
    "產業別": "industry",
    "營業收入-當月營收": "revenue",
    "營業收入-上月營收": "prev_month_revenue",
    "營業收入-去年當月營收": "prev_year_revenue",
    "營業收入-上月比較增減(%)": "mom_pct",
    "營業收入-去年同月增減(%)": "yoy_pct",
    "出表日期": "publish_date",
    "資料年月": "period",
}


def fetch_mops_monthly(roc_year: int, month: int, market: str = "sii") -> pd.DataFrame:
    """從 MOPS 舊版下載單月全市場營收 CSV

    Args:
        roc_year: 民國年
        month: 月份
        market: 'sii' (上市), 'otc' (上櫃), 'rotc' (興櫃)

    Returns:
        DataFrame with standardized columns
    """
    fpath = f"/t21/{market}/"
    fname = f"t21sc03_{roc_year}_{month}.csv"

    payload = {
        "step": "9",
        "functionName": "show_file2",
        "filePath": fpath,
        "fileName": fname,
    }

    try:
        resp = requests.post(
            MOPS_DL_URL, data=payload, headers=HEADERS,
            verify=False, timeout=30,
        )
        if resp.status_code != 200 or len(resp.content) < 2000:
            logger.warning(f"  {market} {roc_year}/{month}: 無資料 (status={resp.status_code}, len={len(resp.content)})")
            return pd.DataFrame()

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

        # 轉換
        western_year = roc_year + 1911
        df["revenue_year"] = western_year
        df["revenue_month"] = month
        # rotc → emerging (內部統一用 emerging 代表興櫃)
        market_internal = "emerging" if market == "rotc" else market
        df["market"] = market_internal
        df["stock_id"] = df["stock_id"].astype(str).str.strip()
        df["date"] = df.get("publish_date", "")

        # 營收轉數值 (MOPS 單位: 千元 → 元)
        for col in ["revenue", "prev_month_revenue", "prev_year_revenue"]:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(",", ""), errors="coerce"
                ) * 1000  # 千元轉元

        # yoy/mom 轉數值
        for col in ["yoy_pct", "mom_pct"]:
            if col in df.columns:
                df[col] = pd.to_numeric(
                    df[col].astype(str).str.replace(",", ""), errors="coerce"
                )

        # 只保留4碼數字代號 (過濾合計列等)
        df = df[df["stock_id"].str.match(r"^\d{4}$", na=False)].copy()

        return df

    except Exception as e:
        logger.error(f"  {market} {roc_year}/{month}: 錯誤 {e}")
        return pd.DataFrame()


def scrape_all_months(end_year: int, end_month: int, months_back: int = 12, years_back: int = 5):
    """批次下載所有需要的月份營收資料

    下載策略:
    1. 近 months_back 個月的完整資料 (用於逐月報表)
    2. 每個月再往前 years_back 年的同月資料 (用於同期新高比較)
    """
    cache_path = os.path.join(DATA_DIR, "all_revenue_mops.csv")

    # 計算需要抓取的所有 (year, month) 組合
    periods_needed = set()

    # 近 N 個月
    y, m = end_year, end_month
    recent_months = []
    for _ in range(months_back):
        recent_months.append((y, m))
        # 這個月 + 往前 years_back 年同月
        for yb in range(years_back + 1):
            periods_needed.add((y - yb, m))
        # 上個月 (用於月增率)
        pm = m - 1 if m > 1 else 12
        py = y if m > 1 else y - 1
        periods_needed.add((py, pm))
        # 上個月的去年同月 (MoM 柱狀圖需要)
        periods_needed.add((py - 1, pm))

        m -= 1
        if m == 0:
            m = 12
            y -= 1
    recent_months.reverse()

    # 還需要近 24 個月的資料 (MoM 柱狀圖)
    y, m = end_year, end_month
    for _ in range(24):
        periods_needed.add((y, m))
        periods_needed.add((y - 1, m))  # 去年同月
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    # 過濾掉不合理的年份
    periods_needed = {(y, m) for y, m in periods_needed if y >= 2018 and 1 <= m <= 12}

    logger.info(f"需要抓取 {len(periods_needed)} 個月份 x 3 市場 = {len(periods_needed)*3} 次下載")

    # 檢查快取
    cached_df = None
    cached_periods = set()
    if os.path.exists(cache_path):
        cached_df = pd.read_csv(cache_path, dtype={"stock_id": str})
        for _, grp in cached_df.groupby(["revenue_year", "revenue_month", "market"]):
            row = grp.iloc[0]
            cached_periods.add((int(row["revenue_year"]), int(row["revenue_month"]), row["market"]))

    # 計算還缺哪些 (上市 sii + 上櫃 otc + 興櫃 rotc)
    # 注意: 快取中興櫃存為 "emerging"，但 MOPS 路徑用 "rotc"
    missing = []
    for y, m in sorted(periods_needed):
        roc = y - 1911
        for mops_mkt, cache_mkt in [("sii", "sii"), ("otc", "otc"), ("rotc", "emerging")]:
            if (y, m, cache_mkt) not in cached_periods:
                missing.append((roc, m, mops_mkt, y))

    if not missing:
        logger.info("全部命中快取，無需下載")
        return cached_df, recent_months

    logger.info(f"需要下載 {len(missing)} 個新的月份/市場組合")

    all_frames = [cached_df] if cached_df is not None else []
    downloaded = 0

    for roc, month, mkt, western in missing:
        df = fetch_mops_monthly(roc, month, mkt)
        if not df.empty:
            all_frames.append(df)
            downloaded += 1
            logger.info(f"  [{downloaded}/{len(missing)}] {western}/{month:02d} {mkt}: {len(df)} 筆")
        else:
            logger.info(f"  [{downloaded}/{len(missing)}] {western}/{month:02d} {mkt}: 無資料")
        time.sleep(random.uniform(0.5, 1.0))

    if not all_frames:
        return pd.DataFrame(), recent_months

    result = pd.concat(all_frames, ignore_index=True)
    result = result.drop_duplicates(
        subset=["stock_id", "revenue_year", "revenue_month", "market"], keep="last"
    )

    # 標記創新板
    sl_path = os.path.join(DATA_DIR, "stock_list.csv")
    if os.path.exists(sl_path):
        sl = pd.read_csv(sl_path, dtype={"stock_id": str})
        tib_ids = set(sl[sl.get("is_tib", pd.Series(dtype=bool)) == True]["stock_id"].unique())
        if not tib_ids:
            # fallback: 名稱以「創」結尾
            tib_ids = set(sl[sl["stock_name"].str.endswith("創", na=False)]["stock_id"].unique())
        if tib_ids:
            result.loc[result["stock_id"].isin(tib_ids), "market"] = "tib"
            logger.info(f"標記 {len(tib_ids)} 檔創新板股票")

    os.makedirs(DATA_DIR, exist_ok=True)
    result.to_csv(cache_path, index=False, encoding="utf-8-sig")
    logger.info(f"已儲存: {cache_path} ({len(result)} 筆)")

    return result, recent_months


def generate_month_report(full_df: pd.DataFrame, year: int, month: int, years_back: int = 5):
    """用全量資料為指定月份生成報表"""

    logger.info(f"--- 生成 {year}/{month:02d} 報表 ---")

    # 篩選目標月份的歷年資料
    month_df = full_df[full_df["revenue_month"] == month].copy()
    if month_df.empty:
        logger.warning(f"  {year}/{month:02d}: 無資料")
        return 0

    # 建 history dict
    history = {}
    for y in range(year - years_back, year + 1):
        year_df = month_df[month_df["revenue_year"] == y].copy()
        if not year_df.empty:
            year_df["year"] = y
            year_df["month"] = month
            history[y] = year_df

    if year not in history:
        logger.warning(f"  {year}/{month:02d}: 無當年資料")
        return 0

    # 上個月資料 (月增率已在 MOPS CSV 中，但也可用 prev_month 資料)
    if month == 1:
        prev_m, prev_y = 12, year - 1
    else:
        prev_m, prev_y = month - 1, year
    prev_df = full_df[
        (full_df["revenue_month"] == prev_m) &
        (full_df["revenue_year"] == prev_y)
    ].copy()
    if not prev_df.empty:
        history["prev_month"] = prev_df

    # 分析
    new_highs = find_revenue_new_highs(history, year)

    if new_highs.empty:
        logger.info(f"  {year}/{month:02d}: 無新高")
        html = generate_html(new_highs, year, month, years_back)
        save_html(html, f"{year}_{month:02d}.html")
        return 0

    logger.info(f"  {year}/{month:02d}: {len(new_highs)} 檔新高")

    # MOPS 已有 yoy/mom，但 analyzer 也會計算，用 MOPS 的回填空值
    cur_df = full_df[
        (full_df["revenue_month"] == month) &
        (full_df["revenue_year"] == year)
    ].copy()
    mops_yoy = dict(zip(cur_df["stock_id"], cur_df.get("yoy_pct", pd.Series())))
    mops_mom = dict(zip(cur_df["stock_id"], cur_df.get("mom_pct", pd.Series())))
    for idx, row in new_highs.iterrows():
        sid = row["stock_id"]
        if pd.isna(row.get("yoy_pct")) and sid in mops_yoy and pd.notna(mops_yoy.get(sid)):
            new_highs.at[idx, "yoy_pct"] = mops_yoy[sid]
        if pd.isna(row.get("mom_pct")) and sid in mops_mom and pd.notna(mops_mom.get(sid)):
            new_highs.at[idx, "mom_pct"] = mops_mom[sid]

    # MoM 柱狀圖資料
    stock_ids = new_highs["stock_id"].tolist()
    monthly_data = _get_monthly_chart_data(full_df, stock_ids, year, month)
    new_highs["monthly_json"] = new_highs["stock_id"].map(
        lambda sid: json.dumps(monthly_data.get(sid, []), ensure_ascii=False)
    )

    # 生成 HTML
    html = generate_html(new_highs, year, month, years_back)
    save_html(html, f"{year}_{month:02d}.html")

    return len(new_highs)


def _get_monthly_chart_data(full_df, stock_ids, year, month):
    """從全量資料中提取近 12 個月 + 去年同期營收"""
    result = {}
    for sid in stock_ids:
        stock_df = full_df[full_df["stock_id"] == sid].copy()
        if stock_df.empty:
            result[sid] = []
            continue
        stock_df = stock_df.sort_values(["revenue_year", "revenue_month"])
        records = []
        for _, row in stock_df.iterrows():
            ry = int(row["revenue_year"])
            rm = int(row["revenue_month"])
            rv = float(row["revenue"]) if pd.notna(row["revenue"]) else 0
            month_diff = (year - ry) * 12 + (month - rm)
            if 0 <= month_diff <= 24:
                records.append({"year": ry, "month": rm, "revenue": rv})
        result[sid] = records
    return result


def main():
    end_year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    end_month = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    months_back = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    years_back = 5

    logger.info(f"===== 批次生成報表: 近 {months_back} 個月 (至 {end_year}/{end_month:02d}) =====")
    logger.info(f"使用 MOPS 舊版 FileDownLoad 批次下載")

    # Step 1: 下載所有需要的資料
    logger.info("Step 1: 下載營收資料...")
    full_df, recent_months = scrape_all_months(end_year, end_month, months_back, years_back)

    if full_df.empty:
        logger.error("無資料")
        return

    logger.info(f"全量資料: {len(full_df)} 筆, "
                f"期間 {int(full_df['revenue_year'].min())}~{int(full_df['revenue_year'].max())}, "
                f"股票 {full_df['stock_id'].nunique()} 檔")

    # Step 2: 逐月生成報表
    logger.info(f"Step 2: 逐月生成報表 ({len(recent_months)} 個月)...")

    summary = []
    for y, m in recent_months:
        count = generate_month_report(full_df, y, m, years_back)
        summary.append((y, m, count))

    # 最新一期存為 index.html
    import shutil
    latest_y, latest_m = recent_months[-1]
    latest_file = os.path.join("output", f"{latest_y}_{latest_m:02d}.html")
    index_file = os.path.join("output", "index.html")
    if os.path.exists(latest_file):
        shutil.copy2(latest_file, index_file)
        logger.info(f"已複製 {latest_y}_{latest_m:02d}.html → index.html")

    # 摘要
    logger.info("===== 摘要 =====")
    for y, m, cnt in summary:
        logger.info(f"  {y}/{m:02d}: {cnt} 檔創同期新高")
    total = sum(c for _, _, c in summary)
    logger.info(f"  共生成 {len(summary)} 個月報表，合計 {total} 檔次新高")
    logger.info("===== 完成 =====")


if __name__ == "__main__":
    main()
