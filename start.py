"""
划词翻译 - 启动入口
同时启动后端翻译服务（线程）和前端界面（主线程）

用法:
  python start.py
"""
import sys
import os
import time
import threading
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# 初始化日志系统
from src.logger import setup_logging
setup_logging()

from src.config import BACKEND_HOST, BACKEND_PORT

HEALTH_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"


def wait_backend(timeout=15):
    """等待后端服务就绪"""
    for _ in range(int(timeout / 0.2)):
        try:
            urllib.request.urlopen(HEALTH_URL, timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def main():
    print("=" * 50)
    print("  划词翻译 (Selection Translator)")
    print("  前端: 划词采集 + 弹窗显示")
    print("  后端: 自有 LLM Agent 翻译")
    print("=" * 50)

    # 1. 启动后端（守护线程）
    print("\n[启动] 正在启动后端翻译服务...")
    from src.backend import run_server
    backend_thread = threading.Thread(target=run_server, daemon=True)
    backend_thread.start()

    # 2. 等待后端就绪
    if wait_backend():
        print("[启动] 后端就绪 ✓")
    else:
        print("[启动] 警告: 后端未在 15 秒内就绪（前端仍会启动，但翻译将不可用）")

    # 3. 启动前端（主线程，阻塞）
    print("[启动] 正在启动前端界面...")
    from src.frontend import TranslateApp
    app = TranslateApp()
    app.run()


if __name__ == "__main__":
    main()
