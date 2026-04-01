"""
T+1 股價分析模組
分析營收創同期新高後隔天(T+1)的股價表現
- 找出歷史上該股票每次創同月新高的時間
- 抓取對應的股價資料
- 計算 T+1 收盤漲跌幅
- 提供推播提示(T-1提醒)
"""

import os
import json
import time
import random
import logging
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)

# 快取目錄
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
T1_CACHE_FILE = os.path.join(DATA_DIR, "t1_cache.json")


# ─────────────── 股價抓取 ───────────────

def _get_yf_suffix(market: str) -> str:
    """市場 → Yahoo Finance ticker 後綴"""
    if market in ("sii", "tib"):
        return ".TW"
    elif market in ("otc",):
        return ".TWO"
    elif market == "emerging":
        return ".TWO"  # 興櫃部分有，沒有就跳過
    return ".TW"


def fetch_stock_price(stock_id: str, market: str,
                      start_date: str, end_date: str) -> pd.DataFrame:
    """用 yfinance 抓取日收盤價
    Returns DataFrame with columns: Date, Close
    """
    import yfinance as yf

    suffix = _get_yf_suffix(market)
    ticker_str = f"{stock_id}{suffix}"

    try:
        ticker = yf.Ticker(ticker_str)
        hist = ticker.history(start=start_date, end=end_date)
        if hist.empty and suffix == ".TW":
            # 試試 .TWO
            ticker = yf.Ticker(f"{stock_id}.TWO")
            hist = ticker.history(start=start_date, end=end_date)
        if hist.empty:
            return pd.DataFrame()

        result = hist[["Close"]].reset_index()
        result.columns = ["date", "close"]
        result["date"] = pd.to_datetime(result["date"]).dt.tz_localize(None)
        return result.sort_values("date").reset_index(drop=True)
    except Exception as e:
        logger.warning(f"抓取 {ticker_str} 股價失敗: {e}")
        return pd.DataFrame()


def get_t1_price_change(prices_df: pd.DataFrame, filing_date: str) -> dict:
    """計算 T 日和 T+1 日收盤價變動

    Args:
        prices_df: 日收盤價 DataFrame (date, close)
        filing_date: 申報日 (YYYY-MM-DD)

    Returns:
        {"t_date": str, "t_close": float, "t1_date": str, "t1_close": float, "t1_pct": float}
        或空 dict
    """
    if prices_df.empty:
        return {}

    fd = pd.Timestamp(filing_date)
    prices_df = prices_df.sort_values("date").reset_index(drop=True)

    # T 日 = 申報日當天或之前最近的交易日收盤
    t_rows = prices_df[prices_df["date"] <= fd]
    if t_rows.empty:
        return {}
    t_idx = t_rows.index[-1]
    t_date = t_rows.iloc[-1]["date"]
    t_close = float(t_rows.iloc[-1]["close"])

    # T+1 = T 日之後的下一個交易日
    t1_rows = prices_df[prices_df.index > t_idx]
    if t1_rows.empty:
        return {}
    t1_date = t1_rows.iloc[0]["date"]
    t1_close = float(t1_rows.iloc[0]["close"])

    pct = (t1_close - t_close) / t_close * 100

    return {
        "t_date": t_date.strftime("%Y-%m-%d"),
        "t_close": round(t_close, 2),
        "t1_date": t1_date.strftime("%Y-%m-%d"),
        "t1_close": round(t1_close, 2),
        "t1_pct": round(pct, 2),
    }


# ─────────────── 歷史新高偵測 ───────────────

