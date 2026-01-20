# Agent Development Guidelines - Telegram Group Backup & AI Bot

This document provides essential information for agentic coding agents to operate effectively in this repository.

## 1. Project Overview
This repository contains two primary components:
- **Group Message Backup Tool**: A Telethon-based client that forwards and backs up messages from source groups to target groups, tracking edits and deletions.
- **AI Bot Service**: A plugin-based AI assistant (using `python-telegram-bot`) that integrates with various AI providers (OpenAI, Gemini, Grok, etc.).

## 2. Build, Lint, and Test Commands

### Environment Setup
The project uses a virtual environment located at `/home/dreaife/bot/venv`.
```bash
source /home/dreaife/bot/venv/bin/activate
pip install -r requirements.txt
```

### Running the Services
- **Group Backup Bot**:
  ```bash
  python3 telebot/group_backup_bot.py --config telebot/group_backup_config.yml
  ```
- **AI Test Bot**:
  ```bash
  python3 telebot/dreaife_test_bot.py
  ```

### Testing & Linting
Currently, there is no formal test suite (like pytest) or linter (like ruff) configured.
- **Run single script test**: Simply execute the script with the venv python.
- **Verification**: Manually run the entry point scripts and check logs in `/logs/bot/<bot-name>/`.

*Recommendation for Agents*: When adding new features, consider adding a `tests/` directory and using `pytest`.

## 3. Code Style Guidelines

### General Principles
- **Language**: Python 3.10+
- **Concurrency**: Use `asyncio` and `async/await` throughout.
- **Encoding**: Always use UTF-8.
- **Line Length**: Aim for 100-120 characters.

### Imports
Group imports in the following order, separated by a blank line:
1. Standard library imports.
2. Third-party library imports.
3. Local application/module imports.
Use absolute imports or explicit relative imports (e.g., `from .mapper import MessageMapper`).

### Naming Conventions
- **Classes**: `PascalCase` (e.g., `GroupBackupClient`).
- **Functions/Variables**: `snake_case` (e.g., `handle_new_message`).
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_RETENTION_DAYS`).
- **Private members**: Prefix with a single underscore (e.g., `_parse_config`).

### Types and Documentation
- **Type Hints**: Mandatory for function signatures. Use `typing` module or built-in types (Python 3.10+ style).
- **Docstrings**: Required for classes and public methods. Prefer Google or ReStructuredText style.
  ```python
  def parse_args() -> argparse.Namespace:
      """
      Parses command line arguments for the backup service.
      
      Returns:
          argparse.Namespace: The parsed arguments.
      """
  ```

### Async/Await
- Use `asyncio.run()` only in the main entry point.
- Avoid blocking calls in async functions; use thread pools if necessary for I/O.
- Properly handle `asyncio.CancelledError` if needed.

### Error Handling
- Use `try...except` blocks around I/O operations and API calls.
- Log errors with `logger.error(..., exc_info=True)` to capture stack traces.
- Don't swallow exceptions silently unless there's a very good reason.

### Logging
- Use the standard `logging` library.
- Log files are typically stored in `/logs/bot/<bot-name>/`.
- Use `TimedRotatingFileHandler` for production logs.
- Use descriptive log messages including relevant IDs (e.g., `chat_id`, `msg_id`).

## 4. Project Structure
- `telebot/`: Contains bot entry points and core logic.
  - `group_backup/`: Core logic for the message backup tool.
  - `doc/`: User manuals and technical documentation.
- `ai_plugins/`: Plugin architecture for AI providers.
  - `base/`: Base classes for AI integration.
  - `openai/`, `gemini/`, etc.: Provider-specific implementations.
- `deploy/`: Systemd service files for deployment.
- `data/`: Local storage for sessions, mappings, and exports.
- `logs/`: Directory for log files.

## 5. Agent-Specific Instructions
- **Configuration**: Always check `telebot/group_backup_config.yml` (or the `.example.yml`) before modifying config-related code.
- **Persistence**: The backup tool uses `MessageMapper` for ID mappings (stored as JSON) and exports message history as JSONL (one JSON object per line) in `.bak` files. Respect these formats when modifying data-related code.
- **Telethon vs python-telegram-bot**: Note that `group_backup_bot.py` uses `Telethon` (Telegram Client API), while `dreaife_test_bot.py` uses `python-telegram-bot` (Bot API). Do not mix their patterns.
- **Security**: Never hardcode API keys or tokens. Use `.env` files and `python-dotenv`.
- **Paths**: Use `pathlib.Path` for all path manipulations. Ensure paths are absolute or correctly resolved relative to the project root.

## 6. Development Workflow
- **Branching**: Every new feature or bug fix must be developed in a separate branch (e.g., `feature/xyz` or `fix/abc`).
- **Pull Requests**: Changes must be submitted via Pull Requests. Do not merge directly into the main branch unless authorized.
- **Verification & Deployment**:
  - Before merging, verify changes by running the bot manually or through tests.
  - Since the service is running on this machine via systemd, after verification, restart the service to apply changes:
    ```bash
    sudo systemctl restart group_backup_bot
    ```

## 7. Existing Rules
No specific `.cursorrules` or `.github/copilot-instructions.md` were found. If you create them, ensure they align with this document.

---
*Created by Antigravity Agent - 2026-01-20*

## 8. Example Workflow: Adding Source Link Feature (2026-01-21)
This section documents the workflow used to implement the "Source Message Link" feature as a reference for future agents.

### Task
Add a clickable link to the original message in the forwarded message header.

### Steps Taken
1.  **Analysis**:
    -   Identified target file: `telebot/group_backup/handlers.py`.
    -   Located `_build_message_header` and message processing methods (`_process_single_target`, `_process_album_target`).

2.  **Implementation**:
    -   Modified `_process_single_target` and `_process_album_target` to fetch `chat` object:
        ```python
        try:
            chat = await message.get_chat()
        except:
            chat = None
        ```
    -   Updated `_build_message_header` signature to accept `chat` and `message_id`.
    -   Added logic to generate links based on public (`t.me/username/id`) or private (`t.me/c/id/id`) chat types.
    -   Appended link to header: `🔗 [跳转原文](url)`.

3.  **Deployment**:
    -   Restarted service: `sudo systemctl restart group_backup_bot`.

4.  **Git Commit**:
    -   `git add telebot/group_backup/handlers.py`
    -   `git commit -m "feat: Add source message link to forward header"`
    -   `git push`
