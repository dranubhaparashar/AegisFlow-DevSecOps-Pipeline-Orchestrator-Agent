# AegisFlow AI v3 Extensions

## Developer intelligence

| Capability | What it does | Output |
|---|---|---|
| Error explanation | Converts raw command output into readable cause | Explanation per failed check |
| Common fixes | Suggests standard remediation steps | Fix list per issue |
| Log summary | Summarizes validation timeline | Passed/failed/skipped lists |
| PR comment writer | Prepares PR review text | Markdown PR comment |

## Governance intelligence

| Capability | What it does | Important rule |
|---|---|---|
| Production deployment support | Recommends blocked/conditional/ready-for-human-approval | Does not deploy to production automatically |
| Secrets/access governance | Flags likely secrets and access risks | Humans approve rotation, Key Vault, service connections |
| Architecture approval support | Checks repo/pipeline readiness and evidence | Architect/tech lead approves design |
| Compliance sign-off pack | Creates evidence matrix | Compliance owner signs off |

## Release decision model

```text
Security/secret finding → blocked
Test failure → blocked
Quality failure in production → blocked or waiver required
Missing governance controls → conditional review
All checks passed → ready for human approval
```

## Human-in-the-loop rule

AegisFlow AI supports decision making. It does not replace governance ownership.
