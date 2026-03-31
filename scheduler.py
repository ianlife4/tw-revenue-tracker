"""
Windows Task Scheduler 排程設定
每月 10 日起每天下午 5:30 自動執行營收追蹤
"""

import os
import sys
import subprocess
import logging

logger = logging.getLogger(__name__)

TASK_NAME = "TW_Revenue_Tracker"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON_EXE = sys.executable
MAIN_SCRIPT = os.path.join(SCRIPT_DIR, "main.py")


def create_schedule():
    """建立 Windows 排程任務"""
    # 使用 schtasks 建立每日排程
    # /SC DAILY = 每天
    # /ST 17:30 = 下午 5:30
    # /SD 開始日期 (每月 10 日後營收資料才齊全)
    cmd = [
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", f'"{PYTHON_EXE}" "{MAIN_SCRIPT}" --no-open',
        "/SC", "DAILY",
        "/ST", "17:30",
        "/F",  # 強制覆寫已存在的排程
    ]

    print(f"即將建立排程任務: {TASK_NAME}")
    print(f"  執行指令: {PYTHON_EXE} {MAIN_SCRIPT} --no-open")
    print(f"  排程: 每天 17:30")
    print()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            print(f"排程任務 '{TASK_NAME}' 建立成功!")
            print("可在 Windows 工作排程器中查看和管理")
        else:
            print(f"建立失敗: {result.stderr}")
            print("請以系統管理員身份執行此腳本")
    except Exception as e:
        print(f"錯誤: {e}")


def delete_schedule():
    """刪除排程任務"""
    cmd = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            print(f"排程任務 '{TASK_NAME}' 已刪除")
        else:
            print(f"刪除失敗: {result.stderr}")
    except Exception as e:
        print(f"錯誤: {e}")


def show_status():
    """查看排程狀態"""
    cmd = ["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            print(result.stdout)
        else:
            print(f"查詢失敗 (可能尚未建立排程): {result.stderr}")
    except Exception as e:
        print(f"錯誤: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="排程管理")
    parser.add_argument("action", choices=["create", "delete", "status"], help="動作")
    args = parser.parse_args()

    if args.action == "create":
        create_schedule()
    elif args.action == "delete":
        delete_schedule()
    elif args.action == "status":
        show_status()
