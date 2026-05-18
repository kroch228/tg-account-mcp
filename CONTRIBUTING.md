# Contributing

Thanks for your interest in contributing to tg-account-mcp!

## Setup

```bash
git clone https://github.com/<owner>/tg-account-mcp.git
cd tg-account-mcp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Development workflow

1. Create a feature branch from `main`.
2. Make your changes.
3. Run checks:
   ```bash
   ruff check .
   ruff format .
   pytest -q
   ```
4. Ensure `pre-commit run --all-files` passes.
5. Commit using [Conventional Commits](https://www.conventionalcommits.org/):
   - `feat:` new feature
   - `fix:` bug fix
   - `docs:` documentation only
   - `chore:` maintenance
6. Open a Pull Request against `main`.

## Security

If you find a security vulnerability, please follow the process in [SECURITY.md](SECURITY.md). Do NOT open a public issue.
