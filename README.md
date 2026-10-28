# OpenRouter Chat

A Windows desktop chat client for OpenRouter, built with Python and PySide6. Choose a model, manage local conversations, and view Markdown replies and code blocks in a VS Code Dark+-inspired interface.

## Features

- Chat with OpenRouter models using the Chat Completions API.
- Choose from the built-in model list:
  - `anthropic/claude-3.7-sonnet`
  - `x-ai/grok-4.7`
  - `openai/gpt-4o`
  - `openai/gpt-4o-mini`
  - `google/gemini-2.5-flash`
  - `deepseek/deepseek-chat-v3-0324`
  - `meta-llama/llama-3.3-70b-instruct`
  - `xingchen-agi/xing4.0-29b-a4b:free`
- Save conversation history locally in SQLite. Rename and delete conversations from the history list.
- Render Markdown and display fenced code blocks in dedicated read-only code areas with copy buttons.
- Attach text files, PDFs, DOCX documents, and images to messages; download saved attachments; and save assistant replies or code blocks to files.
- Export a conversation as a Markdown file, clear its messages, stop a response, or regenerate the last response.
- Configure the API key, default model, system prompt, temperature, and response token limit in Settings.
- Use the welcome screen prompt shortcuts to get started quickly.

## Requirements

- Windows
- Python 3.10 or later
- An OpenRouter API key

## Install

Open PowerShell in the project directory and run:

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python chat_agent.py
```

Open **Settings** in the app, enter your OpenRouter API key, and save it. Choose a model from the selector and start a conversation.

Use **Attach file** in the composer to include up to five text files, PDF/DOCX documents, or images (5 MB each, 10 MB total) with a message. Text is extracted from PDFs and DOCX files and sent to the selected model; scanned PDFs without a text layer are not supported. Images are sent directly, and image support depends on the selected model. Original attachments are stored in local conversation history. Use **Download** on a message attachment or **Save** / **Save code** on an assistant reply to save files locally.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+N` | Create a new chat |
| `Ctrl+,` | Open Settings |
| `Ctrl+Enter` | Send a message |
| `Enter` | Send from the message composer |
| `Shift+Enter` | Insert a newline in the composer |
| `Ctrl+L` | Focus the message composer |
| `Ctrl+Shift+E` | Export the current conversation |

## Local data

Conversation history is stored in:

```text
%LOCALAPPDATA%\OpenRouterChat\chat_history.db
```

If `LOCALAPPDATA` is unavailable, the application uses a folder named `OpenRouterChat` in the user's home directory. The API key and other preferences are stored using Qt application settings for `PragCode` / `OpenRouterChat`.

## Dependencies

See [`requirements.txt`](./requirements.txt) for the Python package requirements.
