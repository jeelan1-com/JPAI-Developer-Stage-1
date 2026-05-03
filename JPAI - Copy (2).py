#!/usr/bin/env python3
"""
JPAI Agentic AI by JeelanPro™ AI team
IDE-style Terminal AI Assistant · ZhipuAI GLM Free Models
"""

import os, sys, json, time, subprocess, threading, queue
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any, Generator

import httpx
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Header, Footer, Static, Input, Button, Collapsible,
    TextArea, Label, Select, Switch, RichLog,
)
from textual.containers import Horizontal, Vertical, VerticalScroll, Container
from textual.reactive import reactive
from textual import work
from textual.message import Message

# ═══════════════════════════════════════════════════════════
#  PATHS
# ═══════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "Data"
CHAT_DIR = DATA_DIR / "chats"
SETTINGS_PATH = DATA_DIR / "settings.json"
TOOLS_PATH = DATA_DIR / "tools.json"
API_KEY_FILE = DATA_DIR / "api_key.txt"
for d in [DATA_DIR, CHAT_DIR]:
    d.mkdir(exist_ok=True)

BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
FREE_MODELS = ["glm-4.7-flash", "glm-4.5-flash", "glm-4.6v-flash"]
MODES = ["Chat", "Agent", "Long Run", "Deep Think", "Quick", "Vision", "Structured"]

# ═══════════════════════════════════════════════════════════
#  SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════

SYSTEM_PROMPTS = {
    "Chat": "You are JPAI, a helpful, concise, and honest assistant. Format responses in markdown. When asked for code, provide working examples.",
    "Agent": "You are an autonomous agent. Loop: THINK → ACT (call tool) → OBSERVE → repeat. Explain reasoning before each action. Summarize when done.",
    "Long Run": "You run in timed mode. Workflow:\n1. PLAN — numbered subtasks with ⬜\n2. THINK — evaluate feasibility\n3. FIX — adjust plan\n4. EXECUTE — work each subtask, mark ✅ done, 🔄 current\n5. Wrap up if time is low.\n\nShow checklist after each step:\n📋 Task Progress:\n  ✅ 1. Done item\n  🔄 2. Current item\n  ⬜ 3. Pending item",
    "Deep Think": "Think step by step before answering. Break problems into parts. Show reasoning then conclusion.\n\n🧠 Reasoning: [step-by-step]\n📌 Conclusion: [answer]",
    "Quick": "Answer in 1-3 sentences. Direct. No fluff. Bullet points if needed, one line each.",
    "Vision": "You analyze images from URLs. Describe what you see, answer questions, extract text, identify objects. Be thorough and detailed.",
    "Structured": "Respond ONLY with valid JSON matching the user's schema. No text outside JSON. On constraint violation: {\"error\": \"description\"}",
}

