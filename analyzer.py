"""
營收創同期新高分析模組
比較當月營收與過去 N 年同月營收，篩選出創同期新高的股票
"""

import logging
import pandas as pd

logger = logging.getLogger(__name__)


def find_revenue_new_highs(
    history: dict[int, pd.DataFrame], current_year: int
) -> pd.DataFrame:
    """找出營收創同期新高的股票

    Args:
        history: {year: revenue_df} 歷史資料字典 (FinMind 格式)
        current_year: 當前年份

    Returns:
        營收創同期新高的股票 DataFrame
    """
    if current_year not in history or history[current_year].empty:
        logger.warning(f"無 {current_year} 年營收資料")
        return pd.DataFrame()

    current_df = history[current_year].copy()
    # 去除重複 stock_id (保留營收最高的)
    current_df = current_df.sort_values("revenue", ascending=False).drop_duplicates("stock_id", keep="first")
    past_years = {y: df for y, df in history.items() if isinstance(y, int) and y < current_year}

    if not past_years:
        logger.warning("無歷史資料可比對")
        return pd.DataFrame()

    # 彙整歷史同月最高營收
    past_frames = []
    for year, df in past_years.items():
        if "stock_id" in df.columns and "revenue" in df.columns:
            past_frames.append(df[["stock_id", "revenue"]].copy())

    if not past_frames:
        return pd.DataFrame()

    past_all = pd.concat(past_frames, ignore_index=True)
    past_all = past_all.drop_duplicates(subset=["stock_id", "revenue"])
    past_max = past_all.groupby("stock_id")["revenue"].max().reset_index()
    past_max.columns = ["stock_id", "hist_max_revenue"]

    # 合併比對
    merged = current_df.merge(past_max, on="stock_id", how="inner")
    merged = merged[merged["revenue"].notna() & merged["hist_max_revenue"].notna()]
    merged = merged[merged["revenue"] > 0]
    merged = merged[merged["hist_max_revenue"] > 0]

    # 篩選: 當月營收 > 歷史同月最高
    new_highs = merged[merged["revenue"] > merged["hist_max_revenue"]].copy()
    new_highs = new_highs.drop_duplicates("stock_id", keep="first")

    if new_highs.empty:
        return new_highs

    # 計算超越幅度
    new_highs["exceed_pct"] = (
        (new_highs["revenue"] - new_highs["hist_max_revenue"])
        / new_highs["hist_max_revenue"]
        * 100
    ).round(2)

    # 計算年增率 (與去年同月比) — 只在沒有現成 yoy_pct 時才計算
    if "yoy_pct" not in new_highs.columns or new_highs["yoy_pct"].isna().all():
        prev_year = current_year - 1
        if prev_year in history:
            prev_df = history[prev_year][["stock_id", "revenue"]].copy()
            prev_df.columns = ["stock_id", "py_revenue"]
            new_highs = new_highs.merge(prev_df, on="stock_id", how="left")
            new_highs["yoy_pct"] = (
                (new_highs["revenue"] - new_highs["py_revenue"])
                / new_highs["py_revenue"]
                * 100
            ).round(2)
            new_highs = new_highs.drop(columns=["py_revenue"], errors="ignore")

    # 計算月增率 (與上個月比) — 只在沒有現成 mom_pct 時才計算
    if "mom_pct" not in new_highs.columns or new_highs["mom_pct"].isna().all():
        if "prev_month" in history:
            pm_df = history["prev_month"][["stock_id", "revenue"]].copy()
            pm_df.columns = ["stock_id", "pm_revenue"]
            new_highs = new_highs.merge(pm_df, on="stock_id", how="left")
            new_highs["mom_pct"] = (
                (new_highs["revenue"] - new_highs["pm_revenue"])
                / new_highs["pm_revenue"]
                * 100
            ).round(2)
            new_highs = new_highs.drop(columns=["pm_revenue"], errors="ignore")

    # 使用 FinMind 提供的產業分類，或回退到 "其他"
    if "industry" not in new_highs.columns:
        new_highs["industry"] = "其他"
    new_highs["industry"] = new_highs["industry"].fillna("其他").replace("", "其他")

    # 排序
    sort_col = "yoy_pct" if "yoy_pct" in new_highs.columns else "exceed_pct"
    new_highs = new_highs.sort_values(sort_col, ascending=False, na_position="last")

    new_highs["compare_years"] = len(past_years)

    logger.info(f"共 {len(new_highs)} 檔營收創同期新高 (比對 {len(past_years)} 年)")
    return new_highs.reset_index(drop=True)


def format_revenue(value: float) -> str:
    """格式化營收金額 (FinMind 單位: 元)"""
    if pd.isna(value) or value == 0:
        return "N/A"
    yi = value / 1e8  # 元 → 億元
    if yi >= 1:
        return f"{yi:,.1f}億"
    wan = value / 1e4  # 元 → 萬元
    if wan >= 1:
        return f"{wan:,.0f}萬"
    return f"{value:,.0f}"
