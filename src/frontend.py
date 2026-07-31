"""
划词翻译 - 前端
系统托盘 + 全局热键 + 选中文本采集 + 翻译弹窗

依赖:
  - pystray   (系统托盘)
  - Pillow    (托盘图标生成)
  - pywin32   (热键注册 + 剪贴板)
  - tkinter   (弹窗界面，Python 内置)
"""
import sys
import os
import json
import time
import threading
import queue
import ctypes
import urllib.request
import tkinter as tk

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from config import (
    BACKEND_HOST, BACKEND_PORT, HOTKEY, HOTKEY_LABEL,
    POPUP_WIDTH, POPUP_HEIGHT, POPUP_TIMEOUT_MS,
    POPUP_BG, POPUP_BORDER, POPUP_HEADER_BG, POPUP_FG,
    POPUP_ACCENT, POPUP_DIM, POPUP_EXPLAIN, POPUP_ERROR,
    TRANSLATE_MODES,
)
from logger import get_logger

log = get_logger("frontend")

BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

import win32api
import win32gui
import win32con
import win32clipboard
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw, ImageFont


# ============================================================
#  热键解析
# ============================================================
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_HOTKEY_MODS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT, "shift": MOD_SHIFT,
    "win": MOD_WIN, "super": MOD_WIN,
}


def parse_hotkey(hotkey_str):
    """解析 'ctrl+alt+d' -> (modifiers, vk_code)"""
    parts = hotkey_str.lower().replace(" ", "").split("+")
    mods = 0
    vk = 0
    for p in parts:
        if p in _HOTKEY_MODS:
            mods |= _HOTKEY_MODS[p]
        elif len(p) == 1 and p.isalpha():
            vk = ord(p.upper())
        elif len(p) == 1 and p.isdigit():
            vk = ord(p)
        elif p.startswith("f") and p[1:].isdigit():
            vk = 0x6F + int(p[1:])  # F1=0x70
        elif p == "space":
            vk = 0x20
    return mods, vk


# ============================================================
#  剪贴板工具
# ============================================================
def clipboard_get():
    """读取剪贴板文本"""
    try:
        win32clipboard.OpenClipboard()
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
    except Exception:
        return ""
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
    return ""


def clipboard_set(text):
    """写入剪贴板文本"""
    try:
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    except Exception:
        pass
    finally:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass


def get_selected_text():
    """
    通过模拟 Ctrl+C 获取当前选中文字。
    原理：保存旧剪贴板 -> 清空 -> 发送 Ctrl+C -> 读取 -> 恢复。
    适用于大多数 GUI 应用（浏览器、编辑器、Office、PDF 等）。
    """
    user32 = ctypes.windll.user32
    KEYUP = 0x0002

    # 释放修饰键，避免 Ctrl+Alt 仍被按住导致干扰
    for vk in (0x10, 0x11, 0x12):  # SHIFT, CTRL, ALT
        user32.keybd_event(vk, 0, KEYUP, 0)
    time.sleep(0.02)

    # 保存旧剪贴板内容
    old_text = clipboard_get()
    clipboard_set("")

    # 模拟 Ctrl+C
    user32.keybd_event(0x11, 0, 0, 0)        # CTRL down
    user32.keybd_event(0x43, 0, 0, 0)        # C down
    time.sleep(0.015)
    user32.keybd_event(0x43, 0, KEYUP, 0)    # C up
    user32.keybd_event(0x11, 0, KEYUP, 0)    # CTRL up

    # 等待剪贴板更新（最多 0.3 秒，高频轮询）
    text = ""
    for _ in range(30):
        time.sleep(0.01)
        text = clipboard_get()
        if text:
            break

    # 恢复旧剪贴板
    if old_text:
        clipboard_set(old_text)

    return text.strip()