def find_historical_period_highs(stock_id: str, full_df: pd.DataFrame,
                                  target_month: int) -> list[dict]:
    """找出該股票在歷史上 target_month 月份營收創同期新高的所有年度

    Returns:
        [{"year": 2024, "month": 3, "revenue": 12345, "filing_month_start": "2024-04-01"}, ...]
    """
    stock_data = full_df[(full_df["stock_id"] == stock_id) &
                         (full_df["revenue_month"] == target_month)].copy()
    if stock_data.empty:
        return []

    stock_data = stock_data.sort_values("revenue_year")
    highs = []
    max_rev = 0

    for _, row in stock_data.iterrows():
        rev = row.get("revenue", 0)
        yr = int(row["revenue_year"])
        if pd.isna(rev) or rev <= 0:
            continue
        if rev > max_rev and max_rev > 0:
            # 營收期間的下個月 = 申報月
            filing_m = target_month + 1 if target_month < 12 else 1
            filing_y = yr if target_month < 12 else yr + 1
            highs.append({
                "year": yr,
                "month": target_month,
                "revenue": float(rev),
                "filing_month_start": f"{filing_y}-{filing_m:02d}-01",
            })
        if rev > max_rev:
            max_rev = rev

    return highs


# ─────────────── 核心 T+1 分析 ───────────────

