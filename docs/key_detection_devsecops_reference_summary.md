# Key Detection Function App — DevSecOps / MLOps Technical Summary

**Project:** GIS Key Detection Function App  
**Branch:** `feature/devsecops-restructure`  
**Technical work name:** DevSecOps-enabled Azure Function repository restructuring with Azure DevOps PR validation pipeline  
**Purpose:** Standardize the repository, add automated validation, improve test coverage, secure configuration, and verify the pipeline from Azure DevOps cloud portal.

---

## 1. Executive Summary

We restructured the Key Detection Function App repository into a clean, standard, CI/CD-ready layout and implemented a DevSecOps validation pipeline using Azure DevOps. The work included unit testing, code coverage, linting, formatting, secret scanning, static security analysis, SonarQube readiness, and cloud-based pipeline validation.

The validation was executed from the Azure DevOps portal, not only from local terminal. The portal run showed successful test execution and high coverage.

---

## 2. High-Level Technical Name

The complete activity can be described as:

> **DevSecOps-enabled Azure Function repository restructuring with Azure DevOps PR validation pipeline**

Alternative technical names:

- **Azure DevOps PR Validation Pipeline Implementation**
- **Key Detection Function App Standardization and CI Validation**
- **Repository Restructuring with Automated Testing, Coverage, Linting, Secret Scan, and Security Scan**
- **DevSecOps Quality Gate Setup for Azure Function App**

---

## 3. What We Did

### 3.1 Repository Restructuring

We converted the repository into a cleaner standard structure.

Final target structure:

```text
root/
├── docs/
├── infra/
│   └── docker/
├── src/
│   ├── __init__.py
│   ├── app.py
│   ├── function.json
│   └── conf/
│       ├── best.pt
│       └── parameters.yaml
├── tests/
│   ├── conftest.py
│   ├── test_app.py
│   ├── test_azure_function_entrypoint.py
│   ├── test_key_detection_api_test.py
│   └── test_placeholder.py
├── .coveragerc
├── .gitignore
├── azure-function.config.yml
├── azure-pipeline.yml
├── host.json
├── pytest.ini
├── README.md
├── requirements.txt
├── requirements-dev.txt
└── sonar-project.properties
```

This improved maintainability, readability, and pipeline compatibility.

---

### 3.2 Root Folder Cleanup

We cleaned unnecessary files from the outer/root folder.

Actions completed:

| Previous root-level item | Action taken |
|---|---|
| `sample_input.jpg` | Removed from root |
| `test.jpg` | Removed from root |
| `best.pt` | Moved to `src/conf/best.pt` |
| `Dockerfile` | Moved to `infra/docker/Dockerfile` |
| `.dockerignore` | Moved to `infra/docker/.dockerignore` |
| `.funcignore` | Removed |
| `azure-pipelines-pr-validation.yml` | Renamed to `azure-pipeline.yml` |
| Generated coverage files | Removed and ignored |
| Cache folders | Removed and ignored |

Purpose:

- Keep repository root clean.
- Separate infrastructure files from source code.
- Keep model/configuration assets in the appropriate folder.
- Remove temporary/generated files from Git.

---

### 3.3 Azure Function App Standardization

We organized files needed for Azure Function app structure.

Files added/organized:

```text
src/__init__.py
src/function.json
host.json
azure-function.config.yml
src/conf/parameters.yaml
```

Purpose:

- Make the function app structure clearer.
- Keep app entrypoint and trigger configuration inside `src/`.
- Keep runtime configuration separate from code.

---

### 3.4 Configuration Management

We added/updated configuration handling.

Files/configs involved:

```text
src/conf/parameters.yaml
.coveragerc
pytest.ini
sonar-project.properties
requirements-dev.txt
.gitignore
```

Purpose:

- Keep model path and threshold parameters in config.
- Define pytest behavior.
- Configure coverage reporting.
- Prepare the repo for SonarQube.
- Keep local/generated files out of Git.

---

### 3.5 Removed ArcGIS Dependency from Validation Flow

Initially, the validation script included ArcGIS-specific workflow:

```text
ArcGIS Portal OAuth
→ ArcGIS Feature Layer query
→ Attachment fetch
→ Image download
→ Azure API detection
```

This was simplified because the validation pipeline should not depend on ArcGIS credentials for normal PR validation.

New validation flow:

```text
Local/test images
→ Azure Key Detection API health check
→ Azure API prediction
→ Detection summary
→ JSON/log evidence
```

Reason:

- CI validation should be cloud-friendly.
- Unit tests should not depend on live ArcGIS credentials.
- External integration can remain optional.

---

### 3.6 Secret Handling and Security Cleanup

We removed hardcoded secrets and moved sensitive values to environment variables.

Examples:

```python
os.getenv("KEY_DETECTION_API_KEY")
os.getenv("ARCGIS_CLIENT_SECRET")
os.getenv("API_KEY")
```

We also updated `.gitignore` to prevent accidental commits of:

```text
local.settings.json
.env
*.env
coverage.xml
test-results.xml
validation_results/
htmlcov/
.pytest_cache/
.ruff_cache/
__pycache__/
```

