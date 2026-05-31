# Agentic design

This tool is agentic because it follows a loop:

1. Observe
   - Inspect repo files, language, structure, existing pipeline controls.

2. Plan
   - Decide which validations and files are required.

3. Act
   - Generate files, run validations, create evidence, optionally commit/push/PR.

4. Evaluate
   - Classify failures and decide whether the issue is code, config, security, dependency, or test data.

5. Report
   - Produce Markdown and JSON evidence.

6. Human checkpoint
   - Push/PR/deploy only when explicitly enabled.

## Future stronger agentic features

- Auto-fix safe lint/format issues.
- Open PR comments automatically.
- Re-run validations after fixes.
- Query Azure DevOps pipeline logs.
- Compare current failure with previous successful run.
- Recommend owner/team based on failure area.
- Auto-create work item for unresolved failures.
- Multi-repo monitoring dashboard.
- Governance policy-as-code.
