# v23 — Actual SonarQube / SonarCloud Scan

AegisFlow v23 adds a real SonarQube/SonarCloud stage.

Flow:

```text
Pytest coverage creates coverage.xml
→ AegisFlow checks sonar-project.properties
→ AegisFlow checks SONAR_HOST_URL and SONAR_TOKEN
→ AegisFlow installs SonarScanner CLI if missing
→ AegisFlow runs sonar-scanner
→ Coverage is uploaded to SonarQube/SonarCloud
→ Quality gate is waited for and can block the run
→ Scanner output is added to the downloadable evidence pack
```

Required credentials:

```text
SONAR_HOST_URL
SONAR_TOKEN
Optional: SONAR_PROJECT_KEY
```

If the credentials are not provided, AegisFlow keeps generating coverage.xml and Sonar-ready configuration, but skips the actual scanner with a clear message.
