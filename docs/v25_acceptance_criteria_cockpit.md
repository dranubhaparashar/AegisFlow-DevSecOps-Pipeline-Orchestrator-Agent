# v25 Acceptance Criteria Cockpit

AegisFlow v25 adds an explicit Acceptance Criteria tab for the Azure Function DevSecOps restructuring user story.

It maps checklist items to evidence, including:

- repo cleanup and generated-folder protection
- src/tests/conf folder structure
- Azure Function files
- import/path/config checks
- requirements split
- .gitignore expectations
- azure-pipelines.yml / azure-function.config.yml / sonar-project.properties
- local verification checks: dependency install, Ruff, Pytest coverage
- DevSecOps capability view: Azure DevOps pipeline, PR validation, CI/CD, SonarQube, unit testing, logging, artifacts, deployment validation, evidence collection

The tab labels each item as Pass, Fail, Partial, Skipped, or Manual/cloud-only so the user can see whether the story is ready to close.
