#!/usr/bin/env python3
"""
JPAI Agentic AI by JeelanPro™ AI Team
Modern IDE-style Terminal AI Assistant · Powered by ZhipuAI GLM Models

Run:  python.exe JPAI1.py
"""

import os
import sys
import json
import time
import subprocess
import threading
import queue
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any, Generator, Dict, List
from collections import deque
import base64

import httpx
import rich.markdown

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, TabbedContent, TabPane,
    Input, Button, Static, Collapsible,
    RichLog, Select, TextArea,
    Label, DirectoryTree, Tree, LoadingIndicator,
    ContentSwitcher, ProgressBar, Switch,
    DataTable, OptionList,
)
from textual.containers import (
    Container, Horizontal, Vertical, VerticalScroll, HorizontalScroll,
    Grid, ScrollableContainer,
)
from textual.reactive import reactive
from textual import work
from textual.binding import Binding
from textual.screen import ModalScreen, Screen
from textual.message import Message
from textual.css.query import NoMatches


# ═══════════════════════════════════════════════════════════
#  PATHS & CONSTANTS
# ═══════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "Data"
CHAT_DIR = DATA_DIR / "chats"
PROJECTS_DIR = DATA_DIR / "projects"
SETTINGS_PATH = DATA_DIR / "settings.json"
TOOLS_PATH = DATA_DIR / "tools.json"
API_KEY_FILE = DATA_DIR / "api_key.txt"

DATA_DIR.mkdir(exist_ok=True)
CHAT_DIR.mkdir(exist_ok=True)
PROJECTS_DIR.mkdir(exist_ok=True)

BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"

# Only free models with 1 request at a time
MODELS = [
    ("glm-4.5-flash", "GLM 4.5 Flash (Fast)"),
    ("glm-4.7-flash", "GLM 4.7 Flash (Balanced)"),
    ("glm-4.6v-flash", "GLM 4.6V Flash (Vision)"),
]

DURATION_OPTIONS = [
    "1 min", "2 min", "5 min", "10 min",
    "15 min", "20 min", "30 min", "45 min", "60 min",
]


# ═══════════════════════════════════════════════════════════
#  CLIPBOARD HELPER
# ═══════════════════════════════════════════════════════════

def read_clipboard() -> str:
    try:
        result = subprocess.run(
            ["powershell", "-command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def write_clipboard(text: str):
    try:
        subprocess.run(
            ["powershell", "-command", f"Set-Clipboard -Value '{text.replace(chr(39), chr(39)+chr(39))}'"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════
#  SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════

DEFAULT_SYSTEM_PROMPTS = {
    "default": (
        "You are JPAI Agentic AI, a helpful, knowledgeable, and honest assistant developed by JeelanPro™ AI Team. "
        "You respond clearly and concisely. When the user asks for code, "
        "you provide working examples with brief explanations. You admit "
        "when you do not know something rather than guessing. You format "
        "your responses using markdown for readability. "
        "You can execute commands when asked, but always ask for confirmation first."
    ),
}

DEFAULT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web for information about a topic",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from disk",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The file path to read"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file on disk",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The file path to write"},
                    "content": {"type": "string", "description": "The content to write"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command and return its output. ALWAYS ask for user confirmation before executing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a mathematical expression",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "The mathematical expression to evaluate"}
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories in a given path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The directory path to list"}
                },
                "required": ["path"]
            }
        }
    },
]


# ═══════════════════════════════════════════════════════════
#  DATA MANAGER
# ═══════════════════════════════════════════════════════════

class DataManager:
    def __init__(self):
        self.settings = self._load_json(SETTINGS_PATH, {
            "api_key": "",
            "model": "glm-4.7-flash",
            "temperature": 0.7,
            "max_tokens": 4096,
            "system_prompts": DEFAULT_SYSTEM_PROMPTS,
            "allow_command_execution": True,
            "project_path": "",
        })
        self.tools = self._load_json(TOOLS_PATH, DEFAULT_TOOLS)

        if not self.settings.get("api_key"):
            if API_KEY_FILE.exists():
                try:
                    key = API_KEY_FILE.read_text(encoding="utf-8").strip()
                    if key and len(key) > 10:
                        self.settings["api_key"] = key
                        self.save_settings()
                except Exception:
                    pass
            if not self.settings.get("api_key"):
                env_key = os.environ.get("ZHIPUAI_API_KEY", "")
                if env_key and len(env_key) > 10:
                    self.settings["api_key"] = env_key
                    self.save_settings()

    def _load_json(self, path: Path, default: Any) -> Any:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return default
        return default

    def _save_json(self, path: Path, data: Any):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save_settings(self):
        self._save_json(SETTINGS_PATH, self.settings)

    def save_tools(self):
        self._save_json(TOOLS_PATH, self.tools)

    def get_system_prompt(self, mode: str) -> str:
        prompts = self.settings.get("system_prompts", {})
        return prompts.get(mode, DEFAULT_SYSTEM_PROMPTS.get(mode, ""))

    def set_system_prompt(self, mode: str, prompt: str):
        if "system_prompts" not in self.settings:
            self.settings["system_prompts"] = {}
        self.settings["system_prompts"][mode] = prompt
        self.save_settings()

    def set_api_key(self, key: str):
        key = key.strip()
        self.settings["api_key"] = key
        self.save_settings()
        try:
            API_KEY_FILE.write_text(key, encoding="utf-8")
        except Exception:
            pass

    def save_chat(self, chat_id: str, messages: list, title: str = "", project_path: str = ""):
        entry = {
            "id": chat_id,
            "title": title or f"Chat {chat_id[:8]}",
            "project_path": project_path,
            "timestamp": datetime.now().isoformat(),
            "messages": messages,
        }
        self._save_json(CHAT_DIR / f"{chat_id}.json", entry)

    def list_chats(self) -> list:
        chats = []
        for path in CHAT_DIR.glob("*.json"):
            try:
                data = self._load_json(path, None)
                if data:
                    chats.append(data)
            except Exception:
                pass
        chats.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return chats

    def delete_chat(self, chat_id: str):
        path = CHAT_DIR / f"{chat_id}.json"
        if path.exists():
            path.unlink()

    def load_chat(self, chat_id: str) -> Optional[dict]:
        path = CHAT_DIR / f"{chat_id}.json"
        return self._load_json(path, None)


