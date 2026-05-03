#!/usr/bin/env python3
"""
JPAI Agentic AI — by JeelanPro™ AI team
Run:  python JPAI.py
"""
import os
import sys
import json
import time
import queue
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator, Optional

import httpx

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Collapsible,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    ProgressBar,
    RichLog,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)
from textual import work

# ═══════════════════════════════════════════════════════════
#  PATHS & CONSTANTS
# ═══════════════════════════════════════════════════════════
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "Data"
CHAT_DIR = DATA_DIR / "chats"
SETTINGS_PATH = DATA_DIR / "settings.json"
TOOLS_PATH = DATA_DIR / "tools.json"
API_KEY_FILE = DATA_DIR / "api_key.txt"

DATA_DIR.mkdir(exist_ok=True)
CHAT_DIR.mkdir(exist_ok=True)

BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"

# Only free models you requested
MODELS = [
    "glm-4.5-flash",
    "glm-4.7-flash",
    "glm-4.6v-flash",
]

DURATION_OPTIONS = ["1 min", "2 min", "5 min", "10 min", "15 min", "20 min", "30 min", "45 min", "60 min"]

# ═══════════════════════════════════════════════════════════
#  CLIPBOARD
# ═══════════════════════════════════════════════════════════
def read_clipboard() -> str:
    try:
        result = subprocess.run(["powershell", "-Command", "Get-Clipboard"], capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception:
        return ""

def write_clipboard(text: str):
    try:
        subprocess.run(["powershell", "-Command", f"Set-Clipboard -Value '{text.replace("'", "''")}'"], timeout=5)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════
#  SYSTEM PROMPTS (unchanged from original)
# ═══════════════════════════════════════════════════════════
DEFAULT_SYSTEM_PROMPTS = {
    "chat": (
        "You are JPAI AI, a helpful, knowledgeable, and honest assistant. "
        "You respond clearly and concisely. When the user asks for code, "
        "you provide working examples with brief explanations. You admit "
        "when you do not know something rather than guessing. You format "
        "your responses using markdown for readability."
    ),
    "agent": (
        "You are an autonomous AI agent. You have access to tools that "
        "you can call to accomplish tasks. Follow this loop:\n\n"
        "1. THINK — Analyze the current state and decide what to do next.\n"
        "2. ACT — Call the appropriate tool with correct parameters.\n"
        "3. OBSERVE — Review the tool's output.\n"
        "4. Repeat until the task is complete.\n\n"
        "Always explain your reasoning before taking action. If a tool "
        "call fails, analyze why and try an alternative approach. When "
        "the task is fully complete, provide a final summary of what "
        "was accomplished."
    ),
    "longrun": (
        "You are a long-running AI assistant operating in timed mode. "
        "You will receive the remaining time with every message.\n\n"
        "WORKFLOW:\n"
        "1. PLAN — Break the task into numbered subtasks. Display them "
        "as a checklist with ⬜ for pending items.\n"
        "2. THINK — Evaluate each subtask for feasibility, dependencies, "
        "and potential issues. Identify problems before they happen.\n"
        "3. FIX — Adjust the plan based on your evaluation. Rearrange, "
        "merge, or split subtasks as needed. Show the revised plan.\n"
        "4. EXECUTE — Work through each subtask one at a time. Mark "
        "completed items with ✅ and the current item with 🔄.\n"
        "5. CHECK OFF — After completing each subtask, explicitly mark "
        "it done and move to the next.\n\n"
        "If time is running low, prioritize the most important remaining "
        "subtasks and wrap up with a summary. Always show the checklist "
        "state after each step so the user can track progress.\n\n"
        "Format your checklist like this:\n"
        "📋 Task Progress:\n"
        "  ✅ 1. Research the topic\n"
        "  ✅ 2. Create outline\n"
        "  🔄 3. Write section one\n"
        "  ⬜ 4. Write section two\n"
        "  ⬜ 5. Final review"
    ),
    "deepthink": (
        "You are a deep reasoning AI. For every question, you must think "
        "step by step before providing your answer. Break complex problems "
        "into smaller parts. Consider multiple perspectives. Identify "
        "assumptions and test them. Show your full reasoning process, "
        "then provide your conclusion clearly marked.\n\n"
        "Structure your response as:\n"
        "🧠 Reasoning: [your step-by-step thinking]\n"
        "📌 Conclusion: [your final answer]"
    ),
    "structured": (
        "You are a structured output AI. You must respond ONLY with valid "
        "JSON that matches the schema provided by the user. Do not include "
        "any text outside the JSON object. If you cannot fulfill the "
        "request within the schema constraints, respond with:\n"
        '{"error": "description of the constraint violation"}'
    ),
    "vision": (
        "You are a vision-capable AI assistant. You can analyze images "
        "that the user provides via URL. Describe what you see in detail, "
        "answer questions about the image content, extract text from "
        "images, identify objects, and provide analysis. When no image "
        "is provided, respond as a normal assistant."
    ),
    "quick": (
        "You are a quick-response AI. Answer in 1-3 sentences maximum. "
        "Be direct. No fluff, no disclaimers, no pleasantries. If the "
        "answer needs more space, use bullet points but keep each point "
        "to one line."
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
                "properties": {"query": {"type": "string", "description": "The search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from disk",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "The file path to read"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file on disk",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "The file path to write"},
                               "content": {"type": "string", "description": "The content to write"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command and return its output",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "The shell command to execute"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a mathematical expression",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "The mathematical expression to evaluate"}},
                "required": ["expression"],
            },
        },
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
            "require_command_approval": True,
        })
        self.tools = self._load_json(TOOLS_PATH, DEFAULT_TOOLS)
        if not self.settings.get("api_key"):
            if API_KEY_FILE.exists():
                key = API_KEY_FILE.read_text(encoding="utf-8").strip()
                if key and len(key) > 10:
                    self.settings["api_key"] = key
                    self.save_settings()
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
        API_KEY_FILE.write_text(key, encoding="utf-8")

    def save_chat(self, chat_id: str, messages: list, mode: str, model: str):
        entry = {
            "id": chat_id, "mode": mode, "model": model,
            "timestamp": datetime.now().isoformat(), "messages": messages,
        }
        self._save_json(CHAT_DIR / f"{chat_id}.json", entry)

    def list_chats(self) -> list:
        chats = []
        for path in CHAT_DIR.glob("*.json"):
            data = self._load_json(path, None)
            if data:
                chats.append(data)
        chats.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return chats

    def delete_chat(self, chat_id: str):
        (CHAT_DIR / f"{chat_id}.json").unlink(missing_ok=True)

# ═══════════════════════════════════════════════════════════
#  API CLIENT
# ═══════════════════════════════════════════════════════════
class ZhipuClient:
    def __init__(self, dm: DataManager):
        self.dm = dm

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
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": model, "messages": messages, "stream": True,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if tools: body["tools"] = tools
        if thinking: body["thinking"] = {"type": "enabled", "budget_tokens": int(max_tokens * 0.5)}
        if response_format: body["response_format"] = response_format

        with httpx.Client(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
            with client.stream("POST", url, json=body, headers=headers) as resp:
                if resp.status_code != 200:
                    error_text = b"".join(resp.iter_bytes()).decode(errors="replace")
                    raise Exception(f"API Error {resp.status_code}: {error_text[:500]}")
                buffer = ""
                for chunk_bytes in resp.iter_bytes():
                    buffer += chunk_bytes.decode("utf-8", errors="replace")
                    while "\n\n" in buffer:
                        event_text, buffer = buffer.split("\n\n", 1)
                        for line in event_text.split("\n"):
                            line = line.strip()
                            if not line or not line.startswith("data:"):
                                continue
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                return
                            try:
                                yield json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                if buffer.strip():
                    for line in buffer.split("\n"):
                        line = line.strip()
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                return
                            try:
                                yield json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

# ═══════════════════════════════════════════════════════════
#  AI REQUEST QUEUE (single worker)
# ═══════════════════════════════════════════════════════════
class AIQueue:
    def __init__(self):
        self.queue = queue.Queue()
        self.current = None

    def put(self, fn, *args, **kwargs):
        self.queue.put((fn, args, kwargs))

    @work(thread=True, exclusive=True)
    def worker(self):
        while True:
            fn, args, kwargs = self.queue.get()
            self.current = fn.__name__ if hasattr(fn, '__name__') else str(fn)
            try:
                fn(*args, **kwargs)
            except Exception as e:
                # Hook to app?
                pass
            self.current = None

# ═══════════════════════════════════════════════════════════
#  TOOL EXECUTOR — now can prompt user for command approval
# ═══════════════════════════════════════════════════════════
import threading
def execute_tool(app: 'App', name: str, arguments: dict) -> str:
    if name == "search_web":
        return f"[Search results for '{arguments.get('query', '')}' — simulated]"
    elif name == "read_file":
        try:
            return Path(arguments.get("path", "")).read_text(encoding="utf-8", errors="replace")[:5000]
        except Exception as e:
            return f"Error: {e}"
    elif name == "write_file":
        try:
            Path(arguments.get("path", "")).write_text(arguments.get("content", ""), encoding="utf-8")
            return f"Wrote to {arguments.get('path')}"
        except Exception as e:
            return f"Error: {e}"
    elif name == "run_command":
        if app.dm.settings.get("require_command_approval", True):
            # Request user approval (blocks the worker thread)
            if app.request_command_approval(arguments.get("command", "")):
                try:
                    return subprocess.check_output(
                        arguments.get("command", ""), shell=True,
                        stderr=subprocess.STDOUT, text=True
                    )[:5000] or "(no output)"
                except subprocess.CalledProcessError as e:
                    return f"Error: {e.output[:500]}"
            else:
                return "Command execution denied by user."
        else:
            try:
                return subprocess.check_output(
                    arguments.get("command", ""), shell=True,
                    stderr=subprocess.STDOUT, text=True
                )[:5000] or "(no output)"
            except subprocess.CalledProcessError as e:
                return f"Error: {e.output[:500]}"
    elif name == "calculate":
        try:
            return str(eval(arguments["expression"], {"__builtins__": None}, {}))
        except Exception as e:
            return f"Error: {e}"
    return f"Unknown tool: {name}"

# ═══════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════
def get_delta(chunk: dict) -> dict:
    return chunk.get("choices", [{}])[0].get("delta", {})

def get_usage(chunk: dict) -> dict:
    return chunk.get("usage", {})

# ═══════════════════════════════════════════════════════════
#  LOADING SCREEN (fancy dark blue)
# ═══════════════════════════════════════════════════════════
class SplashScreen(ModalScreen):
    CSS = """
    SplashScreen {
        align: center middle;
        background: $surface-darken-2;
    }
    #splash-container {
        width: 50%;
        height: auto;
        background: $panel-darken-2;
        border: thick $accent;
        padding: 2 4;
    }
    """
    def compose(self) -> ComposeResult:
        with Container(id="splash-container"):
            yield Label("JPAI Agentic AI", id="splash-title")
            yield Label("by JeelanPro™ AI team", id="splash-sub")
            yield LoadingIndicator()
            yield ProgressBar(total=100, show_eta=False)

    def on_mount(self):
        self.set_timer(0.5, self.update_progress)

    def update_progress(self):
        bar = self.query_one(ProgressBar)
        for i in range(101):
            time.sleep(0.01)
            bar.advance(1)
        self.dismiss()

# ═══════════════════════════════════════════════════════════
#  FILE EXPLORER WIDGET
# ═══════════════════════════════════════════════════════════
class FileExplorer(VerticalScroll):
    folder_path = reactive("", recompose=True)
    selected_file = reactive("")

    def compose(self) -> ComposeResult:
        yield Label("📁 File Explorer")
        yield Input(placeholder="Paste folder path...", id="explorer-path-input")
        with Horizontal():
            yield Button("Browse", id="explorer-browse-btn")
            yield Button("Refresh", id="explorer-refresh-btn")
        yield Label("Files:", id="explorer-file-label")
        yield ListView(id="file-list")

    def on_mount(self):
        self._populate_files()

    def watch_folder_path(self, path):
        self._populate_files()

    def _populate_files(self):
        list_view = self.query_one("#file-list", ListView)
        list_view.clear()
        if not self.folder_path or not Path(self.folder_path).is_dir():
            list_view.append(ListItem(Label("(No folder)")))
            return
        for p in Path(self.folder_path).iterdir():
            list_view.append(ListItem(Label(p.name)))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "explorer-browse-btn":
            path = self.query_one("#explorer-path-input", Input).value.strip()
            if path:
                self.folder_path = path
        elif event.button.id == "explorer-refresh-btn":
            self._populate_files()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item and isinstance(event.item, ListItem):
            name = event.item.query_one(Label).renderable
            full = Path(self.folder_path) / name
            if full.is_file():
                self.selected_file = str(full)
                # post selection to app
                self.app.handle_file_selected(str(full))

# ═══════════════════════════════════════════════════════════
#  WELCOME TAB
# ═══════════════════════════════════════════════════════════
class WelcomeTab(TabPane):
    def compose(self):
        yield Static("Welcome to JPAI Agentic AI\nSelect an option from the menu (☰ top right) to begin.", id="welcome")

# ═══════════════════════════════════════════════════════════
#  UNIFIED CHAT TAB (replaces all mode tabs)
# ═══════════════════════════════════════════════════════════
class UnifiedChatTab(TabPane):
    def __init__(self, dm: DataManager, api: ZhipuClient, app: JPAIApp, **kwargs):
        super().__init__(title="New Chat", **kwargs)
        self.dm = dm
        self.api = api
        self.app = app
        self.messages = []
        self.mode = "chat"
        self.chat_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._is_generating = False
        self._end_time = None
        self._phase = "IDLE"
        self._max_agent_steps = 25
        self._agent_step = 0
        self._longrun_active = False

    def compose(self) -> ComposeResult:
        yield Select(
            [(m, m) for m in ["Chat", "Agent", "Long Run", "Deep Think", "Vision", "Quick", "Structured"]],
            value="Chat", id="mode-select"
        )
        with VerticalScroll(id="chat-scroll"):
            yield Static("Start a conversation...", id="chat-placeholder")
        with Horizontal(id="input-bar"):
            yield Input(placeholder="Type your message...", id="chat-input")
            if self.mode == "vision":
                yield Input(placeholder="Image URL (optional)", id="vision-url")
            yield Button("Send", variant="success", id="send-btn")
            yield Button("Continue", variant="primary", id="continue-btn")
            yield Button("Re-run", id="rerun-btn")
            yield Button("Stop", variant="error", id="stop-btn")

    def on_mount(self):
        self.update_inputs()

    def update_inputs(self):
        bar = self.query_one("#input-bar", Horizontal)
        try:
            bar.query_one("#vision-url", Input)
            if self.mode != "vision":
                bar.query_one("#vision-url", Input).remove()
        except NoMatches:
            if self.mode == "vision":
                bar.mount(Input(placeholder="Image URL (optional)", id="vision-url"))

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "mode-select":
            self.mode = event.value.lower().replace(" ", "")
            self.update_inputs()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button.id
        if btn == "send-btn":
            self.send_message()
        elif btn == "continue-btn":
            self.continue_chat()
        elif btn == "rerun-btn":
            self.rerun_last()
        elif btn == "stop-btn":
            self._is_generating = False
            self._longrun_active = False

    def send_message(self):
        if self._is_generating:
            return
        inp = self.query_one("#chat-input", Input)
        text = inp.value.strip()
        if not text:
            return
        inp.value = ""
        try:
            self.query_one("#chat-placeholder").remove()
        except NoMatches:
            pass

        # Build user message (vision handled inside)
        user_msg = {"role": "user", "content": text}
        if self.mode == "vision":
            url_inp = self.query_one("#vision-url", Input)
            if url_inp.value.strip():
                user_msg["content"] = [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": url_inp.value.strip()}}
                ]
                url_inp.value = ""
        self.messages.append(user_msg)

        scroll = self.query_one("#chat-scroll", VerticalScroll)
        scroll.mount(Collapsible(Static(text), title="💬 You", collapsed=False))
        self._is_generating = True
        self.app.call_from_thread(self._update_scroll)
        self.app.enqueue_ai_task(self._generate_response)

    def continue_chat(self):
        if self._is_generating:
            return
        self.messages.append({"role": "user", "content": "Continue generating from where you left off."})
        self._is_generating = True
        self.app.enqueue_ai_task(self._generate_response)

    def rerun_last(self):
        if self._is_generating:
            return
        for i in range(len(self.messages)-1, -1, -1):
            if self.messages[i]["role"] == "user":
                self.messages = self.messages[:i+1]
                break
        self._is_generating = True
        self.app.enqueue_ai_task(self._generate_response)

    def _generate_response(self):
        """Runs in AI worker thread. UI updates via call_from_thread."""
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        start_time = time.time()
        full_response = ""
        thought_content = ""
        tool_calls = []
        tool_results = []
        total_tokens = 0
        model_used = self.dm.settings.get("model", "glm-4.7-flash")
        if self.mode == "vision":
            model_used = "glm-4.6v-flash"

        system = self.dm.get_system_prompt(self.mode)
        api_msgs = []
        if system:
            api_msgs.append({"role": "system", "content": system})
        api_msgs.extend(self.messages)

        schema = None
        if self.mode == "structured":
            schema = {"type": "json_object"}

        try:
            if self.mode == "agent":
                self._agent_step = 0
                while self._is_generating and self._agent_step < self._max_agent_steps:
                    self._agent_step += 1
                    step_response = ""
                    step_tools = []
                    for chunk in self.api.chat_stream(api_msgs, model=model_used, tools=self.dm.tools):
                        delta = get_delta(chunk)
                        cont = delta.get("content", "")
                        if cont:
                            step_response += cont
                        tc = delta.get("tool_calls", [])
                        if tc:
                            step_tools = tc
                    if not step_tools:
                        full_response = step_response
                        break
                    for tc in step_tools:
                        fn = tc.get("function", {})
                        name = fn.get("name", "")
                        args = json.loads(fn.get("arguments", "{}"))
                        result = execute_tool(self.app, name, args)
                        tool_calls.append(tc)
                        tool_results.append(result)
                        api_msgs.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result})
                    continue
            elif self.mode == "longrun":
                duration = 600  # default 10 min (can be extended)
                self._end_time = datetime.now() + timedelta(seconds=duration)
                self._phase = "PLAN"
                self._longrun_active = True
                while self._longrun_active and datetime.now() < self._end_time:
                    remaining = (self._end_time - datetime.now()).total_seconds()
                    remaining_str = f"{int(remaining//60)}:{int(remaining%60):02d}"
                    time_inject = {"role": "system", "content": f"TIME REMAINING: {remaining_str}. Phase: {self._phase}"}
                    extended = api_msgs + [time_inject]
                    response_part = ""
                    for chunk in self.api.chat_stream(extended, model=model_used):
                        delta = get_delta(chunk)
                        cont = delta.get("content", "")
                        if cont:
                            response_part += cont
                    api_msgs.append({"role": "assistant", "content": response_part})
                    if "task complete" in response_part.lower() or "✅" in response_part:
                        break
                    self._phase = "EXECUTE" if self._phase == "PLAN" else "EXECUTE"
                    time.sleep(1)
                full_response = "\n".join([m["content"] for m in api_msgs if m.get("role") == "assistant"])
            else:
                for chunk in self.api.chat_stream(
                    api_msgs, model=model_used,
                    thinking=(self.mode == "deepthink"),
                    response_format=schema
                ):
                    delta = get_delta(chunk)
                    reasoning = delta.get("reasoning_content", "")
                    cont = delta.get("content", "")
                    if reasoning:
                        thought_content += reasoning
                    if cont:
                        full_response += cont
                    usage = get_usage(chunk)
                    if usage:
                        total_tokens = usage.get("total_tokens", 0)
        except Exception as e:
            full_response = f"Error: {e}"

        gen_time = time.time() - start_time
        self.messages.append({"role": "assistant", "content": full_response})
        self.app.call_from_thread(
            self._finalize,
            full_response, thought_content, gen_time,
            total_tokens, model_used, tool_calls, tool_results
        )
        self._is_generating = False
        self.dm.save_chat(self.chat_id, self.messages, self.mode, model_used)

    def _finalize(self, content, thought, gen_time, tokens, model, tool_calls, results):
        """Called on main thread to display final response."""
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        parts = []
        if thought:
            parts.append(Collapsible(Static(thought), title="🧠 Reasoning", collapsed=False))
        parts.append(Collapsible(Static(content), title="🤖 Response", collapsed=False))
        if tool_calls:
            tool_body = "\n".join(
                [f"🔧 {tc['function']['name']}({tc['function']['arguments']}) → {r}"
                 for tc, r in zip(tool_calls, results)]
            )
            parts.append(Collapsible(Static(tool_body), title="🔧 Tool Calls", collapsed=True))
        meta = f"⏱ {gen_time:.1f}s · 📝 {tokens} tokens · 🤖 {model}"
        parts.append(Static(meta))
        scroll.mount(Vertical(*parts))
        scroll.mount(Button("Copy Response", id="copy-response"))
        scroll.scroll_end(animate=False)

# ═══════════════════════════════════════════════════════════
#  SETTINGS TAB (add command approval toggle)
# ═══════════════════════════════════════════════════════════
class SettingsTab(TabPane):
    def __init__(self, dm, **kwargs):
        super().__init__("⚙ Settings", **kwargs)
        self.dm = dm

    def compose(self):
        with VerticalScroll():
            yield Label("API Key")
            yield Input(self.dm.settings.get("api_key", ""), id="api-key-input", password=True)
            yield Button("Save Key", id="save-key-btn")
            yield Label("Model")
            yield Select([(m, m) for m in MODELS], value=self.dm.settings.get("model", "glm-4.7-flash"), id="model-select")
            yield Label("Temperature")
            yield Input(str(self.dm.settings.get("temperature", 0.7)), id="temp-input")
            yield Label("Max Tokens")
            yield Input(str(self.dm.settings.get("max_tokens", 4096)), id="tokens-input")
            yield Label("Require approval for AI commands")
            yield Select([("Yes", True), ("No", False)], value=self.dm.settings.get("require_command_approval", True), id="command-approval")
            yield Button("Save Settings", id="save-settings-btn")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save-settings-btn":
            self.dm.settings["model"] = self.query_one("#model-select", Select).value
            self.dm.settings["temperature"] = float(self.query_one("#temp-input", Input).value)
            self.dm.settings["max_tokens"] = int(self.query_one("#tokens-input", Input).value)
            self.dm.settings["require_command_approval"] = self.query_one("#command-approval", Select).value
            dm.save_settings()
        elif event.button.id == "save-key-btn":
            self.dm.set_api_key(self.query_one("#api-key-input", Input).value)

# ═══════════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════════
class JPAIApp(App):
    TITLE = "JPAI Agentic AI"
    SUB_TITLE = "by JeelanPro™ AI team"

    CSS = """
    Screen { background: #0b0f19; }
    #custom-header {
        height: 3;
        background: #0f172a;
        color: #38bdf8;
        padding: 0 1;
        layout: horizontal;
        align: center middle;
    }
    #custom-header .title {
        width: 1fr;
        text-style: bold;
        color: $accent;
    }
    #menu-btn {
        dock: right;
        margin: 0 1;
    }
    #file-explorer { width: 25%; height: 100%; border-right: solid $primary; background: #0d1321; }
    #main-area { width: 75%; height: 100%; }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self):
        super().__init__()
        self.dm = DataManager()
        self.api = ZhipuClient(self.dm)
        self._ai_queue = queue.Queue()
        self._worker_thread = None

    def compose(self):
        yield Container(
            Horizontal(
                Static("JPAI Agentic AI — JeelanPro™ AI team", classes="title"),
                Button("☰", id="menu-btn"),
            ),
            id="custom-header",
        )
        with Horizontal():
            with Container(id="file-explorer"):
                yield FileExplorer(id="file-explorer-widget")
            with Container(id="main-area"):
                yield TabbedContent(id="main-tabs")
        yield Footer()

    async def on_mount(self):
        # Start AI request queue worker (background thread)
        self._worker_thread = threading.Thread(target=self._ai_worker_loop, daemon=True)
        self._worker_thread.start()

        # Show fancy loading screen
        await self.push_screen(SplashScreen())

        # Load Welcome tab only
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.add_pane(WelcomeTab("🏠 Welcome", id="welcome-tab"))
        tabs.active = "welcome-tab"

    def _ai_worker_loop(self):
        """Process AI requests sequentially from the queue (runs in background thread)."""
        while True:
            func, args, kwargs = self._ai_queue.get()
            try:
                func(*args, **kwargs)
            except Exception as e:
                # Optionally log error
                pass
            finally:
                self._ai_queue.task_done()

    def enqueue_ai_task(self, func, *args, **kwargs):
        """Put a callable into the AI queue."""
        self._ai_queue.put((func, args, kwargs))

    def request_command_approval(self, command: str) -> bool:
        """
        Called from worker thread. Blocks until user approves/denies via modal.
        Returns True if approved, False otherwise.
        """
        result_event = threading.Event()
        result_holder = [False]

        def show_prompt():
            # Must be called from the main thread
            async def push_and_wait():
                from textual.screen import ModalScreen

                class ConfirmScreen(ModalScreen):
                    def compose(self):
                        yield Label(f"Allow AI to run this command?\n\n{command}")
                        yield Button("Yes", id="yes")
                        yield Button("No", id="no")

                    def on_button_pressed(self, ev):
                        self.dismiss(ev.button.id == "yes")

                # Push the screen and get result
                approved = await self.push_screen_wait(ConfirmScreen())
                result_holder[0] = approved
                result_event.set()

            self.post_message(push_and_wait())  # post_message isasync, but ok from call_from_thread

        self.call_from_thread(show_prompt)
        result_event.wait()
        return result_holder[0]

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "menu-btn":
            await self.show_menu()

    async def show_menu(self):
        """Open the main menu as a pop‑up."""
        from textual.screen import ModalScreen

        class MenuScreen(ModalScreen):
            def compose(self):
                yield ListView(
                    ListItem(Label("New Chat")),
                    ListItem(Label("Settings")),
                    ListItem(Label("History")),
                    ListItem(Label("Close")),
                )
            def on_list_view_selected(self, ev):
                self.dismiss(ev.item.query_one(Label).renderable)

        choice = await self.push_screen_wait(MenuScreen())
        tabs = self.query_one("#main-tabs", TabbedContent)

        if choice == "New Chat":
            tab = UnifiedChatTab(self.dm, self.api, self)
            tabs.add_pane(tab)
            tabs.active = tab.id
        elif choice == "Settings":
            try:
                tabs.query_one("#settings-tab", TabPane)
            except NoMatches:
                tabs.add_pane(SettingsTab(self.dm, id="settings-tab"))
            tabs.active = "settings-tab"
        elif choice == "History":
            try:
                tabs.query_one("#history-tab", TabPane)
            except NoMatches:
                hist_tab = TabPane("📋 History", id="history-tab")
                hist_tab.compose = lambda: [RichLog()]
                tabs.add_pane(hist_tab)
            tabs.active = "history-tab"
        elif choice == "Close":
            pass

    def handle_file_selected(self, path):
        """Open a file viewer tab when a file is selected in the explorer."""
        tabs = self.query_one("#main-tabs", TabbedContent)
        try:
            tabs.query_one(f"#file-view-{path}", TabPane)
        except NoMatches:
            content = Path(path).read_text(encoding="utf-8", errors="replace")[:5000]
            viewer = TabPane(f"📄 {Path(path).name}", id=f"file-view-{path}")
            viewer.mount(TextArea(content, read_only=True))
            tabs.add_pane(viewer)
        tabs.active = f"file-view-{path}"

# ═══════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = JPAIApp()
    app.run()