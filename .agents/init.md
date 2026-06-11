# Agent Operating Instructions

You are working inside this project repository.

Your job is not only to complete tasks, but to preserve project continuity.
Before making decisions or changes, always inspect the project memory.

## Required Workflow

For every task, follow this sequence:

1. STUDY
   - Read the user request carefully.
   - Inspect the relevant files.
   - Read `.memory/progress.md`.
   - Read `.memory/decisions.md`.
   - Identify existing conventions before proposing new ones.

2. VALIDATE
   - Explain the intended change before acting when the change is significant.
   - Check whether the change conflicts with previous decisions.
   - Prefer existing project patterns over introducing new structure.
   - If a decision is required, record it in `.memory/decisions.md`.

3. ACT
   - Make the smallest correct change.
   - Keep code, docs, and project structure consistent.
   - Update `.memory/progress.md` after meaningful work.
   - Update `.memory/decisions.md` when a new architectural, tooling, naming, or workflow decision is made.

## Memory Rules

Always use these files:

- `.memory/progress.md`
  - What has been done
  - Current state of the project
  - Known open tasks

- `.memory/decisions.md`
  - Architecture decisions
  - Tooling choices
  - Naming conventions
  - Rejected alternatives
  - Reasons behind important choices

Do not ignore memory.
Do not overwrite memory blindly.
Append new entries with dates when possible.

## Behavior Rules

- Do not skip the STUDY phase.
- Do not make large structural changes without checking memory first.
- Do not introduce dependencies without a reason.
- Prefer `uv` commands for Python workflows.
- Prefer `uv run` instead of assuming the shell environment is activated.
- Keep the repository reproducible.
- Keep documentation updated when behavior changes.

## Python / uv Rules

Use `uv` as the default Python tool.

Preferred commands:

```bash
uv venv
uv sync
uv add package-name
uv add --dev package-name
uv run python main.py
uv run pytest
````

Avoid raw \`pip install\` unless there is a specific reason.
If dependencies are added, update the project configuration through \`uv\`.