# ═══════════════════════════════════════════════════════════
#  API CLIENT — HTTPX DIRECT
# ═══════════════════════════════════════════════════════════

class ZhipuClient:
    def __init__(self, data_manager: DataManager):
        self.dm = data_manager

    def chat_stream(
        self, messages: list, model: str = None,
        temperature: float = None, max_tokens: int = None,
        tools: list = None, thinking: bool = False,
        response_format: dict = None,
    ) -> Generator[dict, None, None]:
        model = model or self.dm.settings.get("model", "glm-4.7-flash")
        temperature = temperature if temperature is not None else self.dm.settings.get("temperature", 0.7)
        max_tokens = max_tokens or self.dm.settings.get("max_tokens", 4096)
        api_key = self.dm.settings.get("api_key", "")

        if not api_key:
            raise ValueError("API key not set. Go to Settings and enter your ZhipuAI key.")

        url = f"{BASE_URL}chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model, "messages": messages,
            "stream": True, "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
        if thinking:
            body["thinking"] = {"type": "enabled", "budget_tokens": int(max_tokens * 0.5)}
        if response_format:
            body["response_format"] = response_format

        with httpx.Client(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
            with client.stream("POST", url, json=body, headers=headers) as response:
                if response.status_code != 200:
                    error_text = ""
                    for chunk_bytes in response.iter_bytes():
                        error_text += chunk_bytes.decode("utf-8", errors="replace")
                    raise Exception(f"API Error {response.status_code}: {error_text[:500]}")

                buffer = ""
                for chunk_bytes in response.iter_bytes():
                    buffer += chunk_bytes.decode("utf-8", errors="replace")
                    while "\n\n" in buffer:
                        event_text, buffer = buffer.split("\n\n", 1)
                        for line in event_text.split("\n"):
                            line = line.strip()
                            if not line:
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str.strip() == "[DONE]":
                                    return
                                try:
                                    yield json.loads(data_str)
                                except json.JSONDecodeError:
                                    continue

                if buffer.strip():
                    for line in buffer.split("\n"):
                        line = line.strip()
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                return
                            try:
                                yield json.loads(data_str)
                            except json.JSONDecodeError:
                                continue


# ═══════════════════════════════════════════════════════════
#  TOOL EXECUTOR
# ═══════════════════════════════════════════════════════════

def execute_tool(name: str, arguments: dict, allow_commands: bool = True) -> tuple[str, bool]:
    """Execute a tool and return (result, needs_confirmation)"""
    if name == "search_web":
        return f"[Search results for '{arguments.get('query', '')}' — simulated]", False
    elif name == "read_file":
        try:
            path = arguments.get("path", "")
            with open(path, "r", encoding="utf-8") as f:
                return f.read()[:5000], False
        except Exception as e:
            return f"Error: {e}", False
    elif name == "write_file":
        try:
            path = arguments.get("path", "")
            with open(path, "w", encoding="utf-8") as f:
                f.write(arguments.get("content", ""))
            return f"Wrote to {path}", False
        except Exception as e:
            return f"Error: {e}", False
    elif name == "run_command":
        cmd = arguments.get("command", "")
        if not allow_commands:
            return "Command execution is disabled in settings.", False
        # Always require confirmation for commands
        return f"Command ready to execute: {cmd}", True
    elif name == "calculate":
        expr = arguments.get("expression", "")
        try:
            if all(c in "0123456789+-*/.() " for c in expr):
                return str(eval(expr)), False
            return "Error: disallowed characters", False
        except Exception as e:
            return f"Error: {e}", False
    elif name == "list_directory":
        try:
            path = arguments.get("path", ".")
            items = os.listdir(path)
            result = []
            for item in sorted(items):
                full_path = os.path.join(path, item)
                if os.path.isdir(full_path):
                    result.append(f"[DIR] {item}/")
                else:
                    result.append(f"[FILE] {item}")
            return "\n".join(result), False
        except Exception as e:
            return f"Error: {e}", False
    return f"Unknown tool: {name}", False


# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

def get_delta(chunk: dict) -> dict:
    try:
        return chunk.get("choices", [{}])[0].get("delta", {})
    except (IndexError, TypeError):
        return {}

def get_usage(chunk: dict) -> dict:
    return chunk.get("usage", {})


# ═══════════════════════════════════════════════════════════
#  CUSTOM WIDGETS
# ═══════════════════════════════════════════════════════════

class SpinnerWidget(Static):
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    frame_index = reactive(0)

    def __init__(self, label: str = "Thinking", **kwargs):
        super().__init__(**kwargs)
        self.label = label

    def on_mount(self):
        self._spinner_timer = self.set_interval(0.08, self._tick)

    def _tick(self):
        self.frame_index = (self.frame_index + 1) % len(self.frames)
        self.update(f"{self.frames[self.frame_index]} {self.label}...")

    def stop(self, final_text: str = ""):
        if hasattr(self, '_spinner_timer'):
            self._spinner_timer.stop()
        if final_text:
            self.update(final_text)


class MetadataBar(Static):
    def __init__(self, gen_time: float, tokens: int, model: str,
                 thought_tokens: int = 0, tool_calls: int = 0, **kwargs):
        parts = [f"⏱ {gen_time:.1f}s"]
        if tokens > 0:
            parts.append(f"📝 {tokens} tokens")
        if thought_tokens > 0:
            parts.append(f"🧠 {thought_tokens} thought tokens")
        if tool_calls > 0:
            parts.append(f"🔧 {tool_calls} tool call{'s' if tool_calls != 1 else ''}")
        parts.append(f"🤖 {model}")
        super().__init__("  ·  ".join(parts), **kwargs)


class MessageBlock(Vertical):
    """A message block with role indicator and action buttons"""
    def __init__(self, role: str, content: str, chat_ref=None, msg_index: int = 0, **kwargs):
        super().__init__(**kwargs)
        self.role = role
        self.content = content
        self.chat_ref = chat_ref
        self.msg_index = msg_index

    def compose(self) -> ComposeResult:
        icon = "👤" if self.role == "user" else "🤖"
        role_name = "You" if self.role == "user" else "AI"
        
        with Horizontal(classes="message-header"):
            yield Static(f"{icon} {role_name}", classes="message-role")
            with Horizontal(classes="message-actions"):
                yield Button("Copy", variant="default", classes="msg-btn-copy")
                if self.role == "user":
                    yield Button("Edit", variant="default", classes="msg-btn-edit")
                yield Button("Re-run", variant="default", classes="msg-btn-rerun")
                yield Button("Delete", variant="default", classes="msg-btn-delete")
        
        yield Static(content, classes="message-content")


# ═══════════════════════════════════════════════════════════
#  MODAL SCREENS
# ═══════════════════════════════════════════════════════════

class MenuScreen(ModalScreen):
    """Overlay menu for navigation"""
    
    BINDINGS = [("escape", "dismiss", "Close")]
    
    CSS = """
    MenuScreen {
        align: center top;
        background: rgba(0, 0, 0, 0.7);
    }
    
    #menu-container {
        width: 280;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
        margin-top: 8;
    }
    
    #menu-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        padding: 1 0;
    }
    
    .menu-item {
        padding: 1 2;
        background: transparent;
    }
    
    .menu-item:hover {
        background: $primary;
        color: $text;
    }
    
    .menu-separator {
        height: 1;
        background: $surface-darken-2;
        margin: 1 0;
    }
    """
    
    def compose(self) -> ComposeResult:
        with Vertical(id="menu-container"):
            yield Static("MENU", id="menu-title")
            yield Static("", classes="menu-separator")
            yield Button("New Chat", id="menu-new-chat", classes="menu-item", variant="default")
            yield Button("Open Project", id="menu-open-project", classes="menu-item", variant="default")
            yield Button("History", id="menu-history", classes="menu-item", variant="default")
            yield Button("Settings", id="menu-settings", classes="menu-item", variant="default")
            yield Button("Tools", id="menu-tools", classes="menu-item", variant="default")
            yield Static("", classes="menu-separator")
            yield Button("Close", id="menu-close", classes="menu-item", variant="default")


class CommandConfirmScreen(ModalScreen):
    """Confirmation dialog for command execution"""
    
    BINDINGS = [("enter", "confirm", "Confirm"), ("escape", "dismiss", "Cancel")]
    
    CSS = """
    CommandConfirmScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.8);
    }
    
    #confirm-container {
        width: 500;
        background: $surface;
        border: solid $warning;
        padding: 2 3;
    }
    
    #confirm-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        padding: 0 0 1 0;
    }
    
    #confirm-command {
        background: $background;
        padding: 1;
        margin: 1 0;
        text-style: italic;
    }
    
    #confirm-buttons {
        align: center middle;
        margin-top: 2;
    }
    
    #confirm-buttons Button {
        margin: 0 1;
    }
    """
    
    def __init__(self, command: str, **kwargs):
        super().__init__(**kwargs)
        self.command = command
        self.confirmed = False
    
    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-container"):
            yield Static("Execute Command?", id="confirm-title")
            yield Static(f"Command: {self.command}", id="confirm-command")
            yield Static("Do you want to proceed with this command?", id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button("Yes, Execute", id="btn-confirm-yes", variant="success")
                yield Button("No, Cancel", id="btn-confirm-no", variant="error")


class WelcomeScreen(Static):
    """Welcome screen shown on app load"""
    
    CSS = """
    WelcomeScreen {
        align: center middle;
        background: $background;
    }
    
    #welcome-container {
        width: 600;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 3 5;
    }
    
    #welcome-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        font-size: 18;
        padding: 0 0 1 0;
    }
    
    #welcome-subtitle {
        text-align: center;
        color: $text-muted;
        padding: 0 0 2 0;
    }
    
    .welcome-feature {
        padding: 1 0;
    }
    
    #welcome-start-btn {
        margin-top: 2;
        width: 100%;
    }
    """
    
    def compose(self) -> ComposeResult:
        with Vertical(id="welcome-container"):
            yield Static("JPAI Agentic AI", id="welcome-title")
            yield Static("by JeelanPro AI Team", id="welcome-subtitle")
            yield Static("", classes="menu-separator")
            yield Static("Features:", classes="welcome-feature")
            yield Static("  - Modern IDE-style interface", classes="welcome-feature")
            yield Static("  - Multi-chat support with tabs", classes="welcome-feature")
            yield Static("  - Project-aware AI assistance", classes="welcome-feature")
            yield Static("  - Command execution with confirmation", classes="welcome-feature")
            yield Static("  - Vision capabilities", classes="welcome-feature")
            yield Static("  - File editing & management", classes="welcome-feature")
            yield Static("  - Request queuing system", classes="welcome-feature")
            yield Button("Start Using JPAI", id="welcome-start-btn", variant="primary")


class LoadingScreen(Static):
    """Fancy loading screen"""
    
    CSS = """
    LoadingScreen {
        align: center middle;
        background: linear-gradient(45deg, #0a0a1a, #1a0a0a);
    }
    
    #loading-container {
        width: 400;
        height: 200;
        background: rgba(255, 100, 50, 0.1);
        border: solid #ff6b35;
        padding: 3 5;
    }
    
    #loading-title {
        text-align: center;
        text-style: bold;
        color: #ff6b35;
        font-size: 16;
    }
    
    #loading-spinner {
        text-align: center;
        margin: 2 0;
        color: #ff8c5a;
    }
    
    #loading-message {
        text-align: center;
        color: $text-muted;
    }
    """
    
    def compose(self) -> ComposeResult:
        with Vertical(id="loading-container"):
            yield Static("JPAI Agentic AI", id="loading-title")
            yield Static("Initializing...", id="loading-spinner")
            yield Static("Loading your workspace...", id="loading-message")


# ═══════════════════════════════════════════════════════════
#  CHAT SESSION CLASS
# ═══════════════════════════════════════════════════════════

class ChatSession:
    """Represents a single chat session"""
    def __init__(self, chat_id: str = None, title: str = "", project_path: str = ""):
        self.chat_id = chat_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.title = title or f"Chat {self.chat_id[-6:]}"
        self.project_path = project_path
        self.messages: List[dict] = []
        self.is_generating = False
        self.created_at = datetime.now()


# ═══════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════

class JPAIApp(App):
    TITLE = ""
    SUB_TITLE = ""
    
    CSS = """
    Screen {
        background: #0a0a0a;
    }
    
    /* Top Bar */
    #top-bar {
        height: 5;
        background: #1a1a1a;
        border-bottom: solid #ff6b35;
        padding: 0 2;
    }
    
    #menu-btn {
        width: 8;
        height: 3;
        margin: 1 0;
        background: #ff6b35;
        color: #0a0a0a;
    }
    
    #app-title {
        margin: 1 2;
        text-style: bold;
        color: #ff6b35;
    }
    
    #project-display {
        margin: 1 2;
        color: $text-muted;
    }
    
    /* Main Layout */
    #main-container {
        height: 1fr;
        layout: horizontal;
    }
    
    /* Left Sidebar */
    #left-sidebar {
        width: 250;
        background: #111111;
        border-right: solid #333;
        layout: vertical;
    }
    
    #file-explorer-container {
        height: 2fr;
        border-bottom: solid #333;
    }
    
    #file-explorer-title {
        padding: 1;
        text-style: bold;
        color: #ff6b35;
        background: #1a1a1a;
    }
    
    #directory-tree {
        height: 1fr;
    }
    
    #properties-container {
        height: 1fr;
    }
    
    #properties-title {
        padding: 1;
        text-style: bold;
        color: #ff6b35;
        background: #1a1a1a;
    }
    
    #properties-content {
        padding: 1;
        height: 1fr;
    }
    
    /* Center Chat Area */
    #center-container {
        width: 1fr;
        layout: vertical;
    }
    
    #chat-tabs-bar {
        height: 5;
        background: #1a1a1a;
        border-bottom: solid #333;
    }
    
    #chat-tabs-list {
        height: 1fr;
    }
    
    #chat-tab-button {
        background: #222;
        margin: 1;
        padding: 0 2;
    }
    
    #chat-tab-button.active {
        background: #ff6b35;
        color: #0a0a0a;
    }
    
    #chat-tab-new {
        width: 6;
        background: #333;
        margin: 1;
    }
    
    #chat-messages-container {
        height: 1fr;
        background: #0a0a0a;
    }
    
    #chat-messages-scroll {
        height: 1fr;
    }
    
    .message-block {
        margin: 1 2;
        padding: 1;
        background: #111;
        border: solid #222;
    }
    
    .message-header {
        height: 3;
        padding: 0 1;
        background: #1a1a1a;
    }
    
    .message-role {
        width: 1fr;
        color: #ff6b35;
    }
    
    .message-actions {
        height: 3;
    }
    
    .message-actions Button {
        width: 8;
        margin: 0 1;
    }
    
    .message-content {
        padding: 1;
        height: auto;
    }
    
    #chat-input-container {
        height: 8;
        background: #1a1a1a;
        border-top: solid #333;
        padding: 1 2;
    }
    
    #chat-input {
        height: 4;
        width: 1fr;
    }
    
    #chat-send-btn {
        width: 15;
        margin: 1 0 0 1;
        background: #ff6b35;
        color: #0a0a0a;
    }
    
    /* Right Sidebar */
    #right-sidebar {
        width: 280;
        background: #111111;
        border-left: solid #333;
        layout: vertical;
    }
    
    #context-container {
        height: 1fr;
        border-bottom: solid #333;
    }
    
    #context-title {
        padding: 1;
        text-style: bold;
        color: #ff6b35;
        background: #1a1a1a;
    }
    
    #context-content {
        padding: 1;
        height: 1fr;
    }
    
    #tools-container {
        height: 1fr;
    }
    
    #tools-title {
        padding: 1;
        text-style: bold;
        color: #ff6b35;
        background: #1a1a1a;
    }
    
    #tools-content {
        padding: 1;
        height: 1fr;
    }
    
    /* Footer */
    #status-bar {
        height: 3;
        background: #1a1a1a;
        border-top: solid #ff6b35;
        padding: 0 2;
    }
    
    #queue-status {
        color: #ff8c5a;
    }
    
    /* Welcome Screen */
    #welcome-screen {
        align: center middle;
    }
    
    #welcome-box {
        width: 600;
        height: auto;
        background: #1a1a1a;
        border: solid #ff6b35;
        padding: 3 5;
    }
    
    #welcome-title {
        text-align: center;
        text-style: bold;
        color: #ff6b35;
        font-size: 18;
    }
    
    #welcome-subtitle {
        text-align: center;
        color: $text-muted;
        margin: 1 0 2 0;
    }
    
    .feature-item {
        padding: 1 0;
        color: $text;
    }
    
    #start-btn {
        width: 100%;
        margin-top: 2;
        background: #ff6b35;
        color: #0a0a0a;
    }
    
    /* Loading Screen */
    #loading-screen {
        align: center middle;
        background: linear-gradient(45deg, #0a0a1a, #1a0a0a);
    }
    
    #loading-box {
        width: 400;
        height: 200;
        background: rgba(255, 107, 53, 0.1);
        border: solid #ff6b35;
        padding: 3 5;
    }
    
    #loading-title {
        text-align: center;
        text-style: bold;
        color: #ff6b35;
        font-size: 16;
    }
    
    #loading-spinner-text {
        text-align: center;
        margin: 2 0;
        color: #ff8c5a;
    }
    
    #loading-msg {
        text-align: center;
        color: $text-muted;
    }
    """
    
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+n", "new_chat", "New Chat"),
        Binding("ctrl+o", "open_project", "Open Project"),
        Binding("ctrl+s", "toggle_menu", "Menu"),
        Binding("ctrl+f", "search", "Search"),
        Binding("escape", "close_overlay", "Close"),
    ]
    
    # Reactive state
    current_chat_id = reactive(None)
    is_generating = reactive(False)
    queue_count = reactive(0)
    show_welcome = reactive(True)
    
    def __init__(self, dm: DataManager):
        super().__init__()
        self.dm = dm
        self.api = ZhipuClient(self.dm)
        self.chat_sessions: Dict[str, ChatSession] = {}
        self.request_queue: deque = deque()
        self.current_project: str = ""
        self.menu_open = False
        self.loading_done = False
    
    def compose(self) -> ComposeResult:
        # Loading screen
        yield LoadingScreen(id="loading-screen")
        
        # Main UI (hidden initially)
        with Vertical(id="main-ui", styles={"display": "none"}):
            # Top bar
            with Horizontal(id="top-bar"):
                yield Button("Menu", id="menu-btn", variant="default")
                yield Static("JPAI Agentic AI", id="app-title")
                yield Static("", id="project-display")
            
            # Main container
            with Horizontal(id="main-container"):
                # Left sidebar
                with Vertical(id="left-sidebar"):
                    with Vertical(id="file-explorer-container"):
                        yield Static("Project Files", id="file-explorer-title")
                        yield DirectoryTree(".", id="directory-tree")
                    
                    with Vertical(id="properties-container"):
                        yield Static("Properties", id="properties-title")
                        yield Static("Select a file to view properties", id="properties-content")
                
                # Center chat area
                with Vertical(id="center-container"):
                    # Chat tabs bar
                    with Horizontal(id="chat-tabs-bar"):
                        yield OptionList(id="chat-tabs-list")
                        yield Button("+", id="chat-tab-new", variant="default")
                    
                    # Chat messages
                    with Vertical(id="chat-messages-container"):
                        yield VerticalScroll(id="chat-messages-scroll")
                    
                    # Input area
                    with Vertical(id="chat-input-container"):
                        yield TextArea(language="markdown", id="chat-input")
                        with Horizontal():
                            yield Button("Attach", id="chat-attach-btn", variant="default")
                            yield Button("Send", id="chat-send-btn", variant="primary")
                
                # Right sidebar
                with Vertical(id="right-sidebar"):
                    with Vertical(id="context-container"):
                        yield Static("Context", id="context-title")
                        yield Static("Project context will appear here", id="context-content")
                    
                    with Vertical(id="tools-container"):
                        yield Static("Quick Tools", id="tools-title")
                        with Vertical(id="tools-content"):
                            yield Button("Search", id="tool-search", variant="default")
                            yield Button("Copy All", id="tool-copy-all", variant="default")
                            yield Button("Clear Chat", id="tool-clear", variant="default")
            
            # Status bar
            with Horizontal(id="status-bar"):
                yield Static("Ready", id="status-text")
                yield Static("", id="queue-status")
        
        # Welcome screen (shown after loading)
        yield WelcomeScreen(id="welcome-screen", styles={"display": "none"})
    
    def on_mount(self) -> None:
        """Initialize the app"""
        # Show loading screen for 2 seconds
        self.set_timer(2.0, self._finish_loading)
        
        # Set up directory tree
        try:
            tree = self.query_one("#directory-tree", DirectoryTree)
            tree.path = Path.cwd()
        except Exception:
            pass
        
        # Update chat tabs list
        self._update_chat_tabs()
    
    def _finish_loading(self):
        """Hide loading screen and show welcome"""
        try:
            self.query_one("#loading-screen").remove()
        except Exception:
            pass
        
        try:
            self.query_one("#main-ui").styles.display = "block"
        except Exception:
            pass
        
        try:
            welcome = self.query_one("#welcome-screen")
            welcome.styles.display = "block"
        except Exception:
            pass
        
        self.loading_done = True
    
    def _update_chat_tabs(self):
        """Update the chat tabs list"""
        try:
            tabs_list = self.query_one("#chat-tabs-list", OptionList)
            tabs_list.clear_options()
            
            for chat_id, session in self.chat_sessions.items():
                marker = "* " if chat_id == self.current_chat_id else ""
                tabs_list.add_option(f"{marker}{session.title}")
        except Exception:
            pass
    
    def _create_new_chat(self, title: str = "", project_path: str = ""):
        """Create a new chat session"""
        session = ChatSession(title=title, project_path=project_path or self.current_project)
        self.chat_sessions[session.chat_id] = session
        
        # Hide welcome if shown
        try:
            self.query_one("#welcome-screen").styles.display = "none"
        except Exception:
            pass
        
        # Switch to new chat
        self.current_chat_id = session.chat_id
        self._update_chat_tabs()
        self._render_chat_messages()
        
        return session
    
    def _get_current_session(self) -> Optional[ChatSession]:
        """Get the current chat session"""
        if self.current_chat_id and self.current_chat_id in self.chat_sessions:
            return self.chat_sessions[self.current_chat_id]
        return None
    
    def _render_chat_messages(self):
        """Render messages for current chat"""
        session = self._get_current_session()
        if not session:
            return
        
        try:
            scroll = self.query_one("#chat-messages-scroll", VerticalScroll)
            scroll.remove_children()
            
            for i, msg in enumerate(session.messages):
                block = MessageBlock(
                    role=msg["role"],
                    content=msg["content"],
                    chat_ref=self,
                    msg_index=i
                )
                block.add_class("message-block")
                scroll.mount(block)
            
            scroll.scroll_end(animate=False)
        except Exception:
            pass
    
    def _add_message(self, role: str, content: str):
        """Add a message to current chat and render"""
        session = self._get_current_session()
        if not session:
            session = self._create_new_chat()
        
        session.messages.append({"role": role, "content": content})
        self._render_chat_messages()
        
        # Auto-save
        if session.messages:
            title = session.messages[0]["content"][:50] if session.messages else "New Chat"
            self.dm.save_chat(
                session.chat_id,
                session.messages,
                title=title,
                project_path=session.project_path
            )
    
    @work(thread=True)
    def _generate_response(self, user_message: str):
        """Generate AI response in background thread"""
        session = self._get_current_session()
        if not session or session.is_generating:
            return
        
        session.is_generating = True
        self.call_from_thread(lambda: setattr(self, 'is_generating', True))
        
        # Build messages for API
        system_prompt = self.dm.get_system_prompt("default")
        api_messages = []
        
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        
        # Add project context if available
        if session.project_path and os.path.isdir(session.project_path):
            files_info = self._get_project_files_info(session.project_path)
            if files_info:
                api_messages.append({
                    "role": "system",
                    "content": f"Current project path: {session.project_path}\\nFiles:\\n{files_info}"
                })
        
        api_messages.extend(session.messages)
        
        start_time = time.time()
        full_response = ""
        total_tokens = 0
        pending_tool_calls = []
        
        try:
            model = self.dm.settings.get("model", "glm-4.7-flash")
            tools = self.dm.tools if self.dm.settings.get("allow_command_execution", True) else None
            
            for chunk in self.api.chat_stream(api_messages, model=model, tools=tools):
                delta = get_delta(chunk)
                content_piece = delta.get("content", "")
                
                if content_piece:
                    full_response += content_piece
                
                # Handle tool calls
                tc_list = delta.get("tool_calls", [])
                for tc in tc_list:
                    fn = tc.get("function", {})
                    if fn.get("name") and fn.get("arguments"):
                        pending_tool_calls.append({
                            "name": fn["name"],
                            "arguments": json.loads(fn["arguments"])
                        })
                
                usage = get_usage(chunk)
                if usage:
                    total_tokens = usage.get("total_tokens", 0)
            
            # Process tool calls
            if pending_tool_calls:
                tool_results = []
                for tc in pending_tool_calls:
                    result, needs_confirm = execute_tool(
                        tc["name"],
                        tc["arguments"],
                        self.dm.settings.get("allow_command_execution", True)
                    )
                    
                    if needs_confirm:
                        # Show confirmation dialog
                        self.call_from_thread(
                            self._show_command_confirm,
                            tc["arguments"].get("command", ""),
                            tc["name"],
                            tc["arguments"]
                        )
                        # Wait for confirmation (simplified - just add note)
                        result = f"[Awaiting confirmation for: {tc['arguments'].get('command', '')}]"
                    
                    tool_results.append({
                        "name": tc["name"],
                        "result": result
                    })
                    full_response += f"\\n\\n[Tool: {tc['name']} -> {result[:200]}]"
            
            gen_time = time.time() - start_time
            
            # Add response to chat
            session.messages.append({"role": "assistant", "content": full_response})
            self.call_from_thread(self._render_chat_messages)
            
            # Save chat
            title = session.messages[0]["content"][:50] if session.messages else "New Chat"
            self.dm.save_chat(
                session.chat_id,
                session.messages,
                title=title,
                project_path=session.project_path
            )
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            session.messages.append({"role": "assistant", "content": error_msg})
            self.call_from_thread(self._render_chat_messages)
        
        finally:
            session.is_generating = False
            self.call_from_thread(lambda: setattr(self, 'is_generating', False))
    
    def _get_project_files_info(self, path: str, max_files: int = 20) -> str:
        """Get info about files in project"""
        try:
            files = []
            for root, dirs, filenames in os.walk(path):
                # Skip hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for f in filenames[:max_files]:
                    if not f.startswith('.'):
                        files.append(os.path.join(root, f))
                    if len(files) >= max_files:
                        break
                if len(files) >= max_files:
                    break
            
            return "\\n".join(files[:max_files])
        except Exception:
            return ""
    
    def _show_command_confirm(self, command: str, tool_name: str, arguments: dict):
        """Show command confirmation dialog"""
        # This would normally push a modal screen
        # For now, just notify
        self.notify(f"Command awaiting confirmation: {command[:50]}...", severity="warning")
    
    # Event handlers
    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        
        if btn_id == "menu-btn":
            self.action_toggle_menu()
        
        elif btn_id == "chat-tab-new":
            self.action_new_chat()
        
        elif btn_id == "chat-send-btn":
            self._send_message()
        
        elif btn_id == "chat-attach-btn":
            self.notify("Image attachment coming soon!", severity="information")
        
        elif btn_id == "tool-search":
            self.action_search()
        
        elif btn_id == "tool-copy-all":
            self._copy_all_messages()
        
        elif btn_id == "tool-clear":
            self._clear_current_chat()
        
        elif btn_id == "welcome-start-btn":
            self.action_new_chat()
            try:
                self.query_one("#welcome-screen").styles.display = "none"
            except Exception:
                pass
        
        elif btn_id == "settings-save":
            self._save_settings()
        
        elif btn_id.startswith("msg-btn-"):
            self._handle_message_action(btn_id, event.button)
    
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle chat tab selection"""
        if event.option_list.id == "chat-tabs-list":
            chat_ids = list(self.chat_sessions.keys())
            if event.option_index < len(chat_ids):
                self.current_chat_id = chat_ids[event.option_index]
                self._update_chat_tabs()
                self._render_chat_messages()
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "chat-input":
            self._send_message()
    
    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection in directory tree"""
        file_path = event.path
        self._update_properties_panel(file_path)
        self._update_context_panel(file_path)
    
    def _send_message(self):
        """Send message from input"""
        if self.is_generating:
            return
        
        try:
            textarea = self.query_one("#chat-input", TextArea)
            text = textarea.text.strip()
        except Exception:
            return
        
        if not text:
            return
        
        # Clear input
        try:
            self.query_one("#chat-input", TextArea).text = ""
        except Exception:
            pass
        
        # Add user message
        self._add_message("user", text)
        
        # Queue the request
        self.request_queue.append(text)
        self.queue_count = len(self.request_queue)
        self._update_status()
        
        # Process queue
        if not self.is_generating:
            self._process_queue()
    
    def _process_queue(self):
        """Process next request in queue"""
        if self.request_queue and not self.is_generating:
            message = self.request_queue.popleft()
            self.queue_count = len(self.request_queue)
            self._update_status()
            self._generate_response(message)
    
    def _update_status(self):
        """Update status bar"""
        try:
            status_text = self.query_one("#status-text", Static)
            queue_status = self.query_one("#queue-status", Static)
            
            if self.is_generating:
                status_text.update("Generating response...")
            else:
                status_text.update("Ready")
            
            if self.queue_count > 0:
                queue_status.update(f" | Queue: {self.queue_count} request(s)")
            else:
                queue_status.update("")
        except Exception:
            pass
    
    def _update_properties_panel(self, file_path: str):
        """Update properties panel with file info"""
        try:
            content = self.query_one("#properties-content", Static)
            
            stat = os.stat(file_path)
            size = stat.st_size
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            
            ext = Path(file_path).suffix.lower()
            lang_map = {
                '.py': 'Python', '.js': 'JavaScript', '.ts': 'TypeScript',
                '.html': 'HTML', '.css': 'CSS', '.json': 'JSON',
                '.md': 'Markdown', '.txt': 'Text',
            }
            lang = lang_map.get(ext, 'Unknown')
            
            content.update(
                f"File: {Path(file_path).name}\\n"
                f"Path: {file_path}\\n"
                f"Size: {size:,} bytes\\n"
                f"Modified: {modified}\\n"
                f"Type: {lang}"
            )
        except Exception:
            pass
    
    def _update_context_panel(self, file_path: str):
        """Update context panel"""
        try:
            content = self.query_one("#context-content", Static)
            
            # Read first few lines for context
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    preview = f.read(500)
                content.update(f"Preview:\\n{preview}")
            except Exception:
                content.update("Unable to read file")
        except Exception:
            pass
    
    def _copy_all_messages(self):
        """Copy all messages to clipboard"""
        session = self._get_current_session()
        if not session:
            return
        
        text = "\\n\\n".join([
            f"{'You' if m['role'] == 'user' else 'AI'}:\\n{m['content']}"
            for m in session.messages
        ])
        write_clipboard(text)
        self.notify("All messages copied to clipboard!", severity="information")
    
    def _clear_current_chat(self):
        """Clear current chat"""
        session = self._get_current_session()
        if session:
            session.messages = []
            self._render_chat_messages()
            self.notify("Chat cleared!", severity="information")
    
    def _handle_message_action(self, btn_id: str, button: Button):
        """Handle message action buttons"""
        # Find parent message block
        block = button.parent.parent
        if not isinstance(block, MessageBlock):
            return
        
        if btn_id == "msg-btn-copy":
            write_clipboard(block.content)
            self.notify("Message copied!", severity="information")
        
        elif btn_id == "msg-btn-edit":
            # Load message into input for editing
            try:
                textarea = self.query_one("#chat-input", TextArea)
                textarea.text = block.content
            except Exception:
                pass
        
        elif btn_id == "msg-btn-rerun":
            # Re-send the message
            if block.role == "user":
                self.request_queue.append(block.content)
                self.queue_count = len(self.request_queue)
                self._update_status()
                if not self.is_generating:
                    self._process_queue()
        
        elif btn_id == "msg-btn-delete":
            # Delete message
            session = self._get_current_session()
            if session and 0 <= block.msg_index < len(session.messages):
                session.messages.pop(block.msg_index)
                self._render_chat_messages()
                self.notify("Message deleted!", severity="information")
    
    def _save_settings(self):
        """Save settings from settings panel"""
        try:
            api_key = self.query_one("#settings-api-key", Input).value
            if api_key:
                self.dm.set_api_key(api_key)
            
            model = self.query_one("#settings-model", Select).value
            if model:
                self.dm.settings["model"] = model
            
            temp = self.query_one("#settings-temperature", Input).value
            try:
                self.dm.settings["temperature"] = float(temp)
            except ValueError:
                pass
            
            max_tok = self.query_one("#settings-max-tokens", Input).value
            try:
                self.dm.settings["max_tokens"] = int(max_tok)
            except ValueError:
                pass
            
            allow_cmds = self.query_one("#settings-allow-commands", Switch).value
            self.dm.settings["allow_command_execution"] = allow_cmds
            
            self.dm.save_settings()
            self.notify("Settings saved!", severity="information")
        except Exception as e:
            self.notify(f"Error saving settings: {e}", severity="error")
    
    # Actions
    def action_toggle_menu(self):
        """Toggle menu overlay"""
        if self.menu_open:
            try:
                self.screen.dismiss()
            except Exception:
                pass
            self.menu_open = False
        else:
            self.push_screen(MenuScreen())
            self.menu_open = True
    
    def action_new_chat(self):
        """Create new chat"""
        self._create_new_chat()
    
    def action_open_project(self):
        """Open project folder"""
        self.notify("Use the file explorer to navigate projects!", severity="information")
    
    def action_search(self):
        """Search in chat"""
        self.notify("Search feature coming soon!", severity="information")
    
    def action_close_overlay(self):
        """Close any overlay"""
        if self.menu_open:
            try:
                self.screen.dismiss()
            except Exception:
                pass
            self.menu_open = False


# ═══════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════

def startup_check_api_key(dm: DataManager):
    """Check if API key is set"""
    if not dm.settings.get("api_key"):
        print("WARNING: No API key found!")
        print("Set ZHIPUAI_API_KEY environment variable or add it in Settings.")


if __name__ == "__main__":
    dm = DataManager()
    startup_check_api_key(dm)
    app = JPAIApp(dm)
    app.run()
