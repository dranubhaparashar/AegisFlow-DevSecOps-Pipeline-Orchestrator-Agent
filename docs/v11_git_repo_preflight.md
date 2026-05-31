# v11 Git Repository Preflight

AegisFlow AI v11 adds a Git identity preflight before modifying files or running Git automation.

## What it checks

- Whether the path is inside a Git repository
- Git root folder
- Current branch
- Short HEAD commit
- `origin` remote URL
- Remote provider detection: Azure DevOps, GitHub, or unknown
- Azure DevOps org/project/repo parsing when possible
- Working tree changed-file count

## Safety behavior

If the user provides a subfolder inside a repo, AegisFlow automatically operates from the Git root so generated files, tests, commits, and PRs belong to the correct repository.

The Streamlit UI blocks local file changes, branch creation, commits, pushes, and PR creation until the user checks:

```text
I confirm this is the correct Git repository
```

The UI also includes an optional `Expected repo/remote keyword` safety check. If provided, AegisFlow blocks modify/Git actions unless the keyword appears in the detected remote URL, repo name, or Git root.
