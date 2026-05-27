# CLAUDE.md

This file provides guidance to Claw Code (clawcode.dev) when working with code in this repository.

## Detected stack
- Primary language: Python
- Runtime baseline: target Python 3.13, minimum supported Python 3.12
- CLI framework: Typer
- Validation/config: pydantic v2
- Quality tools: pytest, pytest-asyncio, ruff, mypy
- Dependency workflow: uv

## Verification commands
- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run pinser --workspace .`

## Local tool notes
- In your environment, `uv` may be available at `~/.local/bin/uv`.
- If `uv` is not on `PATH`, prefer invoking it explicitly from `~/.local/bin/uv` before changing repo files or workflows.

## Working agreement
- Prefer small, reviewable changes and keep generated bootstrap files aligned with actual repo workflows.
- Keep shared defaults in `.claw.json`; reserve `.claw/settings.local.json` for machine-local overrides.
- Keep `README.md` user-facing and put contributor or implementation details in `HACKING.md`.
- Do not overwrite existing `CLAUDE.md` content automatically; update it intentionally when repo workflows change.