Security objective:

- Prevent API keys and client secrets from being committed.
- Make pipeline secrets configurable from Azure DevOps variables.
- Support secret scanning in CI/CD.

---

### 3.7 Unit Test Development

We added unit tests for major app behavior and validation logic.

Test files:

```text
tests/conftest.py
tests/test_app.py
tests/test_azure_function_entrypoint.py
tests/test_key_detection_api_test.py
tests/test_placeholder.py
```

Coverage areas:

| Area | What was tested |
|---|---|
| FastAPI root endpoint | App returns expected status |
| Health endpoint | Health response and model status |
| API key security | Missing/wrong key rejected |
| Prediction endpoint | Valid/invalid image behavior |
| Inference failure | 500 response for model failure |
| YOLO output handling | Mocked boxes, class names, confidence, bounding boxes |
| No detection case | Empty detection result handled |
| API validation helper | Detection filtering, summaries, image discovery |
| Environment config | Required env vars and missing env handling |
| Error paths | HTTP error and generic exception handling |
| Azure Function wrapper | `/api` prefix stripping behavior |
| Placeholder test | Minimum acceptance test present |

---

### 3.8 Mock-Based Testing

We used mocks to avoid calling real external services during unit tests.

Mocked components:

```text
YOLO model loading
YOLO model prediction
HTTP responses
HTTP errors
Runtime errors
Environment variables
Temporary image files
FastAPI requests
Azure Function path wrapper
```

Why this is important:

- Unit tests should be deterministic.
- Tests should run in CI/CD without real credentials.
- External services should be validated separately as integration tests.

---

### 3.9 Code Coverage Setup

We configured Python coverage reporting using `pytest-cov` and `coverage.py`.

Files involved:

```text
.coveragerc
coverage.xml
pytest.ini
```

Command used locally:

```bash
python -m pytest -v \
  --cov=src \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml \
  --junitxml=test-results.xml
```

Final local validation showed:

```text
38 tests passed
src/app.py                         100%
src/key_detection_api_test.py      100%
src/__init__.py                     95%
TOTAL                               99%
```

Azure DevOps portal showed approximately:

```text
100% tests passed
99.49% line coverage
```

---

### 3.10 Ruff Formatting and Linting

We added Ruff for Python code quality.

Commands used:

```bash
python -m ruff format ./src ./tests
python -m ruff check ./src ./tests
python -m ruff format --check ./src ./tests
```

Issue fixed:

```text
F401: pathlib.Path imported but unused
```

Purpose:

- Enforce formatting.
- Catch unused imports.
- Improve readability and consistency.

---

### 3.11 Secret Scanning

We added secret scanning using `detect-secrets`.

Pipeline step:

```bash
detect-secrets scan
```

Purpose:

- Detect hardcoded secrets.
- Prevent credentials from entering the repository.
- Support DevSecOps validation.

---

### 3.12 Static Security Analysis

We added Bandit for Python static security analysis.

Pipeline step:

```bash
bandit -r src -ll
```

Purpose:

- Detect insecure Python patterns.
- Add SAST-style security validation.
- Improve release confidence.

---

### 3.13 SonarQube Readiness

We added SonarQube configuration.

File:

```text
sonar-project.properties
```

Purpose:

- Define source and test paths.
- Provide coverage report path.
- Make repository ready for SonarQube quality analysis.

Typical configuration items:

```properties
sonar.sources=src
sonar.tests=tests
sonar.python.coverage.reportPaths=coverage.xml
```

---

### 3.14 Azure DevOps YAML Pipeline

We added the main pipeline file:

```text
azure-pipeline.yml
```

The pipeline includes these stages/steps:

```text
Checkout repository
Use Python 3.11
Install dependencies
Create evidence folder
Ruff formatting check
Ruff lint check
Secret scan
Bandit static security scan
Pytest with coverage
Optional Azure Key Detection API cloud test
Publish test results
Publish code coverage results
Publish validation evidence artifact
```

Purpose:

- Run validation in Azure DevOps cloud.
- Verify from portal instead of local-only.
- Provide evidence for PR review.

---

### 3.15 Cloud Pipeline Execution from Azure DevOps Portal

We ran the validation from the Azure DevOps portal.

Portal result summary:

```text
Pipeline status: Passed
Tests: 100% passed
Coverage: 99.49%
Artifacts: Published
```

This satisfied the requirement that the validation should be executed from the Git cloud / Azure DevOps portal.

---

### 3.16 Pipeline Artifact Publishing

The pipeline publishes evidence such as:

```text
test-results.xml
coverage.xml
validation logs
pipeline artifact folder
```

Purpose:

- Provide audit evidence.
- Support PR review.
- Allow the team to download logs and reports.

---

### 3.17 Pull Request Readiness

The branch is ready for PR creation.

Branch:

```text
feature/devsecops-restructure
```

PR target:

```text
main
```

Recommended PR title:

```text
Key Detection - Restructure repo to standard structure
```

Recommended PR description summary:

