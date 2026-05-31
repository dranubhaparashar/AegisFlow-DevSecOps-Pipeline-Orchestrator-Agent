# v18 Hadolint Fix Plan Improvements

AegisFlow v18 improves Dockerfile AI Fix Plan behavior.

## Fixes
- Strips ANSI color codes from Hadolint output before parsing.
- Extracts exact rule numbers, levels, line numbers, and messages.
- Generates deterministic safe patches only where behavior is preserved.
- Handles DL3013 safely when a Dockerfile already uses `pip install -r requirements.txt` by converting it to `pip install --requirement requirements.txt`.
- Keeps DL3008 as review-only because apt package version pinning requires selecting valid OS package versions and should not be guessed by automation.

## Workflow
Run Hadolint → parse findings → propose exact diff if safe → wait for user approval → apply backup patch → rerun Hadolint.