DEFAULT_TOOLS = [
    {"type": "function", "function": {"name": "search_web", "description": "Search the web", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read file contents", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Write content to file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "run_command", "description": "Execute a shell command", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "list_directory", "description": "List directory contents", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "calculate", "description": "Evaluate math expression", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}},
]

# ═══════════════════════════════════════════════════════════
#  CLIPBOARD
# ═══════════════════════════════════════════════════════════

def read_clipboard() -> str:
    try:
        r = subprocess.run(["powershell", "-command", "Get-Clipboard"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip()
    except: return ""

def write_clipboard(text: str):
    try:
        subprocess.run(["powershell", "-command", f"$t = @'\n{text}\n'@; Set-Clipboard -Value $t"], capture_output=True, text=True, timeout=5)
    except: pass

# ═══════════════════════════════════════════════════════════
#  DATA MANAGER
# ═══════════════════════════════════════════════════════════

class DataManager:
    def __init__(self):
        self.settings = self._load(SETTINGS_PATH, {
            "api_key": "", "model": "glm-4.7-flash", "temperature": 0.7,
            "max_tokens": 4096, "system_prompts": SYSTEM_PROMPTS,
            "allow_commands": True, "confirm_commands": True,
            "working_dir": str(Path.home()), "theme": "midnight",
        })
        self.tools = self._load(TOOLS_PATH, DEFAULT_TOOLS)
        if not self.settings.get("api_key"):
            if API_KEY_FILE.exists():
                try:
                    k = API_KEY_FILE.read_text(encoding="utf-8").strip()
                    if k and len(k) > 10: self.settings["api_key"] = k; self.save()
                except: pass

    def _load(self, path, default):
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f: return json.load(f)
            except: return default
        return default

    def _save(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2, ensure_ascii=False)

    def save(self): self._save(SETTINGS_PATH, self.settings)
    def save_tools(self): self._save(TOOLS_PATH, self.tools)

    def set_api_key(self, key):
        self.settings["api_key"] = key.strip(); self.save()
        try: API_KEY_FILE.write_text(key.strip(), encoding="utf-8")
        except: pass

    def get_prompt(self, mode): return self.settings.get("system_prompts", SYSTEM_PROMPTS).get(mode, SYSTEM_PROMPTS.get(mode, ""))

    def save_chat(self, cid, msgs, mode, model, folder=""):
        self._save(CHAT_DIR / f"{cid}.json", {"id": cid, "mode": mode, "model": model, "folder": folder, "ts": datetime.now().isoformat(), "messages": msgs})

    def list_chats(self):
        chats = []
        for p in CHAT_DIR.glob("*.json"):
            try:
                d = self._load(p, None)
                if d: chats.append(d)
            except: pass
        chats.sort(key=lambda x: x.get("ts", ""), reverse=True)
        return chats

    def delete_chat(self, cid):
        p = CHAT_DIR / f"{cid}.json"
        if p.exists(): p.unlink()

# ═══════════════════════════════════════════════════════════
#  API CLIENT + REQUEST QUEUE
# ═══════════════════════════════════════════════════════════

class ZhipuClient:
    def __init__(self, dm: DataManager):
        self.dm = dm
        self._queue = queue.Queue()
        self._busy = False
        self._lock = threading.Lock()

    @property
    def busy(self): return self._busy

    def enqueue(self, messages, model, tools, thinking, response_format, callback_stream, callback_done):
        self._queue.put((messages, model, tools, thinking, response_format, callback_stream, callback_done))
        self._process_next()

    def _process_next(self):
        with self._lock:
            if self._busy or self._queue.empty(): return
            self._busy = True
        item = self._queue.get_nowait()
        threading.Thread(target=self._run, args=item, daemon=True).start()

    def _run(self, messages, model, tools, thinking, response_format, cb_stream, cb_done):
        result = {"content": "", "tokens": 0, "time": 0, "error": ""}
        start = time.time()
        try:
            for chunk in self._stream(messages, model, tools, thinking, response_format):
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                c = delta.get("content", "")
                if c:
                    result["content"] += c
                    cb_stream(c)
                r = delta.get("reasoning_content", "")
                if r:
                    result["content"] += r
                    cb_stream(r)
                u = chunk.get("usage", {})
                if u: result["tokens"] = u.get("total_tokens", 0)
        except Exception as e:
            result["error"] = str(e)
        result["time"] = time.time() - start
        cb_done(result)
        with self._lock:
            self._busy = False
        self._process_next()

    def _stream(self, messages, model=None, tools=None, thinking=False, response_format=None):
        model = model or self.dm.settings.get("model", "glm-4.7-flash")
        key = self.dm.settings.get("api_key", "")
        if not key: raise ValueError("No API key")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body = {"model": model, "messages": messages, "stream": True,
                "temperature": self.dm.settings.get("temperature", 0.7),
                "max_tokens": self.dm.settings.get("max_tokens", 4096)}
        if tools: body["tools"] = tools
        if thinking: body["thinking"] = {"type": "enabled", "budget_tokens": int(body["max_tokens"] * 0.5)}
        if response_format: body["response_format"] = response_format
        with httpx.Client(timeout=httpx.Timeout(180, connect=30)) as client:
            with client.stream("POST", f"{BASE_URL}chat/completions", json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    err = "".join(b.decode("utf-8", errors="replace") for b in resp.iter_bytes())
                    raise Exception(f"API {resp.status_code}: {err[:300]}")
                buf = ""
                for b in resp.iter_bytes():
                    buf += b.decode("utf-8", errors="replace")
                    while "\n\n" in buf:
                        evt, buf = buf.split("\n\n", 1)
                        for line in evt.split("\n"):
                            line = line.strip()
                            if line.startswith("data: "):
                                d = line[6:]
                                if d.strip() == "[DONE]": return
                                try: yield json.loads(d)
                                except: pass

# ═══════════════════════════════════════════════════════════
#  TOOL EXECUTOR
# ═══════════════════════════════════════════════════════════

def execute_tool(name, args, dm):
    if name == "read_file":
        try:
            with open(args.get("path",""), "r", encoding="utf-8") as f: return f.read()[:8000]
        except Exception as e: return f"Error: {e}"
    elif name == "write_file":
        try:
            with open(args.get("path",""), "w", encoding="utf-8") as f: f.write(args.get("content",""))
            return f"Wrote {args.get('path')}"
        except Exception as e: return f"Error: {e}"
    elif name == "run_command":
        if not dm.settings.get("allow_commands", True):
            return "Command execution is disabled in settings."
        if dm.settings.get("confirm_commands", True):
            return "CONFIRM_REQUIRED:" + args.get("command", "")
        try: return os.popen(args.get("command","")).read()[:5000] or "(no output)"
        except Exception as e: return f"Error: {e}"
    elif name == "list_directory":
        try:
            p = Path(args.get("path", "."))
            items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            return "\n".join(f"{'📁' if i.is_dir() else '📄'} {i.name}" for i in items[:100])
        except Exception as e: return f"Error: {e}"
    elif name == "search_web":
        return f"[Web search simulated for: {args.get('query','')}]"
    elif name == "calculate":
        expr = args.get("expression", "")
        try:
            if all(c in "0123456789+-*/.() " for c in expr): return str(eval(expr))
            return "Error: invalid chars"
        except Exception as e: return f"Error: {e}"
    return f"Unknown: {name}"

# ═══════════════════════════════════════════════════════════
#  LOADING SCREEN
# ═══════════════════════════════════════════════════════════

class LoadingScreen(Screen):
    BINDINGS = []
    frame = reactive(0)
    frames = ["⠁","⠃","⠇","⡇","⡗","⡷","⣷","⣯","⣟","⡿","⢿","⣻","⣽","⣾","⣷"]

    def compose(self):
        with Container(id="load-center"):
            yield Label("JPAI", id="load-title")
            yield Label("Agentic AI", id="load-sub")
            yield Label("by JeelanPro™ AI team", id="load-team")
            yield Static("", id="load-anim")
            yield Label("Initializing systems...", id="load-msg")

    def on_mount(self):
        self._msgs = ["Loading models...", "Preparing interface...", "Scanning workspace...", "Ready."]
        self._step = 0
        self._timer = self.set_interval(0.06, self._tick)

    def _tick(self):
        self.frame = (self.frame + 1) % len(self.frames)
        self.query_one("#load-anim", Static).update(self.frames[self.frame])
        if self.frame == 0:
            if self._step < len(self._msgs):
                self.query_one("#load-msg", Label).update(self._msgs[self._step])
                self._step += 1
            if self._step >= len(self._msgs):
                self._timer.stop()
                self.app._show_main()

# ═══════════════════════════════════════════════════════════
#  MENU SCREEN
# ═══════════════════════════════════════════════════════════

class MenuScreen(ModalScreen):
    BINDINGS = [("escape", "close_menu", "Close")]

    class Selected(Message):
        def __init__(self, item: str): super().__init__(); self.item = item

    def compose(self):
        with Container(id="menu-box"):
            yield Label("JPAI Menu", id="menu-title")
            for item in ["💬 New Chat", "🤖 Agent Mode", "⏱ Long Run", "🧠 Deep Think",
                          "👁 Vision", "🎯 Quick", "📐 Structured", "📁 File Editor",
                          "📋 History", "🔍 Search Chats", "⚙ Settings"]:
                yield Button(item, classes="menu-btn", id=f"menu-{item.split(' ',1)[1].lower().replace(' ','-')}")

    def on_button_pressed(self, event):
        self.dismiss(event.button.id.replace("menu-", ""))

    def action_close_menu(self):
        self.dismiss("")

# ═══════════════════════════════════════════════════════════
#  CONFIRM DIALOG
# ═══════════════════════════════════════════════════════════

class ConfirmDialog(ModalScreen):
    def __init__(self, msg, cmd=""):
        super().__init__()
        self.msg = msg
        self.cmd = cmd

    def compose(self):
        with Container(id="confirm-box"):
            yield Label("⚠ Confirm Action", id="confirm-title")
            yield Static(self.msg, id="confirm-msg")
            if self.cmd:
                yield Static(f"$ {self.cmd}", id="confirm-cmd")
            with Horizontal():
                yield Button("✅ Allow", variant="success", id="confirm-yes")
                yield Button("❌ Deny", variant="error", id="confirm-no")

    def on_button_pressed(self, event):
        self.dismiss(event.button.id == "confirm-yes")

# ═══════════════════════════════════════════════════════════
#  FILE EXPLORER WIDGET
# ═══════════════════════════════════════════════════════════

class FileExplorer(Vertical):
    def __init__(self, dm, **kw):
        super().__init__(**kw)
        self.dm = dm
        self.current_path = Path(dm.settings.get("working_dir", str(Path.home())))

    def compose(self):
        yield Label("📁 Explorer", id="explorer-title")
        yield Static(str(self.current_path), id="explorer-path")
        yield Button("📂 Change Folder", id="explorer-change")
        yield Button("🔄 Refresh", id="explorer-refresh")
        with VerticalScroll(id="explorer-list"):
            yield self._render_tree()

    def _render_tree(self):
        items = []
        try:
            entries = sorted(self.current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            for e in entries[:80]:
                icon = "📁" if e.is_dir() else "📄"
                items.append(f"{icon} {e.name}")
        except PermissionError:
            items.append("(no access)")
        return Static("\n".join(items) if items else "(empty)")

    def on_button_pressed(self, event):
        if event.button.id == "explorer-refresh":
            self._refresh()
        elif event.button.id == "explorer-change":
            path_input = self.app.query_one("#folder-input", Input)
            path_input.value = str(self.current_path)
            path_input.focus()

    def navigate(self, path_str):
        p = Path(path_str)
        if p.exists() and p.is_dir():
            self.current_path = p
            self.dm.settings["working_dir"] = str(p)
            self.dm.save()
            self._refresh()

    def _refresh(self):
        try:
            self.query_one("#explorer-path", Static).update(str(self.current_path))
            old = self.query_one("#explorer-list")
            old.remove_children()
            old.mount(self._render_tree())
        except: pass

# ═══════════════════════════════════════════════════════════
#  CHAT MESSAGE WIDGET
# ═══════════════════════════════════════════════════════════

class ChatMessage(Static):
    def __init__(self, role, content, meta="", **kw):
        self.role = role
        self._content = content
        self._meta = meta
        if role == "user":
            display = f"💬 {content[:200]}"
        else:
            display = f"🤖 {content[:500]}"
        super().__init__(display, **kw)
        self.add_class(f"msg-{role}")

    def full_content(self): return self._content

# ═══════════════════════════════════════════════════════════
#  CHAT AREA (Chrome-style within main area)
# ═══════════════════════════════════════════════════════════

class ChatSession:
    def __init__(self, mode="Chat", cid=None):
        self.id = cid or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.mode = mode
        self.messages = []
        self.title = "New Chat"
        self.model = "glm-4.7-flash"

class ChatArea(Vertical):
    def __init__(self, dm, api, **kw):
        super().__init__(**kw)
        self.dm = dm
        self.api = api
        self.sessions = []
        self.active_idx = -1
        self._streaming = False
        self._stream_text = ""

    def compose(self):
        with Horizontal(id="chat-tabs"):
            yield Static("", id="chat-tabs-inner")
            yield Button("+", variant="success", id="new-chat-btn", classes="tab-btn")
        with VerticalScroll(id="chat-messages"):
            yield Label("Open a chat from the menu or press +", id="chat-empty")
        with Vertical(id="chat-input-area"):
            yield Input(placeholder="Message... (Enter to send)", id="msg-input")
            with Horizontal(id="chat-actions"):
                yield Button("▶ Send", variant="primary", id="send-btn")
                yield Button("↻ Re-run", id="rerun-btn")
                yield Button("🗑 Delete", variant="error", id="delete-btn")
                yield Button("✏ Edit", id="edit-btn")
                yield Button("⏩ Continue", id="continue-btn")
                yield Button("📋 Copy", id="copy-btn")
                yield Button("📋 Paste", id="paste-btn")
                yield Label("", id="queue-status")

    def on_mount(self):
        self._render_tabs()

    def new_session(self, mode="Chat"):
        s = ChatSession(mode)
        s.model = self.dm.settings.get("model", "glm-4.7-flash")
        self.sessions.append(s)
        self.active_idx = len(self.sessions) - 1
        self._render_tabs()
        self._render_messages()

    def switch_session(self, idx):
        if 0 <= idx < len(self.sessions):
            self.active_idx = idx
            self._render_tabs()
            self._render_messages()

    def close_session(self, idx):
        if 0 <= idx < len(self.sessions):
            s = self.sessions.pop(idx)
            self.dm.delete_chat(s.id)
            if self.sessions:
                self.active_idx = min(self.active_idx, len(self.sessions) - 1)
            else:
                self.active_idx = -1
            self._render_tabs()
            self._render_messages()

    def _render_tabs(self):
        try:
            inner = self.query_one("#chat-tabs-inner", Static)
            if not self.sessions:
                inner.update("")
                return
            tabs = []
            for i, s in enumerate(self.sessions):
                marker = "▶" if i == self.active_idx else " "
                tabs.append(f"[{marker}] {s.title[:20]}")
            inner.update("  ".join(tabs))
        except: pass

    def _render_messages(self):
        try:
            scroll = self.query_one("#chat-messages", VerticalScroll)
            scroll.remove_children()
            if self.active_idx < 0 or not self.sessions:
                scroll.mount(Label("Open a chat from the menu or press +", id="chat-empty2"))
                return
            s = self.sessions[self.active_idx]
            for m in s.messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "system": continue
                meta = ""
                if "gen_time" in m:
                    meta = f"⏱{m['gen_time']:.1f}s 📝{m.get('tokens',0)}tok"
                scroll.mount(ChatMessage(role, content, meta))
            scroll.scroll_end(animate=False)
        except: pass

    def _current(self):
        if 0 <= self.active_idx < len(self.sessions):
            return self.sessions[self.active_idx]
        return None

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "new-chat-btn":
            self.new_session("Chat")
        elif bid == "send-btn":
            self._send()
        elif bid == "rerun-btn":
            self._rerun()
        elif bid == "delete-btn":
            self._delete_last()
        elif bid == "edit-btn":
            self._edit_last()
        elif bid == "continue-btn":
            self._continue()
        elif bid == "copy-btn":
            self._copy_response()
        elif bid == "paste-btn":
            self._paste()

    def on_input_submitted(self, event):
        if event.input.id == "msg-input":
            self._send()

    def _send(self):
        s = self._current()
        if not s or self._streaming:
            return
        inp = self.query_one("#msg-input", Input)
        text = inp.value.strip()
        if not text: return
        inp.value = ""
        s.messages.append({"role": "user", "content": text})
        if len(s.messages) == 1:
            s.title = text[:30]
        self._render_tabs()
        self._render_messages()
        self._generate(s)

    def _rerun(self):
        s = self._current()
        if not s or self._streaming: return
        while s.messages and s.messages[-1].get("role") == "assistant":
            s.messages.pop()
        self._render_messages()
        self._generate(s)

    def _delete_last(self):
        s = self._current()
        if not s: return
        if s.messages:
            s.messages.pop()
            self._render_messages()

    def _edit_last(self):
        s = self._current()
        if not s: return
        if s.messages and s.messages[-1].get("role") == "user":
            last = s.messages.pop()
            self.query_one("#msg-input", Input).value = last.get("content", "")
            self._render_messages()

    def _continue(self):
        s = self._current()
        if not s or self._streaming: return
        s.messages.append({"role": "user", "content": "Continue generating from where you left off."})
        self._render_messages()
        self._generate(s)

    def _copy_response(self):
        s = self._current()
        if not s: return
        for m in reversed(s.messages):
            if m.get("role") == "assistant":
                write_clipboard(m.get("content", ""))
                break

    def _paste(self):
        clip = read_clipboard()
        if clip:
            self.query_one("#msg-input", Input).value = clip

    def _generate(self, session):
        self._streaming = True
        self._stream_text = ""
        app = self.app

        api_msgs = []
        prompt = self.dm.get_prompt(session.mode)
        if prompt:
            api_msgs.append({"role": "system", "content": prompt})
        wd = self.dm.settings.get("working_dir", "")
        if wd:
            api_msgs.append({"role": "system", "content": f"Working directory: {wd}"})
        api_msgs.extend(session.messages)

        model = session.model
        if session.mode == "Vision":
            model = "glm-4.6v-flash"
        elif session.mode == "Quick":
            model = "glm-4.5-flash"

        tools = self.dm.tools if session.mode in ("Agent", "Chat") else None
        thinking = session.mode == "Deep Think"
        rf = {"type": "json_object"} if session.mode == "Structured" else None

        def on_stream(text):
            self._stream_text += text
            try:
                scroll = self.query_one("#chat-messages", VerticalScroll)
                stream_widget = None
                try:
                    stream_widget = self.query_one("#stream-out", Static)
                except: pass
                if not stream_widget:
                    stream_widget = Static("", id="stream-out")
                    scroll.mount(stream_widget)
                stream_widget.update(self._stream_text)
                scroll.scroll_end(animate=False)
            except: pass

        def on_done(result):
            self._streaming = False
            if result.get("error"):
                session.messages.append({"role": "assistant", "content": f"Error: {result['error']}"})
            else:
                session.messages.append({
                    "role": "assistant", "content": result["content"],
                    "gen_time": result["time"], "tokens": result["tokens"],
                })
            try:
                self.query_one("#stream-out", Static).remove()
            except: pass
            self._render_messages()
            self.dm.save_chat(session.id, session.messages, session.mode, session.model)
            self._update_queue_status()

        self._update_queue_status()
        self.api.enqueue(api_msgs, model, tools, thinking, rf, on_stream, on_done)

    def _update_queue_status(self):
        try:
            qs = self.query_one("#queue-status", Label)
            if self.api.busy:
                qs.update("⏳ Processing...")
            else:
                qs.update("✅ Ready")
        except: pass

# ═══════════════════════════════════════════════════════════
#  FILE EDITOR PANEL
# ═══════════════════════════════════════════════════════════

class FileEditorPanel(Vertical):
    def __init__(self, dm, **kw):
        super().__init__(**kw)
        self.dm = dm
        self.current_file = None

    def compose(self):
        yield Label("📝 File Editor", id="editor-title")
        yield Input(placeholder="File path...", id="editor-path")
        with Horizontal():
            yield Button("📂 Open", id="editor-open")
            yield Button("💾 Save", variant="success", id="editor-save")
            yield Button("📋 Copy All", id="editor-copy")
            yield Button("🤖 AI Suggest", variant="primary", id="editor-ai")
        yield TextArea(id="editor-content")

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "editor-open":
            self._open()
        elif bid == "editor-save":
            self._save()
        elif bid == "editor-copy":
            write_clipboard(self.query_one("#editor-content", TextArea).text)
        elif bid == "editor-ai":
            self._ai_suggest()

    def _open(self):
        path = self.query_one("#editor-path", Input).value.strip()
        if not path: return
        try:
            content = Path(path).read_text(encoding="utf-8")
            self.query_one("#editor-content", TextArea).text = content
            self.current_file = path
        except Exception as e:
            self.query_one("#editor-content", TextArea).text = f"Error: {e}"

    def _save(self):
        if not self.current_file: return
        try:
            Path(self.current_file).write_text(self.query_one("#editor-content", TextArea).text, encoding="utf-8")
        except Exception: pass

    def _ai_suggest(self):
        content = self.query_one("#editor-content", TextArea).text
        if not content: return
        chat = self.app.query_one(ChatArea)
        if chat._current():
            chat.query_one("#msg-input", Input).value = f"Review and improve this code:\n```\n{content[:2000]}\n```"

    def open_file(self, path):
        self.query_one("#editor-path", Input).value = path
        self._open()

# ═══════════════════════════════════════════════════════════
#  WELCOME SCREEN
# ═══════════════════════════════════════════════════════════

class WelcomeWidget(Vertical):
    def compose(self):
        yield Label("JPAI", id="welcome-title")
        yield Label("Agentic AI", id="welcome-sub")
        yield Label("by JeelanPro™ AI team", id="welcome-team")
        yield Static("")
        yield Label("Quick Start:", id="welcome-qs")
        yield Static("  📋 Press ≡ Menu (top-right) to open modes & tools")
        yield Static("  💬 Press + to start a new chat")
        yield Static("  📁 Set a working folder in the Explorer panel")
        yield Static("  ⚙ Configure your API key in Settings")
        yield Static("")
        yield Label("Free Models:", id="welcome-models")
        yield Static("  • glm-4.7-flash — Fast all-rounder")
        yield Static("  • glm-4.5-flash — Lightweight & quick")
        yield Static("  • glm-4.6v-flash — Vision & image analysis")
        yield Static("")
        yield Label("Modes:", id="welcome-modes")
        yield Static("  💬 Chat · 🤖 Agent · ⏱ Long Run · 🧠 Deep Think")
        yield Static("  👁 Vision · 🎯 Quick · 📐 Structured")
        yield Static("")
        yield Static("All chats, agent loops, and long-running tasks are queued.", id="welcome-note")

# ═══════════════════════════════════════════════════════════
#  SETTINGS PANEL
# ═══════════════════════════════════════════════════════════

class SettingsPanel(VerticalScroll):
    def __init__(self, dm, **kw):
        super().__init__(**kw)
        self.dm = dm

    def compose(self):
        yield Label("─── API Key ───", classes="section-head")
        yield Input(placeholder="API key...", id="s-api-key", password=True)
        with Horizontal():
            yield Button("📋 Paste Clipboard", variant="primary", id="s-paste")
            yield Button("📁 Load File", id="s-load-file")
            yield Button("👁 Toggle", id="s-toggle")
            yield Button("💾 Save", variant="success", id="s-save-key")
        yield Static("—", id="s-key-status")

        yield Label("─── Model ───", classes="section-head")
        yield Select([(m, m) for m in FREE_MODELS], value="glm-4.7-flash", id="s-model")

        yield Label("─── Parameters ───", classes="section-head")
        yield Label("Temperature:")
        yield Input(value="0.7", id="s-temp")
        yield Label("Max Tokens:")
        yield Input(value="4096", id="s-tokens")

        yield Label("─── Security ───", classes="section-head")
        yield Label("Allow command execution:")
        yield Switch(value=True, id="s-allow-cmd")
        yield Label("Confirm before executing:")
        yield Switch(value=True, id="s-confirm-cmd")

        yield Label("─── System Prompts ───", classes="section-head")
        yield Select([(k, k) for k in SYSTEM_PROMPTS.keys()], value="Chat", id="s-prompt-mode")
        yield Button("Load", id="s-load-prompt")
        yield TextArea(id="s-prompt-editor")
        with Horizontal():
            yield Button("Save", variant="success", id="s-save-prompt")
            yield Button("Reset", variant="warning", id="s-reset-prompt")

        yield Label("─── Tools ───", classes="section-head")
        yield TextArea(json.dumps(self.dm.tools, indent=2), id="s-tools-editor")
        yield Button("Save Tools", variant="success", id="s-save-tools")

    def on_mount(self):
        self.query_one("#s-api-key", Input).value = self.dm.settings.get("api_key", "")
        self.query_one("#s-model", Select).value = self.dm.settings.get("model", "glm-4.7-flash")
        self.query_one("#s-temp", Input).value = str(self.dm.settings.get("temperature", 0.7))
        self.query_one("#s-tokens", Input).value = str(self.dm.settings.get("max_tokens", 4096))
        self.query_one("#s-allow-cmd", Switch).value = self.dm.settings.get("allow_commands", True)
        self.query_one("#s-confirm-cmd", Switch).value = self.dm.settings.get("confirm_commands", True)
        self._update_status()
        self._load_prompt("Chat")

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "s-paste":
            c = read_clipboard()
            if c:
                self.query_one("#s-api-key", Input).value = c
                self.dm.set_api_key(c); self._update_status()
        elif bid == "s-load-file":
            if API_KEY_FILE.exists():
                k = API_KEY_FILE.read_text(encoding="utf-8").strip()
                if k: self.query_one("#s-api-key", Input).value = k; self.dm.set_api_key(k); self._update_status()
        elif bid == "s-toggle":
            i = self.query_one("#s-api-key", Input); i.password = not i.password
        elif bid == "s-save-key":
            self.dm.set_api_key(self.query_one("#s-api-key", Input).value.strip()); self._update_status()
        elif bid == "s-load-prompt":
            self._load_prompt(str(self.query_one("#s-prompt-mode", Select).value))
        elif bid == "s-save-prompt":
            mode = str(self.query_one("#s-prompt-mode", Select).value)
            if "system_prompts" not in self.dm.settings: self.dm.settings["system_prompts"] = {}
            self.dm.settings["system_prompts"][mode] = self.query_one("#s-prompt-editor", TextArea).text
            self.dm.save()
        elif bid == "s-reset-prompt":
            mode = str(self.query_one("#s-prompt-mode", Select).value)
            self.query_one("#s-prompt-editor", TextArea).text = SYSTEM_PROMPTS.get(mode, "")
        elif bid == "s-save-tools":
            try: self.dm.tools = json.loads(self.query_one("#s-tools-editor", TextArea).text); self.dm.save_tools()
            except: pass

    def on_switch_changed(self, event):
        if event.switch.id == "s-allow-cmd":
            self.dm.settings["allow_commands"] = event.value; self.dm.save()
        elif event.switch.id == "s-confirm-cmd":
            self.dm.settings["confirm_commands"] = event.value; self.dm.save()

    def on_select_changed(self, event):
        if event.select.id == "s-model":
            self.dm.settings["model"] = str(event.value); self.dm.save()

    def _update_status(self):
        k = self.dm.settings.get("api_key", "")
        self.query_one("#s-key-status", Static).update(
            f"✅ Key set ({len(k)} chars)" if k else "❌ No key set")

    def _load_prompt(self, mode):
        self.query_one("#s-prompt-editor", TextArea).text = self.dm.get_prompt(mode)

# ═══════════════════════════════════════════════════════════
#  HISTORY PANEL
# ═══════════════════════════════════════════════════════════

class HistoryPanel(VerticalScroll):
    def __init__(self, dm, api, **kw):
        super().__init__(**kw)
        self.dm = dm; self.api = api

    def compose(self):
        yield Label("📋 Chat History", classes="section-head")
        yield Button("🔄 Refresh", id="h-refresh")
        yield Button("🗑 Clear All", variant="error", id="h-clear")
        yield Button("📤 Export", id="h-export")
        yield Button("🔍 Search", id="h-search")
        yield Input(placeholder="Search query...", id="h-search-input")
        with VerticalScroll(id="h-list"):
            yield Static("")

    def on_mount(self): self._refresh()

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "h-refresh": self._refresh()
        elif bid == "h-clear":
            for c in self.dm.list_chats(): self.dm.delete_chat(c.get("id",""))
            self._refresh()
        elif bid == "h-export":
            with open(DATA_DIR / "export_all.json", "w", encoding="utf-8") as f:
                json.dump(self.dm.list_chats(), f, indent=2, ensure_ascii=False)
        elif bid == "h-search": self._search()

    def _search(self):
        q = self.query_one("#h-search-input", Input).value.strip().lower()
        chats = self.dm.list_chats()
        if q:
            filtered = []
            for c in chats:
                for m in c.get("messages", []):
                    if q in m.get("content", "").lower():
                        filtered.append(c); break
            chats = filtered
        self._render(chats)

    def _refresh(self): self._render(self.dm.list_chats())

    def _render(self, chats):
        try:
            lst = self.query_one("#h-list", VerticalScroll); lst.remove_children()
            if not chats: lst.mount(Static("No chats found.")); return
            for c in chats[:30]:
                ts = c.get("ts", "?"); mode = c.get("mode", "?"); model = c.get("model", "?")
                n = len(c.get("messages", []))
                preview = ""
                for m in c.get("messages", []):
                    if m.get("role") == "user":
                        txt = m.get("content", "")
                        if isinstance(txt, str): preview = txt[:60]
                        break
                lst.mount(Static(f"📂 {ts} · {mode} · {model}\n   \"{preview}\" ({n} msgs)"))
        except: pass

# ═══════════════════════════════════════════════════════════
#  MAIN SCREEN (IDE Layout)
# ═══════════════════════════════════════════════════════════

class MainScreen(Screen):
    BINDINGS = [
        Binding("ctrl+n", "new_chat", "New Chat"),
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+m", "menu", "Menu"),
    ]

    def __init__(self, dm, api):
        super().__init__()
        self.dm = dm; self.api = api

    def compose(self):
        with Horizontal(id="top-bar"):
            yield Label("JPAI", id="app-label")
            yield Label("Agentic AI", id="app-sub")
            yield Static("", id="top-spacer")
            yield Label("", id="model-label")
            yield Label("", id="queue-label")
            yield Button("≡", id="menu-btn", classes="top-btn")
            yield Button("⚙", id="settings-btn", classes="top-btn")
            yield Button("📋", id="history-btn", classes="top-btn")
            yield Button("📝", id="editor-btn", classes="top-btn")
            yield Button("❌", id="quit-btn", classes="top-btn")

        with Horizontal(id="main-area"):
            with Vertical(id="left-panel"):
                yield Label("Mode", classes="panel-head")
                yield Select([(m, m) for m in MODES], value="Chat", id="mode-select")
                yield Label("Working Folder", classes="panel-head")
                yield Input(placeholder="Path...", id="folder-input")
                yield Button("📂 Set", id="set-folder-btn")
                yield Static("", id="folder-display")
                yield Label("Properties", classes="panel-head")
                yield Static("Model: —\nMode: —\nChats: 0\nQueue: idle", id="props-display")
                yield Label("Actions", classes="panel-head")
                yield Button("📋 Paste to Input", id="paste-input-btn")
                yield Button("🔍 Search Chats", id="search-chats-btn")

            yield ChatArea(self.dm, self.api, id="center-panel")

            with Vertical(id="right-panel"):
                yield FileExplorer(self.dm, id="file-explorer")

        with Horizontal(id="status-bar"):
            yield Label("JPAI Agentic AI by JeelanPro™ AI team", id="status-left")
            yield Static("", id="status-right")

    def on_mount(self):
        self._update_props()
        self.query_one("#model-label", Label).update(f"🤖 {self.dm.settings.get('model', 'glm-4.7-flash')}")
        self.query_one("#folder-display", Static).update(self.dm.settings.get("working_dir", "—"))

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "menu-btn":
            self._open_menu()
        elif bid == "settings-btn":
            self._open_panel("settings")
        elif bid == "history-btn":
            self._open_panel("history")
        elif bid == "editor-btn":
            self._open_panel("editor")
        elif bid == "quit-btn":
            self.app.exit()
        elif bid == "set-folder-btn":
            path = self.query_one("#folder-input", Input).value.strip()
            if path:
                self.dm.settings["working_dir"] = path; self.dm.save()
                self.query_one("#folder-display", Static).update(path)
                self.query(FileExplorer).navigate(path)
        elif bid == "paste-input-btn":
            clip = read_clipboard()
            if clip:
                self.query_one(ChatArea).query_one("#msg-input", Input).value = clip
        elif bid == "search-chats-btn":
            self._open_panel("history")

    def on_select_changed(self, event):
        if event.select.id == "mode-select":
            chat = self.query_one(ChatArea)
            s = chat._current()
            if s:
                s.mode = str(event.value)

    def _open_menu(self):
        def handle(result):
            if not result: return
            chat = self.query_one(ChatArea)
            mode_map = {
                "new-chat": "Chat", "agent-mode": "Agent", "long-run": "Long Run",
                "deep-think": "Deep Think", "vision": "Vision", "quick": "Quick",
                "structured": "Structured", "file-editor": "editor",
                "history": "history", "search-chats": "history",
                "settings": "settings",
            }
            target = mode_map.get(result, result)
            if target in MODES:
                chat.new_session(target)
                self.query_one("#mode-select", Select).value = target
            elif target in ("editor", "history", "settings"):
                self._open_panel(target)
        self.app.push_screen(MenuScreen(), handle)

    def _open_panel(self, name):
        right = self.query_one("#right-panel")
        right.remove_children()
        if name == "settings":
            right.mount(SettingsPanel(self.dm))
        elif name == "history":
            right.mount(HistoryPanel(self.dm, self.api))
        elif name == "editor":
            right.mount(FileEditorPanel(self.dm))
        else:
            right.mount(FileExplorer(self.dm, id="file-explorer"))

    def action_new_chat(self):
        self.query_one(ChatArea).new_session("Chat")

    def action_menu(self):
        self._open_menu()

    def _update_props(self):
        try:
            chat = self.query_one(ChatArea)
            s = chat._current()
            props = f"Model: {s.model if s else '—'}\nMode: {s.mode if s else '—'}\nChats: {len(chat.sessions)}\nQueue: {'busy' if self.api.busy else 'idle'}"
            self.query_one("#props-display", Static).update(props)
            self.query_one("#queue-label", Label).update("⏳" if self.api.busy else "✅")
            self.query_one("#status-right", Static).update(f"Chats: {len(chat.sessions)} | {'Processing' if self.api.busy else 'Ready'}")
        except: pass

# ═══════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════

class JPAIApp(App):
    TITLE = "JPAI Agentic AI"
    CSS = """
    Screen {
        background: #0a0e1a;
    }
    #load-center {
        align: center middle;
        height: 100%;
    }
    #load-title {
        text-align: center;
        color: #5b9dff;
        text-style: bold;
        margin: 1;
    }
    #load-sub {
        text-align: center;
        color: #88b4ff;
        margin: 0;
    }
    #load-team {
        text-align: center;
        color: #4a6a9f;
        margin: 0 0 0 2;
    }
    #load-anim {
        text-align: center;
        color: #5b9dff;
    }
    #load-msg {
        text-align: center;
        color: #6a8abf;
    }

    #menu-box {
        background: #0f1628;
        border: thick #1a2744;
        padding: 1;
        width: 40;
        height: auto;
    }
    #menu-title {
        color: #5b9dff;
        text-style: bold;
        margin: 0 0 0 1;
    }
    .menu-btn {
        width: 100%;
        margin: 0;
        background: #111b30;
        color: #c0d4f0;
    }
    .menu-btn:hover {
        background: #1a2d50;
    }

    #confirm-box {
        background: #0f1628;
        border: thick #ff6b6b;
        padding: 1;
        width: 60;
    }
    #confirm-title {
        color: #ff6b6b;
        text-style: bold;
    }
    #confirm-msg {
        color: #c0d4f0;
    }
    #confirm-cmd {
        color: #ffa500;
        background: #111b30;
        padding: 1;
    }

    #top-bar {
        background: #0c1220;
        height: 3;
        padding: 0 1;
    }
    #app-label {
        color: #5b9dff;
        text-style: bold;
        width: 8;
    }
    #app-sub {
        color: #4a6a9f;
        width: 16;
    }
    #top-spacer {
        width: 1fr;
    }
    #model-label {
        color: #6a8abf;
        width: 20;
    }
    #queue-label {
        color: #5b9dff;
        width: 4;
    }
    .top-btn {
        background: #111b30;
        color: #5b9dff;
        min-width: 3;
        margin: 0 0 0 1;
    }
    .top-btn:hover {
        background: #1a2d50;
    }

    #main-area {
        height: 1fr;
    }

    #left-panel {
        width: 22;
        background: #0c1220;
        border-right: solid #1a2744;
        padding: 1;
    }
    .panel-head {
        color: #5b9dff;
        text-style: bold;
        margin: 1 0 0 0;
    }
    #folder-display {
        color: #6a8abf;
        margin: 0 0 0 1;
    }

    #center-panel {
        width: 1fr;
    }

    #right-panel {
        width: 26;
        background: #0c1220;
        border-left: solid #1a2744;
        padding: 1;
    }
    #explorer-title {
        color: #5b9dff;
        text-style: bold;
    }
    #explorer-path {
        color: #6a8abf;
        margin: 0 0 0 1;
    }
    #explorer-list {
        height: 1fr;
    }

    #chat-tabs {
        background: #0c1220;
        height: 3;
        padding: 0 1;
        border-bottom: solid #1a2744;
    }
    #chat-tabs-inner {
        color: #88b4ff;
        width: 1fr;
    }
    .tab-btn {
        min-width: 3;
    }
    #chat-messages {
        height: 1fr;
        background: #080c18;
        border: none;
    }
    #chat-empty, #chat-empty2 {
        color: #4a6a9f;
        text-align: center;
        padding: 4;
    }
    #chat-input-area {
        height: auto;
        background: #0c1220;
        border-top: solid #1a2744;
        padding: 1;
    }
    #msg-input {
        width: 100%;
        margin: 0 0 0 1;
        background: #111b30;
    }
    #chat-actions {
        height: auto;
    }
    #chat-actions Button {
        margin: 0 1 0 0;
        min-width: 5;
        background: #111b30;
        color: #88b4ff;
    }
    #chat-actions Button:hover {
        background: #1a2d50;
    }
    #queue-status {
        color: #5b9dff;
        width: 16;
    }

    .msg-user {
        color: #c0d4f0;
        background: #111b30;
        padding: 1;
        margin: 1 2;
        border-left: thick #5b9dff;
    }
    .msg-assistant {
        color: #d4e0f5;
        background: #0f1628;
        padding: 1;
        margin: 1 2;
        border-left: thick #2a5a9f;
    }

    #status-bar {
        background: #080c18;
        height: 1;
        padding: 0 1;
    }
    #status-left {
        color: #3a5a8f;
        width: 1fr;
    }
    #status-right {
        color: #5b9dff;
        width: 30;
    }

    .section-head {
        color: #5b9dff;
        text-style: bold;
        margin: 1 0 0 0;
    }
    #welcome-title {
        color: #5b9dff;
        text-style: bold;
        text-align: center;
        margin: 1;
    }
    #welcome-sub {
        color: #88b4ff;
        text-align: center;
    }
    #welcome-team {
        color: #4a6a9f;
        text-align: center;
        margin: 0 0 0 1;
    }
    #welcome-qs {
        color: #5b9dff;
        text-style: bold;
    }
    #welcome-models {
        color: #5b9dff;
        text-style: bold;
    }
    #welcome-modes {
        color: #5b9dff;
        text-style: bold;
    }
    #welcome-note {
        color: #4a6a9f;
        margin: 1 0;
    }

    #editor-title {
        color: #5b9dff;
        text-style: bold;
    }
    #editor-content {
        height: 1fr;
        background: #080c18;
    }

    Switch {
        margin: 0 0 0 1;
    }
    Select {
        margin: 0 0 0 1;
    }
    Input {
        margin: 0 0 0 1;
    }
    TextArea {
        margin: 0 0 0 1;
    }
    Label {
        margin: 0;
        color: #88b4ff;
    }
    Static {
        color: #88b4ff;
    }
    Button {
        margin: 0 0 0 1;
    }
    """

    BINDINGS = []

    def __init__(self, dm):
        super().__init__()
        self.dm = dm
        self.api = ZhipuClient(dm)

    def on_mount(self):
        self._loading = LoadingScreen()
        self.push_screen(self._loading)

    def _show_main(self):
        try:
            self.pop_screen()
        except Exception:
            pass
        self.push_screen(MainScreen(self.dm, self.api))

# ═══════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════

def startup_check(dm):
    key = dm.settings.get("api_key", "")
    if key and len(key) > 10: return
    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║  JPAI Agentic AI                         ║")
    print("  ║  by JeelanPro™ AI team                   ║")
    print("  ║                                          ║")
    print("  ║  No API key found. Paste it here.        ║")
    print("  ║  Ctrl+V works. Or press Enter to skip.   ║")
    print("  ╚══════════════════════════════════════════╝")
    print()
    try: api_key = input("  API key: ").strip()
    except: api_key = ""
    if api_key and len(api_key) > 10:
        dm.set_api_key(api_key)
        print(f"\n  ✅ Saved ({len(api_key)} chars)\n")
        time.sleep(1)
    else:
        print("\n  ⚠ Set it later in ⚙ Settings.\n")
        time.sleep(2)

if __name__ == "__main__":
    dm = DataManager()
    startup_check(dm)
    JPAIApp(dm).run()