# ============================================================
#  后端调用
# ============================================================
def call_backend_stream(text, mode="auto"):
    """
    调用后端 /translate_stream 接口（SSE 流式）
    生成器：逐个 yield delta 文本片段，最后 yield 完整译文
    """
    payload = json.dumps({"text": text, "mode": mode}).encode("utf-8")
    req = urllib.request.Request(
        f"{BACKEND_URL}/translate_stream",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = json.loads(line[5:].strip())
            if "error" in data:
                raise RuntimeError(data["error"])
            if data.get("done"):
                yield ("done", data.get("translation", ""))
                return
            if "delta" in data:
                yield ("delta", data["delta"])


# ============================================================
#  托盘图标
# ============================================================
def create_tray_icon_image():
    """生成托盘图标（蓝底白"译"字）"""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([6, 6, 58, 58], fill=(137, 180, 250, 255))
    try:
        font = ImageFont.truetype("msyh.ttc", 32)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", 32)
        except Exception:
            font = ImageFont.load_default()
    text = "译"
    try:
        bbox = d.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((64 - w) / 2 - bbox[0], (64 - h) / 2 - bbox[1]), text,
               fill=(30, 30, 46, 255), font=font)
    except Exception:
        d.text((20, 16), text, fill=(30, 30, 46, 255), font=font)
    return img


# ============================================================
#  全局热键监听器（基于 RegisterHotKey，无需额外依赖）
# ============================================================
class HotkeyListener:
    """通过 Windows RegisterHotKey API 注册全局热键"""

    def __init__(self, modifiers, vk, callback):
        self.modifiers = modifiers
        self.vk = vk
        self.callback = callback
        self.hwnd = None
        # 保持对 wndproc 的引用，防止被 GC 回收
        self._wnd_proc_ref = None
        self._wc = None

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_HOTKEY:
            try:
                self.callback()
            except Exception as e:
                log.error("热键回调异常: %s", e, exc_info=True)
        elif msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def run(self):
        """在当前线程运行消息循环（阻塞）"""
        hinst = win32api.GetModuleHandle(None)

        wc = win32gui.WNDCLASS()
        self._wnd_proc_ref = self._wnd_proc
        wc.lpfnWndProc = self._wnd_proc_ref
        wc.lpszClassName = "SelectionTranslatorHotkeyWnd"
        wc.hInstance = hinst
        self._wc = wc
        atom = win32gui.RegisterClass(wc)

        self.hwnd = win32gui.CreateWindowEx(
            0, atom, "SelectionTranslator", 0,
            0, 0, 0, 0, 0, 0, hinst, None
        )

        ok = ctypes.windll.user32.RegisterHotKey(
            self.hwnd, 1, self.modifiers | MOD_NOREPEAT, self.vk
        )
        if not ok:
            log.warning("热键 %s 注册失败（可能被其他程序占用）", HOTKEY_LABEL)
            log.warning("请修改 config.py 中的 HOTKEY 后重试")
        else:
            log.info("全局热键已注册: %s", HOTKEY_LABEL)

        # 消息循环（阻塞）
        win32gui.PumpMessages()

        # 清理
        try:
            ctypes.windll.user32.UnregisterHotKey(self.hwnd, 1)
        except Exception:
            pass


