#!/usr/bin/env python3
"""JPAI Agentic AI by JeelanPro(TM) AI team"""

import os, sys, json, time, subprocess, threading, queue
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any, Generator

import httpx
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Static, Input, Button, Collapsible, TextArea, Label,
    Select, Switch, DataTable,
)
from textual.containers import Horizontal, Vertical, VerticalScroll, Container
from textual.reactive import reactive
from textual import work
from textual.message import Message

# ═══════════════════════════════════════════════════════════
#  PATHS & CONSTANTS
# ═══════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "Data"
CHAT_DIR = DATA_DIR / "chats"
SETTINGS_PATH = DATA_DIR / "settings.json"
TOOLS_PATH = DATA_DIR / "tools.json"
API_KEY_FILE = DATA_DIR / "api_key.txt"
for d in [DATA_DIR, CHAT_DIR]: d.mkdir(exist_ok=True)

BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
FREE_MODELS = ["glm-4.7-flash", "glm-4.5-flash", "glm-4.6v-flash"]
MODES = ["Chat", "Agent", "Long Run", "Deep Think", "Quick", "Vision", "Structured"]

SYSTEM_PROMPTS = {
    "Chat": "You are JPAI, a helpful, concise, and honest assistant. Format responses in markdown. When asked for code, provide working examples.",
    "Agent": "You are an autonomous agent. Loop: THINK -> ACT (call tool) -> OBSERVE -> repeat. Explain reasoning before each action. Summarize when done.",
    "Long Run": "You run in timed mode. Workflow:\n1. PLAN - numbered subtasks with [ ]\n2. THINK - evaluate feasibility\n3. FIX - adjust plan\n4. EXECUTE - work each subtask, mark [x] done, [>] current\n5. Wrap up if time is low.",
    "Deep Think": "Think step by step before answering. Break problems into parts. Show reasoning then conclusion.",
    "Quick": "Answer in 1-3 sentences. Direct. No fluff. Bullet points if needed.",
    "Vision": "You analyze images from URLs. Describe what you see, answer questions, extract text. Be thorough.",
    "Structured": 'Respond ONLY with valid JSON matching the schema. No text outside JSON. On error: {"error": "description"}',
}

DEFAULT_TOOLS = [
    {"type": "function", "function": {"name": "search_web", "description": "Search the web", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Write file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "run_command", "description": "Run shell command", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "list_directory", "description": "List directory", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "calculate", "description": "Evaluate math", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}},
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
        subprocess.run(["powershell", "-command", "Set-Clipboard -Value @'\n" + text + "\n'@"], capture_output=True, text=True, timeout=5)
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
            "working_dir": str(Path.home()),
        })
        self.tools = self._load(TOOLS_PATH, DEFAULT_TOOLS)
        if not self.settings.get("api_key") and API_KEY_FILE.exists():
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
    def save_chat(self, cid, msgs, mode, model):
        self._save(CHAT_DIR / f"{cid}.json", {"id": cid, "mode": mode, "model": model, "ts": datetime.now().isoformat(), "messages": msgs})
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
#  API CLIENT + QUEUE
# ═══════════════════════════════════════════════════════════

class ZhipuClient:
    def __init__(self, dm):
        self.dm = dm
        self._queue = queue.Queue()
        self._busy = False
        self._lock = threading.Lock()
        self._cancel = False

    @property
    def busy(self): return self._busy

    def cancel(self): self._cancel = True

    def enqueue(self, messages, model, tools, thinking, response_format, cb_stream, cb_done):
        self._queue.put((messages, model, tools, thinking, response_format, cb_stream, cb_done))
        self._process_next()

    def _process_next(self):
        with self._lock:
            if self._busy or self._queue.empty(): return
            self._busy = True
        self._cancel = False
        item = self._queue.get_nowait()
        threading.Thread(target=self._run, args=item, daemon=True).start()

    def _run(self, messages, model, tools, thinking, rf, cb_stream, cb_done):
        result = {"content": "", "tokens": 0, "time": 0, "error": ""}
        start = time.time()
        try:
            for chunk in self._stream(messages, model, tools, thinking, rf):
                if self._cancel:
                    result["error"] = "Cancelled by user"
                    break
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                c = delta.get("content", "")
                if c: result["content"] += c; cb_stream(c)
                r = delta.get("reasoning_content", "")
                if r: result["content"] += r; cb_stream(r)
                u = chunk.get("usage", {})
                if u: result["tokens"] = u.get("total_tokens", 0)
        except Exception as e:
            result["error"] = str(e)
        result["time"] = time.time() - start
        cb_done(result)
        with self._lock: self._busy = False
        self._process_next()

    def _stream(self, messages, model=None, tools=None, thinking=False, rf=None):
        model = model or self.dm.settings.get("model", "glm-4.7-flash")
        key = self.dm.settings.get("api_key", "")
        if not key: raise ValueError("No API key")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        body = {"model": model, "messages": messages, "stream": True,
                "temperature": self.dm.settings.get("temperature", 0.7),
                "max_tokens": self.dm.settings.get("max_tokens", 4096)}
        if tools: body["tools"] = tools
        if thinking: body["thinking"] = {"type": "enabled", "budget_tokens": int(body["max_tokens"] * 0.5)}
        if rf: body["response_format"] = rf
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
        if not dm.settings.get("allow_commands", True): return "Commands disabled in settings."
        if dm.settings.get("confirm_commands", True): return "CONFIRM_REQUIRED:" + args.get("command", "")
        try: return os.popen(args.get("command","")).read()[:5000] or "(no output)"
        except Exception as e: return f"Error: {e}"
    elif name == "list_directory":
        try:
            p = Path(args.get("path", "."))
            items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            return "\n".join(("[D] " + i.name if i.is_dir() else "[F] " + i.name) for i in items[:100])
        except Exception as e: return f"Error: {e}"
    elif name == "search_web": return f"[Search simulated: {args.get('query','')}]"
    elif name == "calculate":
        try:
            if all(c in "0123456789+-*/.() " for c in args.get("expression","")): return str(eval(args["expression"]))
            return "Error: invalid chars"
        except Exception as e: return f"Error: {e}"
    return f"Unknown: {name}"

