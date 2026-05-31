# AegisFlow AI v5 — Downloadable Evidence, Ollama Automation, CI/CD Experience

## New in v5

### 1. Downloadable evidence pack
AegisFlow now creates a ZIP package for every run under `orchestrator_reports/`.

The evidence ZIP includes, when available:

- Markdown report
- JSON report
- `coverage.xml`
- `test-results.xml`
- `azure-pipeline.yml` or `azure-pipelines.yml`
- `sonar-project.properties`
- `pytest.ini`
- `.coveragerc`
- `requirements.txt`
- `requirements-dev.txt`

The Streamlit UI provides direct download buttons for:

- Full evidence ZIP
- Markdown report
- JSON report

Heavy source/model files are intentionally not copied into the evidence ZIP.

### 2. Ollama model automation
When local AI is enabled, AegisFlow now:

1. Checks whether the Ollama server is available.
2. Tries to start `ollama serve` in the background if the server is not responding.
3. Checks whether the selected model exists locally.
4. Runs `ollama pull <model>` automatically if the model is missing.
5. Retries recommendation generation after model download if Ollama returned HTTP 404.

### 3. Better failure experience
Every failed or skipped check now shows:

- What failed
- The command that ran
- Failure classification
- Suggested owner
- Severity
- Common fixes
- Tail of the raw evidence log

### 4. Better CI/CD UI experience
The app now has:

- Enterprise dashboard styling
- CI/CD stage cards
- Passed/failed/skipped metric cards
- Release decision support card
- Download panel
- Better progress timeline
- Governance and PR comment tabs

### 5. Optional Hadolint automation
When correction tools are enabled, AegisFlow tries to install Hadolint into:

```text
~/.local/bin/hadolint
```

This avoids needing sudo for Dockerfile linting.

## Important governance rule

AegisFlow can recommend production readiness, but it must not automatically approve:

- Production deployment
- Secrets/access governance
- Architecture approval
- Compliance sign-off

Those remain human-owned decisions.
