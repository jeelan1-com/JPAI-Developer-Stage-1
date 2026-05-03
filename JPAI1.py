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

import httpx

from textual.app import App, ComposeResult
from textual.widgets import (
    Header, Footer, TabbedContent, TabPane,
    Input, Button, Static, Collapsible,
    RichLog, Select, TextArea,
    Label, DirectoryTree, Tree, LoadingIndicator,
    ContentSwitcher, ProgressBar,
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
    "glm-4.5-flash",
    "glm-4.7-flash", 
    "glm-4.6v-flash",
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


# ═══════════════════════════════════════════════════════════
#  SYSTEM PROMPTS
# ═══════════════════════════════════════════════════════════

DEFAULT_SYSTEM_PROMPTS = {
    "chat": (
        "You are JFO AI, a helpful, knowledgeable, and honest assistant. "
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
            "description": "Run a shell command and return its output",
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

    def save_chat(self, chat_id: str, messages: list, mode: str, model: str):
        entry = {
            "id": chat_id, "mode": mode, "model": model,
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

def execute_tool(name: str, arguments: dict) -> str:
    if name == "search_web":
        return f"[Search results for '{arguments.get('query', '')}' — simulated]"
    elif name == "read_file":
        try:
            with open(arguments.get("path", ""), "r", encoding="utf-8") as f:
                return f.read()[:5000]
        except Exception as e:
            return f"Error: {e}"
    elif name == "write_file":
        try:
            with open(arguments.get("path", ""), "w", encoding="utf-8") as f:
                f.write(arguments.get("content", ""))
            return f"Wrote to {arguments.get('path')}"
        except Exception as e:
            return f"Error: {e}"
    elif name == "run_command":
        try:
            return os.popen(arguments.get("command", "")).read()[:5000] or "(no output)"
        except Exception as e:
            return f"Error: {e}"
    elif name == "calculate":
        expr = arguments.get("expression", "")
        try:
            if all(c in "0123456789+-*/.() " for c in expr):
                return str(eval(expr))
            return "Error: disallowed characters"
        except Exception as e:
            return f"Error: {e}"
    return f"Unknown tool: {name}"


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
#  CUSTOM WIDGETS — ALL COLLAPSIBLE USE title= KEYWORD
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


class UserMessageBlock(Collapsible):
    def __init__(self, content: str, **kwargs):
        preview = content[:60].replace("\n", " ")
        if len(content) > 60:
            preview += "..."
        super().__init__(
            Static(content),
            title=f"💬 You: {preview}",
            collapsed=False,
            **kwargs,
        )


class ToolCallBlock(Collapsible):
    def __init__(self, calls: list, results: list, **kwargs):
        body_parts = []
        for i, call in enumerate(calls):
            fn_name = call.get("function", {}).get("name", "unknown")
            fn_args = call.get("function", {}).get("arguments", "{}")
            result_text = results[i] if i < len(results) else "(pending)"
            body_parts.append(f"┌ {fn_name}({fn_args})\n└ → {result_text[:500]}")
        super().__init__(
            Static("\n\n".join(body_parts)),
            title=f"🔧 Tool Calls ({len(calls)})",
            collapsed=True,
            **kwargs,
        )


class AIResponseBlock(Collapsible):
    def __init__(self, content: str, metadata: MetadataBar,
                 tool_block: Optional[ToolCallBlock] = None, **kwargs):
        children = [Static(content)]
        if tool_block:
            children.append(tool_block)
        children.append(metadata)
        super().__init__(
            Vertical(*children),
            title="🤖 AI Response",
            collapsed=False,
            **kwargs,
        )


class ContinueButton(Button):
    def __init__(self, chat_tab_ref, **kwargs):
        super().__init__("Continue ↪", variant="primary", **kwargs)
        self.chat_tab_ref = chat_tab_ref


# ═══════════════════════════════════════════════════════════
#  CHAT TAB
# ═══════════════════════════════════════════════════════════

class ChatTab(TabPane):
    def __init__(self, dm: DataManager, api: ZhipuClient, **kwargs):
        super().__init__("💬 Chat", **kwargs)
        self.dm = dm
        self.api = api
        self.messages = []
        self.chat_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._is_generating = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="chat-scroll"):
            yield Static("Start a conversation by typing below.", id="chat-placeholder")
        with Horizontal(id="chat-input-bar"):
            yield Input(placeholder="Type your message...", id="chat-input")
            yield Button("Send", variant="success", id="chat-send-btn")
            yield Button("Clear", variant="default", id="chat-clear-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "chat-send-btn":
            self.action_send_message()
        elif event.button.id == "chat-clear-btn":
            self.query_one("#chat-input", Input).value = ""

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "chat-input":
            self.action_send_message()

    def action_send_message(self):
        if self._is_generating:
            return
        input_widget = self.query_one("#chat-input", Input)
        text = input_widget.value.strip()
        if not text:
            return
        input_widget.value = ""
        try:
            self.query_one("#chat-placeholder").remove()
        except Exception:
            pass

        self.messages.append({"role": "user", "content": text})
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        scroll.mount(UserMessageBlock(text))
        self._generate_response()

    def continue_generation(self):
        if self._is_generating:
            return
        self.messages.append({"role": "user", "content": "Continue generating from where you left off."})
        self._generate_response()

    @work(thread=True)
    def _generate_response(self):
        self._is_generating = True
        app = self.app
        app.call_from_thread(self._show_spinner)

        system_prompt = self.dm.get_system_prompt("chat")
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(self.messages)

        start_time = time.time()
        full_response = ""
        total_tokens = 0

        try:
            for chunk in self.api.chat_stream(api_messages):
                delta = get_delta(chunk)
                content_piece = delta.get("content", "")
                if content_piece:
                    if not full_response:
                        app.call_from_thread(self._start_streaming)
                    full_response += content_piece
                    app.call_from_thread(self._stream_text, content_piece)
                usage = get_usage(chunk)
                if usage:
                    total_tokens = usage.get("total_tokens", 0)
        except Exception as e:
            full_response = f"Error: {e}"
            app.call_from_thread(self._remove_spinner)

        gen_time = time.time() - start_time
        model = self.dm.settings.get("model", "glm-4.7-flash")
        self.messages.append({"role": "assistant", "content": full_response})
        app.call_from_thread(self._finalize, full_response, gen_time, total_tokens, model)
        self._is_generating = False

    def _show_spinner(self):
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        self._spinner = SpinnerWidget("Thinking")
        scroll.mount(self._spinner)
        scroll.scroll_end(animate=False)

    def _remove_spinner(self):
        try:
            self._spinner.stop()
            self._spinner.remove()
        except Exception:
            pass

    def _start_streaming(self):
        self._remove_spinner()
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        self._stream_static = Static("")
        self._stream_collapsible = Collapsible(
            self._stream_static,
            title="🤖 AI Response",
            collapsed=False,
        )
        scroll.mount(self._stream_collapsible)
        scroll.scroll_end(animate=False)

    def _stream_text(self, new_text: str):
        if hasattr(self, '_stream_static') and self._stream_static:
            current = self._stream_static.renderable or ""
            self._stream_static.update(current + new_text)
            self.query_one("#chat-scroll", VerticalScroll).scroll_end(animate=False)

    def _finalize(self, content: str, gen_time: float, tokens: int, model: str):
        scroll = self.query_one("#chat-scroll", VerticalScroll)
        try:
            self._stream_collapsible.remove()
        except Exception:
            pass

        metadata = MetadataBar(gen_time, tokens, model)
        response_block = AIResponseBlock(content, metadata)
        continue_btn = ContinueButton(self)
        scroll.mount(Vertical(response_block, continue_btn))
        scroll.scroll_end(animate=False)
        self.dm.save_chat(self.chat_id, self.messages, "chat", model)


# ═══════════════════════════════════════════════════════════
#  AGENT TAB
# ═══════════════════════════════════════════════════════════

class AgentTab(TabPane):
    def __init__(self, dm: DataManager, api: ZhipuClient, **kwargs):
        super().__init__("🤖 Agent", **kwargs)
        self.dm = dm
        self.api = api
        self.messages = []
        self.chat_id = datetime.now().strftime("%Y%m%d_%H%M%S_agent")
        self._is_running = False
        self.step_count = 0
        self.max_steps = 25

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="agent-scroll"):
            yield Static("Give the agent a task. It will use tools to accomplish it.", id="agent-placeholder")
        with Horizontal(id="agent-input-bar"):
            yield Input(placeholder="Describe a task for the agent...", id="agent-input")
            yield Button("Start", variant="success", id="agent-start-btn")
            yield Button("Stop", variant="error", id="agent-stop-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "agent-start-btn":
            self._start_agent()
        elif event.button.id == "agent-stop-btn":
            self._is_running = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "agent-input":
            self._start_agent()

    def _start_agent(self):
        if self._is_running:
            return
        input_widget = self.query_one("#agent-input", Input)
        task = input_widget.value.strip()
        if not task:
            return
        input_widget.value = ""
        try:
            self.query_one("#agent-placeholder").remove()
        except Exception:
            pass
        self.messages = []
        system_prompt = self.dm.get_system_prompt("agent")
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})
        self.messages.append({"role": "user", "content": task})
        self.step_count = 0
        self._is_running = True
        self._agent_loop()

    @work(thread=True)
    def _agent_loop(self):
        app = self.app
        tools = self.dm.tools

        while self._is_running and self.step_count < self.max_steps:
            self.step_count += 1
            start_time = time.time()
            app.call_from_thread(self._add_step_header, self.step_count)

            full_response = ""
            tool_calls_accum = []
            total_tokens = 0

            try:
                for chunk in self.api.chat_stream(self.messages, tools=tools):
                    delta = get_delta(chunk)
                    content_piece = delta.get("content", "")
                    if content_piece:
                        full_response += content_piece
                        app.call_from_thread(self._stream_text, content_piece)
                    tc_list = delta.get("tool_calls", [])
                    for tc in tc_list:
                        idx = tc.get("index", 0)
                        while idx >= len(tool_calls_accum):
                            tool_calls_accum.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        if tc.get("id"):
                            tool_calls_accum[idx]["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            tool_calls_accum[idx]["function"]["name"] += fn["name"]
                        if fn.get("arguments"):
                            tool_calls_accum[idx]["function"]["arguments"] += fn["arguments"]
                    usage = get_usage(chunk)
                    if usage:
                        total_tokens = usage.get("total_tokens", 0)
            except Exception as e:
                full_response = f"Error: {e}"

            gen_time = time.time() - start_time
            model = self.dm.settings.get("model", "glm-4.7-flash")

            assistant_msg = {"role": "assistant", "content": full_response}
            if tool_calls_accum:
                assistant_msg["tool_calls"] = tool_calls_accum
            self.messages.append(assistant_msg)

            tool_results = []
            if tool_calls_accum:
                for tc in tool_calls_accum:
                    fn_name = tc["function"]["name"]
                    try:
                        fn_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        fn_args = {}
                    result = execute_tool(fn_name, fn_args)
                    tool_results.append(result)
                    self.messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "content": result})

            app.call_from_thread(self._finalize_step, full_response, gen_time, total_tokens, model, tool_calls_accum, tool_results)

            if not tool_calls_accum:
                self._is_running = False
                break

        self._is_running = False
        app.call_from_thread(self._add_completion_message)

    def _add_step_header(self, step: int):
        scroll = self.query_one("#agent-scroll", VerticalScroll)
        scroll.mount(Static(f"━━━ Step {step}/{self.max_steps} ━━━"))
        self._step_stream = Static("")
        scroll.mount(self._step_stream)
        scroll.scroll_end(animate=False)

    def _stream_text(self, new_text: str):
        if hasattr(self, '_step_stream') and self._step_stream:
            current = self._step_stream.renderable or ""
            self._step_stream.update(current + new_text)
            self.query_one("#agent-scroll", VerticalScroll).scroll_end(animate=False)

    def _finalize_step(self, content, gen_time, tokens, model, tool_calls, tool_results):
        scroll = self.query_one("#agent-scroll", VerticalScroll)
        try:
            self._step_stream.remove()
        except Exception:
            pass
        metadata = MetadataBar(gen_time, tokens, model, tool_calls=len(tool_calls))
        tool_block = ToolCallBlock(tool_calls, tool_results) if tool_calls else None
        response_block = AIResponseBlock(content, metadata, tool_block)
        scroll.mount(response_block)
        scroll.scroll_end(animate=False)

    def _add_completion_message(self):
        scroll = self.query_one("#agent-scroll", VerticalScroll)
        scroll.mount(Static("✅ Agent finished."))
        self.dm.save_chat(self.chat_id, self.messages, "agent", self.dm.settings.get("model", "glm-4.7-flash"))


# ═══════════════════════════════════════════════════════════
#  LONG RUN TAB
# ═══════════════════════════════════════════════════════════

class LongRunTab(TabPane):
    def __init__(self, dm: DataManager, api: ZhipuClient, **kwargs):
        super().__init__("⏱ Long Run", **kwargs)
        self.dm = dm
        self.api = api
        self.messages = []
        self.chat_id = datetime.now().strftime("%Y%m%d_%H%M%S_longrun")
        self._is_running = False
        self._end_time = None
        self._phase = "IDLE"

    def compose(self) -> ComposeResult:
        yield Label("Duration:")
        yield Select([(d, d) for d in DURATION_OPTIONS], value="10 min", id="lr-duration")
        with VerticalScroll(id="lr-scroll"):
            yield Static("Set a duration, describe a task, and click Start.", id="lr-placeholder")
        yield Label("Progress:")
        yield Static("No active task", id="lr-progress")
        yield Label("Time Remaining:")
        yield Static("--:--", id="lr-timer")
        with Horizontal(id="lr-input-bar"):
            yield Input(placeholder="Describe the task...", id="lr-input")
            yield Button("Start", variant="success", id="lr-start-btn")
            yield Button("Stop", variant="error", id="lr-stop-btn")
            yield Button("Pause", variant="warning", id="lr-pause-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "lr-start-btn":
            self._start_long_run()
        elif event.button.id == "lr-stop-btn":
            self._is_running = False
        elif event.button.id == "lr-pause-btn":
            self._is_running = False

    def _parse_duration(self, text: str) -> int:
        try:
            return int(text.strip().split()[0]) * 60
        except (ValueError, IndexError):
            return 600

    def _start_long_run(self):
        if self._is_running:
            return
        input_widget = self.query_one("#lr-input", Input)
        task = input_widget.value.strip()
        if not task:
            return
        input_widget.value = ""
        try:
            self.query_one("#lr-placeholder").remove()
        except Exception:
            pass
        duration_secs = self._parse_duration(str(self.query_one("#lr-duration", Select).value))
        self._end_time = datetime.now() + timedelta(seconds=duration_secs)
        self.messages = []
        system_prompt = self.dm.get_system_prompt("longrun")
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})
        self.messages.append({"role": "user", "content": task})
        self._phase = "PLAN"
        self._is_running = True
        self._long_run_loop()

    @work(thread=True)
    def _long_run_loop(self):
        app = self.app
        while self._is_running:
            remaining = self._end_time - datetime.now()
            if remaining.total_seconds() <= 0:
                break
            remaining_str = f"{int(remaining.total_seconds() // 60)}:{int(remaining.total_seconds() % 60):02d}"
            time_inject = {"role": "system", "content": f"⏱ TIME REMAINING: {remaining_str}. Current phase: {self._phase}. Continue working. If time is running low, wrap up."}
            api_messages = list(self.messages)
            api_messages.append(time_inject)
            start_time = time.time()
            full_response = ""
            total_tokens = 0

            app.call_from_thread(self._update_timer, remaining_str)
            app.call_from_thread(self._update_progress)
            app.call_from_thread(self._add_phase_header, self._phase)

            try:
                for chunk in self.api.chat_stream(api_messages):
                    delta = get_delta(chunk)
                    content_piece = delta.get("content", "")
                    if content_piece:
                        full_response += content_piece
                        app.call_from_thread(self._stream_text, content_piece)
                    usage = get_usage(chunk)
                    if usage:
                        total_tokens = usage.get("total_tokens", 0)
            except Exception as e:
                full_response = f"Error: {e}"

            gen_time = time.time() - start_time
            model = self.dm.settings.get("model", "glm-4.7-flash")
            self.messages.append({"role": "assistant", "content": full_response})
            self._advance_phase(full_response)
            app.call_from_thread(self._finalize_step, full_response, gen_time, total_tokens, model)
            if "task complete" in full_response.lower() or ("✅" in full_response and self._phase == "COMPLETE"):
                self._is_running = False
                break
            time.sleep(0.5)

        self._is_running = False
        app.call_from_thread(self._mark_complete)

    def _advance_phase(self, response: str):
        if self._phase == "PLAN":
            if "📋" in response or len(response) > 200:
                self._phase = "THINK"
        elif self._phase == "THINK":
            if "adjust" in response.lower() or "revise" in response.lower() or len(response) > 300:
                self._phase = "FIX"
        elif self._phase == "FIX":
            self._phase = "EXECUTE"
        elif self._phase == "EXECUTE":
            if not any("⬜" in l or "🔄" in l for l in response.split("\n")):
                self._phase = "COMPLETE"

    def _update_timer(self, text: str):
        try: self.query_one("#lr-timer", Static).update(f"⏱ {text}")
        except Exception: pass

    def _update_progress(self):
        try: self.query_one("#lr-progress", Static).update(f"Phase: {self._phase} · Messages: {len(self.messages)}")
        except Exception: pass

    def _add_phase_header(self, phase: str):
        scroll = self.query_one("#lr-scroll", VerticalScroll)
        icons = {"PLAN": "📋", "THINK": "🧠", "FIX": "🔧", "EXECUTE": "⚡", "COMPLETE": "✅"}
        scroll.mount(Static(f"\n{icons.get(phase, '📌')} ━━━ Phase: {phase} ━━━\n"))
        self._lr_stream = Static("")
        scroll.mount(self._lr_stream)
        scroll.scroll_end(animate=False)

    def _stream_text(self, new_text: str):
        if hasattr(self, '_lr_stream') and self._lr_stream:
            current = self._lr_stream.renderable or ""
            self._lr_stream.update(current + new_text)
            self.query_one("#lr-scroll", VerticalScroll).scroll_end(animate=False)

    def _finalize_step(self, content, gen_time, tokens, model):
        scroll = self.query_one("#lr-scroll", VerticalScroll)
        try: self._lr_stream.remove()
        except Exception: pass
        scroll.mount(AIResponseBlock(content, MetadataBar(gen_time, tokens, model)))
        scroll.scroll_end(animate=False)
        self.dm.save_chat(self.chat_id, self.messages, "longrun", model)

    def _mark_complete(self):
        scroll = self.query_one("#lr-scroll", VerticalScroll)
        scroll.mount(Static("\n🏁 Long run task finished.\n"))
        try:
            self.query_one("#lr-timer", Static).update("Done!")
            self.query_one("#lr-progress", Static).update("Phase: COMPLETE")
        except Exception: pass