# ============================================================
#  主应用
# ============================================================
class TranslateApp:
    """划词翻译主应用"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # 隐藏主窗口（仅用 Toplevel 弹窗）
        self.queue = queue.Queue()
        self.mode = "auto"
        self.popup_win = None
        self.popup_body = None
        self.timeout_id = None
        self.icon = None
        self.busy = False
        self._last_translation = ""
        self._drag_start_x = 0
        self._drag_start_y = 0

        # 轮询队列（线程间通信）
        self.root.after(80, self._poll)

    # ---- 队列轮询 ----
    def _poll(self):
        try:
            while True:
                task = self.queue.get_nowait()
                task()
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    # ---- 键盘热键回调（在热键线程触发）----
    def on_hotkey(self):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        """热键触发：采集选中文本 → 翻译"""
        text = get_selected_text()
        if not text:
            self.queue.put(lambda: self._show_message(
                "", "未获取到选中文本", error=True))
            self.busy = False
            return
        self._translate_text(text)

    # ---- 翻译工作线程 ----
    def _translate_text(self, text):
        """
        翻译指定文本（流式）。
        由热键触发，调用方负责设置 self.busy。
        """
        try:
            # 显示加载中
            self.queue.put(lambda: self._show_loading(text))

            # 流式调用后端，边接收边显示
            try:
                accumulated = []
                first_chunk = True
                for kind, content in call_backend_stream(text, self.mode):
                    if kind == "delta":
                        accumulated.append(content)
                        if first_chunk:
                            # 首个 token 到达，切换为流式显示模式
                            first_chunk = False
                            self.queue.put(
                                lambda c=content: self._show_stream_start(text, c)
                            )
                        else:
                            self.queue.put(
                                lambda c=content: self._show_stream_append(c)
                            )
                    elif kind == "done":
                        full = content or "".join(accumulated)
                        self.queue.put(
                            lambda f=full: self._show_stream_done(f)
                        )
            except Exception as e:
                log.error("翻译失败: %s", e)
                # 若已有部分内容，追加错误信息；否则显示错误弹窗
                if accumulated:
                    err_msg = f"\n\n[翻译中断: {e}]"
                    self.queue.put(
                        lambda m=err_msg: self._show_stream_append(m)
                    )
                else:
                    self.queue.put(lambda: self._show_message(
                        text, f"翻译失败: {e}", error=True))
        finally:
            self.busy = False

    # ---- 弹窗显示 ----
    def _close_popup(self):
        if self.timeout_id:
            try:
                self.root.after_cancel(self.timeout_id)
            except Exception:
                pass
            self.timeout_id = None
        if self.popup_win:
            try:
                self.popup_win.destroy()
            except Exception:
                pass
            self.popup_win = None
            self.popup_body = None

    def _get_virtual_screen_bounds(self):
        left = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
        top = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
        width = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
        height = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
        return left, top, left + width, top + height

    def _start_drag_popup(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _drag_popup(self, event):
        if not self.popup_win:
            return
        x = self.popup_win.winfo_x() + event.x - self._drag_start_x
        y = self.popup_win.winfo_y() + event.y - self._drag_start_y
        self.popup_win.geometry(f"+{x}+{y}")

    def _create_popup(self, original):
        """创建弹窗基础结构，返回 (win, body_text_widget)"""
        self._close_popup()

        win = tk.Toplevel(self.root)
        win.overrideredirect(True)  # 无边框
        win.attributes("-topmost", True)
        win.configure(bg=POPUP_BORDER)

        try:
            pt = win32api.GetCursorPos()
            mx, my = pt[0] + 14, pt[1] + 14
        except Exception:
            mx, my = 100, 100
        left, top, right, bottom = self._get_virtual_screen_bounds()
        min_x = left + 10
        min_y = top + 10
        max_x = max(min_x, right - POPUP_WIDTH - 10)
        max_y = max(min_y, bottom - POPUP_HEIGHT - 10)
        mx = min(max(mx, min_x), max_x)
        my = min(max(my, min_y), max_y)
        win.geometry(f"{POPUP_WIDTH}x{POPUP_HEIGHT}+{mx}+{my}")

        # ---- 头部栏 ----
        header = tk.Frame(win, bg=POPUP_HEADER_BG, height=26)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title = TRANSLATE_MODES.get(self.mode, "翻译")
        title_lbl = tk.Label(header, text=f"  译  ·  {title}", bg=POPUP_HEADER_BG,
                             fg=POPUP_DIM, font=("Microsoft YaHei UI", 8),
                             cursor="fleur")
        title_lbl.pack(side="left", padx=4)

        close_lbl = tk.Label(header, text="  ✕  ", bg=POPUP_HEADER_BG,
                             fg=POPUP_DIM, font=("Microsoft YaHei UI", 9),
                             cursor="hand2")
        close_lbl.pack(side="right")
        close_lbl.bind("<Button-1>", lambda e: self._close_popup())

        header.bind("<Button-1>", self._start_drag_popup)
        header.bind("<B1-Motion>", self._drag_popup)
        title_lbl.bind("<Button-1>", self._start_drag_popup)
        title_lbl.bind("<B1-Motion>", self._drag_popup)

        # ---- 内容区 ----
        inner = tk.Frame(win, bg=POPUP_BG)
        inner.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        body = tk.Text(inner, wrap="word", bg=POPUP_BG, fg=POPUP_FG,
                       padx=14, pady=10, font=("Microsoft YaHei UI", 11),
                       borderwidth=0, highlightthickness=0,
                       spacing1=3, spacing3=3, undo=False)
        sb = tk.Scrollbar(inner, command=body.yview, bg=POPUP_BG,
                          troughcolor=POPUP_BG, activebackground="#45475a",
                          highlightthickness=0, bd=0, width=6)
        body.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        body.pack(side="left", fill="both", expand=True)

        # 标签样式
        body.tag_config("label", foreground=POPUP_ACCENT,
                        font=("Microsoft YaHei UI", 8, "bold"))
        body.tag_config("original", foreground=POPUP_DIM,
                        font=("Microsoft YaHei UI", 10),
                        lmargin1=6, lmargin2=6)
        body.tag_config("translation", foreground=POPUP_FG,
                        font=("Microsoft YaHei UI", 13),
                        lmargin1=6, lmargin2=6, spacing1=4)
        body.tag_config("explain", foreground=POPUP_EXPLAIN,
                        font=("Microsoft YaHei UI", 10),
                        lmargin1=6, lmargin2=6)
        body.tag_config("msg", foreground=POPUP_ACCENT,
                        font=("Microsoft YaHei UI", 11),
                        lmargin1=6, lmargin2=6)
        body.tag_config("error_msg", foreground=POPUP_ERROR,
                        font=("Microsoft YaHei UI", 11),
                        lmargin1=6, lmargin2=6)

        # 绑定
        win.bind("<Escape>", lambda e: self._close_popup())
        body.bind("<Double-Button-1>", lambda e: self._copy_translation())

        self.popup_win = win
        self.popup_body = body
        return win, body

    def _auto_resize(self, win, body):
        """根据内容自适应弹窗高度，并限制在虚拟桌面范围内"""
        win.update_idletasks()
        try:
            result = body.count("1.0", "end-1c", "displaylines")
            if isinstance(result, (tuple, list)):
                lines = result[0] if result else 10
            elif isinstance(result, int):
                lines = result
            else:
                lines = 10
        except Exception:
            lines = 10

        # 每行约 22px + 头部 26px + 内边距 20px
        h = min(max(lines * 22 + 50, 90), 420)

        # 保持原位置，按虚拟桌面边界夹紧
        w = win.winfo_width() or POPUP_WIDTH
        x = win.winfo_x()
        y = win.winfo_y()
        left, top, right, bottom = self._get_virtual_screen_bounds()
        x = min(max(x, left + 10), max(left + 10, right - w - 10))
        y = min(max(y, top + 10), max(top + 10, bottom - h - 10))
        win.geometry(f"{w}x{h}+{x}+{y}")

    def _insert_original(self, body, original):
        """向 body 插入原文区域（带标签），仅在 original 非空时插入"""
        if not original:
            return
        body.insert("end", "原文\n", "label")
        preview = original[:300] + ("\n…" if len(original) > 300 else "")
        body.insert("end", preview + "\n\n", "original")

    def _schedule_auto_close(self, ms):
        """重置自动关闭计时器"""
        if self.timeout_id:
            try:
                self.root.after_cancel(self.timeout_id)
            except Exception:
                pass
        self.timeout_id = self.root.after(ms, self._close_popup)

    def _show_loading(self, original):
        win, body = self._create_popup(original)
        self._insert_original(body, original)
        body.insert("end", "正在翻译…", "msg")
        body.config(state="disabled")
        self._auto_resize(win, body)
        # 加载状态给较长超时（等结果）
        self._schedule_auto_close(POPUP_TIMEOUT_MS)

    # ---- 流式显示 ----
    def _show_stream_start(self, original, first_chunk):
        """首个 token 到达：将 loading 替换为流式翻译区"""
        if not self.popup_body:
            win, body = self._create_popup(original)
            self._insert_original(body, original)
            body.insert("end", "翻译\n", "label")
            body.insert("end", first_chunk, "translation")
            body.config(state="disabled")
            self._auto_resize(win, body)
        else:
            # 替换"正在翻译…"为首个片段
            body = self.popup_body
            body.config(state="normal")
            body.delete("1.0", "end")
            self._insert_original(body, original)
            body.insert("end", "翻译\n", "label")
            body.insert("end", first_chunk, "translation")
            body.config(state="disabled")
            self._auto_resize(self.popup_win, body)

    def _show_stream_append(self, chunk):
        """追加流式 token"""
        if not self.popup_body:
            return
        body = self.popup_body
        body.config(state="normal")
        body.insert("end", chunk, "translation")
        body.config(state="disabled")
        self._auto_resize(self.popup_win, body)

    def _show_stream_done(self, full_translation):
        """流式结束：保存译文并启动自动关闭计时"""
        self._last_translation = full_translation
        if self.popup_body:
            body = self.popup_body
            body.config(state="normal")
            body.insert("end", "\n\n双击复制译文 · Esc 关闭", "label")
            body.config(state="disabled")
            self._auto_resize(self.popup_win, body)
        self._schedule_auto_close(POPUP_TIMEOUT_MS)

    def _show_message(self, original, message, error=False):
        win, body = self._create_popup(original)
        self._insert_original(body, original)
        body.insert("end", message, "error_msg" if error else "msg")
        body.config(state="disabled")
        self._auto_resize(win, body)
        self._schedule_auto_close(POPUP_TIMEOUT_MS)

    def _copy_translation(self):
        if self._last_translation:
            clipboard_set(self._last_translation)

    # ---- 模式切换 ----
    def set_mode(self, mode):
        self.mode = mode
        self._close_popup()
        log.info("模式切换: %s", TRANSLATE_MODES.get(mode, mode))

    # ---- 退出 ----
    def quit(self):
        self._close_popup()
        if self.icon:
            self.icon.stop()
        self.root.after(100, self.root.destroy)

    # ---- 运行 ----
    def run(self):
        # 启动全局热键监听线程
        mods, vk = parse_hotkey(HOTKEY)
        threading.Thread(
            target=self._run_hotkey, args=(mods, vk), daemon=True
        ).start()

        # 启动托盘
        self.icon = Icon(
            "SelectionTranslator", create_tray_icon_image(), "划词翻译",
            menu=Menu(
                MenuItem("智能翻译", lambda: self.set_mode("auto"),
                         radio=True, checked=lambda i: self.mode == "auto"),
                MenuItem("单词详解", lambda: self.set_mode("word"),
                         radio=True, checked=lambda i: self.mode == "word"),
                MenuItem("句子翻译", lambda: self.set_mode("sentence"),
                         radio=True, checked=lambda i: self.mode == "sentence"),
                Menu.SEPARATOR,
                MenuItem(f"热键: {HOTKEY_LABEL}", None, enabled=False),
                Menu.SEPARATOR,
                MenuItem("退出", lambda: self.quit()),
            ),
        )
        threading.Thread(target=self.icon.run, daemon=True).start()

        log.info("划词翻译已启动")
        log.info("热键: %s", HOTKEY_LABEL)
        log.info("后端: %s", BACKEND_URL)
        log.info("模式: %s", TRANSLATE_MODES[self.mode])

        self.root.mainloop()

    def _run_hotkey(self, mods, vk):
        listener = HotkeyListener(mods, vk, self.on_hotkey)
        listener.run()


def main():
    from logger import setup_logging
    setup_logging()
    app = TranslateApp()
    app.run()


if __name__ == "__main__":
    main()