# ═══════════════════════════════════════════════════════════
#  MENU SCREEN
# ═══════════════════════════════════════════════════════════

class MenuScreen(ModalScreen):
    BINDINGS = [("escape", "close_menu", "Close")]
    def compose(self):
        with Container(id="menu-box"):
            yield Label("JPAI Menu", id="menu-title")
            for label, uid in [("New Chat","new-chat"),("Agent Mode","agent"),("Long Run","long-run"),
                               ("Deep Think","deep-think"),("Vision","vision"),("Quick","quick"),
                               ("Structured","structured"),("File Editor","editor"),("File Upload","upload"),
                               ("History","history"),("Search Chats","search"),("Settings","settings"),("Welcome","welcome")]:
                yield Button(label, classes="menu-btn", id=f"m-{uid}")
    def on_button_pressed(self, event): self.dismiss(event.button.id.replace("m-", ""))
    def action_close_menu(self): self.dismiss("")

# ═══════════════════════════════════════════════════════════
#  CONFIRM DIALOG
# ═══════════════════════════════════════════════════════════

class ConfirmDialog(ModalScreen):
    def __init__(self, msg, cmd=""):
        super().__init__(); self.msg = msg; self.cmd = cmd
    def compose(self):
        with Container(id="confirm-box"):
            yield Label("Confirm Action", id="confirm-title")
            yield Static(self.msg, id="confirm-msg")
            if self.cmd: yield Static(f"$ {self.cmd}", id="confirm-cmd")
            with Horizontal():
                yield Button("Allow", variant="success", id="confirm-yes")
                yield Button("Deny", variant="error", id="confirm-no")
    def on_button_pressed(self, event): self.dismiss(event.button.id == "confirm-yes")

# ═══════════════════════════════════════════════════════════
#  FILE EXPLORER
# ═══════════════════════════════════════════════════════════

