# v22 Generated Folder Protection

AegisFlow-generated folders are now globally excluded from repository inspection, validation, Dockerfile linting, test generation, AI fix plans, backups, and Git commits.

Protected folders:

- `.aegisflow_backups/`
- `orchestrator_reports/`
- common cache/build folders such as `.git/`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `node_modules/`, `dist/`, `build/`, and `htmlcov/`

This prevents old backup Dockerfiles or generated evidence files from being validated as if they were source code.
