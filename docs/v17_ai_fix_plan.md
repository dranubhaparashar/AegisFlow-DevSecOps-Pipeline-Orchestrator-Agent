# AegisFlow AI v17 — AI Fix Plan

v17 adds an approval-based fix workflow:

```text
Run validations
→ collect failures
→ create AI Fix Plan
→ show exact proposed file diffs
→ user approves patch
→ apply only safe deterministic patches
→ rerun affected validation
→ show before/after result
```

## Dockerfile / Hadolint flow

```text
Run hadolint
→ collect rule numbers and affected lines
→ generate deterministic safe fixes for common rules
→ show unified diff
→ require explicit user approval
→ apply patch with backup
→ rerun hadolint
```

AegisFlow does not blindly change business logic, tests, production config, secrets, or architecture decisions.