class FileExplorer(Vertical):
    def __init__(self, dm, **kw):
        super().__init__(**kw)
        self.dm = dm
        self.current_path = Path(dm.settings.get("working_dir", str(Path.home())))

    def compose(self):
        yield Label("Explorer", id="exp-title")
        yield Static(str(self.current_path), id="exp-path")
        with Horizontal():
            yield Button("..", id="exp-up")
            yield Button("Refresh", id="exp-refresh")
        yield Input(placeholder="Go to path...", id="exp-goto")
        yield Button("Go", id="exp-go")
        with VerticalScroll(id="exp-list"): yield Static("")

    def on_mount(self): self._refresh_list()

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "exp-up": self._go_up()
        elif bid == "exp-refresh": self._refresh_list()
        elif bid == "exp-go":
            p = self.query_one("#exp-goto", Input).value.strip()
            if p: self.navigate(p)

    def on_input_submitted(self, event):
        if event.input.id == "exp-goto":
            p = event.input.value.strip()
            if p: self.navigate(p)

    def _go_up(self):
        parent = self.current_path.parent
        if parent != self.current_path:
            self.navigate(str(parent))

    def navigate(self, path_str):
        p = Path(path_str)
        if p.exists() and p.is_dir():
            self.current_path = p
            self.dm.settings["working_dir"] = str(p)
            self.dm.save()
            self._refresh_list()

    def _refresh_list(self):
        try:
            self.query_one("#exp-path", Static).update(str(self.current_path))
            lst = self.query_one("#exp-list", VerticalScroll)
            lst.remove_children()
            items = []
            try:
                entries = sorted(self.current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
                for e in entries[:100]:
                    tag = "[D]" if e.is_dir() else "[F]"
                    btn_id = f"fentry-{e.name}"
                    items.append(Button(f"{tag} {e.name}", classes="file-entry", id=btn_id))
            except PermissionError:
                items.append(Static("(no access)"))
            for w in items: lst.mount(w)
        except: pass

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid and bid.startswith("fentry-"):
            name = bid[7:]
            target = self.current_path / name
            if target.is_dir():
                self.navigate(str(target))
            else:
                # Open file in editor tab
                try:
                    app = self.app
                    main = app.query_one("#main-screen", MainScreen)
                    main.open_editor_tab(str(target))
                except: pass
        elif bid == "exp-up": self._go_up()
        elif bid == "exp-refresh": self._refresh_list()
        elif bid == "exp-go":
            p = self.query_one("#exp-goto", Input).value.strip()
            if p: self.navigate(p)

# ═══════════════════════════════════════════════════════════
#  CHAT SESSION
# ═══════════════════════════════════════════════════════════

class ChatSession:
    def __init__(self, mode="Chat", cid=None):
        self.id = cid or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.mode = mode
        self.messages = []
        self.title = "New Chat"
        self.model = "glm-4.7-flash"

# ═══════════════════════════════════════════════════════════
#  TAB SYSTEM
# ═══════════════════════════════════════════════════════════

class TabInfo:
    def __init__(self, tid, ttype, title, session=None):
        self.id = tid
        self.type = ttype  # "chat", "settings", "history", "editor", "welcome", "upload"
        self.title = title
        self.session = session  # ChatSession if type=="chat"

# ═══════════════════════════════════════════════════════════
#  MAIN SCREEN
# ═══════════════════════════════════════════════════════════

class MainScreen(Screen):
    BINDINGS = [
        Binding("ctrl+n", "new_chat", "New"),
        Binding("ctrl+m", "menu", "Menu"),
    ]

    def __init__(self, dm, api):
        super().__init__()
        self.dm = dm
        self.api = api
        self.tabs = []
        self.active_tab = None
        self._tab_counter = 0
        self._stream_widget = None
        self._streaming = False

    def compose(self):
        # Top bar
        with Horizontal(id="top-bar"):
            yield Label("JPAI", id="app-label")
            yield Static("", id="top-spacer")
            yield Label("", id="model-label")
            yield Label("", id="queue-label")
            yield Button("Menu", id="btn-menu", classes="top-btn")
            yield Button("New", id="btn-new", classes="top-btn")
            yield Button("Stop", id="btn-stop", classes="top-btn")

        # Tab bar
        with Horizontal(id="tab-bar"):
            yield Static("", id="tab-bar-inner")
            yield Button("+", variant="success", id="btn-add-tab")

        # Main area: left | center | right
        with Horizontal(id="main-area"):
            with Vertical(id="left-panel"):
                yield Label("Mode", classes="panel-head")
                yield Select([(m, m) for m in MODES], value="Chat", id="mode-select")
                yield Label("Folder", classes="panel-head")
                yield Static(self.dm.settings.get("working_dir", "-"), id="folder-display")
                yield Label("Properties", classes="panel-head")
                yield Static("Ready", id="props-display")
                yield Label("Actions", classes="panel-head")
                yield Button("Paste to Input", id="btn-paste-input")
                yield Button("Upload File", id="btn-upload")

            with VerticalScroll(id="center-panel"):
                yield Label("Welcome to JPAI", id="center-placeholder")

            with Vertical(id="right-panel"):
                yield FileExplorer(self.dm)

        # Status bar
        with Horizontal(id="status-bar"):
            yield Label("JPAI Agentic AI by JeelanPro(TM) AI team", id="status-left")
            yield Static("", id="status-right")

    def on_mount(self):
        self.query_one("#model-label", Label).update(self.dm.settings.get("model", "glm-4.7-flash"))
        # Add welcome tab
        self._add_tab("welcome", "Welcome")

    # ── Tab management ──

    def _add_tab(self, ttype, title, session=None):
        self._tab_counter += 1
        tab = TabInfo(f"tab-{self._tab_counter}", ttype, title, session)
        self.tabs.append(tab)
        self._render_tab_bar()
        self._switch_to_tab(tab)
        return tab

    def _close_tab(self, tab_id):
        self.tabs = [t for t in self.tabs if t.id != tab_id]
        if not self.tabs:
            self._add_tab("welcome", "Welcome")
        elif self.active_tab and self.active_tab.id == tab_id:
            self._switch_to_tab(self.tabs[-1])
        self._render_tab_bar()

    def _switch_to_tab(self, tab):
        self.active_tab = tab
        self._render_tab_bar()
        self._render_active_tab()

    def _render_tab_bar(self):
        try:
            parts = []
            for t in self.tabs:
                marker = ">" if t == self.active_tab else " "
                parts.append(f"[{marker}{t.title[:16]}]")
            self.query_one("#tab-bar-inner", Static).update("  ".join(parts))
        except: pass

    def _render_active_tab(self):
        if not self.active_tab: return
        center = self.query_one("#center-panel", VerticalScroll)
        center.remove_children()

        tab = self.active_tab
        if tab.type == "welcome":
            center.mount(self._make_welcome())
        elif tab.type == "chat":
            center.mount(self._make_chat(tab))
        elif tab.type == "settings":
            center.mount(self._make_settings())
        elif tab.type == "history":
            center.mount(self._make_history())
        elif tab.type == "editor":
            center.mount(self._make_editor())
        elif tab.type == "upload":
            center.mount(self._make_upload())

    # ── Welcome panel ──

    def _make_welcome(self):
        w = Vertical()
        w.mount(Label("JPAI Agentic AI", id="w-title"))
        w.mount(Label("by JeelanPro(TM) AI team", id="w-sub"))
        w.mount(Static(""))
        w.mount(Label("Quick Start:"))
        w.mount(Static("  - Click Menu or Ctrl+M to open modes"))
        w.mount(Static("  - Click + or Ctrl+N for new chat"))
        w.mount(Static("  - Set working folder in Explorer (right panel)"))
        w.mount(Static("  - Configure API key in Settings"))
        w.mount(Static(""))
        w.mount(Label("Free Models:"))
        w.mount(Static("  - glm-4.7-flash  Fast all-rounder"))
        w.mount(Static("  - glm-4.5-flash  Lightweight"))
        w.mount(Static("  - glm-4.6v-flash Vision"))
        w.mount(Static(""))
        w.mount(Label("Modes:"))
        w.mount(Static("  Chat | Agent | Long Run | Deep Think | Vision | Quick | Structured"))
        return w

    # ── Chat panel ──

    def _make_chat(self, tab):
        w = Vertical()
        s = tab.session

        # Messages area
        scroll = VerticalScroll(id="chat-msgs")
        if s.messages:
            for m in s.messages:
                role = m.get("role", "user")
                content = m.get("content", "")
                if role == "system": continue
                meta = ""
                if "gen_time" in m: meta = f" {m['gen_time']:.1f}s | {m.get('tokens',0)} tok"
                label = f"You: {content[:80]}" if role == "user" else f"AI:{meta}"
                col = Collapsible(Static(content), title=label, collapsed=(role=="user" and len(content)>100))
                col.add_class(f"msg-{role}")
                scroll.mount(col)
        else:
            scroll.mount(Static("Send a message to start.", id="chat-empty-msg"))

        # Input area
        inp_area = Vertical(id="chat-input-area")
        inp_area.mount(Input(placeholder="Type message, Enter to send...", id="chat-input"))
        btn_row = Horizontal(id="chat-btns")
        btn_row.mount(Button("Send", variant="primary", id="btn-send"))
        btn_row.mount(Button("Stop", variant="error", id="btn-stop-chat"))
        btn_row.mount(Button("Rerun", id="btn-rerun"))
        btn_row.mount(Button("Delete Last", id="btn-delete"))
        btn_row.mount(Button("Edit Last", id="btn-edit"))
        btn_row.mount(Button("Continue", id="btn-continue"))
        btn_row.mount(Button("Copy AI", id="btn-copy-ai"))
        btn_row.mount(Button("Paste", id="btn-paste-chat"))
        btn_row.mount(Label("", id="chat-status"))
        inp_area.mount(btn_row)

        w.mount(scroll)
        w.mount(inp_area)
        return w

    # ── Settings panel ──

    def _make_settings(self):
        w = VerticalScroll()
        w.mount(Label("API Key", classes="panel-head"))
        w.mount(Input(placeholder="API key...", id="s-key", password=True, value=self.dm.settings.get("api_key","")))
        btns = Horizontal()
        btns.mount(Button("Paste", variant="primary", id="s-paste"))
        btns.mount(Button("Load File", id="s-load"))
        btns.mount(Button("Toggle", id="s-toggle"))
        btns.mount(Button("Save", variant="success", id="s-save"))
        w.mount(btns)
        w.mount(Static("", id="s-status"))

        w.mount(Label("Model", classes="panel-head"))
        w.mount(Select([(m,m) for m in FREE_MODELS], value=self.dm.settings.get("model","glm-4.7-flash"), id="s-model"))

        w.mount(Label("Temperature", classes="panel-head"))
        w.mount(Input(value=str(self.dm.settings.get("temperature",0.7)), id="s-temp"))
        w.mount(Label("Max Tokens", classes="panel-head"))
        w.mount(Input(value=str(self.dm.settings.get("max_tokens",4096)), id="s-tokens"))

        w.mount(Label("Security", classes="panel-head"))
        w.mount(Label("Allow commands:"))
        w.mount(Switch(value=self.dm.settings.get("allow_commands",True), id="s-allow-cmd"))
        w.mount(Label("Confirm commands:"))
        w.mount(Switch(value=self.dm.settings.get("confirm_commands",True), id="s-confirm-cmd"))

        w.mount(Label("System Prompts", classes="panel-head"))
        w.mount(Select([(k,k) for k in SYSTEM_PROMPTS], value="Chat", id="s-pmode"))
        w.mount(Button("Load", id="s-pload"))
        w.mount(TextArea(id="s-peditor"))
        btns2 = Horizontal()
        btns2.mount(Button("Save", variant="success", id="s-psave"))
        btns2.mount(Button("Reset", id="s-preset"))
        w.mount(btns2)

        w.mount(Label("Tools (JSON)", classes="panel-head"))
        w.mount(TextArea(json.dumps(self.dm.tools, indent=2), id="s-tools"))
        w.mount(Button("Save Tools", variant="success", id="s-save-tools"))

        # Init values
        def _init():
            try:
                k = self.dm.settings.get("api_key","")
                w.query_one("#s-status", Static).update(f"Key: {'set' if k else 'NOT SET'} ({len(k)} chars)")
                w.query_one("#s-peditor", TextArea).text = self.dm.get_prompt("Chat")
            except: pass
        self.set_timer(0.1, _init)
        return w

    # ── History panel ──

    def _make_history(self):
        w = VerticalScroll()
        w.mount(Label("Chat History", classes="panel-head"))
        w.mount(Input(placeholder="Search...", id="h-search"))
        w.mount(Button("Search", id="h-do-search"))
        w.mount(Button("Refresh", id="h-refresh"))
        w.mount(Button("Clear All", variant="error", id="h-clear"))
        with VerticalScroll(id="h-list-inner"): pass

        def _load():
            try: self._render_history_list(w)
            except: pass
        self.set_timer(0.1, _load)
        return w

    def _render_history_list(self, parent_widget, query=""):
        try:
            lst = parent_widget.query_one("#h-list-inner", VerticalScroll)
            lst.remove_children()
            chats = self.dm.list_chats()
            if query:
                q = query.lower()
                chats = [c for c in chats if any(q in m.get("content","").lower() for m in c.get("messages",[]))]
            if not chats:
                lst.mount(Static("No chats found."))
                return
            for c in chats[:30]:
                ts = c.get("ts","?"); mode = c.get("mode","?"); n = len(c.get("messages",[]))
                preview = ""
                for m in c.get("messages",[]):
                    if m.get("role")=="user":
                        txt = m.get("content","")
                        if isinstance(txt,str): preview = txt[:60]
                        break
                lst.mount(Static(f"{ts} | {mode} | {n} msgs\n  \"{preview}\""))
        except: pass

    # ── Editor panel ──

    def _make_editor(self):
        w = Vertical()
        w.mount(Label("File Editor", classes="panel-head"))
        w.mount(Input(placeholder="File path...", id="e-path"))
        btns = Horizontal()
        btns.mount(Button("Open", id="e-open"))
        btns.mount(Button("Save", variant="success", id="e-save"))
        btns.mount(Button("Copy All", id="e-copy"))
        btns.mount(Button("AI Review", variant="primary", id="e-ai"))
        w.mount(btns)
        w.mount(TextArea(id="e-content"))
        return w

    # ── Upload panel ──

    def _make_upload(self):
        w = Vertical()
        w.mount(Label("Upload File as Context", classes="panel-head"))
        w.mount(Static("Enter a file path. Its content will be added to your next chat message."))
        w.mount(Input(placeholder="File path...", id="u-path"))
        w.mount(Button("Read File", variant="primary", id="u-read"))
        w.mount(Static("", id="u-preview"))
        w.mount(Button("Send to Chat", variant="success", id="u-send"))
        return w

    # ── Button handler ──

    def on_button_pressed(self, event):
        bid = event.button.id

        # Top bar
        if bid == "btn-menu": self._open_menu()
        elif bid == "btn-new": self._new_chat()
        elif bid == "btn-stop": self.api.cancel()

        # Tab bar
        elif bid == "btn-add-tab": self._open_menu()

        # Left panel
        elif bid == "btn-paste-input":
            clip = read_clipboard()
            if clip and self.active_tab and self.active_tab.type == "chat":
                try: self.query_one("#chat-input", Input).value = clip
                except: pass
        elif bid == "btn-upload":
            self._add_tab("upload", "Upload")

        # Chat buttons
        elif bid == "btn-send": self._chat_send()
        elif bid == "btn-stop-chat": self.api.cancel()
        elif bid == "btn-rerun": self._chat_rerun()
        elif bid == "btn-delete": self._chat_delete()
        elif bid == "btn-edit": self._chat_edit()
        elif bid == "btn-continue": self._chat_continue()
        elif bid == "btn-copy-ai": self._chat_copy()
        elif bid == "btn-paste-chat":
            clip = read_clipboard()
            if clip:
                try: self.query_one("#chat-input", Input).value = clip
                except: pass

        # Settings buttons
        elif bid == "s-paste":
            c = read_clipboard()
            if c:
                try:
                    self.query_one("#s-key", Input).value = c
                    self.dm.set_api_key(c)
                    self.query_one("#s-status", Static).update(f"Key: set ({len(c)} chars)")
                except: pass
        elif bid == "s-load":
            if API_KEY_FILE.exists():
                try:
                    k = API_KEY_FILE.read_text(encoding="utf-8").strip()
                    if k:
                        self.query_one("#s-key", Input).value = k
                        self.dm.set_api_key(k)
                        self.query_one("#s-status", Static).update(f"Key: set ({len(k)} chars)")
                except: pass
        elif bid == "s-toggle":
            i = self.query_one("#s-key", Input); i.password = not i.password
        elif bid == "s-save":
            k = self.query_one("#s-key", Input).value.strip()
            self.dm.set_api_key(k)
            self.query_one("#s-status", Static).update(f"Key: {'set' if k else 'NOT SET'} ({len(k)} chars)")
        elif bid == "s-pload":
            mode = str(self.query_one("#s-pmode", Select).value)
            self.query_one("#s-peditor", TextArea).text = self.dm.get_prompt(mode)
        elif bid == "s-psave":
            mode = str(self.query_one("#s-pmode", Select).value)
            if "system_prompts" not in self.dm.settings: self.dm.settings["system_prompts"] = {}
            self.dm.settings["system_prompts"][mode] = self.query_one("#s-peditor", TextArea).text
            self.dm.save()
        elif bid == "s-preset":
            mode = str(self.query_one("#s-pmode", Select).value)
            self.query_one("#s-peditor", TextArea).text = SYSTEM_PROMPTS.get(mode,"")
        elif bid == "s-save-tools":
            try:
                self.dm.tools = json.loads(self.query_one("#s-tools", TextArea).text)
                self.dm.save_tools()
            except: pass

        # History buttons
        elif bid == "h-refresh":
            try: self._render_history_list(self.query_one("#center-panel", VerticalScroll))
            except: pass
        elif bid == "h-clear":
            for c in self.dm.list_chats(): self.dm.delete_chat(c.get("id",""))
            try: self._render_history_list(self.query_one("#center-panel", VerticalScroll))
            except: pass
        elif bid == "h-do-search":
            try:
                q = self.query_one("#h-search", Input).value.strip()
                self._render_history_list(self.query_one("#center-panel", VerticalScroll), q)
            except: pass

        # Editor buttons
        elif bid == "e-open": self._editor_open()
        elif bid == "e-save": self._editor_save()
        elif bid == "e-copy":
            try: write_clipboard(self.query_one("#e-content", TextArea).text)
            except: pass
        elif bid == "e-ai": self._editor_ai()

        # Upload buttons
        elif bid == "u-read": self._upload_read()
        elif bid == "u-send": self._upload_send()

    def on_input_submitted(self, event):
        if event.input.id == "chat-input":
            self._chat_send()

    def on_switch_changed(self, event):
        if event.switch.id == "s-allow-cmd": self.dm.settings["allow_commands"] = event.value; self.dm.save()
        elif event.switch.id == "s-confirm-cmd": self.dm.settings["confirm_commands"] = event.value; self.dm.save()

    def on_select_changed(self, event):
        if event.select.id == "s-model": self.dm.settings["model"] = str(event.value); self.dm.save()
        elif event.select.id == "mode-select":
            if self.active_tab and self.active_tab.session:
                self.active_tab.session.mode = str(event.value)

    # ── Menu ──

    def _open_menu(self):
        def handle(result):
            if not result: return
            mode_map = {"new-chat":"Chat","agent":"Agent","long-run":"Long Run",
                        "deep-think":"Deep Think","vision":"Vision","quick":"Quick","structured":"Structured"}
            if result in mode_map:
                self._new_chat(mode_map[result])
            elif result == "settings": self._add_tab("settings", "Settings")
            elif result == "history": self._add_tab("history", "History")
            elif result == "editor": self._add_tab("editor", "Editor")
            elif result == "upload": self._add_tab("upload", "Upload")
            elif result == "welcome": self._add_tab("welcome", "Welcome")
            elif result == "search": self._add_tab("history", "Search")
        self.app.push_screen(MenuScreen(), handle)

    def _new_chat(self, mode="Chat"):
        s = ChatSession(mode)
        s.model = self.dm.settings.get("model", "glm-4.7-flash")
        tab = self._add_tab("chat", f"Chat {len(self.tabs)}", s)

    # ── Chat actions ──

    def _get_session(self):
        if self.active_tab and self.active_tab.type == "chat" and self.active_tab.session:
            return self.active_tab.session
        return None

    def _chat_send(self):
        s = self._get_session()
        if not s or self._streaming: return
        try: text = self.query_one("#chat-input", Input).value.strip()
        except: return
        if not text: return
        self.query_one("#chat-input", Input).value = ""
        s.messages.append({"role": "user", "content": text})
        if len(s.messages) <= 2: s.title = text[:20]; self._render_tab_bar()
        self._add_msg_to_ui("user", text)
        self._generate(s)

    def _chat_rerun(self):
        s = self._get_session()
        if not s or self._streaming: return
        while s.messages and s.messages[-1].get("role") == "assistant":
            s.messages.pop()
        self._rebuild_chat_ui(s)
        if s.messages: self._generate(s)

    def _chat_delete(self):
        s = self._get_session()
        if not s: return
        if s.messages: s.messages.pop()
        self._rebuild_chat_ui(s)

    def _chat_edit(self):
        s = self._get_session()
        if not s: return
        if s.messages and s.messages[-1].get("role") == "user":
            last = s.messages.pop()
            try: self.query_one("#chat-input", Input).value = last.get("content","")
            except: pass
            self._rebuild_chat_ui(s)

    def _chat_continue(self):
        """Re-send entire conversation without adding a new user message."""
        s = self._get_session()
        if not s or self._streaming: return
        if not s.messages: return
        self._generate(s)

    def _chat_copy(self):
        s = self._get_session()
        if not s: return
        for m in reversed(s.messages):
            if m.get("role") == "assistant":
                write_clipboard(m.get("content",""))
                break

    def _add_msg_to_ui(self, role, content, meta=""):
        try:
            scroll = self.query_one("#chat-msgs", VerticalScroll)
            # Remove placeholder
            try: self.query_one("#chat-empty-msg", Static).remove()
            except: pass
            label = f"You: {content[:80]}" if role == "user" else f"AI:{meta}"
            col = Collapsible(Static(content), title=label, collapsed=(role=="user" and len(content)>100))
            col.add_class(f"msg-{role}")
            scroll.mount(col)
            scroll.scroll_end(animate=False)
        except: pass

    def _rebuild_chat_ui(self, s):
        try:
            scroll = self.query_one("#chat-msgs", VerticalScroll)
            scroll.remove_children()
            for m in s.messages:
                role = m.get("role","user"); content = m.get("content","")
                if role == "system": continue
                meta = ""
                if "gen_time" in m: meta = f" {m['gen_time']:.1f}s | {m.get('tokens',0)} tok"
                label = f"You: {content[:80]}" if role == "user" else f"AI:{meta}"
                col = Collapsible(Static(content), title=label, collapsed=(role=="user" and len(content)>100))
                col.add_class(f"msg-{role}")
                scroll.mount(col)
            scroll.scroll_end(animate=False)
        except: pass

    def _generate(self, session):
        self._streaming = True
        self._stream_text = ""

        api_msgs = []
        prompt = self.dm.get_prompt(session.mode)
        if prompt: api_msgs.append({"role": "system", "content": prompt})
        wd = self.dm.settings.get("working_dir","")
        if wd: api_msgs.append({"role": "system", "content": f"Working directory: {wd}"})
        api_msgs.extend(session.messages)

        model = session.model
        if session.mode == "Vision": model = "glm-4.6v-flash"
        elif session.mode == "Quick": model = "glm-4.5-flash"

        tools = self.dm.tools if session.mode in ("Agent","Chat") else None
        thinking = session.mode == "Deep Think"
        rf = {"type": "json_object"} if session.mode == "Structured" else None

        def on_stream(text):
            self._stream_text += text
            try:
                scroll = self.query_one("#chat-msgs", VerticalScroll)
                if not self._stream_widget:
                    self._stream_widget = Static("", id="stream-out")
                    scroll.mount(self._stream_widget)
                self._stream_widget.update(self._stream_text)
                scroll.scroll_end(animate=False)
            except: pass

        def on_done(result):
            self._streaming = False
            # Remove stream widget
            try: self.query_one("#stream-out", Static).remove()
            except: pass
            self._stream_widget = None

            if result.get("error"):
                session.messages.append({"role": "assistant", "content": f"Error: {result['error']}"})
                self._add_msg_to_ui("assistant", f"Error: {result['error']}")
            else:
                meta = f" {result['time']:.1f}s | {result['tokens']} tok"
                session.messages.append({
                    "role": "assistant", "content": result["content"],
                    "gen_time": result["time"], "tokens": result["tokens"],
                })
                self._add_msg_to_ui("assistant", result["content"], meta)

            self.dm.save_chat(session.id, session.messages, session.mode, session.model)
            try: self.query_one("#chat-status", Label).update("Ready")
            except: pass

        try: self.query_one("#chat-status", Label).update("Generating...")
        except: pass
        self.api.enqueue(api_msgs, model, tools, thinking, rf, on_stream, on_done)

    # ── Editor ──

    def _editor_open(self):
        try:
            path = self.query_one("#e-path", Input).value.strip()
            if path:
                content = Path(path).read_text(encoding="utf-8")
                self.query_one("#e-content", TextArea).text = content
        except Exception as e:
            self.query_one("#e-content", TextArea).text = f"Error: {e}"

    def _editor_save(self):
        try:
            path = self.query_one("#e-path", Input).value.strip()
            if path:
                Path(path).write_text(self.query_one("#e-content", TextArea).text, encoding="utf-8")
        except: pass

    def _editor_ai(self):
        try:
            content = self.query_one("#e-content", TextArea).text
            if content and self.active_tab and self.active_tab.session:
                self.query_one("#chat-input", Input).value = f"Review and improve:\n```\n{content[:2000]}\n```"
        except: pass

    def open_editor_tab(self, filepath):
        tab = self._add_tab("editor", Path(filepath).name)
        def _init():
            try:
                self.query_one("#e-path", Input).value = filepath
                content = Path(filepath).read_text(encoding="utf-8")
                self.query_one("#e-content", TextArea).text = content
            except: pass
        self.set_timer(0.2, _init)

    # ── Upload ──

    def _upload_read(self):
        try:
            path = self.query_one("#u-path", Input).value.strip()
            if path:
                content = Path(path).read_text(encoding="utf-8")
                self.query_one("#u-preview", Static).update(content[:2000] + ("..." if len(content)>2000 else ""))
        except Exception as e:
            self.query_one("#u-preview", Static).update(f"Error: {e}")

    def _upload_send(self):
        try:
            path = self.query_one("#u-path", Input).value.strip()
            if not path: return
            content = Path(path).read_text(encoding="utf-8")
            # Create new chat with file context
            s = ChatSession("Chat")
            s.model = self.dm.settings.get("model", "glm-4.7-flash")
            s.messages.append({"role": "user", "content": f"Here is a file for context ({path}):\n```\n{content[:6000]}\n```\n\nPlease review and be ready for questions about it."})
            s.title = Path(path).name
            tab = self._add_tab("chat", s.title, s)
            self._generate(s)
        except Exception as e:
            try: self.query_one("#u-preview", Static).update(f"Error: {e}")
            except: pass

    # ── Actions ──

    def action_new_chat(self): self._new_chat()
    def action_menu(self): self._open_menu()

# ═══════════════════════════════════════════════════════════
#  LOADING SCREEN
# ═══════════════════════════════════════════════════════════

class LoadingScreen(Screen):
    BINDINGS = []
    _frame = reactive(0)
    def compose(self):
        with Container(id="load-center"):
            yield Label("JPAI", id="load-title")
            yield Label("Agentic AI", id="load-sub")
            yield Label("by JeelanPro(TM) AI team", id="load-team")
            yield Static("", id="load-spin")
            yield Label("Initializing...", id="load-msg")
    def on_mount(self):
        self._step = 0
        self._msgs = ["Loading models...", "Preparing...", "Ready."]
        self._timer = self.set_interval(0.5, self._tick)
    def _tick(self):
        self._step += 1
        frames = ["|", "/", "-", "\\"]
        self.query_one("#load-spin", Static).update(frames[self._step % 4])
        if self._step <= len(self._msgs):
            self.query_one("#load-msg", Label).update(self._msgs[min(self._step-1, len(self._msgs)-1)])
        if self._step >= len(self._msgs) + 1:
            self._timer.stop()
            try: self.app._show_main()
            except: pass

# ═══════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════

class JPAIApp(App):
    TITLE = "JPAI"
    CSS = """
    Screen { background: #1a1210; }
    #load-center { align: center middle; height: 100%; }
    #load-title { text-align: center; color: #d97757; text-style: bold; margin: 1; }
    #load-sub { text-align: center; color: #e8956a; margin: 0; }
    #load-team { text-align: center; color: #8a7568; margin: 1; }
    #load-spin { text-align: center; color: #d97757; }
    #load-msg { text-align: center; color: #8a7568; }

    #menu-box { background: #241c18; border: thick #3d2e25; padding: 1; width: 36; height: auto; }
    #menu-title { color: #d97757; text-style: bold; margin: 0 0 0 1; }
    .menu-btn { width: 100%; margin: 0; background: #2d2420; color: #e8d5c4; }
    .menu-btn:hover { background: #3d2e25; }

    #confirm-box { background: #241c18; border: thick #e85d5d; padding: 1; width: 50; }
    #confirm-title { color: #e85d5d; text-style: bold; }
    #confirm-msg { color: #e8d5c4; }
    #confirm-cmd { color: #e8956a; background: #2d2420; padding: 1; }

    #top-bar { background: #1a1210; height: 3; padding: 0 1; border-bottom: solid #3d2e25; }
    #app-label { color: #d97757; text-style: bold; width: 6; }
    #top-spacer { width: 1fr; }
    #model-label { color: #8a7568; width: 18; }
    #queue-label { color: #d97757; width: 4; }
    .top-btn { background: #2d2420; color: #d97757; min-width: 6; margin: 0 0 0 1; }
    .top-btn:hover { background: #3d2e25; }

    #tab-bar { background: #1a1210; height: 3; padding: 0 1; border-bottom: solid #3d2e25; }
    #tab-bar-inner { color: #e8956a; width: 1fr; }
    #btn-add-tab { min-width: 3; }

    #main-area { height: 1fr; }

    #left-panel { width: 20; background: #1a1210; border-right: solid #3d2e25; padding: 1; }
    .panel-head { color: #d97757; text-style: bold; margin: 1 0 0 0; }
    #folder-display { color: #8a7568; }

    #center-panel { width: 1fr; background: #1a1210; }
    #center-placeholder { color: #8a7568; text-align: center; padding: 4; }
    #w-title { color: #d97757; text-style: bold; text-align: center; margin: 1; }
    #w-sub { color: #e8956a; text-align: center; }

    #right-panel { width: 24; background: #1a1210; border-left: solid #3d2e25; padding: 1; }
    #exp-title { color: #d97757; text-style: bold; }
    #exp-path { color: #8a7568; margin: 0 0 0 1; }
    .file-entry { width: 100%; margin: 0; background: #2d2420; color: #e8d5c4; }
    .file-entry:hover { background: #3d2e25; }

    #chat-msgs { height: 1fr; background: #130e0c; }
    #chat-empty-msg { color: #8a7568; text-align: center; padding: 4; }
    #chat-input-area { height: auto; background: #1a1210; border-top: solid #3d2e25; padding: 1; }
    #chat-input { width: 100%; margin: 0 0 0 1; background: #2d2420; }
    #chat-btns { height: auto; }
    #chat-btns Button { margin: 0 1 0 0; min-width: 5; background: #2d2420; color: #e8956a; }
    #chat-btns Button:hover { background: #3d2e25; }
    #chat-status { color: #d97757; width: 16; }

    .msg-user { color: #e8d5c4; background: #2d2420; padding: 1; margin: 1 2; border-left: thick #d97757; }
    .msg-assistant { color: #e8d5c4; background: #241c18; padding: 1; margin: 1 2; border-left: thick #8a7568; }

    #status-bar { background: #130e0c; height: 1; padding: 0 1; }
    #status-left { color: #5a4a3e; width: 1fr; }
    #status-right { color: #8a7568; width: 30; }

    Switch { margin: 0 0 0 1; }
    Select { margin: 0 0 0 1; }
    Input { margin: 0 0 0 1; }
    TextArea { margin: 0 0 0 1; }
    Label { margin: 0; color: #e8d5c4; }
    Static { color: #e8d5c4; }
    Button { margin: 0 0 0 1; }
    """

    def __init__(self, dm):
        super().__init__()
        self.dm = dm
        self.api = ZhipuClient(dm)

    def on_mount(self):
        self.push_screen(LoadingScreen())

    def _show_main(self):
        try: self.pop_screen()
        except: pass
        main = MainScreen(self.dm, self.api)
        main.id = "main-screen"
        self.push_screen(main)

# ═══════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════

def startup_check(dm):
    key = dm.settings.get("api_key","")
    if key and len(key) > 10: return
    print()
    print("  JPAI Agentic AI - by JeelanPro(TM) AI team")
    print("  No API key found. Paste it here (Ctrl+V works).")
    print("  Or press Enter to skip and set later in Settings.")
    print()
    try: api_key = input("  API key: ").strip()
    except: api_key = ""
    if api_key and len(api_key) > 10:
        dm.set_api_key(api_key)
        print(f"  Saved ({len(api_key)} chars)")
        time.sleep(1)
    else:
        print("  Set it later in Settings.")
        time.sleep(2)

if __name__ == "__main__":
    dm = DataManager()
    startup_check(dm)
    JPAIApp(dm).run()