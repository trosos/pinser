# CLAUDE.md

This file provides guidance to Claw Code (clawcode.dev) when working with code in this repository.

## Detected stack
- Primary language: Python
- Runtime baseline: target Python 3.13, minimum supported Python 3.12
- CLI framework: Typer
- Validation/config: pydantic v2
- Quality tools: pytest, pytest-asyncio, ruff, mypy
- Dependency workflow: uv

## Commit sequence for Python code changes
- For commits that touch Python code, run verification in this order:
  1. `uv run mypy .`
  2. `uv run pytest`
  3. `uv run ruff check .`
- Only commit after all three pass.
- After committing, clean Python cache artifacts with `pyclean .` (note: routine post-commit cleanup does not use `--debris`).

## Local tool notes
- In your environment, `uv` and `pyclean` may be available at `~/.local/bin/uv` and `~/.local/bin/pyclean`.
- If either is not on `PATH`, prefer invoking it explicitly from `~/.local/bin/`.

## Working agreement
- Prefer small, reviewable changes and keep generated bootstrap files aligned with actual repo workflows.
- Keep shared defaults in `.claw.json`; reserve `.claw/settings.local.json` for machine-local overrides.
- Keep `README.md` user-facing and put contributor or implementation details in `HACKING.md`.
- Do not overwrite existing `CLAUDE.md` content automatically; update it intentionally when repo workflows change.
