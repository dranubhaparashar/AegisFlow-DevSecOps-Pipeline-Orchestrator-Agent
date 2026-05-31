# AI DevSecOps Pipeline Orchestrator Agent — MVP v2

A local-first, agentic DevSecOps orchestration tool.

You give it a repository path. It inspects the repo, explains exactly what it is doing, runs validations, generates CI/CD and governance files, classifies failures, creates an evidence report, and can optionally create a branch, commit, push, and prepare/create a Pull Request.

This is designed for Azure DevOps pipelines, Azure Functions, Python APIs, ML/AI repos, and general CI/CD governance workflows.

## What is improved in v2

v1 scanned and generated basic pipeline suggestions.

v2 adds:

- Local repo intake
- Live step-by-step progress log
- Validation checklist with status
- Local file generation and safe repo updates
- Optional branch creation
- Optional commit
- Optional push
- Optional Azure DevOps PR creation
- Pipeline issue classification:
  - Developer code issue
  - Pipeline/config issue
  - Security issue
  - Test/data issue
  - Tooling/dependency issue
  - Needs human review
- Evidence report in Markdown + JSON
- Optional local LLM recommendation through Ollama
- Industry use-case catalogue

## Important safety rule

The tool does **not** push or create a PR unless you explicitly enable those options.

Default mode is read-only + report generation.

## Quick start

```bash
cd ai_devsecops_orchestrator_agent_v2
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Then paste your local repo path, for example:

```text
/mnt/c/Users/Anubha/OneDrive - Pearce Services, LLC/onedrive_ubuntu/project/gis-key-detection-func
```

## CLI usage

Read-only audit:

```bash
python agent.py "/path/to/repo"
```

Generate missing DevSecOps files locally:

```bash
python agent.py "/path/to/repo" --generate-files --apply
```

Run validations:

```bash
python agent.py "/path/to/repo" --run-validations
```

Create branch, commit, and push:

```bash
python agent.py "/path/to/repo" \
  --generate-files \
  --run-validations \
  --apply \
  --branch orchestrator/devsecops-ready \
  --commit \
  --push
```

Create Azure DevOps PR also:

```bash
export AZDO_ORG_URL="https://dev.azure.com/YOUR_ORG"
export AZDO_PROJECT="YOUR_PROJECT"
export AZDO_REPO_ID="YOUR_REPO_ID_OR_NAME"
export AZDO_PAT="YOUR_PAT"

python agent.py "/path/to/repo" \
  --generate-files \
  --run-validations \
  --apply \
  --branch orchestrator/devsecops-ready \
  --commit \
  --push \
  --create-pr \
  --target-branch main
```

## Optional local model

Install Ollama and pull a code model:

```bash
ollama pull qwen2.5-coder:7b
```

Run:

```bash
python agent.py "/path/to/repo" --run-validations --llm --model qwen2.5-coder:7b
```

## What the agent reports while running

It prints and stores events like:

- Inspect repository structure
- Detect project type
- Check existing CI/CD files
- Check Azure Function structure
- Check Python package configuration
- Run Python compile check
- Run Ruff format check
- Run Ruff lint check
- Run lightweight secret scan
- Run detect-secrets if installed
- Run Bandit security scan if installed
- Run Pytest with coverage if installed
- Generate Azure DevOps pipeline YAML
- Generate SonarQube config
- Generate requirements-dev.txt
- Update .gitignore with generated/evidence files
- Classify validation failures
- Create evidence report
- Create branch
- Commit changes
- Push branch
- Create or prepare PR

## Can this replace a DevOps person?

It can reduce daily manual checking of 10–20 pipelines by automating:
- first-level diagnosis
- evidence collection
- validation execution
- config generation
- PR preparation
- common failure classification

But it should not fully replace human approval for:
- production deployments
- secrets/service connections
- access governance
- cloud cost-impacting changes
- compliance sign-off
- architecture decisions

## Recommended internal name

**AI DevSecOps Pipeline Orchestrator Agent**

Enterprise-friendly name:

**Pipeline Governance & Validation Orchestrator**