```text
Restructured the Key Detection Function App repo according to acceptance criteria. Added tests, Ruff linting/formatting, secret scanning, Bandit security scan, SonarQube config, coverage reporting, and Azure DevOps pipeline validation. Pipeline passed from Azure DevOps portal with 100% tests passed and 99.49% coverage.
```

---

## 4. Technologies Used

### 4.1 Version Control and Collaboration

| Technology | Purpose |
|---|---|
| Git | Source control and commits |
| Azure Repos | Cloud Git repository |
| Feature branch workflow | Development on `feature/devsecops-restructure` |
| Pull Request workflow | Review and merge process |

---

### 4.2 Cloud CI/CD

| Technology | Purpose |
|---|---|
| Azure DevOps Pipelines | Cloud pipeline execution |
| YAML pipeline | Pipeline-as-code configuration |
| Pipeline artifacts | Publish validation evidence |
| Test result publishing | Show test results in Azure DevOps |
| Code coverage publishing | Show coverage in Azure DevOps |

---

### 4.3 Azure / Deployment Related

| Technology | Purpose |
|---|---|
| Azure Function App structure | Serverless API/function organization |
| `host.json` | Azure Function host configuration |
| `function.json` | Function trigger/route configuration |
| `azure-function.config.yml` | Function deployment/runtime config |
| Azure Container Apps endpoint | Optional deployed API validation |

---

### 4.4 Python Backend / ML API

| Technology | Purpose |
|---|---|
| Python 3.11 | Runtime language |
| FastAPI | API framework |
| Requests | HTTP calls for validation test |
| Pillow | Image creation/loading in tests |
| Ultralytics YOLO | Key detection model inference |
| YAML config | Externalized parameters |

---

### 4.5 Testing

| Technology | Purpose |
|---|---|
| Pytest | Unit testing framework |
| pytest-cov | Coverage plugin |
| FastAPI TestClient | API endpoint testing |
| unittest.mock | Mock external calls and model behavior |
| tmp_path fixture | Temporary file/image testing |
| monkeypatch fixture | Environment variable testing |

---

### 4.6 Code Quality

| Technology | Purpose |
|---|---|
| Ruff | Python formatting and linting |
| Ruff F401 check | Detect unused imports |
| `.coveragerc` | Coverage reporting rules |
| `pytest.ini` | Pytest configuration |

---

### 4.7 Security / DevSecOps

| Technology | Purpose |
|---|---|
| detect-secrets | Secret scanning |
| Bandit | Python static security analysis |
| Environment variables | Secure secret handling |
| `.gitignore` | Prevent local/generated/secret files from entering Git |

---

### 4.8 Code Coverage and Reporting

| Technology | Purpose |
|---|---|
| coverage.py | Coverage engine |
| `coverage.xml` | Coverage report for CI/SonarQube |
| JUnit XML | Test result format for Azure DevOps |
| Azure DevOps Code Coverage tab | Portal visibility of coverage |

---

### 4.9 Static Analysis Readiness

| Technology | Purpose |
|---|---|
| SonarQube | Static code quality analysis readiness |
| `sonar-project.properties` | SonarQube project/source/test configuration |

---

## 5. Validation Evidence Summary

Local validation:

```text
38 tests passed
src/app.py                         100%
src/key_detection_api_test.py      100%
src/__init__.py                     95%
TOTAL                               99%
```

Azure DevOps portal validation:

```text
Pipeline passed
100% tests passed
99.49% coverage
Artifacts published
```

---

## 6. Commands Used

### 6.1 Ruff

```bash
python -m ruff format ./src ./tests
python -m ruff check ./src ./tests
python -m ruff format --check ./src ./tests
```

### 6.2 Pytest and Coverage

```bash
python -m pytest -v \
  --cov=src \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml \
  --junitxml=test-results.xml
```

### 6.3 Cleanup Generated Files

```bash
rm -f coverage.xml test-results.xml .coverage
rm -rf htmlcov .pytest_cache .ruff_cache validation_results
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
```

### 6.4 Git Commit and Push

```bash
git add -A
git commit -m "Match repo structure acceptance criteria"
git push
```

---

## 7. Final Team Update

Suggested update to share:

> I restructured the Key Detection Function App repo into a standard Azure Function layout and implemented an Azure DevOps PR validation pipeline. The pipeline runs Ruff formatting/linting, secret scanning, Bandit static security scan, Pytest unit tests, coverage reporting, and artifact publishing. I also cleaned the repo root, moved Docker files to `infra/docker`, moved the model to `src/conf`, added tests for app behavior and validation logic, and verified the pipeline from the Azure DevOps portal. The cloud run passed with 100% tests passed and 99.49% code coverage.

---

## 8. Pending / Next Step

Before closing the user story:

```text
1. Create Pull Request from feature/devsecops-restructure to main.
2. Link the PR to the Azure DevOps work item.
3. Add Arth/team as reviewers.
4. Attach or reference pipeline evidence.
5. Close the story only after review/approval.
```

Recommended PR title:

```text
Key Detection - Restructure repo to standard structure
```

Recommended PR validation note:

```text
Azure DevOps pipeline passed from portal with 100% tests passed and 99.49% coverage.
```
