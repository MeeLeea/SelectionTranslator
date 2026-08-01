# 划词翻译（Selection Translator）

Windows 桌面划词翻译工具。选中文本后按下全局热键 `Ctrl + Alt + D`，即可在鼠标附近弹出翻译窗口，基于 LLM 流式输出译文。

## 功能特性

- **全局热键触发**：通过 Windows `RegisterHotKey` API 注册全局热键，在任何应用（浏览器、编辑器、Office、PDF 等）中选中文字后按热键即可翻译
- **流式输出**：后端使用 SSE（Server-Sent Events）逐 token 返回译文，首字响应快
- **悬浮弹窗**：翻译结果在鼠标附近显示，自适应内容高度，双击复制译文
- **系统托盘**：托盘图标可切换翻译模式、退出程序
- **多模式翻译**：智能翻译 / 单词详解 / 句子翻译
- **多 LLM 提供商**：支持智谱AI、DeepSeek、通义千问、Kimi（均兼容 OpenAI API 格式）

## 目录结构

```
SelectionTranslator/
├── start.py              # 启动入口（同时启动后端 + 前端）
├── llm_config.json       # LLM 配置（API Key、模型）
├── requirements.txt      # 依赖清单
├── logs/                 # 日志目录（运行时自动创建）
│   └── app.log
└── src/
    ├── config.py         # 共享配置（热键、弹窗、后端端口等）
    ├── logger.py         # 统一日志配置
    ├── llm_client.py     # LLM 客户端（基于 openai SDK）
    ├── backend.py        # 后端翻译服务（HTTP + SSE）
    └── frontend.py       # 前端（托盘 + 热键 + 选词采集 + 弹窗）
```

## 环境要求

- Windows 系统
- Python 3.10+
- 依赖：`openai`、`pystray`、`Pillow`、`pywin32`（tkinter 为 Python 内置）

## 安装

### 1. 创建虚拟环境（推荐）

```powershell
cd d:\work\SelectionTranslator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 安装依赖

```powershell
pip install -r requirements.txt
```

### 3. 配置 LLM API Key

编辑 [llm_config.json](llm_config.json)，填入你的 API Key：

```json
{
    "zhipu": {
        "api_key": "你的智谱API Key",
        "model": "glm-4-flash"
    }
}
```

默认使用智谱AI（glm-4-flash）。如需切换其他提供商，修改 `llm_config.json` 中对应字段，并在 [src/config.py](src/config.py) 中将 `LLM_PROVIDER` 改为 `deepseek` / `qwen` / `kimi`。

> 获取智谱 API Key：https://open.bigmodel.cn/

## 启动

```powershell
cd d:\work\SelectionTranslator
.\.venv\Scripts\python.exe start.py
```

或激活虚拟环境后直接运行：

```powershell
python start.py
```

启动成功后控制台会输出：

```
[启动] 后端就绪 ✓
[启动] 正在启动前端界面...
INFO  [frontend]  全局热键已注册: Ctrl + Alt + D
INFO  [frontend]  划词翻译已启动
```

系统托盘会出现蓝色"译"字图标，程序在后台运行。

## 使用

### 翻译流程

1. 在任意应用中用鼠标选中要翻译的文字
2. 按下热键 `Ctrl + Alt + D`
3. 鼠标附近弹出翻译窗口，流式显示译文
4. 双击弹窗内容可复制译文
5. 按 `Esc` 或等待 10 秒自动关闭弹窗

### 翻译模式

通过系统托盘右键菜单切换：

| 模式     | 说明                       |
| -------- | -------------------------- |
| 智能翻译 | 自动判断语言方向（默认）   |
| 单词详解 | 针对单词给出音标、词性、释义、例句 |
| 句子翻译 | 针对整句进行翻译           |

### 翻译领域

通过修改src/config.py中`TRANS_SECTOR = "xxxx"`领域来完成翻译领域的定义，例如`TRANS_SECTOR = "电子信息"`。

### 托盘菜单

- 智能翻译 / 单词详解 / 句子翻译（单选切换模式）
- 热键: Ctrl + Alt + D（仅显示）
- 退出

## 配置

主要配置项在 [src/config.py](src/config.py)：

| 配置项            | 说明                 | 默认值          |
| ----------------- | -------------------- | --------------- |
| `HOTKEY`          | 全局热键             | `"ctrl+alt+d"`  |
| `HOTKEY_LABEL`    | 热键显示文本         | `"Ctrl + Alt + D"` |
| `BACKEND_HOST`    | 后端监听地址         | `"127.0.0.1"`   |
| `BACKEND_PORT`    | 后端监听端口         | `9988`          |
| `POPUP_WIDTH`     | 弹窗宽度             | `440`           |
| `POPUP_TIMEOUT_MS`| 弹窗自动关闭毫秒数   | `10000`         |
| `LLM_PROVIDER`    | LLM 提供商           | `"zhipu"`       |

### 修改热键

编辑 [src/config.py](src/config.py) 中的 `HOTKEY`，支持格式：

```python
HOTKEY = "ctrl+alt+d"        # Ctrl + Alt + D
HOTKEY = "ctrl+shift+t"      # Ctrl + Shift + T
HOTKEY = "alt+z"             # Alt + Z
HOTKEY = "ctrl+f8"           # Ctrl + F8
```

修改后重启程序生效。

## 日志

日志同时输出到控制台和 `logs/app.log`，按天轮转保留 7 天。格式：

```
2026-07-10 15:35:00  INFO     [frontend]  全局热键已注册: Ctrl + Alt + D
```

## 常见问题

### 热键注册失败

日志出现 `热键 Ctrl + Alt + D 注册失败`，说明热键被其他程序占用。解决方法：

1. 检查是否有上一个实例仍在运行（任务管理器查找 `python.exe`），结束残留进程
2. 或修改 [src/config.py](src/config.py) 中的 `HOTKEY` 换一个组合键

### 翻译无响应

1. 检查 [llm_config.json](llm_config.json) 中 API Key 是否正确
2. 查看日志 `logs/app.log` 是否有 401 认证错误
3. 确认网络可访问 LLM 服务

### 获取不到选中文本

程序通过模拟 `Ctrl+C` 读取剪贴板获取选中文本，少数应用（如部分 Electron 应用、DRM 保护的 PDF）可能不响应。可尝试在该应用中使用右键菜单"复制"后，再用热键翻译。
