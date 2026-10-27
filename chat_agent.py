"""
OpenRouter Desktop Chat Agent — single-file PySide6 application.

Install:
    py -m pip install PySide6 requests markdown

Run:
    py chat_agent.py

Features:
- Multiple conversations, rename/delete, persistent SQLite history
- OpenRouter API key and model settings
- Model list fetched from OpenRouter
- OpenRouter chat completions, stop button, regenerate, copy
- Markdown/code rendering, system prompt, temperature and max tokens
- Local database stored in %LOCALAPPDATA%\\OpenRouterChat\\chat_history.db
"""

import sys
import os
import json
import sqlite3
import html
import re
import uuid
from datetime import datetime

import requests
import markdown

from PySide6.QtCore import Qt, QThread, Signal, QSettings, QSize
from PySide6.QtGui import QAction, QFont, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QLineEdit,
    QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QDialog, QFormLayout, QDialogButtonBox, QMessageBox, QSplitter,
    QScrollArea, QFrame, QTextBrowser, QToolButton, QMenu, QStatusBar,
    QCheckBox, QSizePolicy, QFileDialog
)

APP_NAME = "OpenRouter Chat"
API_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o"
DEFAULT_SYSTEM = "You are a helpful, clear, and accurate AI assistant."
DARK_STYLE = """
QWidget { background:#1e1e1e; color:#cccccc; font-family:Segoe UI,Arial; font-size:10pt; }
QMainWindow { background:#1e1e1e; }
QFrame#Sidebar { background:#252526; border-right:1px solid #333333; }
QLabel#Brand { font-size:17pt; font-weight:700; color:#ffffff; padding:6px 4px 0; }
QLabel#BrandSub { color:#858585; font-size:8pt; font-weight:700; letter-spacing:2px; padding:0 6px 8px; }
QLabel#Muted { color:#858585; }
QLabel#Eyebrow { color:#4ec9b0; font-size:8pt; font-weight:700; letter-spacing:2px; background:transparent; }
QLabel#WelcomeTitle { color:#ffffff; font-size:22pt; font-weight:700; background:transparent; }
QLabel#WelcomeCopy { color:#cccccc; font-size:10pt; background:transparent; }
QFrame#WelcomePanel { background:#252526; border:1px solid #3c3c3c; border-radius:8px; }
QListWidget { background:#252526; border:0; outline:0; padding:5px; }
QListWidget::item { padding:12px 10px; margin:3px 0; border-radius:4px; color:#cccccc; }
QListWidget::item:selected { background:#094771; color:#ffffff; border-left:2px solid #007acc; }
QListWidget::item:hover { background:#2a2d2e; }
QPushButton { background:#333333; border:1px solid #454545; border-radius:4px; padding:9px 12px; color:#cccccc; }
QPushButton:hover { background:#3e3e3e; border-color:#606060; color:#ffffff; }
QPushButton:pressed { background:#094771; }
QPushButton:disabled { color:#858585; background:#2a2a2a; border-color:#3c3c3c; }
QPushButton#Primary { background:#0e639c; color:#ffffff; font-weight:600; border:0; }
QPushButton#Primary:hover { background:#1177bb; color:#ffffff; }
QPushButton#Danger { color:#f48771; border-color:#5a3835; }
QPushButton#Ghost { background:transparent; border-color:#454545; }
QPushButton#Prompt { text-align:left; background:#2a2d2e; border:1px solid #3c3c3c; padding:12px; color:#cccccc; }
QPushButton#Prompt:hover { background:#333333; border-color:#007acc; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
 background:#3c3c3c; border:1px solid #3c3c3c; border-radius:4px; padding:9px; selection-background-color:#264f78;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus { border:1px solid #007acc; }
QComboBox QAbstractItemView { background:#252526; selection-background-color:#094771; }
QTextBrowser { background:transparent; border:0; }
QScrollArea { border:0; }
QScrollBar:vertical { background:#1e1e1e; width:10px; margin:2px; }
QScrollBar::handle:vertical { background:#424242; min-height:24px; border-radius:4px; }
QScrollBar::handle:vertical:hover { background:#5a5a5a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QStatusBar { background:#007acc; color:#ffffff; border-top:0; }
QToolButton { background:transparent; border:0; padding:5px; color:#cccccc; }
QToolButton:hover { background:#2a2d2e; border-radius:4px; }
QDialog { background:#252526; }
"""

