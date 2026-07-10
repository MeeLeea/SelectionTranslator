"""
划词翻译 - 统一日志配置
日志同时输出到控制台和 logs/app.log，按日期轮转
"""
import os
import logging
from logging.handlers import TimedRotatingFileHandler

# 项目根目录（src 的上级）
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

# 日志格式
_FMT = "%(asctime)s  %(levelname)-7s  [%(name)s]  %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def setup_logging(level=logging.INFO):
    """初始化全局日志（幂等，重复调用不会重复添加 handler）"""
    root = logging.getLogger()
    # 已有 handler 则不重复添加（防止日志重复输出）
    if root.handlers:
        root.setLevel(level)
        return

    # 确保日志目录存在
    os.makedirs(LOG_DIR, exist_ok=True)
    root.setLevel(level)

    # 控制台输出
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(_FMT, _DATEFMT))
    root.addHandler(sh)

    # 文件输出（按天轮转，保留 7 天）
    fh = TimedRotatingFileHandler(
        LOG_FILE, when="midnight", interval=1,
        backupCount=7, encoding="utf-8"
    )
    fh.setFormatter(logging.Formatter(_FMT, _DATEFMT))
    root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    """获取子 logger（自动确保已初始化）"""
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)