# ═══════════════════════════════════════════════════════════
#  DEEP THINK TAB
# ═══════════════════════════════════════════════════════════

class DeepThinkTab(TabPane):
    def __init__(self, dm: DataManager, api: ZhipuClient, **kwargs):
        super().__init__("🧠 Deep Think", **kwargs)
        self.dm = dm
        self.api = api
        self.messages = []
        self.chat_id = datetime.now().strftime("%Y%m%d_%H%M%S_think")
        self._is_generating = False
        self._thought_mounted = False
        self._answer_mounted = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="think-scroll"):
            yield Static("Ask a complex question. The AI will show its reasoning before answering.", id="think-placeholder")
        with Horizontal(id="think-input-bar"):
            yield Input(placeholder="Ask something that requires deep reasoning...", id="think-input")
            yield Button("Think", variant="success", id="think-send-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "think-send-btn":
            self._send()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "think-input":
            self._send()

    def _send(self):
        if self._is_generating:
            return
        input_widget = self.query_one("#think-input", Input)
        text = input_widget.value.strip()
        if not text:
            return
        input_widget.value = ""
        try: self.query_one("#think-placeholder").remove()
        except Exception: pass
        self.messages.append({"role": "user", "content": text})
        self.query_one("#think-scroll", VerticalScroll).mount(UserMessageBlock(text))
        self._thought_mounted = False
        self._answer_mounted = False
        self._generate()

    @work(thread=True)
    def _generate(self):
        self._is_generating = True
        app = self.app
        app.call_from_thread(self._show_spinner)

        system_prompt = self.dm.get_system_prompt("deepthink")
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(self.messages)

        start_time = time.time()
        full_response = ""
        thought_content = ""
        total_tokens = 0

        try:
            for chunk in self.api.chat_stream(api_messages, thinking=True):
                delta = get_delta(chunk)
                reasoning = delta.get("reasoning_content", "")
                if reasoning:
                    thought_content += reasoning
                    if not self._thought_mounted:
                        app.call_from_thread(self._mount_thought_block)
                        self._thought_mounted = True
                    app.call_from_thread(self._stream_thought, reasoning)
                content_piece = delta.get("content", "")
                if content_piece:
                    full_response += content_piece
                    if not self._answer_mounted:
                        app.call_from_thread(self._mount_answer_block)
                        self._answer_mounted = True
                    app.call_from_thread(self._stream_answer, content_piece)
                usage = get_usage(chunk)
                if usage:
                    total_tokens = usage.get("total_tokens", 0)
        except Exception as e:
            full_response = f"Error: {e}"

        gen_time = time.time() - start_time
        model = self.dm.settings.get("model", "glm-4.7-flash")
        self.messages.append({"role": "assistant", "content": full_response})
        app.call_from_thread(self._finalize, full_response, thought_content, gen_time, total_tokens, model)
        self._is_generating = False

    def _show_spinner(self):
        scroll = self.query_one("#think-scroll", VerticalScroll)
        self._spinner = SpinnerWidget("Thinking deeply")
        scroll.mount(self._spinner)
        scroll.scroll_end(animate=False)

    def _mount_thought_block(self):
        try: self._spinner.stop(); self._spinner.remove()
        except Exception: pass
        scroll = self.query_one("#think-scroll", VerticalScroll)
        self._thought_static = Static("")
        self._thought_col = Collapsible(self._thought_static, title="🧠 Reasoning", collapsed=False)
        scroll.mount(self._thought_col)
        scroll.scroll_end(animate=False)

    def _mount_answer_block(self):
        scroll = self.query_one("#think-scroll", VerticalScroll)
        self._answer_static = Static("")
        self._answer_col = Collapsible(self._answer_static, title="📌 Conclusion", collapsed=False)
        scroll.mount(self._answer_col)
        scroll.scroll_end(animate=False)

    def _stream_thought(self, text: str):
        if hasattr(self, '_thought_static') and self._thought_static:
            current = self._thought_static.renderable or ""
            self._thought_static.update(current + text)
            self.query_one("#think-scroll", VerticalScroll).scroll_end(animate=False)

    def _stream_answer(self, text: str):
        if hasattr(self, '_answer_static') and self._answer_static:
            current = self._answer_static.renderable or ""
            self._answer_static.update(current + text)
            self.query_one("#think-scroll", VerticalScroll).scroll_end(animate=False)

    def _finalize(self, content, thought, gen_time, tokens, model):
        if not self._thought_mounted and not self._answer_mounted:
            try: self._spinner.stop(); self._spinner.remove()
            except Exception: pass
            scroll = self.query_one("#think-scroll", VerticalScroll)
            if thought:
                scroll.mount(Collapsible(Static(thought), title="🧠 Reasoning", collapsed=False))
            scroll.mount(Collapsible(Static(content), title="📌 Conclusion", collapsed=False))

        scroll = self.query_one("#think-scroll", VerticalScroll)
        scroll.mount(MetadataBar(gen_time, tokens, model, thought_tokens=tokens // 2 if thought else 0))
        scroll.scroll_end(animate=False)
        self.dm.save_chat(self.chat_id, self.messages, "deepthink", model)


# ═══════════════════════════════════════════════════════════
#  STRUCTURED TAB
# ═══════════════════════════════════════════════════════════

class StructuredTab(TabPane):
    def __init__(self, dm: DataManager, api: ZhipuClient, **kwargs):
        super().__init__("📐 Structured", **kwargs)
        self.dm = dm
        self.api = api
        self._is_generating = False

    def compose(self) -> ComposeResult:
        yield Label("JSON Schema:")
        yield TextArea('{"type":"object","properties":{"answer":{"type":"string"},"confidence":{"type":"number"}}}', id="struct-schema")
        with VerticalScroll(id="struct-scroll"):
            yield Static("Define a schema and send a request. The AI will respond with matching JSON.", id="struct-placeholder")
        with Horizontal(id="struct-input-bar"):
            yield Input(placeholder="Your request...", id="struct-input")
            yield Button("Generate", variant="success", id="struct-send-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "struct-send-btn":
            self._send()

    def _send(self):
        if self._is_generating:
            return
        input_widget = self.query_one("#struct-input", Input)
        text = input_widget.value.strip()
        if not text:
            return
        input_widget.value = ""
        try: self.query_one("#struct-placeholder").remove()
        except Exception: pass
        schema_text = self.query_one("#struct-schema", TextArea).text
        try: schema = json.loads(schema_text)
        except json.JSONDecodeError: schema = None
        system_prompt = self.dm.get_system_prompt("structured")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if schema:
            messages.append({"role": "system", "content": f"Respond in this JSON schema: {json.dumps(schema)}"})
        messages.append({"role": "user", "content": text})
        self._is_generating = True
        self._generate(messages)

    @work(thread=True)
    def _generate(self, messages):
        app = self.app
        start_time = time.time()
        full_response = ""
        try:
            for chunk in self.api.chat_stream(messages, response_format={"type": "json_object"}):
                delta = get_delta(chunk)
                if delta.get("content"):
                    full_response += delta["content"]
        except Exception as e:
            full_response = f"Error: {e}"
        gen_time = time.time() - start_time
        model = self.dm.settings.get("model", "glm-4.7-flash")
        app.call_from_thread(self._show_result, full_response, gen_time, model)
        self._is_generating = False

    def _show_result(self, content, gen_time, model):
        scroll = self.query_one("#struct-scroll", VerticalScroll)
        scroll.mount(AIResponseBlock(content, MetadataBar(gen_time, 0, model)))
        scroll.scroll_end(animate=False)


# ═══════════════════════════════════════════════════════════
#  VISION TAB
# ═══════════════════════════════════════════════════════════

class VisionTab(TabPane):
    def __init__(self, dm: DataManager, api: ZhipuClient, **kwargs):
        super().__init__("👁 Vision", **kwargs)
        self.dm = dm
        self.api = api
        self._is_generating = False

    def compose(self) -> ComposeResult:
        yield Label("Image URL:")
        yield Input(placeholder="https://example.com/image.jpg", id="vision-url")
        with VerticalScroll(id="vision-scroll"):
            yield Static("Provide an image URL and ask a question about it.", id="vision-placeholder")
        with Horizontal(id="vision-input-bar"):
            yield Input(placeholder="What do you see in this image?", id="vision-input")
            yield Button("Analyze", variant="success", id="vision-send-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "vision-send-btn":
            self._send()

    def _send(self):
        if self._is_generating:
            return
        url = self.query_one("#vision-url", Input).value.strip()
        text = self.query_one("#vision-input", Input).value.strip()
        if not text:
            return
        self.query_one("#vision-input", Input).value = ""
        try: self.query_one("#vision-placeholder").remove()
        except Exception: pass
        system_prompt = self.dm.get_system_prompt("vision")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if url:
            messages.append({"role": "user", "content": [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": url}}]})
        else:
            messages.append({"role": "user", "content": text})
        self._is_generating = True
        self._generate(messages)

    @work(thread=True)
    def _generate(self, messages):
        app = self.app
        start_time = time.time()
        full_response = ""
        try:
            for chunk in self.api.chat_stream(messages, model="glm-4.6v-flash"):
                delta = get_delta(chunk)
                if delta.get("content"):
                    full_response += delta["content"]
        except Exception as e:
            full_response = f"Error: {e}"
        gen_time = time.time() - start_time
        app.call_from_thread(self._show_result, full_response, gen_time)
        self._is_generating = False

    def _show_result(self, content, gen_time):
        scroll = self.query_one("#vision-scroll", VerticalScroll)
        scroll.mount(AIResponseBlock(content, MetadataBar(gen_time, 0, "glm-4.6v-flash")))
        scroll.scroll_end(animate=False)


# ═══════════════════════════════════════════════════════════
#  QUICK TAB
# ═══════════════════════════════════════════════════════════

class QuickTab(TabPane):
    def __init__(self, dm: DataManager, api: ZhipuClient, **kwargs):
        super().__init__("🎯 Quick", **kwargs)
        self.dm = dm
        self.api = api
        self._is_generating = False

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="quick-scroll"):
            yield Static("Ask anything. Get a fast, direct answer.", id="quick-placeholder")
        with Horizontal(id="quick-input-bar"):
            yield Input(placeholder="Quick question...", id="quick-input")
            yield Button("Ask", variant="success", id="quick-send-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quick-send-btn":
            self._send()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "quick-input":
            self._send()

    def _send(self):
        if self._is_generating:
            return
        input_widget = self.query_one("#quick-input", Input)
        text = input_widget.value.strip()
        if not text:
            return
        input_widget.value = ""
        try: self.query_one("#quick-placeholder").remove()
        except Exception: pass
        system_prompt = self.dm.get_system_prompt("quick")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": text})
        self._is_generating = True
        self._generate(messages, text)

    @work(thread=True)
    def _generate(self, messages, original_text):
        app = self.app
        start_time = time.time()
        full_response = ""
        try:
            for chunk in self.api.chat_stream(messages):
                delta = get_delta(chunk)
                if delta.get("content"):
                    full_response += delta["content"]
        except Exception as e:
            full_response = f"Error: {e}"
        gen_time = time.time() - start_time
        model = self.dm.settings.get("model", "glm-4.7-flash")
        app.call_from_thread(self._show_result, original_text, full_response, gen_time, model)
        self._is_generating = False

    def _show_result(self, question, answer, gen_time, model):
        scroll = self.query_one("#quick-scroll", VerticalScroll)
        scroll.mount(UserMessageBlock(question))
        scroll.mount(AIResponseBlock(answer, MetadataBar(gen_time, 0, model)))
        scroll.scroll_end(animate=False)


# ═══════════════════════════════════════════════════════════
#  SETTINGS TAB — WITH PASTE SUPPORT
# ═══════════════════════════════════════════════════════════

class SettingsTab(TabPane):
    def __init__(self, dm: DataManager, **kwargs):
        super().__init__("⚙ Settings", **kwargs)
        self.dm = dm

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="settings-scroll"):
            yield Label("─── API Key ───")
            yield Label("Click '📋 Paste from Clipboard' to paste your key from Ctrl+C.\nOr click '📁 Load from File' to read Data/api_key.txt")
            yield Input(placeholder="API key will appear here...", id="settings-api-key", password=True)
            with Horizontal():
                yield Button("📋 Paste from Clipboard", variant="primary", id="settings-paste-clipboard")
                yield Button("📁 Load from File", variant="default", id="settings-load-file")
                yield Button("👁 Show/Hide", id="settings-toggle-key")
                yield Button("💾 Save Key", variant="success", id="settings-save-key")
            yield Static("—", id="settings-key-status")

            yield Label("")
            yield Label("─── Model & Parameters ───")
            yield Label("Default Model:")
            yield Select([(m, m) for m in MODELS], value=self.dm.settings.get("model", "glm-4.7-flash"), id="settings-model")
            yield Label("Temperature (0.0 to 1.0):")
            yield Input(value=str(self.dm.settings.get("temperature", 0.7)), id="settings-temp")
            yield Label("Max Tokens:")
            yield Input(value=str(self.dm.settings.get("max_tokens", 4096)), id="settings-tokens")

            yield Label("")
            yield Label("─── System Prompts (editable per mode) ───")
            yield Select([(k, k) for k in DEFAULT_SYSTEM_PROMPTS.keys()], value="chat", id="settings-prompt-mode")
            yield Button("Load Prompt", id="settings-load-prompt")
            yield TextArea(id="settings-prompt-editor")
            with Horizontal():
                yield Button("Save Prompt", variant="success", id="settings-save-prompt")
                yield Button("Reset to Default", variant="warning", id="settings-reset-prompt")

            yield Label("")
            yield Label("─── Tool Definitions ───")
            yield TextArea(json.dumps(self.dm.tools, indent=2), id="settings-tools-editor")
            yield Button("Save Tools", variant="success", id="settings-save-tools")

    def on_mount(self):
        self.query_one("#settings-api-key", Input).value = self.dm.settings.get("api_key", "")
        self._update_key_status()
        self._load_prompt("chat")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "settings-paste-clipboard":
            clip = read_clipboard()
            if clip:
                self.query_one("#settings-api-key", Input).value = clip
                self.dm.set_api_key(clip)
                self._update_key_status()
        elif btn_id == "settings-load-file":
            if API_KEY_FILE.exists():
                try:
                    key = API_KEY_FILE.read_text(encoding="utf-8").strip()
                    if key:
                        self.query_one("#settings-api-key", Input).value = key
                        self.dm.set_api_key(key)
                        self._update_key_status()
                except Exception:
                    pass
        elif btn_id == "settings-toggle-key":
            key_input = self.query_one("#settings-api-key", Input)
            key_input.password = not key_input.password
        elif btn_id == "settings-save-key":
            key = self.query_one("#settings-api-key", Input).value.strip()
            self.dm.set_api_key(key)
            self._update_key_status()
        elif btn_id == "settings-load-prompt":
            self._load_prompt(str(self.query_one("#settings-prompt-mode", Select).value))
        elif btn_id == "settings-save-prompt":
            mode = str(self.query_one("#settings-prompt-mode", Select).value)
            self.dm.set_system_prompt(mode, self.query_one("#settings-prompt-editor", TextArea).text)
        elif btn_id == "settings-reset-prompt":
            mode = str(self.query_one("#settings-prompt-mode", Select).value)
            default = DEFAULT_SYSTEM_PROMPTS.get(mode, "")
            self.query_one("#settings-prompt-editor", TextArea).text = default
            self.dm.set_system_prompt(mode, default)
        elif btn_id == "settings-save-tools":
            try:
                self.dm.tools = json.loads(self.query_one("#settings-tools-editor", TextArea).text)
                self.dm.save_tools()
            except json.JSONDecodeError:
                pass

    def _update_key_status(self):
        key = self.dm.settings.get("api_key", "")
        if key:
            masked = key[:6] + "•••••" + key[-4:] if len(key) > 12 else key[:3] + "••••"
            self.query_one("#settings-key-status", Static).update(f"✅ Key set ({len(key)} chars): {masked}")
        else:
            self.query_one("#settings-key-status", Static).update("❌ No API key set")

    def _load_prompt(self, mode: str):
        self.query_one("#settings-prompt-editor", TextArea).text = self.dm.get_system_prompt(mode)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "settings-model":
            self.dm.settings["model"] = str(event.value)
            self.dm.save_settings()


# ═══════════════════════════════════════════════════════════
#  HISTORY TAB
# ═══════════════════════════════════════════════════════════

class HistoryTab(TabPane):
    def __init__(self, dm: DataManager, **kwargs):
        super().__init__("📋 History", **kwargs)
        self.dm = dm

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="history-scroll"):
            yield Static("Loading history...")
        with Horizontal():
            yield Button("Refresh", id="history-refresh")
            yield Button("Delete All", variant="error", id="history-delete")
            yield Button("Export All", variant="default", id="history-export")

    def on_mount(self):
        self._refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "history-refresh":
            self._refresh()
        elif event.button.id == "history-delete":
            for chat in self.dm.list_chats():
                self.dm.delete_chat(chat.get("id", ""))
            self._refresh()
        elif event.button.id == "history-export":
            with open(DATA_DIR / "export_all.json", "w", encoding="utf-8") as f:
                json.dump(self.dm.list_chats(), f, indent=2, ensure_ascii=False)

    def _refresh(self):
        scroll = self.query_one("#history-scroll", VerticalScroll)
        scroll.remove_children()
        chats = self.dm.list_chats()
        if not chats:
            scroll.mount(Static("No saved conversations yet."))
            return
        for chat in chats:
            ts = chat.get("timestamp", "Unknown")
            mode = chat.get("mode", "chat")
            model = chat.get("model", "unknown")
            msg_count = len(chat.get("messages", []))
            first_msg = ""
            for m in chat.get("messages", []):
                if m.get("role") == "user":
                    c = m.get("content", "")
                    if isinstance(c, str):
                        first_msg = c[:80]
                    break
            scroll.mount(Static(f"📂 {ts} · {mode} · {model} · {msg_count} msgs\n   \"{first_msg}\""))


# ═══════════════════════════════════════════════════════════
#  STARTUP — ASK FOR API KEY IN PLAIN TERMINAL
# ═══════════════════════════════════════════════════════════

def startup_check_api_key(dm: DataManager) -> None:
    key = dm.settings.get("api_key", "")
    if key and len(key) > 10:
        return
    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║  JFO — JeelanPro Fly OffCoder                       ║")
    print("║                                                      ║")
    print("║  No API key found. Paste it here (Ctrl+V works).     ║")
    print("║  Or press Enter to skip and set it later in          ║")
    print("║  the Settings tab using Paste from Clipboard.        ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()
    try:
        api_key = input("Paste your ZhipuAI API key: ").strip()
    except (EOFError, KeyboardInterrupt):
        api_key = ""
    if api_key and len(api_key) > 10:
        dm.set_api_key(api_key)
        print(f"\n✅ API key saved! ({len(api_key)} chars)\n")
        time.sleep(1)
    else:
        print("\n⚠ No key entered. Set it later in ⚙ Settings.\n")
        time.sleep(2)


# ═══════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════

class JFOApp(App):
    TITLE = "JFO — JeelanPro Fly OffCoder"
    SUB_TITLE = "Terminal AI Assistant · ZhipuAI GLM"

    CSS = """
    Screen { layout: vertical; }
    TabbedContent { height: 1fr; }
    #chat-scroll, #agent-scroll, #lr-scroll,
    #think-scroll, #struct-scroll, #vision-scroll,
    #quick-scroll, #settings-scroll, #history-scroll {
        height: 1fr; border: round $primary; padding: 1; margin: 0 1;
    }
    #chat-input-bar, #agent-input-bar, #lr-input-bar,
    #think-input-bar, #struct-input-bar, #vision-input-bar,
    #quick-input-bar { height: auto; padding: 1; margin: 0 1; }
    #chat-input, #agent-input, #lr-input,
    #think-input, #struct-input, #vision-input,
    #quick-input { width: 1fr; }
    Label { margin: 1 1 0 1; }
    Button { margin: 0 1; }
    Input { margin: 0 1; }
    Select { margin: 0 1; }
    TextArea { margin: 1; height: 8; }
    #settings-prompt-editor { height: 12; }
    #settings-tools-editor { height: 12; }
    #lr-progress { color: $accent; }
    #lr-timer { color: $warning; text-style: bold; }
    #settings-key-status { margin: 0 1; padding: 0 1; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "toggle_dark", "Dark mode"),
    ]

    def __init__(self, dm: DataManager):
        super().__init__()
        self.dm = dm
        self.api = ZhipuClient(self.dm)

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            yield ChatTab(self.dm, self.api)
            yield AgentTab(self.dm, self.api)
            yield LongRunTab(self.dm, self.api)
            yield DeepThinkTab(self.dm, self.api)
            yield StructuredTab(self.dm, self.api)
            yield VisionTab(self.dm, self.api)
            yield QuickTab(self.dm, self.api)
            yield SettingsTab(self.dm)
            yield HistoryTab(self.dm)
        yield Footer()

    def on_mount(self):
        if not self.dm.settings.get("api_key"):
            self.notify("No API key set. Go to ⚙ Settings and click 'Paste from Clipboard'.", severity="warning", timeout=10)


# ═══════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    dm = DataManager()
    startup_check_api_key(dm)
    app = JFOApp(dm)
    app.run()