def analyze_stock_t1(stock_id: str, market: str, full_df: pd.DataFrame,
                     target_month: int, current_filing_date: str = None,
                     cache: dict = None) -> dict:
    """分析單一股票的 T+1 歷史表現

    Args:
        stock_id: 股票代號
        market: 市場 (sii/otc/emerging)
        full_df: 完整歷史營收 DataFrame
        target_month: 目標月份
        current_filing_date: 當期申報日 (YYYY-MM-DD)，用來推算歷史申報日
        cache: 快取 dict (可選)

    Returns:
        {
            "stock_id": str,
            "historical_highs": [...],  # 每次新高的 T+1 表現
            "avg_t1": float,            # 平均 T+1 報酬
            "median_t1": float,         # 中位數 T+1 報酬
            "max_t1": float,            # 最大 T+1 報酬
            "min_t1": float,            # 最小 T+1 報酬
            "hit_rate": float,          # 正報酬比率
            "count": int,              # 歷史新高次數
            "typical_filing_day": int,  # 典型申報日
        }
    """
    # 檢查快取
    cache_key = f"{stock_id}_{target_month}"
    if cache and cache_key in cache:
        cached = cache[cache_key]
        # 快取 7 天內有效
        if cached.get("cached_at"):
            cached_time = datetime.fromisoformat(cached["cached_at"])
            if (datetime.now() - cached_time).days < 7:
                return cached

    # 找歷史新高
    highs = find_historical_period_highs(stock_id, full_df, target_month)
    if not highs:
        return {"stock_id": stock_id, "count": 0, "historical_highs": []}

    # 推算歷史申報日
    # 若有當期申報日，用同一天號推算歷史 (假設每月固定日期申報)
    typical_day = 10  # 預設第 10 天
    if current_filing_date:
        try:
            typical_day = int(current_filing_date.split("-")[2])
        except (IndexError, ValueError):
            pass

    # 抓取股價並計算 T+1
    results = []
    for h in highs:
        filing_start = h["filing_month_start"]  # YYYY-MM-01
        fy, fm = int(filing_start[:4]), int(filing_start[5:7])

        # 估算申報日 = 申報月的 typical_day
        est_filing_date = f"{fy}-{fm:02d}-{min(typical_day, 28):02d}"

        # 抓申報前後兩週股價
        price_start = f"{fy}-{fm:02d}-01"
        price_end_dt = datetime(fy, fm, 1) + timedelta(days=20)
        price_end = price_end_dt.strftime("%Y-%m-%d")

        prices = fetch_stock_price(stock_id, market, price_start, price_end)
        if prices.empty:
            continue

        t1 = get_t1_price_change(prices, est_filing_date)
        if not t1:
            continue

        t1["year"] = h["year"]
        t1["month"] = h["month"]
        t1["revenue"] = h["revenue"]
        results.append(t1)

        time.sleep(random.uniform(0.3, 0.8))

    # 彙總統計
    if not results:
        return {"stock_id": stock_id, "count": 0, "historical_highs": []}

    pcts = [r["t1_pct"] for r in results]
    analysis = {
        "stock_id": stock_id,
        "historical_highs": results,
        "avg_t1": round(sum(pcts) / len(pcts), 2),
        "median_t1": round(sorted(pcts)[len(pcts) // 2], 2),
        "max_t1": round(max(pcts), 2),
        "min_t1": round(min(pcts), 2),
        "hit_rate": round(sum(1 for p in pcts if p > 0) / len(pcts) * 100, 1),
        "count": len(results),
        "typical_filing_day": typical_day,
        "cached_at": datetime.now().isoformat(),
    }

    # 寫快取
    if cache is not None:
        cache[cache_key] = analysis

    return analysis


# ─────────────── 批次分析 ───────────────

def analyze_all_period_highs(new_highs_df: pd.DataFrame, full_df: pd.DataFrame,
                              monitor_state: dict, target_month: int) -> list[dict]:
    """分析所有當期創新高股票的 T+1 歷史表現

    Args:
        new_highs_df: 當期營收創同期新高的股票
        full_df: 完整歷史營收
        monitor_state: 監控狀態 (含 first_seen)
        target_month: 營收月份

    Returns:
        按 avg_t1 降序排列的分析結果列表
    """
    # 載入快取
    cache = {}
    if os.path.exists(T1_CACHE_FILE):
        try:
            with open(T1_CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    stocks_info = monitor_state.get("stocks", {})
    results = []
    total = len(new_highs_df)

    for i, (_, row) in enumerate(new_highs_df.iterrows()):
        sid = str(row["stock_id"])
        market = row.get("market", "sii")
        sname = row.get("stock_name", "")

        # 取得當期申報日
        first_seen = stocks_info.get(sid, {}).get("first_seen", "")
        # first_seen 格式: "04-01 22:45"
        current_filing_date = None
        if first_seen:
            try:
                period_year = monitor_state.get("period_year", 2026)
                month_part = first_seen.split(" ")[0]  # "04-01"
                mm, dd = month_part.split("-")
                filing_year = period_year if int(mm) >= target_month else period_year + 1
                current_filing_date = f"{filing_year}-{mm}-{dd}"
            except (ValueError, IndexError):
                pass

        logger.info(f"  [{i+1}/{total}] 分析 {sid} {sname} T+1 (申報日: {current_filing_date})")

        analysis = analyze_stock_t1(
            stock_id=sid, market=market, full_df=full_df,
            target_month=target_month, current_filing_date=current_filing_date,
            cache=cache,
        )
        analysis["stock_name"] = sname
        analysis["market"] = market
        analysis["current_filing_date"] = current_filing_date
        results.append(analysis)

    # 儲存快取
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(T1_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"T1 快取儲存失敗: {e}")

    # 按 avg_t1 降序排列 (有歷史資料的在前)
    results.sort(key=lambda x: (x.get("count", 0) > 0, x.get("avg_t1", -999)), reverse=True)
    return results


# ─────────────── T-1 推播提醒 ───────────────

def generate_early_alerts(t1_results: list[dict], threshold_avg: float = 2.0,
                           threshold_hit_rate: float = 60.0) -> list[dict]:
    """生成 T-1 推播提醒：過去創新高後 T+1 容易大漲的個股

    篩選條件:
    - 至少有 2 次歷史新高記錄
    - 平均 T+1 報酬 >= threshold_avg%
    - 正報酬率 >= threshold_hit_rate%

    Returns:
        [{stock_id, stock_name, market, avg_t1, hit_rate, count, typical_filing_day, alert_msg}, ...]
    """
    alerts = []
    for r in t1_results:
        if (r.get("count", 0) >= 2 and
            r.get("avg_t1", 0) >= threshold_avg and
            r.get("hit_rate", 0) >= threshold_hit_rate):

            day = r.get("typical_filing_day", "?")
            alerts.append({
                "stock_id": r["stock_id"],
                "stock_name": r.get("stock_name", ""),
                "market": r.get("market", ""),
                "avg_t1": r["avg_t1"],
                "median_t1": r.get("median_t1", 0),
                "max_t1": r.get("max_t1", 0),
                "hit_rate": r["hit_rate"],
                "count": r["count"],
                "typical_filing_day": day,
                "alert_msg": f"過去 {r['count']} 次創新高後 T+1 平均 +{r['avg_t1']:.1f}%，"
                             f"正報酬率 {r['hit_rate']:.0f}%，通常每月 {day} 日申報",
            })

    alerts.sort(key=lambda x: x["avg_t1"], reverse=True)
    return alerts
