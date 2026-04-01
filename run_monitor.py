"""
本機營收即時監控 + 自動推送 GitHub Pages
每 interval_sec 秒執行一次偵測，若有新申報則 commit + push

用法：
  python run_monitor.py          # 預設每 300 秒
  python run_monitor.py 180      # 自訂間隔 180 秒
"""

import os
import sys
import time
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def git_push():
    """將變更推送到 GitHub"""
    try:
        os.chdir(BASE_DIR)

        # 檢查是否有變更
        result = subprocess.run(
            ["git", "status", "--porcelain", "output/", "data/monitor_state.json"],
            capture_output=True, text=True
        )
        if not result.stdout.strip():
            logger.info("無檔案變更，跳過推送")
            return False

        # git add
        subprocess.run(["git", "add", "output/index.html", "data/monitor_state.json"], check=True)

        # git commit
        from datetime import datetime
        msg = f"auto: update revenue filings {datetime.now().strftime('%m-%d %H:%M')}"
        subprocess.run(["git", "commit", "-m", msg], check=True)

        # git push
        subprocess.run(["git", "push"], check=True)
        logger.info("✅ 已推送至 GitHub")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Git 操作失敗: {e}")
        return False


def main():
    from monitor import run_once

    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    logger.info(f"🚀 啟動營收即時監控，每 {interval} 秒偵測，自動推送 GitHub Pages")

    while True:
        try:
            state = run_once()
            git_push()
        except Exception as e:
            logger.error(f"執行錯誤: {e}", exc_info=True)

        logger.info(f"⏳ 下次偵測: {interval} 秒後\n")
        time.sleep(interval)


if __name__ == "__main__":
    main()
