# tg-account-mcp

> MCP server giving Claude Code safe, auditable control over your personal Telegram account via Telethon (MTProto).

[![CI](https://github.com/kroch228/tg-account-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/kroch228/tg-account-mcp/actions/workflows/ci.yml)
[![CodeQL](https://github.com/kroch228/tg-account-mcp/actions/workflows/codeql.yml/badge.svg)](https://github.com/kroch228/tg-account-mcp/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![MCP](https://img.shields.io/badge/protocol-MCP-green.svg)](https://modelcontextprotocol.io)

---

<details open><summary>🇬🇧 English</summary>

## What it is

A self-contained [MCP](https://modelcontextprotocol.io) server that wraps [Telethon](https://github.com/LonamiWebs/Telethon) to let Claude Code interact with your **personal Telegram account** over MTProto — reading chats, sending messages, searching history, and managing contacts.

**⚠️ Security warning:** This drives a *real user account*, not a bot. Aggressive automation can get your account limited or banned by Telegram. Use responsibly.

## Features

- `tg_list_dialogs` — list chats, channels, and DMs with unread counts
- `tg_read_history` — read message history from any dialog
- `tg_send_message` — send a message (with optional reply and silent mode)
- `tg_edit_message` — edit an existing message
- `tg_delete_message` — delete messages (for everyone or self only)
- `tg_search` — full-text search globally or within a dialog
- `tg_mark_read` — mark messages as read
- `tg_list_contacts` — list all contacts from the address book
- `tg_resolve_username` — resolve @username to entity ID and type

## Requirements

- Python 3.11+
- Telegram `api_id` and `api_hash` from [my.telegram.org](https://my.telegram.org/apps)
- A phone number linked to your Telegram account

## Install

```bash
git clone https://github.com/<owner>/tg-account-mcp.git
cd tg-account-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Fill in TG_API_ID, TG_API_HASH, TG_PHONE
```

## First-run auth

**You must complete this step before connecting to Claude Code.** The MCP server will hang on first connection if the session is not authorized.

```bash
python -m tg_account_mcp.auth
```

You will be prompted to enter the SMS code sent to your phone. If you have 2FA enabled, you'll also need to enter your password (or set `TG_2FA_PASSWORD` in `.env`).

The session is saved to `.tg-session/user.session` (chmod 600, gitignored). You won't need to re-authenticate unless the session expires.

## Register with Claude Code

### CLI

```bash
claude mcp add tg-account -- python -m tg_account_mcp.server
```

### JSON config (`~/.config/claude/claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "tg-account": {
      "command": "python",
      "args": ["-m", "tg_account_mcp.server"],
      "env": {
        "TG_API_ID": "12345678",
        "TG_API_HASH": "your_api_hash_here",
        "TG_PHONE": "+79001234567"
      }
    }
  }
}
```

Restart Claude Code after adding — `tg_*` tools will appear.

## Tool reference

| Tool | Params | Returns | Write? |
|------|--------|---------|--------|
| `tg_list_dialogs` | `limit?`, `archived?` | `[{id, title, kind, unread_count, last_message_at}]` | |
| `tg_read_history` | `dialog_id`, `limit?`, `offset_id?` | `[{id, from, text, date, reply_to_id}]` | |
| `tg_send_message` | `dialog_id`, `text`, `reply_to?`, `silent?` | `{id, date}` | ✏️ |
| `tg_edit_message` | `dialog_id`, `message_id`, `text` | `{ok}` | ✏️ |
| `tg_delete_message` | `dialog_id`, `message_ids`, `revoke?` | `{deleted}` | ✏️ |
| `tg_search` | `query`, `dialog_id?`, `limit?` | `[{id, from, text, date, chat_id}]` | |
| `tg_mark_read` | `dialog_id`, `max_message_id?` | `{ok}` | ✏️ |
| `tg_list_contacts` | — | `[{id, first_name, last_name, username, phone}]` | |
| `tg_resolve_username` | `username` | `{id, kind, title}` | |

`dialog_id` accepts: numeric peer ID, `@username`, or `"me"` (Saved Messages).

## Security model

- **Secrets via environment only** — `TG_API_ID`, `TG_API_HASH`, `TG_PHONE`, `TG_2FA_PASSWORD` are never hardcoded or returned in tool responses.
- **Session file** — stored at `.tg-session/user.session` with `chmod 600`, listed in `.gitignore`.
- **No leakage** — no tool ever returns `api_hash`, session bytes, 2FA password, or unmasked phone numbers.
- **Write logging** — `tg_send_message` and `tg_delete_message` log to stderr only (peer masked, text truncated).
- **Rate limiting** — minimum 1s between sends to the same peer.
- **FloodWait** — handled with sleep + single retry; never busy-loops.
- See [SECURITY.md](SECURITY.md) for vulnerability reporting.

## Development

```bash
pre-commit install
ruff check .
ruff format .
pytest -q
```

## License

[MIT](LICENSE)

</details>

---

<details><summary>🇷🇺 Русский</summary>

## Что это

Автономный [MCP](https://modelcontextprotocol.io)-сервер на базе [Telethon](https://github.com/LonamiWebs/Telethon), который позволяет Claude Code взаимодействовать с вашим **личным аккаунтом Telegram** по протоколу MTProto — читать чаты, отправлять сообщения, искать по истории и управлять контактами.

**⚠️ Внимание:** Это управление *реальным пользовательским аккаунтом*, а не ботом. Агрессивная автоматизация может привести к ограничению или бану аккаунта со стороны Telegram. Используйте ответственно.

## Возможности

- `tg_list_dialogs` — список чатов, каналов и ЛС с количеством непрочитанных
- `tg_read_history` — чтение истории сообщений из любого диалога
- `tg_send_message` — отправка сообщения (с ответом и тихим режимом)
- `tg_edit_message` — редактирование существующего сообщения
- `tg_delete_message` — удаление сообщений (для всех или только для себя)
- `tg_search` — полнотекстовый поиск глобально или в конкретном диалоге
- `tg_mark_read` — пометить сообщения как прочитанные
- `tg_list_contacts` — список всех контактов из адресной книги
- `tg_resolve_username` — резолв @username в ID и тип сущности

## Требования

- Python 3.11+
- `api_id` и `api_hash` с [my.telegram.org](https://my.telegram.org/apps)
- Номер телефона, привязанный к аккаунту Telegram

## Установка

```bash
git clone https://github.com/<owner>/tg-account-mcp.git
cd tg-account-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Заполните TG_API_ID, TG_API_HASH, TG_PHONE
```

## Первый запуск (авторизация)

**Этот шаг обязателен до подключения к Claude Code.** MCP-сервер зависнет при первом подключении, если сессия не авторизована.

```bash
python -m tg_account_mcp.auth
```

Вам будет предложено ввести SMS-код. Если включена двухфакторная аутентификация — также пароль (или задайте `TG_2FA_PASSWORD` в `.env`).

Сессия сохраняется в `.tg-session/user.session` (chmod 600, в `.gitignore`). Повторная авторизация не потребуется до истечения сессии.

## Подключение к Claude Code

### CLI

```bash
claude mcp add tg-account -- python -m tg_account_mcp.server
```

### JSON-конфиг (`~/.config/claude/claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "tg-account": {
      "command": "python",
      "args": ["-m", "tg_account_mcp.server"],
      "env": {
        "TG_API_ID": "12345678",
        "TG_API_HASH": "your_api_hash_here",
        "TG_PHONE": "+79001234567"
      }
    }
  }
}
```

После добавления перезапустите Claude Code — инструменты `tg_*` появятся в списке.

## Справочник инструментов

| Инструмент | Параметры | Возвращает | Запись? |
|------------|-----------|------------|---------|
| `tg_list_dialogs` | `limit?`, `archived?` | `[{id, title, kind, unread_count, last_message_at}]` | |
| `tg_read_history` | `dialog_id`, `limit?`, `offset_id?` | `[{id, from, text, date, reply_to_id}]` | |
| `tg_send_message` | `dialog_id`, `text`, `reply_to?`, `silent?` | `{id, date}` | ✏️ |
| `tg_edit_message` | `dialog_id`, `message_id`, `text` | `{ok}` | ✏️ |
| `tg_delete_message` | `dialog_id`, `message_ids`, `revoke?` | `{deleted}` | ✏️ |
| `tg_search` | `query`, `dialog_id?`, `limit?` | `[{id, from, text, date, chat_id}]` | |
| `tg_mark_read` | `dialog_id`, `max_message_id?` | `{ok}` | ✏️ |
| `tg_list_contacts` | — | `[{id, first_name, last_name, username, phone}]` | |
| `tg_resolve_username` | `username` | `{id, kind, title}` | |

`dialog_id` принимает: числовой ID, `@username` или `"me"` (Избранное).

## Модель безопасности

- **Секреты только через переменные окружения** — `TG_API_ID`, `TG_API_HASH`, `TG_PHONE`, `TG_2FA_PASSWORD` никогда не хардкодятся и не возвращаются в ответах.
- **Файл сессии** — хранится в `.tg-session/user.session` с правами `chmod 600`, в `.gitignore`.
- **Без утечек** — ни один инструмент не возвращает `api_hash`, байты сессии, пароль 2FA или немаскированные номера телефонов.
- **Логирование записи** — `tg_send_message` и `tg_delete_message` пишут только в stderr (peer замаскирован, текст обрезан).
- **Rate limiting** — минимум 1 секунда между отправками в один диалог.
- **FloodWait** — обрабатывается через sleep + одна повторная попытка; без busy-loop.
- См. [SECURITY.md](SECURITY.md) для сообщения об уязвимостях.

## Разработка

```bash
pre-commit install
ruff check .
ruff format .
pytest -q
```

## Лицензия

[MIT](LICENSE)

</details>

---

<details><summary>🇨🇳 中文</summary>

## 简介

一个基于 [Telethon](https://github.com/LonamiWebs/Telethon) 的独立 [MCP](https://modelcontextprotocol.io) 服务器，让 Claude Code 通过 MTProto 协议与你的**个人 Telegram 账号**交互——读取聊天、发送消息、搜索历史记录和管理联系人。

**⚠️ 安全警告：** 这是对*真实用户账号*的操控，而非机器人。过度自动化可能导致 Telegram 限制或封禁你的账号。请负责任地使用。

## 功能

- `tg_list_dialogs` — 列出聊天、频道和私信，含未读数
- `tg_read_history` — 读取任意对话的消息历史
- `tg_send_message` — 发送消息（支持回复和静默模式）
- `tg_edit_message` — 编辑已发送的消息
- `tg_delete_message` — 删除消息（双向或仅自己）
- `tg_search` — 全局或指定对话内全文搜索
- `tg_mark_read` — 标记消息为已读
- `tg_list_contacts` — 列出通讯录中的所有联系人
- `tg_resolve_username` — 将 @用户名 解析为实体 ID 和类型

## 环境要求

- Python 3.11+
- 从 [my.telegram.org](https://my.telegram.org/apps) 获取的 `api_id` 和 `api_hash`
- 绑定 Telegram 账号的手机号码

## 安装

```bash
git clone https://github.com/<owner>/tg-account-mcp.git
cd tg-account-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# 填写 TG_API_ID、TG_API_HASH、TG_PHONE
```

## 首次运行（授权）

**必须在连接 Claude Code 之前完成此步骤。** 如果会话未授权，MCP 服务器在首次连接时会挂起。

```bash
python -m tg_account_mcp.auth
```

系统会提示你输入收到的短信验证码。如果启用了两步验证，还需要输入密码（或在 `.env` 中设置 `TG_2FA_PASSWORD`）。

会话文件保存在 `.tg-session/user.session`（权限 chmod 600，已加入 `.gitignore`）。除非会话过期，否则无需重新授权。

## 注册到 Claude Code

### 命令行方式

```bash
claude mcp add tg-account -- python -m tg_account_mcp.server
```

### JSON 配置（`~/.config/claude/claude_desktop_config.json`）

```json
{
  "mcpServers": {
    "tg-account": {
      "command": "python",
      "args": ["-m", "tg_account_mcp.server"],
      "env": {
        "TG_API_ID": "12345678",
        "TG_API_HASH": "your_api_hash_here",
        "TG_PHONE": "+79001234567"
      }
    }
  }
}
```

添加后重启 Claude Code，`tg_*` 工具将出现在可用列表中。

## 工具参考

| 工具 | 参数 | 返回值 | 写操作? |
|------|------|--------|---------|
| `tg_list_dialogs` | `limit?`, `archived?` | `[{id, title, kind, unread_count, last_message_at}]` | |
| `tg_read_history` | `dialog_id`, `limit?`, `offset_id?` | `[{id, from, text, date, reply_to_id}]` | |
| `tg_send_message` | `dialog_id`, `text`, `reply_to?`, `silent?` | `{id, date}` | ✏️ |
| `tg_edit_message` | `dialog_id`, `message_id`, `text` | `{ok}` | ✏️ |
| `tg_delete_message` | `dialog_id`, `message_ids`, `revoke?` | `{deleted}` | ✏️ |
| `tg_search` | `query`, `dialog_id?`, `limit?` | `[{id, from, text, date, chat_id}]` | |
| `tg_mark_read` | `dialog_id`, `max_message_id?` | `{ok}` | ✏️ |
| `tg_list_contacts` | — | `[{id, first_name, last_name, username, phone}]` | |
| `tg_resolve_username` | `username` | `{id, kind, title}` | |

`dialog_id` 接受：数字 peer ID、`@username` 或 `"me"`（收藏夹/已保存消息）。

## 安全模型

- **仅通过环境变量传递密钥** — `TG_API_ID`、`TG_API_HASH`、`TG_PHONE`、`TG_2FA_PASSWORD` 永远不会硬编码或在工具响应中返回。
- **会话文件** — 存储在 `.tg-session/user.session`，权限 `chmod 600`，已加入 `.gitignore`。
- **无泄露** — 任何工具都不会返回 `api_hash`、会话字节、两步验证密码或未脱敏的手机号。
- **写操作日志** — `tg_send_message` 和 `tg_delete_message` 仅输出到 stderr（对端已脱敏，文本已截断）。
- **速率限制** — 向同一对端发送消息的最小间隔为 1 秒。
- **FloodWait** — 通过 sleep + 单次重试处理；绝不会忙等待。
- 漏洞报告请参阅 [SECURITY.md](SECURITY.md)。

## 开发

```bash
pre-commit install
ruff check .
ruff format .
pytest -q
```

## 许可证

[MIT](LICENSE)

</details>
