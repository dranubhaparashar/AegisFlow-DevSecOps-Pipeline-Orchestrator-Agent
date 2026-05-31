# AegisFlow: DevSecOps Pipeline Orchestrator Agent

## v29 Dashboard tab layout update

This version keeps the v28 evidence cockpit and changes the dashboard navigation so tabs wrap into two lines instead of using a horizontal scrollbar.

Run:

```bash
conda activate aegisflow
pip install -r requirements.txt
python -m streamlit run app.py
```

# AegisFlow: DevSecOps Pipeline Orchestrator Agent

## v28 Evidence Cockpit

This version improves the Report & Downloads experience:

- Evidence ZIP, Markdown, and JSON downloads use robust file names and browser-safe download buttons.
- The dashboard shows the evidence pack contents before download.
- Coverage evidence is parsed from `coverage.xml` and shown as dashboard metrics/table.
- Test evidence is parsed from `test-results.xml` and shown as dashboard metrics.
- Validation results are shown in a table.
- Markdown, JSON, coverage XML, test XML, and Sonar output previews are visible inside the dashboard.
- If browser download does not start, the local file path and copy command are shown.

Run:

```bash
conda activate aegisflow
pip install -r requirements.txt
python -m streamlit run app.py
```

# AegisFlow: DevSecOps Pipeline Orchestrator Agent

Version v27 removes the internal release banner from the dashboard while keeping persistent run results across tabs/downloads.

# AegisFlow: DevSecOps Pipeline Orchestrator Agent v23

Agentic DevSecOps & MLOps Orchestrator.

## What is new in v16

- Long-running commands now show live heartbeat progress in the dashboard.
- Pytest, Hadolint, Ollama install, and Ollama model downloads no longer appear frozen.
- The Live Progress tab shows:
  - current running step
  - command being executed
  - current step progress
  - elapsed time
  - latest log output tail
  - execution timeline cards
- Repo scanning still runs only when you click **Prefetch repo details** or **Run orchestrator**.

## Run in WSL with Conda

```bash
cd aegisflow_ai_v16
conda activate aegisflow
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Use a WSL path like:

```text
/mnt/c/Users/AnubhaAnubha/OneDrive - Pearce Services, LLC/onedrive_ubuntu/project/gis-key-detection-func
```

## Notes

Ollama first-run setup is now built in. v16 checks whether Ollama is installed, starts the server, checks the local model cache, downloads the selected model if missing, shows live download progress/elapsed time, and skips the download on future runs when the model already exists locally.

## Ollama/model bootstrap behavior

When **Use local Ollama recommendation** is enabled, AegisFlow performs this sequence:

```text
Check Ollama CLI
→ install Ollama in WSL/Linux if missing
→ start `ollama serve` if the server is not running
→ check local model cache with `/api/tags` and `ollama list`
→ if the selected model is missing, run `ollama pull <model>`
→ show live progress and latest output while the model downloads
→ on future runs, detect the local model and skip download
```

The first model download can take several minutes because models are large. The dashboard keeps updating so clients can see that the setup is still progressing.


## v16 fixes
- Fixed missing FailureIntelligenceEngine crash.
- Adds deterministic failure analysis, log summary, governance decision support, and PR comment generation.
- Installs repo requirements.txt and requirements-dev.txt when install/update tools is enabled.
- Runs validations with PYTHONPATH including repo root and src.
- Keeps Ollama/model bootstrap with live progress.


## v19 AI Fix Plan

AegisFlow now supports a safer auto-fix workflow: generate a fix plan, review exact file diffs, approve, apply patch, rerun affected validation, and compare before/after results. Dockerfile/Hadolint fixes are deterministic and approval-gated.


## v19 updates

- Adds an **Aegis Chat** tab for questions about the last run, failures, fixes, and approvals.
- Adds approval-based Dockerfile fix proposals for Hadolint rules such as DL3008/DL3013 when exact package versions cannot be safely inferred.
- Shows exact diffs before applying any patch.
- Requires explicit approval before applying patches and reruns affected validation afterward.
- Keeps version pinning / policy exceptions visible instead of silently editing risky files.


## v21 update

Aegis Chat now uses the Ollama HTTP API (`/api/generate`) instead of the interactive `ollama run` command. This prevents terminal spinner/ANSI control sequences from appearing as garbled text in the dashboard. If Ollama is unavailable, the chat falls back to deterministic run-context answers.


## v22 safety fix: generated folder protection

AegisFlow now treats `.aegisflow_backups/` and `orchestrator_reports/` as protected generated folders. It will not scan, lint, patch, back up recursively, or commit these folders. This prevents nested backup paths such as `.aegisflow_backups/.../.aegisflow_backups/.../infra/docker/Dockerfile` from being incorrectly treated as real source files.

Recommended one-time cleanup in existing repositories:

```bash
rm -rf .aegisflow_backups
git rm -r --cached .aegisflow_backups orchestrator_reports 2>/dev/null || true
```


## v23 SonarQube / SonarCloud actual scan

AegisFlow now supports actual SonarQube/SonarCloud analysis, not just Sonar readiness. Enable **Run SonarQube/SonarCloud scan with coverage** in the sidebar and provide:

```bash
export SONAR_HOST_URL="https://your-sonarqube-server"
export SONAR_TOKEN="your-token"
export SONAR_PROJECT_KEY="your-project-key"   # optional; repo name is used if omitted
```

The agent runs Pytest coverage first, creates `coverage.xml`, runs `sonar-scanner`, waits for the quality gate when enabled, and puts `validation_results/sonar-scanner-output.txt` into the evidence ZIP.

## v26 update — Acceptance Criteria cockpit

This version adds an **Acceptance Criteria** tab that shows the restructuring checklist and DevSecOps closure readiness as a visible pass/fail/manual-review table. It is designed for the user story requiring repo restructuring before connecting the central Azure DevOps pipeline template.


## v26 update

- Keeps the last orchestrator run visible across Streamlit tab changes, download clicks, chat input, and normal UI reruns.
- Adds a persistent Report & Downloads view restored from `st.session_state["last_report"]`.
- Adds a clearer SonarQube tab explanation: Azure DevOps Code Coverage is `pytest -> coverage.xml -> PublishCodeCoverageResults`; SonarQube is separate and requires `SONAR_HOST_URL` and `SONAR_TOKEN`.
- Adds persistent Live Progress replay from the saved event timeline.


## v30 - Azure DevOps-style coverage dashboard

Adds a visual coverage cockpit inside Report & Downloads that renders coverage.xml with Azure DevOps-like cards: Information, Line coverage, Branch coverage, Method coverage, and per-file progress bars. This makes the coverage result visible inside AegisFlow without opening Azure DevOps.
