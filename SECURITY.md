# Security Policy

## Reporting a Vulnerability

**Please do NOT file public issues for security vulnerabilities.**

If you discover a security issue in this project, please report it responsibly:

- Email: **security@example.com** (replace with your actual contact)
- Subject: `[tg-account-mcp] Security vulnerability`

You will receive an acknowledgment within 48 hours and a detailed response within 7 days.

## Scope

This project wraps Telethon to provide MCP tools for a personal Telegram account. Security-sensitive areas include:

- Session file handling (`.tg-session/`)
- Credential management (API ID, API hash, phone, 2FA password)
- Rate limiting and flood protection
- Input validation on tool parameters

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Security Design

- Secrets are loaded exclusively from environment variables — never hardcoded.
- The session file is stored with `chmod 600` permissions.
- No tool response ever contains `api_hash`, session bytes, 2FA passwords, or unmasked phone numbers.
- Write operations (`tg_send_message`, `tg_delete_message`) are logged to stderr only.
- `FloodWaitError` is handled with a single retry after sleep — no busy loops.
