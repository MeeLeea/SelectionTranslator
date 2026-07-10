"""
划词翻译 - 共享配置
后端与前端均从此文件读取配置
"""
import os

# ===== 项目路径 =====
# 项目根目录 = src 的上级
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ===== LLM 配置 =====
# llm_config.json 位于项目根目录
LLM_CONFIG_FILE = os.path.join(BASE_DIR, "llm_config.json")
# 默认提供商（对应 llm_config.json 中的 key）
LLM_PROVIDER = "zhipu"

# ===== 后端 HTTP 服务 =====
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 9988

# ===== 前端 - 触发方式 =====
# 全局键盘热键（选中文字后按下热键触发翻译）
# 支持格式: ctrl+alt+d / ctrl+shift+t / alt+z / ctrl+f8 等
HOTKEY = "ctrl+alt+d"
HOTKEY_LABEL = "Ctrl + Alt + D"

# ===== 前端 - 弹窗 =====
POPUP_WIDTH = 440
POPUP_HEIGHT = 260
POPUP_TIMEOUT_MS = 10000  # 自动关闭（毫秒）

# 配色（Catppuccin Mocha 风格暗色主题）
POPUP_BG = "#1e1e2e"          # 背景色
POPUP_BORDER = "#313244"      # 边框色
POPUP_HEADER_BG = "#181825"   # 头部背景
POPUP_FG = "#cdd6f4"          # 主文字色
POPUP_ACCENT = "#89b4fa"      # 强调色（标签等）
POPUP_DIM = "#6c7086"         # 次要文字色（原文）
POPUP_EXPLAIN = "#a6adc8"     # 释义文字色
POPUP_ERROR = "#f38ba8"       # 错误色

# ===== 翻译模式 =====
TRANSLATE_MODES = {
    "auto": "智能翻译",
    "word": "单词详解",
    "sentence": "句子翻译",
}
