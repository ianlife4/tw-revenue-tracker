import os
from datetime import datetime, timezone, timedelta

TW_TZ = timezone(timedelta(hours=8))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# 比對歷史年數
HISTORY_YEARS = 5

# 請求間隔秒數範圍
REQUEST_DELAY_MIN = 0.3
REQUEST_DELAY_MAX = 0.6

# 請求 headers
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}


def get_current_period() -> tuple[int, int]:
    """取得當前應查詢的年月 (西元年, 月份)
    營收資料通常在次月 10 日前公告，所以查上個月的資料
    一律用台灣時間：CI 跑在 UTC，每月 1 號 00:00~08:00 TW 會算成上上個月"""
    now = datetime.now(TW_TZ)
    if now.month == 1:
        return now.year - 1, 12
    return now.year, now.month - 1