def app_data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "OpenRouterChat")
    os.makedirs(path, exist_ok=True)
    return path

DB_PATH = os.path.join(app_data_dir(), "chat_history.db")

class Store:
    def __init__(self, path=DB_PATH):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS chats(
            id TEXT PRIMARY KEY, title TEXT NOT NULL, model TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY(chat_id) REFERENCES chats(id) ON DELETE CASCADE
        );
        """)
        self.db.commit()

    def chats(self):
        return self.db.execute("SELECT * FROM chats ORDER BY updated_at DESC").fetchall()

    def create_chat(self, model):
        cid = str(uuid.uuid4())
        now = datetime.now().isoformat(timespec="seconds")
        self.db.execute("INSERT INTO chats VALUES(?,?,?,?,?)",
                        (cid, "New chat", model, now, now))
        self.db.commit()
        return cid

    def rename_chat(self, cid, title):
        title = title.strip()[:100] or "New chat"
        self.db.execute("UPDATE chats SET title=?, updated_at=? WHERE id=?",
                        (title, datetime.now().isoformat(timespec="seconds"), cid))
        self.db.commit()

    def delete_chat(self, cid):
        self.db.execute("DELETE FROM chats WHERE id=?", (cid,))
        self.db.commit()

    def get_chat(self, cid):
        return self.db.execute("SELECT * FROM chats WHERE id=?", (cid,)).fetchone()

    def messages(self, cid):
        return self.db.execute(
            "SELECT role,content,created_at FROM messages WHERE chat_id=? ORDER BY id", (cid,)
        ).fetchall()

    def add_message(self, cid, role, content):
        now = datetime.now().isoformat(timespec="seconds")
        self.db.execute("INSERT INTO messages(chat_id,role,content,created_at) VALUES(?,?,?,?)",
                        (cid, role, content, now))
        self.db.execute("UPDATE chats SET updated_at=? WHERE id=?",
                        (now, cid))
        # Use the first user message as the conversation title.
        if role == "user":
            row = self.db.execute("SELECT title FROM chats WHERE id=?", (cid,)).fetchone()
            if row and row["title"] == "New chat":
                title = re.sub(r"\s+", " ", content).strip()[:42]
                self.db.execute("UPDATE chats SET title=? WHERE id=?", (title or "New chat", cid))
        self.db.commit()

    def update_model(self, cid, model):
        self.db.execute("UPDATE chats SET model=?, updated_at=? WHERE id=?",
                        (model, datetime.now().isoformat(timespec="seconds"), cid))
        self.db.commit()

    def clear_messages(self, cid):
        self.db.execute("DELETE FROM messages WHERE chat_id=?", (cid,))
        self.db.execute("UPDATE chats SET updated_at=? WHERE id=?",
                        (datetime.now().isoformat(timespec="seconds"), cid))
        self.db.commit()

class StreamWorker(QThread):
    token = Signal(str)
    finished_text = Signal(str)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, api_key, model, messages, temperature, max_tokens, parent=None):
        super().__init__(parent)
        self.api_key = api_key
        self.model = model
        self.messages = messages
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._stop_requested = False
        self._response = None

    def stop(self):
        self._stop_requested = True
        # The read timeout keeps cancellation responsive if the server stalls.
        try:
            if self._response:
                self._response.close()
        except Exception:
            pass

    def run(self):
        """
        Non-streaming OpenRouter Chat Completions request, matching the
        user's curl example: POST endpoint + Bearer auth + JSON model/messages.
        """
        # Accept either a raw key or a pasted value such as "Bearer sk-or-v1-...".
        api_key = (self.api_key or "").strip().strip('"').strip("'")
        if api_key.lower().startswith("bearer "):
            api_key = api_key[7:].strip()

        if not api_key:
            self.failed.emit(
                "No OpenRouter API key was loaded. Open Settings, paste your API key, "
                "click Save, and try again."
            )
            return

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
            "HTTP-Referer": "http://localhost",
            "X-OpenRouter-Title": APP_NAME,
        }
        payload = {
            "model": self.model,
            "messages": self.messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        try:
            response = requests.post(
                f"{API_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=(20, 180),
                allow_redirects=False,
            )
            self._response = response

            if response.is_redirect or response.is_permanent_redirect:
                target = response.headers.get("Location", "(no Location header)")
                raise RuntimeError(
                    f"OpenRouter endpoint returned HTTP {response.status_code} redirect to {target}. "
                    "The app stopped instead of forwarding your API key to another host. "
                    "Check network/proxy settings and use the official endpoint."
                )

            try:
                data = response.json()
            except ValueError:
                data = {}

            if not response.ok:
                error_data = data.get("error", {}) if isinstance(data, dict) else {}
                message = error_data.get("message") or response.text or "Unknown API error"
                raise RuntimeError(f"OpenRouter returned HTTP {response.status_code}: {message}")

            choices = data.get("choices") or []
            if not choices:
                error_data = data.get("error", {}) if isinstance(data, dict) else {}
                message = error_data.get("message") or "The API returned no choices."
                raise RuntimeError(message)

            message = choices[0].get("message") or {}
            content = message.get("content", "")
            if isinstance(content, list):
                # Some model endpoints can return content as a list of blocks.
                content = "\\n".join(
                    str(block.get("text", "")) if isinstance(block, dict) else str(block)
                    for block in content
                )
            if not isinstance(content, str):
                content = str(content)

            # Emit once so the existing UI can render and save the final reply.
            if content and not self._stop_requested:
                self.token.emit(content)
            self.finished_text.emit(content)
        except Exception as exc:
            if self._stop_requested:
                self.finished_text.emit("")
            else:
                self.failed.emit(str(exc))
        finally:
            try:
                if self._response:
                    self._response.close()
            except Exception:
                pass

class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(500)
        self.settings = settings
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.key = QLineEdit(settings.value("api_key", ""))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("sk-or-v1-...")
        self.show_key = QCheckBox("Show API key")
        self.show_key.toggled.connect(
            lambda checked: self.key.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        key_wrap = QWidget()
        key_layout = QVBoxLayout(key_wrap)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.key)
        key_layout.addWidget(self.show_key)
        self.model = QLineEdit(settings.value("model", DEFAULT_MODEL))
        self.model.setPlaceholderText("provider/model-name")
        self.system = QPlainTextEdit(settings.value("system_prompt", DEFAULT_SYSTEM))
        self.system.setMinimumHeight(90)
        self.temp = QDoubleSpinBox()
        self.temp.setRange(0, 2)
        self.temp.setSingleStep(0.1)
        self.temp.setValue(float(settings.value("temperature", 0.7)))
        self.tokens = QSpinBox()
        self.tokens.setRange(128, 32768)
        self.tokens.setSingleStep(512)
        self.tokens.setValue(int(settings.value("max_tokens", 4096)))
        form.addRow("OpenRouter API key", key_wrap)
        form.addRow("Default model", self.model)
        form.addRow("System prompt", self.system)
        form.addRow("Temperature", self.temp)
        form.addRow("Max response tokens", self.tokens)
        layout.addLayout(form)
        note = QLabel("Your API key is stored in local application settings. Keep your Windows account secure.")
        note.setWordWrap(True)
        note.setObjectName("Muted")
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        self.settings.setValue("api_key", self.key.text().strip())
        self.settings.setValue("model", self.model.text().strip() or DEFAULT_MODEL)
        self.settings.setValue("system_prompt", self.system.toPlainText().strip() or DEFAULT_SYSTEM)
        self.settings.setValue("temperature", self.temp.value())
        self.settings.setValue("max_tokens", self.tokens.value())

class MessageCard(QFrame):
    def __init__(self, role, content="", parent=None):
        super().__init__(parent)
        self.role = role
        self.setObjectName("MessageCard")
        self.setStyleSheet(
            "QFrame#MessageCard { background:%s; border:1px solid %s; border-radius:12px; }" %
            (("#252526" if role == "assistant" else "#222222"),
             ("#3c3c3c" if role == "assistant" else "#333333"))
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(15, 11, 15, 12)
        outer.setSpacing(7)
        header = QHBoxLayout()
        name = QLabel("Assistant" if role == "assistant" else "You")
        name.setStyleSheet("font-weight:700;color:%s;background:transparent;" %
                           ("#4ec9b0" if role == "assistant" else "#9cdcfe"))
        header.addWidget(name)
        header.addStretch()
        self.copy_btn = QToolButton()
        self.copy_btn.setText("Copy")
        self.copy_btn.setToolTip("Copy message")
        self.copy_btn.clicked.connect(self.copy_text)
        header.addWidget(self.copy_btn)
        outer.addLayout(header)
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        outer.addLayout(self.content_layout)
        self.code_areas = []
        self.content = content
        self.set_content(content)

    def _add_text_area(self, content):
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setReadOnly(True)
        browser.setMinimumHeight(25)
        browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        browser.document().setDocumentMargin(0)
        rendered = markdown.markdown(
            content,
            extensions=["tables", "nl2br", "sane_lists"]
        )
        css = """
        <style>
        body{font-family:Segoe UI,Arial;color:#cccccc;font-size:10pt;line-height:1.5;margin:0;overflow-wrap:anywhere}
        p{margin:4px 0 10px 0} h1,h2,h3{margin:14px 0 7px;color:#ffffff}
        a{color:#3794ff} blockquote{border-left:3px solid #007acc;padding-left:10px;color:#9da0a6}
        code{font-family:Consolas,monospace;color:#ce9178;background:#2d2d2d;border-radius:3px;padding:2px 4px}
        table{border-collapse:collapse} th,td{border:1px solid #454545;padding:5px 8px} th{background:#333333}
        ul,ol{margin-top:5px;margin-bottom:8px} hr{border:0;border-top:1px solid #454545}
        </style>
        """
        browser.setHtml(css + "<body>" + rendered + "</body>")
        doc = browser.document()
        doc.adjustSize()
        height = int(doc.size().height()) + 10
        browser.setMinimumHeight(max(28, min(height, 3000)))
        browser.setMaximumHeight(max(60, min(height, 3000)))
        self.content_layout.addWidget(browser)

    def _add_code_area(self, language, code):
        code_frame = QFrame()
        code_frame.setStyleSheet(
            "QFrame { background:#1e1e1e; border:1px solid #3c3c3c; border-radius:4px; }"
        )
        code_layout = QVBoxLayout(code_frame)
        code_layout.setContentsMargins(10, 7, 10, 9)
        code_layout.setSpacing(6)
        toolbar = QHBoxLayout()
        language_label = QLabel(language.strip().upper() or "CODE")
        language_label.setStyleSheet(
            "color:#4ec9b0;font-size:8pt;font-weight:700;letter-spacing:1px;"
            "background:transparent;border:0;"
        )
        toolbar.addWidget(language_label)
        toolbar.addStretch()
        copy_code_btn = QToolButton()
        copy_code_btn.setText("Copy code")
        copy_code_btn.setToolTip("Copy code block")
        copy_code_btn.clicked.connect(
            lambda checked=False, source=code.rstrip("\n"): QApplication.clipboard().setText(source)
        )
        toolbar.addWidget(copy_code_btn)
        code_layout.addLayout(toolbar)
        code_area = QPlainTextEdit()
        code_area.setReadOnly(True)
        code_area.setPlainText(code.rstrip("\n"))
        code_area.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        code_area.setStyleSheet(
            "QPlainTextEdit { background:transparent; color:#d4d4d4; border:0;"
            "font-family:Consolas,monospace; font-size:9pt; padding:2px; }"
        )
        line_height = code_area.fontMetrics().lineSpacing()
        visible_lines = min(max(code.count("\n") + 1, 3), 18)
        code_area.setFixedHeight(visible_lines * line_height + 18)
        code_layout.addWidget(code_area)
        self.content_layout.addWidget(code_frame)
        self.code_areas.append(code_area)

    def set_content(self, content):
        self.content = content
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.code_areas.clear()

        if not content:
            if self.role == "assistant":
                self._add_text_area("<span style='color:#858585'>Thinking…</span>")
            return

        code_pattern = re.compile(r"```([^\n`]*)\n(.*?)(?:```|$)", re.DOTALL)
        cursor = 0
        for match in code_pattern.finditer(content):
            prose = content[cursor:match.start()]
            if prose.strip():
                self._add_text_area(prose)
            self._add_code_area(match.group(1), match.group(2))
            cursor = match.end()
        trailing_text = content[cursor:]
        if trailing_text.strip() or not self.code_areas:
            self._add_text_area(trailing_text)

    def copy_text(self):
        QApplication.clipboard().setText(self.content)
        self.copy_btn.setText("Copied")
        QThread.msleep(250)
        self.copy_btn.setText("Copy")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenRouter Chat")
        self.resize(1250, 850)
        self.setMinimumSize(900, 600)
        self.settings = QSettings("PragCode", "OpenRouterChat")
        self.store = Store()
        self.current_chat = None
        self.worker = None
        self.current_assistant_card = None
        self.stream_buffer = ""
        self._building_history = False

        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main.addWidget(splitter)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setMinimumWidth(225)
        sidebar.setMaximumWidth(330)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 14, 12, 12)
        side.setSpacing(10)
        brand = QLabel("OpenRouter Chat")
        brand.setObjectName("Brand")
        side.addWidget(brand)
        self.new_btn = QPushButton("+  New chat")
        self.new_btn.setObjectName("Primary")
        self.new_btn.clicked.connect(self.new_chat)
        side.addWidget(self.new_btn)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search conversations…")
        self.search.textChanged.connect(self.filter_chats)
        side.addWidget(self.search)
        self.chat_list = QListWidget()
        self.chat_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self.chat_context_menu)
        self.chat_list.currentItemChanged.connect(self.chat_selected)
        side.addWidget(self.chat_list, 1)
        self.settings_btn = QPushButton("⚙  Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        side.addWidget(self.settings_btn)
        side_note = QLabel("●  LOCAL HISTORY ENABLED")
        side_note.setObjectName("Muted")
        side.addWidget(side_note)
        splitter.addWidget(sidebar)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        topbar = QFrame()
        topbar.setStyleSheet("background:#252526;border-bottom:1px solid #333333;")
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(20, 12, 20, 12)
        self.chat_title = QLabel("New chat")
        self.chat_title.setStyleSheet("font-size:12pt;font-weight:700;color:#ffffff;background:transparent;")
        top_layout.addWidget(self.chat_title)
        top_layout.addStretch()
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(220)
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.model_combo.setToolTip("Choose an OpenRouter model")
        self.model_combo.currentTextChanged.connect(self.model_changed)
        top_layout.addWidget(self.model_combo)
        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("Ghost")
        self.export_btn.setToolTip("Export this conversation as Markdown")
        self.export_btn.clicked.connect(self.export_chat)
        top_layout.addWidget(self.export_btn)
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("Danger")
        self.clear_btn.setToolTip("Clear messages in this conversation")
        self.clear_btn.clicked.connect(self.clear_chat)
        top_layout.addWidget(self.clear_btn)
        center_layout.addWidget(topbar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.messages_host = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_host)
        self.messages_layout.setContentsMargins(0, 24, 0, 24)
        self.messages_layout.setSpacing(14)
        self.messages_layout.addStretch(1)
        self.welcome_panel = self._create_welcome_panel()
        self.messages_layout.addWidget(self.welcome_panel)
        self.messages_layout.addStretch(1)
        self.scroll.setWidget(self.messages_host)
        center_layout.addWidget(self.scroll, 1)

        composer_wrap = QFrame()
        composer_wrap.setStyleSheet("background:#252526;border-top:1px solid #333333;")
        composer_layout = QVBoxLayout(composer_wrap)
        composer_layout.setContentsMargins(22, 12, 22, 15)
        composer_layout.setSpacing(8)
        input_row = QHBoxLayout()
        self.input = QTextEdit()
        self.input.setPlaceholderText("Message the model…  (Enter to send · Shift+Enter for newline)")
        self.input.setFixedHeight(90)
        self.input.setAcceptRichText(False)
        input_row.addWidget(self.input, 1)
        buttons_col = QVBoxLayout()
        self.send_btn = QPushButton("Send  ➤")
        self.send_btn.setObjectName("Primary")
        self.send_btn.setMinimumWidth(100)
        self.send_btn.clicked.connect(self.send_message)
        buttons_col.addWidget(self.send_btn)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_generation)
        buttons_col.addWidget(self.stop_btn)
        self.regen_btn = QPushButton("Regenerate")
        self.regen_btn.setEnabled(False)
        self.regen_btn.clicked.connect(self.regenerate)
        buttons_col.addWidget(self.regen_btn)
        buttons_col.addStretch()
        input_row.addLayout(buttons_col)
        composer_layout.addLayout(input_row)
        foot = QHBoxLayout()
        foot.addWidget(QLabel("ENTER to send  ·  SHIFT+ENTER for a new line  ·  AI can make mistakes"))
        foot.addStretch()
        self.model_status = QLabel("OpenRouter")
        self.model_status.setObjectName("Muted")
        foot.addWidget(self.model_status)
        composer_layout.addLayout(foot)
        center_layout.addWidget(composer_wrap)
        splitter.addWidget(center)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([270, 980])

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")
        self.input.installEventFilter(self)
        self._populate_models()
        self.refresh_chat_list()
        if self.chat_list.count():
            self.chat_list.setCurrentRow(0)
        else:
            self.new_chat()
        self._update_api_status()

        settings_action = QAction("Settings", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self.open_settings)
        self.addAction(settings_action)
        new_action = QAction("New chat", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self.new_chat)
        self.addAction(new_action)
        send_action = QAction("Send", self)
        send_action.setShortcut(QKeySequence("Ctrl+Return"))
        send_action.triggered.connect(self.send_message)
        self.addAction(send_action)
        focus_action = QAction("Focus composer", self)
        focus_action.setShortcut(QKeySequence("Ctrl+L"))
        focus_action.triggered.connect(self.input.setFocus)
        self.addAction(focus_action)
        export_action = QAction("Export conversation", self)
        export_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        export_action.triggered.connect(self.export_chat)
        self.addAction(export_action)

    def _create_welcome_panel(self):
        panel = QFrame()
        panel.setObjectName("WelcomePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        eyebrow = QLabel("YOUR NEXT IDEA STARTS HERE")
        eyebrow.setObjectName("Eyebrow")
        layout.addWidget(eyebrow)
        title = QLabel("Think it. Build it.")
        title.setObjectName("WelcomeTitle")
        layout.addWidget(title)
        copy = QLabel("A focused workspace for coding, debugging, and shipping faster.")
        copy.setObjectName("WelcomeCopy")
        copy.setWordWrap(True)
        layout.addWidget(copy)
        for label, prompt in (
            ("⌘  Explain a codebase", "Explain this codebase and identify its main components:"),
            ("⚡  Debug an error", "Help me debug this error. Explain the cause, then suggest a fix:\n\n"),
            ("↗  Build a feature", "Help me plan and implement this feature step by step:"),
        ):
            button = QPushButton(label)
            button.setObjectName("Prompt")
            button.setProperty("prompt", prompt)
            button.clicked.connect(self._use_button_prompt)
            layout.addWidget(button)
        layout.addStretch()
        return panel

    def _use_button_prompt(self):
        button = self.sender()
        if isinstance(button, QPushButton):
            self.use_prompt(button.property("prompt"))

    def use_prompt(self, prompt):
        self.input.setPlainText(prompt)
        self.input.setFocus()
        self.input.moveCursor(QTextCursor.MoveOperation.End)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.input and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            ):
                self.send_message()
                return True
        return super().eventFilter(obj, event)

    def _populate_models(self):
        model = self.settings.value("model", DEFAULT_MODEL)
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems([
            "anthropic/claude-3.7-sonnet",
            "x-ai/grok-4.7",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "google/gemini-2.5-flash",
            "deepseek/deepseek-chat-v3-0324",
            "meta-llama/llama-3.3-70b-instruct",
            "xingchen-agi/xing4.0-29b-a4b:free",
        ])
        self.model_combo.setCurrentText(model)
        self.model_combo.blockSignals(False)

    def _update_api_status(self):
        key = str(self.settings.value("api_key", "") or "").strip().strip('"').strip("'")
        if key.lower().startswith("bearer "):
            key = key[7:].strip()
        self.model_status.setText("API key configured" if key else "API key required")
        self.model_status.setStyleSheet("color:%s;background:transparent;" %
                                        ("#4ec9b0" if key else "#f48771"))

    def refresh_chat_list(self, select_id=None):
        self._building_history = True
        self.chat_list.clear()
        for row in self.store.chats():
            item = QListWidgetItem(row["title"])
            item.setData(Qt.ItemDataRole.UserRole, row["id"])
            item.setToolTip(f"{row['title']}\nModel: {row['model']}")
            self.chat_list.addItem(item)
            if row["id"] == select_id:
                self.chat_list.setCurrentItem(item)
        self._building_history = False
        self.filter_chats(self.search.text())

    def filter_chats(self, text):
        text = text.lower().strip()
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    def new_chat(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Generation in progress", "Stop the current response before creating a new chat.")
            return
        model = self.model_combo.currentText().strip() or self.settings.value("model", DEFAULT_MODEL)
        cid = self.store.create_chat(model)
        self.refresh_chat_list(cid)
        self.load_chat(cid)
        self.input.setFocus()

    def chat_selected(self, current, previous):
        if self._building_history or current is None:
            return
        cid = current.data(Qt.ItemDataRole.UserRole)
        if cid and cid != self.current_chat:
            if self.worker and self.worker.isRunning():
                self.statusBar().showMessage("Stop generation before switching conversations.")
                self.chat_list.blockSignals(True)
                for i in range(self.chat_list.count()):
                    if self.chat_list.item(i).data(Qt.ItemDataRole.UserRole) == self.current_chat:
                        self.chat_list.setCurrentRow(i)
                        break
                self.chat_list.blockSignals(False)
                return
            self.load_chat(cid)

    def load_chat(self, cid):
        self.current_chat = cid
        row = self.store.get_chat(cid)
        if not row:
            return
        self.chat_title.setText(row["title"])
        self.model_combo.blockSignals(True)
        self.model_combo.setCurrentText(row["model"])
        self.model_combo.blockSignals(False)
        self.clear_messages()
        messages = self.store.messages(cid)
        self.welcome_panel.setVisible(not messages)
        for message in messages:
            self.add_card(message["role"], message["content"])
        self.regen_btn.setEnabled(bool(messages))
        self.scroll_to_bottom()

    def clear_messages(self):
        while self.messages_layout.count():
            item = self.messages_layout.takeAt(0)
            widget = item.widget()
            if widget:
                if widget is self.welcome_panel:
                    widget.hide()
                else:
                    widget.deleteLater()
        self.messages_layout.addStretch(1)
        self.messages_layout.addWidget(self.welcome_panel)
        self.messages_layout.addStretch(1)

    def add_card(self, role, content=""):
        self.welcome_panel.hide()
        card = MessageCard(role, content)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, card)
        self.scroll_to_bottom()
        return card

    def scroll_to_bottom(self):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def model_changed(self, model):
        model = model.strip()
        if self.current_chat and model:
            self.store.update_model(self.current_chat, model)
            self.chat_title.setText(self.store.get_chat(self.current_chat)["title"])

    def open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.save()
            self._populate_models()
            self._update_api_status()
            if self.current_chat:
                self.store.update_model(self.current_chat, self.model_combo.currentText().strip())
            self.statusBar().showMessage("Settings saved", 3000)

    def export_chat(self):
        if not self.current_chat:
            return
        chat = self.store.get_chat(self.current_chat)
        if not chat:
            return
        default_name = re.sub(r'[<>:"/\\|?*]+', "_", chat["title"]).strip(" .") or "conversation"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export conversation", f"{default_name}.md",
            "Markdown files (*.md)"
        )
        if not path:
            return
        lines = [
            f"# {chat['title']}",
            "",
            f"- Model: `{chat['model']}`",
            f"- Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
        ]
        for message in self.store.messages(self.current_chat):
            role = "You" if message["role"] == "user" else "Assistant"
            lines.extend([f"## {role}", "", message["content"], ""])
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as export_file:
                export_file.write("\n".join(lines))
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", f"Could not save the conversation:\n{exc}")
            return
        self.statusBar().showMessage("Conversation exported", 4000)

    def clear_chat(self):
        if not self.current_chat:
            return
        answer = QMessageBox.question(
            self, "Clear conversation",
            "Remove all messages from this conversation? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.store.clear_messages(self.current_chat)
        self.load_chat(self.current_chat)
        self.refresh_chat_list(self.current_chat)
        self.statusBar().showMessage("Conversation cleared", 4000)

    def _messages_for_api(self, cid):
        system = self.settings.value("system_prompt", DEFAULT_SYSTEM)
        messages = [{"role": "system", "content": system}]
        for row in self.store.messages(cid):
            if row["role"] in ("user", "assistant") and row["content"].strip():
                messages.append({"role": row["role"], "content": row["content"]})
        return messages

    def send_message(self):
        if self.worker and self.worker.isRunning():
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        key = str(self.settings.value("api_key", "") or "").strip().strip('"').strip("'")
        if key.lower().startswith("bearer "):
            key = key[7:].strip()
        if not key:
            QMessageBox.information(self, "OpenRouter API key required",
                                    "Open Settings and add your API key from OpenRouter.")
            self.open_settings()
            return
        if not self.current_chat:
            self.new_chat()
        self.input.clear()
        self.store.add_message(self.current_chat, "user", text)
        self.add_card("user", text)
        self.refresh_chat_list(self.current_chat)
        self.chat_title.setText(self.store.get_chat(self.current_chat)["title"])
        self._start_generation()

    def _start_generation(self):
        if not self.current_chat:
            return
        key = self.settings.value("api_key", "").strip()
        model = self.model_combo.currentText().strip() or self.settings.value("model", DEFAULT_MODEL)
        self.store.update_model(self.current_chat, model)
        self.stream_buffer = ""
        self.current_assistant_card = self.add_card("assistant", "")
        self.worker = StreamWorker(
            key, model, self._messages_for_api(self.current_chat),
            float(self.settings.value("temperature", 0.7)),
            int(self.settings.value("max_tokens", 4096)), self
        )
        self.worker.token.connect(self.on_token)
        self.worker.finished_text.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.regen_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.statusBar().showMessage(f"Generating with {model}…")

    def on_token(self, token):
        self.stream_buffer += token
        if self.current_assistant_card:
            self.current_assistant_card.set_content(self.stream_buffer)
        self.scroll_to_bottom()

    def on_finished(self, full_text):
        if full_text:
            self.stream_buffer = full_text
            if self.current_assistant_card:
                self.current_assistant_card.set_content(full_text)
            self.store.add_message(self.current_chat, "assistant", full_text)
        elif self.current_assistant_card and not self.stream_buffer:
            self.current_assistant_card.set_content("_Generation stopped._")
        self._generation_done()

    def on_failed(self, error):
        if self.current_assistant_card:
            self.current_assistant_card.set_content(
                "⚠️ **Request failed**\n\n" + error +
                "\n\nCheck your API key, selected model, network connection, and OpenRouter credits."
            )
        self.statusBar().showMessage("Request failed", 5000)
        self._generation_done()

    def _generation_done(self):
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.export_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.regen_btn.setEnabled(bool(self.store.messages(self.current_chat)))
        self.statusBar().showMessage("Ready", 3000)
        self.refresh_chat_list(self.current_chat)
        if self.current_chat:
            row = self.store.get_chat(self.current_chat)
            if row:
                self.chat_title.setText(row["title"])
        self.worker = None
        self.current_assistant_card = None

    def stop_generation(self):
        if self.worker and self.worker.isRunning():
            self.statusBar().showMessage("Stopping response…")
            self.stop_btn.setEnabled(False)
            self.worker.stop()

    def regenerate(self):
        if self.worker and self.worker.isRunning():
            return
        rows = self.store.messages(self.current_chat) if self.current_chat else []
        if not rows:
            return
        # Remove trailing assistant response so it can be regenerated.
        self.store.db.execute(
            "DELETE FROM messages WHERE id=(SELECT MAX(id) FROM messages WHERE chat_id=? AND role='assistant')",
            (self.current_chat,)
        )
        self.store.db.commit()
        self.load_chat(self.current_chat)
        self._start_generation()

    def chat_context_menu(self, pos):
        item = self.chat_list.itemAt(pos)
        if not item:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(self.chat_list.mapToGlobal(pos))
        if chosen == rename_action:
            from PySide6.QtWidgets import QInputDialog
            title, ok = QInputDialog.getText(self, "Rename conversation", "Conversation name:", text=item.text())
            if ok:
                self.store.rename_chat(cid, title)
                self.refresh_chat_list(cid)
                if cid == self.current_chat:
                    self.chat_title.setText(title.strip() or "New chat")
        elif chosen == delete_action:
            answer = QMessageBox.question(self, "Delete conversation",
                                          f"Delete “{item.text()}” and its messages?",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                if cid == self.current_chat:
                    self.current_chat = None
                self.store.delete_chat(cid)
                self.refresh_chat_list()
                if self.chat_list.count():
                    self.chat_list.setCurrentRow(0)
                else:
                    self.new_chat()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1500)
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
