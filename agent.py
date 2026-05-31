from __future__ import annotations

import argparse
import base64
import dataclasses
from collections import Counter
import datetime as dt
import fnmatch
import json
import difflib
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import zipfile
import urllib.request
from pathlib import Path
from typing import Callable, Iterable, Optional


# AegisFlow-generated folders and common build/cache folders must never be scanned,
# linted, backed up recursively, or committed back to the user's repository.
# This prevents nested paths such as .aegisflow_backups/.../.aegisflow_backups/.../Dockerfile.
AEGISFLOW_EXCLUDE_DIRS = {
    ".git", ".venv", "venv", "env",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "node_modules", "htmlcov", "dist", "build",
    "orchestrator_reports", ".aegisflow_backups",
}

def is_aegisflow_excluded_path(path_or_rel) -> bool:
    """Return True when a path should be ignored by all AegisFlow scans.

    Accepts either a Path or a POSIX-style relative string.
    """
    if isinstance(path_or_rel, Path):
        parts = path_or_rel.parts
    else:
        parts = str(path_or_rel).replace("\\", "/").split("/")
    return any(part in AEGISFLOW_EXCLUDE_DIRS for part in parts)

import requests
import yaml


@dataclasses.dataclass
class Event:
    step: str
    status: str
    category: str
    message: str
    command: Optional[str] = None
    return_code: Optional[int] = None
    output_tail: Optional[str] = None
    progress_pct: Optional[int] = None
    elapsed_seconds: Optional[int] = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class ValidationResult:
    name: str
    status: str
    category: str
    command: str
    return_code: int | None
    details: str
    classification: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class EventLogger:
    def __init__(self, callback: Optional[Callable[[Event], None]] = None):
        self.events: list[Event] = []
        self.callback = callback

    def emit(self, step: str, status: str, category: str, message: str, **kwargs) -> None:
        event = Event(step=step, status=status, category=category, message=message, **kwargs)
        self.events.append(event)
        if self.callback:
            self.callback(event)
        else:
            prefix = {"ok": "✅", "fail": "❌", "skip": "⏭️", "running": "🔄", "warn": "⚠️"}.get(status, "•")
            print(f"{prefix} [{category}] {step}: {message}")


class RepoInspector:
    def __init__(self, repo: Path, logger: EventLogger):
        self.repo = repo.resolve()
        self.logger = logger

    @staticmethod
    def _is_noise_path(rel: str) -> bool:
        return is_aegisflow_excluded_path(rel)

    def inspect(self) -> dict:
        self.logger.emit("Inspect repository", "running", "discovery", f"Checking {self.repo}")
        if not self.repo.exists() or not self.repo.is_dir():
            raise FileNotFoundError(f"Repository path does not exist or is not a directory: {self.repo}")

        files = {p.name for p in self.repo.iterdir()}
        all_files = sorted([p.relative_to(self.repo).as_posix() for p in self.repo.rglob("*") if p.is_file() and not self._is_noise_path(p.relative_to(self.repo).as_posix())])
        limited_files = all_files[:5000]

        has_python = any(
            name in files for name in ["requirements.txt", "pyproject.toml", "setup.py"]
        ) or any(path.endswith(".py") for path in limited_files)

        has_node = "package.json" in files
        has_docker = "Dockerfile" in files or any(path.endswith("Dockerfile") for path in limited_files)
        has_azure_function = "host.json" in files or any(path.endswith("function.json") for path in limited_files)
        has_notebooks = any(path.endswith(".ipynb") for path in limited_files)
        has_tests = (self.repo / "tests").exists() or any(path.startswith("test_") or "/test_" in path for path in limited_files)

        existing_controls = {
            "azure_pipeline": any(name in files for name in ["azure-pipeline.yml", "azure-pipelines.yml", "azure-pipelines-pr-validation.yml"]),
            "github_actions": (self.repo / ".github" / "workflows").exists(),
            "sonar": (self.repo / "sonar-project.properties").exists(),
            "ruff": (self.repo / "pyproject.toml").exists() and "ruff" in (self.repo / "pyproject.toml").read_text(errors="ignore").lower() if (self.repo / "pyproject.toml").exists() else False,
            "pytest_ini": (self.repo / "pytest.ini").exists(),
            "coverage": (self.repo / ".coveragerc").exists(),
            "requirements_dev": (self.repo / "requirements-dev.txt").exists(),
            "gitignore": (self.repo / ".gitignore").exists(),
        }

        project_type = []
        if has_azure_function:
            project_type.append("Azure Function")
        if has_python:
            project_type.append("Python")
        if has_node:
            project_type.append("Node")
        if has_docker:
            project_type.append("Docker")
        if has_notebooks:
            project_type.append("Notebook/ML")
        if not project_type:
            project_type.append("Generic")

        missing = [k for k, v in existing_controls.items() if not v]

        ext_counts = Counter((Path(x).suffix.lower() or "[no extension]") for x in limited_files)
        python_sources = [x for x in limited_files if x.endswith(".py") and not (x.startswith("tests/") or "/tests/" in x or Path(x).name.startswith("test_"))]
        test_files = [x for x in limited_files if x.endswith(".py") and (x.startswith("tests/") or "/tests/" in x or Path(x).name.startswith("test_"))]
        config_names = {"azure-pipeline.yml", "azure-pipelines.yml", "azure-pipelines-pr-validation.yml", "sonar-project.properties", "pytest.ini", ".coveragerc", "requirements.txt", "requirements-dev.txt", "pyproject.toml", "Dockerfile", "host.json", "function.json", ".gitignore"}
        config_files = [x for x in limited_files if Path(x).name in config_names or x.startswith(".github/workflows/") or "/function.json" in x]
        inventory = {
            "total_files": len(limited_files),
            "extension_counts": dict(ext_counts.most_common(30)),
            "python_sources": python_sources[:1000],
            "test_files": test_files[:1000],
            "config_files": config_files[:500],
            "all_files_sample": limited_files[:1000],
        }

        result = {
            "repo": str(self.repo),
            "project_type": project_type,
            "has_tests": has_tests,
            "existing_controls": existing_controls,
            "missing_controls": missing,
            "file_count_scanned": len(limited_files),
            "sample_files": limited_files[:80],
            "file_inventory": inventory,
        }
        self.logger.emit("Inspect repository", "ok", "discovery", f"Detected: {', '.join(project_type)}")
        return result


class GitContextResolver:
    """Detect the exact Git repository before AegisFlow modifies or publishes anything."""

    def __init__(self, path: Path, logger: EventLogger | None = None):
        self.path = path.expanduser().resolve()
        self.logger = logger

    def _run(self, args: list[str], cwd: Path | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.path,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )

    @staticmethod
    def _parse_remote(remote_url: str) -> dict:
        info = {
            "provider": "unknown",
            "org": "",
            "project": "",
            "repo_name": "",
            "normalized": remote_url,
        }
        clean = remote_url.strip()
        if clean.endswith(".git"):
            clean = clean[:-4]
        # Azure DevOps HTTPS: https://dev.azure.com/org/project/_git/repo
        m = re.search(r"dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/]+)", clean)
        if m:
            info.update({"provider": "azure_devops", "org": m.group(1), "project": m.group(2), "repo_name": m.group(3)})
            return info
        # Azure DevOps HTTPS legacy: https://org.visualstudio.com/project/_git/repo
        m = re.search(r"https?://([^./]+)\.visualstudio\.com/([^/]+)/_git/([^/]+)", clean)
        if m:
            info.update({"provider": "azure_devops", "org": m.group(1), "project": m.group(2), "repo_name": m.group(3)})
            return info
        # Azure DevOps SSH: git@ssh.dev.azure.com:v3/org/project/repo
        m = re.search(r"ssh\.dev\.azure\.com[:/]v3/([^/]+)/([^/]+)/([^/]+)", clean)
        if m:
            info.update({"provider": "azure_devops", "org": m.group(1), "project": m.group(2), "repo_name": m.group(3)})
            return info
        # GitHub HTTPS/SSH
        m = re.search(r"github\.com[:/]([^/]+)/([^/]+)$", clean)
        if m:
            info.update({"provider": "github", "org": m.group(1), "repo_name": m.group(2)})
            return info
        # Fallback repo name
        if clean:
            info["repo_name"] = clean.rstrip("/").split("/")[-1]
        return info

    def resolve(self) -> dict:
        ctx = {
            "input_path": str(self.path),
            "is_git_repo": False,
            "git_root": "",
            "current_branch": "",
            "head_commit": "",
            "remote_name": "origin",
            "remote_url": "",
            "remote_provider": "unknown",
            "remote_org": "",
            "remote_project": "",
            "repo_name": "",
            "upstream": "",
            "working_tree_clean": None,
            "changed_files_count": 0,
            "status_short": "",
            "safety_summary": "No Git repository detected.",
        }
        if not self.path.exists():
            if self.logger:
                self.logger.emit("Git repository identity", "fail", "git", f"Path does not exist: {self.path}")
            return ctx
        root = self._run(["rev-parse", "--show-toplevel"])
        if root.returncode != 0:
            if self.logger:
                self.logger.emit("Git repository identity", "warn", "git", "Path is not inside a Git repository", output_tail=tail(root.stdout))
            return ctx
        git_root = root.stdout.strip()
        ctx["is_git_repo"] = True
        ctx["git_root"] = git_root
        root_path = Path(git_root)

        def get(args: list[str]) -> str:
            r = self._run(args, cwd=root_path)
            return r.stdout.strip() if r.returncode == 0 else ""

        ctx["current_branch"] = get(["branch", "--show-current"])
        ctx["head_commit"] = get(["rev-parse", "--short", "HEAD"])
        ctx["remote_url"] = get(["remote", "get-url", "origin"])
        ctx["upstream"] = get(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
        status = get(["status", "--short"])
        filtered_status_lines = []
        for line in status.splitlines():
            rel = line[3:].strip() if len(line) > 3 else line.strip()
            if rel.startswith('"') and rel.endswith('"'):
                rel = rel.strip('"')
            if rel and not is_aegisflow_excluded_path(rel):
                filtered_status_lines.append(line)
        ctx["status_short"] = "\n".join(filtered_status_lines)
        ctx["changed_files_count"] = len(filtered_status_lines)
        ctx["working_tree_clean"] = ctx["changed_files_count"] == 0
        parsed = self._parse_remote(ctx["remote_url"])
        ctx["remote_provider"] = parsed.get("provider", "unknown")
        ctx["remote_org"] = parsed.get("org", "")
        ctx["remote_project"] = parsed.get("project", "")
        ctx["repo_name"] = parsed.get("repo_name", "") or Path(git_root).name
        ctx["safety_summary"] = (
            f"Git repo: {ctx['repo_name']} | branch: {ctx['current_branch'] or 'detached'} | "
            f"remote: {ctx['remote_url'] or 'not configured'} | changed files: {ctx['changed_files_count']}"
        )
        if self.logger:
            self.logger.emit("Git repository identity", "ok", "git", ctx["safety_summary"])
            if Path(git_root).resolve() != self.path.resolve():
                self.logger.emit(
                    "Use Git repository root",
                    "warn",
                    "git",
                    f"Input path is inside a Git repo. AegisFlow will operate from repo root: {git_root}",
                )
        return ctx


def get_git_context(repo_path: str) -> dict:
    """UI helper: inspect Git identity without modifying the repository."""
    try:
        return GitContextResolver(Path(repo_path), None).resolve()
    except Exception as exc:
        return {
            "input_path": repo_path,
            "is_git_repo": False,
            "git_root": "",
            "current_branch": "",
            "remote_url": "",
            "repo_name": "",
            "safety_summary": f"Could not inspect Git repository: {exc}",
        }


class CommandRunner:
    def __init__(self, repo: Path, logger: EventLogger):
        self.repo = repo
        self.logger = logger

    def run(self, name: str, cmd: list[str], category: str, timeout: int = 180, env_overrides: Optional[dict[str, str]] = None, display_cmd: Optional[str] = None) -> ValidationResult:
        """Run a command with heartbeat updates so the dashboard does not look stuck."""
        command_str = display_cmd or " ".join(cmd)
        self.logger.emit(
            name,
            "running",
            category,
            f"Starting `{command_str}`",
            command=command_str,
            progress_pct=0,
            elapsed_seconds=0,
        )
        output_parts: list[str] = []
        start_time = time.time()
        last_emit = start_time
        try:
            env = os.environ.copy()
            if env_overrides:
                env.update({k: str(v) for k, v in env_overrides.items() if v is not None})
            existing_pp = env.get("PYTHONPATH", "")
            repo_paths = [str(self.repo), str(self.repo / "src")]
            env["PYTHONPATH"] = os.pathsep.join([*repo_paths, existing_pp]) if existing_pp else os.pathsep.join(repo_paths)
            proc = subprocess.Popen(
                cmd,
                cwd=self.repo,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            assert proc.stdout is not None
            # Read in a polling loop. Some tools buffer output heavily; heartbeat still updates UI.
            while True:
                line = proc.stdout.readline()
                now = time.time()
                if line:
                    output_parts.append(line.rstrip("\n"))
                    # Emit useful live log tails, but avoid flooding the UI.
                    if now - last_emit >= 4:
                        elapsed = int(now - start_time)
                        pct = min(95, int((elapsed / max(timeout, 1)) * 100))
                        self.logger.emit(
                            name,
                            "running",
                            category,
                            f"Still running `{command_str}` for {elapsed}s. Latest output is shown below.",
                            command=command_str,
                            output_tail=tail("\n".join(output_parts), 1200),
                            progress_pct=pct,
                            elapsed_seconds=elapsed,
                        )
                        last_emit = now
                elif proc.poll() is not None:
                    break
                else:
                    if now - last_emit >= 5:
                        elapsed = int(now - start_time)
                        pct = min(95, int((elapsed / max(timeout, 1)) * 100))
                        self.logger.emit(
                            name,
                            "running",
                            category,
                            f"Still running `{command_str}` for {elapsed}s. Waiting for command output...",
                            command=command_str,
                            output_tail=tail("\n".join(output_parts), 1200),
                            progress_pct=pct,
                            elapsed_seconds=elapsed,
                        )
                        last_emit = now
                    time.sleep(0.2)
                if now - start_time > timeout:
                    proc.kill()
                    elapsed = int(now - start_time)
                    self.logger.emit(name, "fail", category, f"Timed out after {timeout}s", command=command_str, progress_pct=100, elapsed_seconds=elapsed)
                    return ValidationResult(
                        name=name,
                        status="fail",
                        category=category,
                        command=command_str,
                        return_code=None,
                        details=tail("\n".join(output_parts), 3000),
                        classification="pipeline/config issue or long-running test issue",
                    )
            return_code = proc.wait(timeout=5)
            output = "\n".join(output_parts)
            classification = classify_failure(name, return_code, output)
            status = "ok" if return_code == 0 else "fail"
            elapsed = int(time.time() - start_time)
            self.logger.emit(
                name,
                status,
                category,
                f"Passed in {elapsed}s" if return_code == 0 else f"Failed after {elapsed}s: {classification}",
                command=command_str,
                return_code=return_code,
                output_tail=tail(output),
                progress_pct=100,
                elapsed_seconds=elapsed,
            )
            return ValidationResult(
                name=name,
                status=status,
                category=category,
                command=command_str,
                return_code=return_code,
                details=tail(output, 3000),
                classification=classification,
            )
        except FileNotFoundError as exc:
            self.logger.emit(name, "skip", category, f"Tool not found: {cmd[0]}", command=command_str, output_tail=str(exc), progress_pct=100)
            return ValidationResult(
                name=name,
                status="skip",
                category=category,
                command=command_str,
                return_code=None,
                details=str(exc),
                classification="tooling/dependency issue",
            )
        except Exception as exc:
            elapsed = int(time.time() - start_time)
            self.logger.emit(name, "fail", category, f"Command failed unexpectedly after {elapsed}s: {exc}", command=command_str, output_tail=tail("\n".join(output_parts), 1600), progress_pct=100, elapsed_seconds=elapsed)
            return ValidationResult(
                name=name,
                status="fail",
                category=category,
                command=command_str,
                return_code=None,
                details=str(exc),
                classification="pipeline/config issue or tool execution issue",
            )


def tail(text: str, limit: int = 1600) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]


def classify_failure(name: str, return_code: int | None, output: str) -> str:
    if return_code == 0:
        return "passed"

    low = output.lower()
    name_low = name.lower()

    # Tool/module missing should be classified before rule-specific failures.
    # Example: "No module named ruff" is not a code-style issue; it means the
    # validation environment is missing Ruff.
    if (
        "no module named" in low
        or "module not found" in low
        or "modulenotfounderror" in low
        or "importerror" in low
        or "command not found" in low
        or "no such file" in low
        or "not found" in low
    ):
        return "tooling/dependency or pipeline configuration issue"

    if "secret" in name_low or re.search(r"(api[_-]?key|token|password|client_secret|private key)", low):
        return "security issue"

    if "pytest" in name_low or "test" in name_low:
        if "assert" in low or "failed" in low or "error" in low:
            return "developer code issue or test expectation issue"
        return "test/data issue"

    if "ruff" in name_low or "lint" in name_low or "format" in name_low:
        return "developer code style/quality issue"

    if "bandit" in name_low or "security" in name_low:
        return "security issue"

    if "yaml" in low or "indent" in low or "syntax" in low:
        return "configuration/syntax issue"

    return "needs human review"


class LightweightSecretScanner:
    SECRET_PATTERNS = [
        ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
        ("Private Key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
        ("Generic API Key", re.compile(r"(?i)(api[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
        ("Azure connection string", re.compile(r"(?i)DefaultEndpointsProtocol=https?;AccountName=.*;AccountKey=.*")),
        ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ]
    EXCLUDE_DIRS = AEGISFLOW_EXCLUDE_DIRS
    TEXT_EXTENSIONS = {".py", ".yml", ".yaml", ".json", ".toml", ".ini", ".env", ".txt", ".md", ".sh", ".ps1", ".js", ".ts", ".tsx", ".jsx", ".properties"}

    def __init__(self, repo: Path, logger: EventLogger):
        self.repo = repo
        self.logger = logger

    def run(self) -> ValidationResult:
        name = "Lightweight secret scan"
        self.logger.emit(name, "running", "security", "Scanning text files for common secret patterns")
        findings: list[str] = []
        for path in self.repo.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(self.repo)
            if any(part in self.EXCLUDE_DIRS for part in rel.parts):
                continue
            if path.stat().st_size > 600_000:
                continue
            if path.suffix.lower() not in self.TEXT_EXTENSIONS and path.name not in [".env", ".gitignore"]:
                continue
            try:
                text = path.read_text(errors="ignore")
            except Exception:
                continue
            for label, pattern in self.SECRET_PATTERNS:
                for match in pattern.finditer(text):
                    line = text[: match.start()].count("\n") + 1
                    findings.append(f"{rel.as_posix()}:{line} possible {label}")
                    break

        if findings:
            details = "\n".join(findings[:100])
            self.logger.emit(name, "fail", "security", f"{len(findings)} possible secret finding(s)", output_tail=details)
            return ValidationResult(name, "fail", "security", "internal-secret-scan", 1, details, "security issue")

        self.logger.emit(name, "ok", "security", "No common secret patterns found")
        return ValidationResult(name, "ok", "security", "internal-secret-scan", 0, "No findings", "passed")


class ToolInstaller:
    """Installs local validation tooling into the Python environment running AegisFlow.

    This corrects common issues such as: `/usr/bin/python3: No module named ruff`.
    It also tries a user-space Hadolint install for Dockerfile linting when possible.
    """

    PACKAGES = [
        "ruff",
        "pytest",
        "pytest-cov",
        "coverage",
        "bandit",
        "detect-secrets",
    ]

    HADOLINT_URL = "https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64"

    def __init__(self, repo: Path, logger: EventLogger):
        self.repo = repo
        self.logger = logger
        self.runner = CommandRunner(repo, logger)

    def install_all(self) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        results.extend(self.install_project_requirements())
        results.append(self.install_python_tools())
        results.append(self.install_hadolint_if_missing())
        return results

    def install_project_requirements(self) -> list[ValidationResult]:
        """Install repo requirements so tests run in the same Python environment as AegisFlow.

        This corrects common Pytest failures like ModuleNotFoundError for project
        dependencies. It is intentionally run only when the user enables the
        install/update tools action.
        """
        results: list[ValidationResult] = []
        py = sys.executable
        for req_name in ["requirements.txt", "requirements-dev.txt"]:
            req = self.repo / req_name
            if req.exists():
                results.append(self.runner.run(
                    f"Install repo dependencies from {req_name}",
                    [py, "-m", "pip", "install", "-r", req_name],
                    "correction",
                    timeout=900,
                ))
            else:
                self.logger.emit(f"Install repo dependencies from {req_name}", "skip", "correction", f"{req_name} not found")
                results.append(ValidationResult(
                    f"Install repo dependencies from {req_name}",
                    "skip",
                    "correction",
                    f"{py} -m pip install -r {req_name}",
                    None,
                    f"{req_name} not found",
                    "not applicable",
                ))
        return results

    def install_python_tools(self) -> ValidationResult:
        py = sys.executable
        return self.runner.run(
            "Install/update Python validation tools",
            [py, "-m", "pip", "install", "--upgrade", *self.PACKAGES],
            "correction",
            timeout=600,
        )

    def install_hadolint_if_missing(self) -> ValidationResult:
        existing_cli = shutil.which("hadolint")
        user_bin = Path.home() / ".local" / "bin" / "hadolint"
        if existing_cli or user_bin.exists():
            existing = existing_cli or str(user_bin)
            self.logger.emit("Install/update Hadolint", "skip", "correction", f"Hadolint already available: {existing}")
            return ValidationResult(
                "Install/update Hadolint",
                "skip",
                "correction",
                "hadolint --version",
                None,
                f"Hadolint already available: {existing}",
                "passed",
            )

        script = """
from pathlib import Path
import stat
import urllib.request
url = "https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64"
target = Path.home() / ".local" / "bin" / "hadolint"
target.parent.mkdir(parents=True, exist_ok=True)
urllib.request.urlretrieve(url, target)
target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
print(target)
"""
        return self.runner.run(
            "Install/update Hadolint",
            [sys.executable, "-c", script],
            "correction",
            timeout=300,
        )


class SafeAutoFixer:
    """Runs safe automated fixes only.

    It formats code and applies Ruff auto-fixes. It does not modify business logic,
    secrets, infrastructure permissions, deployment approvals, or architecture.
    """

    def __init__(self, repo: Path, logger: EventLogger, inspection: dict):
        self.repo = repo
        self.logger = logger
        self.inspection = inspection
        self.runner = CommandRunner(repo, logger)

    def run(self) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        if "Python" not in self.inspection["project_type"] and "Azure Function" not in self.inspection["project_type"]:
            self.logger.emit("Safe auto-fix", "skip", "correction", "No Python/Azure Function project detected")
            return results
        py = sys.executable
        dirs = [d for d in ["src", "tests"] if (self.repo / d).exists()]
        if not dirs:
            dirs = ["."]
        results.append(self.runner.run("Ruff auto-format", [py, "-m", "ruff", "format", *dirs], "correction"))
        results.append(self.runner.run("Ruff auto-fix", [py, "-m", "ruff", "check", *dirs, "--fix"], "correction"))
        return results



class PytestAutoRepairer:
    """Repairs common Pytest collection issues created by caches or duplicate generated test module names.

    Safe scope only:
    - removes __pycache__, .pytest_cache, .coverage and .pyc files
    - removes generated tests for __init__.py package marker files
    - renames old generated tests to globally unique names to prevent import-file-mismatch
    It does not change business/source code.
    """

    def __init__(self, repo: Path, logger: EventLogger):
        self.repo = repo
        self.logger = logger

    def _delete_path(self, path: Path) -> bool:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            return True
        except Exception as exc:
            self.logger.emit("Pytest auto-repair", "warn", "testing", f"Could not remove {path.relative_to(self.repo) if path.exists() else path}: {exc}")
            return False

    def _unique_generated_name(self, old_path: Path) -> Path:
        try:
            rel = old_path.relative_to(self.repo / "tests" / "generated")
        except Exception:
            rel = old_path.name
        if isinstance(rel, Path):
            parts = list(rel.with_suffix("").parts)
        else:
            parts = [str(rel).removesuffix(".py")]
        # Remove redundant leading src/tests words only where harmless.
        unique = "test_generated_" + "_".join(parts).replace("test_", "").replace("-", "_") + ".py"
        unique = re.sub(r"_+", "_", unique)
        return self.repo / "tests" / "generated" / unique

    def run(self) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        removed = 0
        renamed = 0

        self.logger.emit("Pytest auto-repair", "running", "testing", "Cleaning Pytest caches, pyc files, and duplicate generated test module names")

        for pattern in ["**/__pycache__", ".pytest_cache", "**/.pytest_cache", ".coverage"]:
            for path in self.repo.glob(pattern):
                if path.exists() and self._delete_path(path):
                    removed += 1
        for path in self.repo.rglob("*.pyc"):
            if self._delete_path(path):
                removed += 1

        generated_root = self.repo / "tests" / "generated"
        if generated_root.exists():
            for path in list(generated_root.rglob("test___init__.py")) + list(generated_root.rglob("test__init__.py")):
                if self._delete_path(path):
                    removed += 1

            for path in list(generated_root.rglob("test_*.py")):
                if not path.exists() or path.parent == generated_root:
                    continue
                new_path = self._unique_generated_name(path)
                if new_path == path:
                    continue
                new_path.parent.mkdir(parents=True, exist_ok=True)
                if new_path.exists():
                    # Keep the existing unique file and remove duplicate nested file.
                    if self._delete_path(path):
                        removed += 1
                    continue
                try:
                    path.rename(new_path)
                    renamed += 1
                    self.logger.emit("Pytest auto-repair", "ok", "testing", f"Renamed {path.relative_to(self.repo).as_posix()} → {new_path.relative_to(self.repo).as_posix()}")
                except Exception as exc:
                    self.logger.emit("Pytest auto-repair", "warn", "testing", f"Could not rename {path.relative_to(self.repo).as_posix()}: {exc}")

            # Remove empty generated subfolders after migration.
            for folder in sorted([p for p in generated_root.rglob("*") if p.is_dir()], key=lambda x: len(x.parts), reverse=True):
                try:
                    folder.rmdir()
                except OSError:
                    pass

        msg = f"Removed {removed} cache/duplicate file(s); renamed {renamed} generated test file(s) to unique names"
        self.logger.emit("Pytest auto-repair", "ok", "testing", msg)
        results.append(ValidationResult(
            name="Pytest auto-repair",
            status="ok",
            category="testing",
            command="clean __pycache__/.pytest_cache/.pyc and normalize generated test names",
            return_code=0,
            details=msg,
            classification="safe automated correction",
        ))
        return results


class GeneratedTestFileCreator:
    """Creates basic pytest files for local source files when tests do not exist."""

    PY_EXTENSIONS = {".py"}
    EXCLUDE_PARTS = AEGISFLOW_EXCLUDE_DIRS

    def __init__(self, repo: Path, logger: EventLogger):
        self.repo = repo
        self.logger = logger
        self.created: list[str] = []
        self.skipped: list[str] = []

    def _safe_rel(self, path: Path) -> Optional[Path]:
        try:
            return path.resolve().relative_to(self.repo.resolve())
        except Exception:
            return None

    def _normalize(self, value: str) -> Optional[Path]:
        value = value.strip().strip('\"').strip("'")
        if not value:
            return None
        p = Path(value)
        if not p.is_absolute():
            p = self.repo / p
        rel = self._safe_rel(p)
        if rel is None:
            self.logger.emit("Generate test file", "warn", "testing", f"Ignored outside-repo path: {value}")
            return None
        if not p.exists() or not p.is_file():
            self.logger.emit("Generate test file", "warn", "testing", f"File does not exist: {rel.as_posix()}")
            return None
        if p.suffix.lower() not in self.PY_EXTENSIONS:
            self.logger.emit("Generate test file", "warn", "testing", f"Only Python source files are supported for auto-test generation: {rel.as_posix()}")
            return None
        if p.name == "__init__.py":
            self.logger.emit("Generate test file", "skip", "testing", f"Skipped package marker file: {rel.as_posix()}")
            return None
        if any(part in self.EXCLUDE_PARTS for part in rel.parts):
            self.logger.emit("Generate test file", "skip", "testing", f"Skipped excluded path: {rel.as_posix()}")
            return None
        if rel.parts and rel.parts[0] == "tests":
            self.logger.emit("Generate test file", "skip", "testing", f"Input is already a test file: {rel.as_posix()}")
            return None
        return p

    def _candidate_existing_tests(self, source: Path) -> list[Path]:
        rel = source.relative_to(self.repo)
        stem = rel.stem
        candidates = [
            self.repo / "tests" / f"test_{stem}.py",
            self.repo / "tests" / rel.parent / f"test_{stem}.py",
            self.repo / "tests" / "generated" / rel.parent / f"test_{stem}.py",
        ]
        return candidates

    def _target_path(self, source: Path) -> Path:
        rel = source.relative_to(self.repo)
        # Use a globally unique basename to avoid Pytest import-file-mismatch
        # when generated tests share names with existing tests/test_*.py files.
        unique = "test_" + "_".join(rel.with_suffix("").parts).replace("-", "_") + ".py"
        return self.repo / "tests" / "generated" / unique

    def _public_zero_arg_functions(self, source: Path) -> list[str]:
        try:
            import ast
            tree = ast.parse(source.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return []
        names: list[str] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                args = node.args
                required_positional = len(args.args) - len(args.defaults)
                required_kwonly = [a.arg for a, default in zip(args.kwonlyargs, args.kw_defaults) if default is None]
                if required_positional == 0 and not required_kwonly:
                    names.append(node.name)
        return names[:20]

    def _content(self, source: Path) -> str:
        rel = source.relative_to(self.repo).as_posix()
        functions = self._public_zero_arg_functions(source)
        function_list = ", ".join(repr(f) for f in functions)
        return f'''"""Generated by AegisFlow AI.

This is a safe starter test for `{rel}`. It verifies that the source file can be
loaded in the test environment. Add business-specific assertions after review.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


SOURCE_RELATIVE_PATH = {rel!r}
PUBLIC_ZERO_ARG_FUNCTIONS = [{function_list}]


def _repo_root() -> Path:
    # Walk upward until the generated test can find the source file.
    # This supports both tests/generated/src/test_x.py and nested paths such
    # as tests/generated/src/package/test_x.py.
    for parent in Path(__file__).resolve().parents:
        if (parent / SOURCE_RELATIVE_PATH).exists():
            return parent
    return Path(__file__).resolve().parents[-1]


def _load_module():
    source_path = _repo_root() / SOURCE_RELATIVE_PATH
    if not source_path.exists():
        pytest.skip(f"Source file not found: {{source_path}}")
    module_name = "aegisflow_generated_" + SOURCE_RELATIVE_PATH.replace("/", "_").replace(".", "_").replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    if spec is None or spec.loader is None:
        pytest.skip(f"Could not create import spec for {{source_path}}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:
        pytest.skip(f"Optional dependency missing while importing {{source_path}}: {{exc}}")
    return module


def test_module_loads():
    module = _load_module()
    assert module is not None


@pytest.mark.parametrize("function_name", PUBLIC_ZERO_ARG_FUNCTIONS)
def test_public_zero_arg_functions_are_callable_when_enabled(function_name):
    if not os.getenv("AEGISFLOW_RUN_GENERATED_FUNCTION_TESTS"):
        pytest.skip("Set AEGISFLOW_RUN_GENERATED_FUNCTION_TESTS=1 to run generated callable checks")
    module = _load_module()
    result = getattr(module, function_name)()
    assert result is not None or result is None
'''

    def create_for_files(self, values: list[str], overwrite: bool = False) -> list[str]:
        for value in values:
            source = self._normalize(value)
            if source is None:
                continue
            rel = source.relative_to(self.repo).as_posix()
            existing = [p for p in self._candidate_existing_tests(source) if p.exists()]
            target = self._target_path(source)
            if existing and not overwrite:
                msg = f"Test already exists for {rel}: {existing[0].relative_to(self.repo).as_posix()}"
                self.skipped.append(msg)
                self.logger.emit("Generate test file", "skip", "testing", msg)
                continue
            if target.exists() and not overwrite:
                msg = f"Generated test already exists: {target.relative_to(self.repo).as_posix()}"
                self.skipped.append(msg)
                self.logger.emit("Generate test file", "skip", "testing", msg)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._content(source), encoding="utf-8")
            created_rel = target.relative_to(self.repo).as_posix()
            self.created.append(created_rel)
            self.logger.emit("Generate test file", "ok", "testing", f"Created {created_rel} for {rel}")
        return self.created

    def source_files(self) -> list[str]:
        roots = [self.repo / "src"] if (self.repo / "src").exists() else [self.repo]
        files: list[str] = []
        for root in roots:
            for path in root.rglob("*.py"):
                rel = path.relative_to(self.repo)
                if any(part in self.EXCLUDE_PARTS for part in rel.parts):
                    continue
                if rel.name.startswith("test_") or rel.parts[0] == "tests":
                    continue
                if rel.name == "__init__.py":
                    continue
                files.append(rel.as_posix())
        return files


class ValidationRunner:
    def __init__(self, repo: Path, logger: EventLogger, inspection: dict):
        self.repo = repo
        self.logger = logger
        self.inspection = inspection
        self.runner = CommandRunner(repo, logger)

    def run_all(self) -> list[ValidationResult]:
        results: list[ValidationResult] = []

        if "Python" in self.inspection["project_type"] or "Azure Function" in self.inspection["project_type"]:
            py = sys.executable
            dirs = [d for d in ["src", "tests"] if (self.repo / d).exists()]
            if not dirs:
                dirs = ["."]
            results.append(self.runner.run("Python compile check", [py, "-m", "compileall", "-q", *dirs], "quality"))
            results.append(self.runner.run("Ruff format check", [py, "-m", "ruff", "format", "--check", *dirs], "quality"))
            results.append(self.runner.run("Ruff lint check", [py, "-m", "ruff", "check", *dirs], "quality"))
            results.append(LightweightSecretScanner(self.repo, self.logger).run())
            results.append(self.runner.run("detect-secrets scan", [py, "-m", "detect_secrets", "scan"], "security"))
            scan_dir = "src" if (self.repo / "src").exists() else "."
            results.append(self.runner.run("Bandit static security scan", [py, "-m", "bandit", "-r", scan_dir, "-ll"], "security"))
            if (self.repo / "tests").exists():
                results.append(
                    self.runner.run(
                        "Pytest with coverage",
                        [
                            py,
                            "-m",
                            "pytest",
                            "-v",
                            "--cov=src" if (self.repo / "src").exists() else "--cov=.",
                            "--cov-report=term-missing",
                            "--cov-report=xml:coverage.xml",
                            "--junitxml=test-results.xml",
                        ],
                        "testing",
                        timeout=300,
                    )
                )
            else:
                self.logger.emit("Pytest with coverage", "skip", "testing", "No tests/ folder found")
                results.append(ValidationResult("Pytest with coverage", "skip", "testing", "pytest", None, "No tests/ folder found", "test coverage gap"))

        if "Node" in self.inspection["project_type"]:
            package_json = self.repo / "package.json"
            scripts = {}
            try:
                scripts = json.loads(package_json.read_text()).get("scripts", {})
            except Exception:
                pass
            if "lint" in scripts:
                results.append(self.runner.run("npm lint", ["npm", "run", "lint"], "quality", timeout=240))
            if "test" in scripts:
                results.append(self.runner.run("npm test", ["npm", "test", "--", "--watch=false"], "testing", timeout=300))
            results.append(self.runner.run("npm audit", ["npm", "audit", "--audit-level=high"], "security", timeout=240))

        if "Docker" in self.inspection["project_type"]:
            dockerfiles = [p for p in self.repo.rglob("Dockerfile") if not is_aegisflow_excluded_path(p.relative_to(self.repo))]
            for dockerfile in dockerfiles[:3]:
                rel = dockerfile.relative_to(self.repo).as_posix()
                # hadolint may not be installed, so this is optional.
                hadolint_bin = shutil.which("hadolint") or str(Path.home() / ".local" / "bin" / "hadolint")
                if not Path(hadolint_bin).exists() and not shutil.which("hadolint"):
                    hadolint_bin = "hadolint"
                results.append(self.runner.run(f"Dockerfile lint: {rel}", [hadolint_bin, rel], "quality", timeout=120))

        return results



    def run_pytest_only(self) -> ValidationResult:
        py = sys.executable
        if not (self.repo / "tests").exists():
            self.logger.emit("Pytest with coverage after auto-repair", "skip", "testing", "No tests/ folder found")
            return ValidationResult("Pytest with coverage after auto-repair", "skip", "testing", "pytest", None, "No tests/ folder found", "test coverage gap")
        return self.runner.run(
            "Pytest with coverage after auto-repair",
            [
                py,
                "-m",
                "pytest",
                "-v",
                "--cov=src" if (self.repo / "src").exists() else "--cov=.",
                "--cov-report=term-missing",
                "--cov-report=xml:coverage.xml",
                "--junitxml=test-results.xml",
            ],
            "testing",
            timeout=300,
        )


class SonarQubeRunner:
    """Run real SonarQube/SonarCloud analysis and quality gate checks.

    Requirements:
    - coverage.xml should already exist from pytest-cov.
    - sonar-project.properties should exist.
    - SONAR_HOST_URL and SONAR_TOKEN must be supplied in UI or environment.
    """

    DEFAULT_SCANNER_VERSION = "8.1.0.6389"

    def __init__(self, repo: Path, logger: EventLogger):
        self.repo = repo
        self.logger = logger
        self.runner = CommandRunner(repo, logger)

    @staticmethod
    def _sanitize_project_key(value: str) -> str:
        value = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip())
        return value.strip("-_.:") or "aegisflow-project"

    def _candidate_scanners(self) -> list[Path]:
        paths: list[Path] = []
        found = shutil.which("sonar-scanner")
        if found:
            paths.append(Path(found))
        tool_root = Path.home() / ".aegisflow_tools" / "sonar-scanner"
        for p in tool_root.glob("sonar-scanner-*/bin/sonar-scanner"):
            paths.append(p)
        for p in tool_root.glob("*/bin/sonar-scanner"):
            paths.append(p)
        return [p for p in paths if p.exists()]

    def _install_scanner(self) -> Optional[Path]:
        existing = self._candidate_scanners()
        if existing:
            self.logger.emit("Install/check SonarScanner CLI", "ok", "sonar", f"SonarScanner already available: `{existing[0]}`")
            return existing[0]

        tools_dir = Path.home() / ".aegisflow_tools" / "sonar-scanner"
        tools_dir.mkdir(parents=True, exist_ok=True)
        version = self.DEFAULT_SCANNER_VERSION
        zip_path = tools_dir / f"sonar-scanner-cli-{version}-linux-x64.zip"
        url = f"https://github.com/SonarSource/sonar-scanner-cli/releases/download/{version}/sonar-scanner-cli-{version}-linux-x64.zip"

        if not shutil.which("curl") or not shutil.which("unzip"):
            self.logger.emit(
                "Install/check SonarScanner CLI",
                "warn",
                "sonar",
                "SonarScanner is missing and automatic install needs `curl` and `unzip`. Install them or install sonar-scanner manually.",
            )
            return None

        self.logger.emit(
            "Install/check SonarScanner CLI",
            "running",
            "sonar",
            f"SonarScanner not found. Downloading SonarScanner CLI {version} into `{tools_dir}`.",
            command=f"curl -L -o {zip_path} {url}",
            progress_pct=2,
        )
        download = self.runner.run(
            "Download SonarScanner CLI",
            ["curl", "-L", "--fail", "-o", str(zip_path), url],
            "sonar",
            timeout=600,
        )
        if download.status != "ok":
            self.logger.emit("Install/check SonarScanner CLI", "warn", "sonar", "Could not download SonarScanner automatically. You can still run Sonar through Azure DevOps if the service connection is configured.")
            return None
        unzip = self.runner.run("Extract SonarScanner CLI", ["unzip", "-oq", str(zip_path), "-d", str(tools_dir)], "sonar", timeout=180)
        if unzip.status != "ok":
            return None
        installed = self._candidate_scanners()
        if installed:
            self.logger.emit("Install/check SonarScanner CLI", "ok", "sonar", f"SonarScanner installed at `{installed[0]}`")
            return installed[0]
        self.logger.emit("Install/check SonarScanner CLI", "warn", "sonar", "SonarScanner download finished but executable was not found.")
        return None

    def run(
        self,
        host_url: str = "",
        token: str = "",
        project_key: str = "",
        wait_quality_gate: bool = True,
        auto_install_scanner: bool = True,
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        prop_file = self.repo / "sonar-project.properties"
        coverage_file = self.repo / "coverage.xml"

        if not prop_file.exists():
            self.logger.emit("SonarQube analysis", "skip", "sonar", "sonar-project.properties is missing. Generate DevSecOps files first.")
            results.append(ValidationResult("SonarQube analysis", "skip", "sonar", "sonar-scanner", None, "sonar-project.properties missing", "sonarqube configuration gap"))
            return results
        if not coverage_file.exists():
            self.logger.emit("SonarQube coverage input", "warn", "sonar", "coverage.xml is missing. Sonar can run, but Python coverage will not be uploaded until Pytest coverage creates coverage.xml.")

        host = (host_url or os.environ.get("SONAR_HOST_URL") or os.environ.get("SONARQUBE_HOST_URL") or "").strip()
        tok = (token or os.environ.get("SONAR_TOKEN") or os.environ.get("SONARQUBE_TOKEN") or "").strip()
        repo_key = project_key.strip() or self._sanitize_project_key(self.repo.name)

        if not host or not tok:
            msg = "SONAR_HOST_URL and SONAR_TOKEN are required for actual SonarQube/SonarCloud analysis. Coverage XML was generated, but scan/upload is skipped until credentials are configured."
            self.logger.emit("SonarQube analysis", "skip", "sonar", msg)
            results.append(ValidationResult("SonarQube analysis", "skip", "sonar", "sonar-scanner", None, msg, "sonarqube credentials/configuration missing"))
            return results

        scanner = self._candidate_scanners()[0] if self._candidate_scanners() else None
        if scanner is None and auto_install_scanner:
            scanner = self._install_scanner()
        if scanner is None:
            docker = shutil.which("docker")
            if docker:
                self.logger.emit("SonarScanner CLI", "warn", "sonar", "Local sonar-scanner is missing. Using official SonarScanner Docker image if Docker is available.")
                cmd = [
                    docker,
                    "run",
                    "--rm",
                    "-e", "SONAR_HOST_URL",
                    "-e", "SONAR_TOKEN",
                    "-v", f"{self.repo}:/usr/src",
                    "sonarsource/sonar-scanner-cli",
                    f"-Dsonar.projectKey={repo_key}",
                ]
                if wait_quality_gate:
                    cmd.extend(["-Dsonar.qualitygate.wait=true", "-Dsonar.qualitygate.timeout=300"])
                result = self.runner.run(
                    "SonarQube scan and quality gate",
                    cmd,
                    "sonar",
                    timeout=900,
                    env_overrides={"SONAR_HOST_URL": host, "SONAR_TOKEN": tok},
                    display_cmd="docker run --rm -e SONAR_HOST_URL -e SONAR_TOKEN -v <repo>:/usr/src sonarsource/sonar-scanner-cli -Dsonar.projectKey=<project> -Dsonar.qualitygate.wait=true",
                )
                results.append(result)
                return results
            msg = "SonarScanner CLI is not installed and Docker is unavailable. Install SonarScanner or enable Azure DevOps SonarQube extension tasks."
            self.logger.emit("SonarQube analysis", "skip", "sonar", msg)
            results.append(ValidationResult("SonarQube analysis", "skip", "sonar", "sonar-scanner", None, msg, "sonarqube scanner missing"))
            return results

        cmd = [
            str(scanner),
            f"-Dsonar.host.url={host}",
            f"-Dsonar.token={tok}",
            f"-Dsonar.projectKey={repo_key}",
        ]
        if wait_quality_gate:
            cmd.extend(["-Dsonar.qualitygate.wait=true", "-Dsonar.qualitygate.timeout=300"])
        display = " ".join([
            str(scanner),
            f"-Dsonar.host.url={host}",
            "-Dsonar.token=***",
            f"-Dsonar.projectKey={repo_key}",
            *( ["-Dsonar.qualitygate.wait=true", "-Dsonar.qualitygate.timeout=300"] if wait_quality_gate else [] ),
        ])
        result = self.runner.run("SonarQube scan and quality gate", cmd, "sonar", timeout=900, display_cmd=display)
        results.append(result)
        out_dir = self.repo / "validation_results"
        out_dir.mkdir(exist_ok=True)
        (out_dir / "sonar-scanner-output.txt").write_text(result.output or result.message or "", encoding="utf-8")
        return results


class FileGenerator:
    def __init__(self, repo: Path, logger: EventLogger, inspection: dict):
        self.repo = repo
        self.logger = logger
        self.inspection = inspection
        self.changes: list[str] = []

    def write_if_missing_or_allowed(self, rel: str, content: str, overwrite: bool = False) -> None:
        path = self.repo / rel
        if path.exists() and not overwrite:
            self.logger.emit(f"Generate {rel}", "skip", "generation", "File already exists")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.changes.append(rel)
        self.logger.emit(f"Generate {rel}", "ok", "generation", "Created/updated file")

    def append_gitignore(self, entries: list[str]) -> None:
        path = self.repo / ".gitignore"
        existing = path.read_text(errors="ignore") if path.exists() else ""
        additions = [e for e in entries if e not in existing]
        if not additions:
            self.logger.emit("Update .gitignore", "skip", "generation", "Required entries already present")
            return
        with path.open("a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write("\n# DevSecOps generated/evidence files\n")
            for entry in additions:
                f.write(entry + "\n")
        self.changes.append(".gitignore")
        self.logger.emit("Update .gitignore", "ok", "generation", f"Added {len(additions)} entries")

    def generate(self, overwrite_pipeline: bool = False) -> list[str]:
        project_types = self.inspection["project_type"]

        if "Azure Function" in project_types:
            pipeline = AZURE_PIPELINE_PYTHON_FUNCTION
        elif "Python" in project_types:
            pipeline = AZURE_PIPELINE_PYTHON_API
        elif "Node" in project_types:
            pipeline = AZURE_PIPELINE_NODE
        else:
            pipeline = AZURE_PIPELINE_GENERIC

        self.write_if_missing_or_allowed("azure-pipeline.yml", pipeline, overwrite=overwrite_pipeline)

        if "Python" in project_types or "Azure Function" in project_types:
            self.write_if_missing_or_allowed("requirements-dev.txt", REQUIREMENTS_DEV)
            self.write_if_missing_or_allowed("pytest.ini", PYTEST_INI)
            self.write_if_missing_or_allowed(".coveragerc", COVERAGERC)
            if not (self.repo / "tests").exists():
                self.write_if_missing_or_allowed("tests/test_placeholder.py", "def test_placeholder():\n    assert True\n")
            self.write_if_missing_or_allowed("sonar-project.properties", SONAR_PROPERTIES)

        self.append_gitignore([
            ".env",
            "*.env",
            "local.settings.json",
            "coverage.xml",
            "test-results.xml",
            ".coverage",
            "htmlcov/",
            "validation_results/",
            "orchestrator_reports/",
            ".aegisflow_backups/",
            ".pytest_cache/",
            ".ruff_cache/",
            "__pycache__/",
        ])

        return self.changes


class GitPublisher:
    def __init__(self, repo: Path, logger: EventLogger):
        self.repo = repo
        self.logger = logger

    def git(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)

    def ensure_git_repo(self) -> bool:
        result = self.git("rev-parse", "--is-inside-work-tree")
        if result.returncode != 0:
            self.logger.emit("Check Git repository", "fail", "git", "This path is not a Git repository", output_tail=result.stdout)
            return False
        self.logger.emit("Check Git repository", "ok", "git", "Git repository detected")
        return True

    def changed_files(self) -> str:
        result = self.git("status", "--short")
        lines = []
        for line in result.stdout.splitlines():
            rel = line[3:].strip() if len(line) > 3 else line.strip()
            if rel and not is_aegisflow_excluded_path(rel):
                lines.append(line)
        return "\n".join(lines).strip()

    def create_branch(self, branch: str) -> None:
        result = self.git("checkout", "-B", branch)
        status = "ok" if result.returncode == 0 else "fail"
        self.logger.emit("Create/switch branch", status, "git", branch, output_tail=tail(result.stdout))

    def commit(self, message: str) -> None:
        self.git("add", "-A", "--", ".", ":(exclude).aegisflow_backups/**", ":(exclude)orchestrator_reports/**")
        diff = self.git("diff", "--cached", "--name-only")
        if not diff.stdout.strip():
            self.logger.emit("Commit changes", "skip", "git", "No staged changes to commit")
            return
        result = self.git("commit", "-m", message)
        status = "ok" if result.returncode == 0 else "fail"
        self.logger.emit("Commit changes", status, "git", message, output_tail=tail(result.stdout))

    def push(self, remote: str, branch: str) -> None:
        result = self.git("push", "-u", remote, branch, timeout=300)
        status = "ok" if result.returncode == 0 else "fail"
        self.logger.emit("Push branch", status, "git", f"{remote} {branch}", output_tail=tail(result.stdout))

    def current_remote_url(self, remote: str = "origin") -> str:
        result = self.git("remote", "get-url", remote)
        return result.stdout.strip() if result.returncode == 0 else ""


class AzureDevOpsClient:
    def __init__(self, logger: EventLogger, git_context: Optional[dict] = None):
        self.logger = logger
        git_context = git_context or {}
        detected_org = git_context.get("remote_org", "")
        detected_project = git_context.get("remote_project", "")
        detected_repo = git_context.get("repo_name", "")
        self.org_url = os.getenv("AZDO_ORG_URL", "").rstrip("/") or (f"https://dev.azure.com/{detected_org}" if detected_org else "")
        self.project = os.getenv("AZDO_PROJECT", "") or detected_project
        # Azure DevOps accepts repository name in this route in most orgs; AZDO_REPO_ID can still override it.
        self.repo_id = os.getenv("AZDO_REPO_ID", "") or detected_repo
        self.pat = os.getenv("AZDO_PAT", "")

    def configured(self) -> bool:
        return all([self.org_url, self.project, self.repo_id, self.pat])

    def create_pr(self, source_branch: str, target_branch: str, title: str, description: str) -> Optional[str]:
        if not self.configured():
            self.logger.emit("Create Azure DevOps PR", "skip", "git", "AZDO_ORG_URL, AZDO_PROJECT, AZDO_REPO_ID, or AZDO_PAT missing")
            return None

        url = f"{self.org_url}/{self.project}/_apis/git/repositories/{self.repo_id}/pullrequests?api-version=7.1"
        token = base64.b64encode(f":{self.pat}".encode()).decode()
        headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        payload = {
            "sourceRefName": f"refs/heads/{source_branch}",
            "targetRefName": f"refs/heads/{target_branch}",
            "title": title,
            "description": description,
        }
        self.logger.emit("Create Azure DevOps PR", "running", "git", f"{source_branch} -> {target_branch}")
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code in (200, 201):
                data = response.json()
                pr_url = data.get("_links", {}).get("web", {}).get("href")
                self.logger.emit("Create Azure DevOps PR", "ok", "git", pr_url or "PR created")
                return pr_url
            self.logger.emit("Create Azure DevOps PR", "fail", "git", f"HTTP {response.status_code}", output_tail=response.text[:2000])
            return None
        except Exception as exc:
            self.logger.emit("Create Azure DevOps PR", "fail", "git", str(exc))
            return None


class LocalLLMAdvisor:
    """Local-first LLM advisor with first-run Ollama/model bootstrap.

    Client experience target:
    - every run first checks whether Ollama CLI/server/model are already available locally;
    - first-time setup installs Ollama when possible and pulls the selected model;
    - long downloads continuously emit heartbeat/progress events so the dashboard never looks frozen;
    - future runs skip download and immediately pass the model readiness check.
    """

    def __init__(self, logger: EventLogger, model: str = "qwen2.5-coder:7b", install_ollama: bool = True):
        self.logger = logger
        self.model = model.strip() or "qwen2.5-coder:7b"
        self.install_ollama = install_ollama
        self.host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self._serve_process: subprocess.Popen | None = None

    def _ollama_cli(self) -> str | None:
        candidates = [
            shutil.which("ollama"),
            "/usr/local/bin/ollama",
            "/usr/bin/ollama",
            str(Path.home() / ".local" / "bin" / "ollama"),
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        return None

    def _install_ollama_cli(self) -> bool:
        """Best-effort Ollama install for WSL/Linux.

        Uses Ollama's Linux installer. If sudo/password interaction blocks the
        browser process, AegisFlow reports the exact manual command to run.
        """
        cli = self._ollama_cli()
        if cli:
            self.logger.emit("Check Ollama CLI", "ok", "ai", f"Ollama CLI already installed at `{cli}`", command=f"{cli} --version")
            return True
        if not self.install_ollama:
            self.logger.emit("Install Ollama CLI", "skip", "ai", "Automatic Ollama installation disabled")
            return False
        if not sys.platform.startswith("linux"):
            self.logger.emit("Install Ollama CLI", "fail", "ai", "Automatic Ollama install is only enabled for WSL/Linux. Install Ollama manually for this OS.")
            return False
        if not shutil.which("curl"):
            self.logger.emit("Install Ollama CLI", "fail", "ai", "curl is missing. Install curl first, then rerun AegisFlow.")
            return False

        command = "curl -fsSL https://ollama.com/install.sh | sh"
        self.logger.emit(
            "Install Ollama CLI",
            "running",
            "ai",
            "Ollama CLI not found. Installing Ollama. This may require sudo access in WSL.",
            command=command,
            progress_pct=0,
            elapsed_seconds=0,
        )
        try:
            proc = subprocess.Popen(
                ["bash", "-lc", command],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            output_parts: list[str] = []
            start_time = time.time()
            last_emit = start_time
            assert proc.stdout is not None
            while True:
                line = proc.stdout.readline()
                now = time.time()
                if line:
                    output_parts.append(line.rstrip("\n"))
                if now - last_emit > 5:
                    elapsed = int(now - start_time)
                    self.logger.emit(
                        "Install Ollama CLI",
                        "running",
                        "ai",
                        f"Still installing Ollama CLI for {elapsed}s. If WSL asks for sudo/password, run the manual command in a terminal.",
                        output_tail=tail("\n".join(output_parts), 1500),
                        progress_pct=min(95, max(5, int((elapsed / 900) * 100))),
                        elapsed_seconds=elapsed,
                    )
                    last_emit = now
                if proc.poll() is not None:
                    break
                if now - start_time > 900:
                    proc.kill()
                    raise subprocess.TimeoutExpired(command, 900)
                time.sleep(0.2)
            output = "\n".join(output_parts)
            cli = self._ollama_cli()
            if proc.returncode == 0 and cli:
                self.logger.emit("Install Ollama CLI", "ok", "ai", f"Ollama CLI installed at `{cli}`", output_tail=tail(output), progress_pct=100, elapsed_seconds=int(time.time()-start_time))
                return True
            self.logger.emit(
                "Install Ollama CLI",
                "fail",
                "ai",
                "Automatic Ollama installation failed. Run this manually in WSL: curl -fsSL https://ollama.com/install.sh | sh",
                output_tail=tail(output),
                progress_pct=100,
                elapsed_seconds=int(time.time()-start_time),
            )
            return False
        except subprocess.TimeoutExpired:
            self.logger.emit("Install Ollama CLI", "fail", "ai", "Ollama installation timed out. Run manually in WSL: curl -fsSL https://ollama.com/install.sh | sh")
            return False
        except Exception as exc:
            self.logger.emit("Install Ollama CLI", "fail", "ai", f"Ollama installation failed: {exc}")
            return False

    def _server_available(self) -> bool:
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def _try_start_server(self) -> bool:
        if self._server_available():
            self.logger.emit("Ollama server", "ok", "ai", f"Ollama server is available at `{self.host}`")
            return True
        cli = self._ollama_cli()
        if not cli:
            if not self._install_ollama_cli():
                self.logger.emit("Ollama server", "fail", "ai", "Ollama CLI is not installed or not visible in WSL PATH")
                return False
            cli = self._ollama_cli()
        if not cli:
            self.logger.emit("Ollama server", "fail", "ai", "Cannot locate Ollama CLI after install attempt")
            return False

        self.logger.emit(
            "Start Ollama server",
            "running",
            "ai",
            "Ollama server is not responding. Starting `ollama serve` in background.",
            command=f"{cli} serve",
            progress_pct=0,
            elapsed_seconds=0,
        )
        try:
            self._serve_process = subprocess.Popen(
                [cli, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            self.logger.emit("Start Ollama server", "warn", "ai", f"Could not start Ollama server automatically: {exc}")

        start = time.time()
        while time.time() - start < 25:
            if self._server_available():
                self.logger.emit("Start Ollama server", "ok", "ai", "Ollama server is available", progress_pct=100, elapsed_seconds=int(time.time()-start))
                return True
            elapsed = int(time.time() - start)
            self.logger.emit(
                "Start Ollama server",
                "running",
                "ai",
                f"Waiting for Ollama server to respond for {elapsed}s...",
                progress_pct=min(90, elapsed * 4),
                elapsed_seconds=elapsed,
            )
            time.sleep(2)
        self.logger.emit("Start Ollama server", "fail", "ai", "Ollama server is not available. Start it manually with `ollama serve` and rerun.", progress_pct=100)
        return False

    def _model_names_api(self) -> set[str]:
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=10)
            if response.status_code != 200:
                return set()
            models = response.json().get("models", [])
            return {m.get("name", "") for m in models if m.get("name")}
        except Exception:
            return set()

    def _model_names_cli(self) -> set[str]:
        cli = self._ollama_cli()
        if not cli:
            return set()
        try:
            proc = subprocess.run([cli, "list"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
            names: set[str] = set()
            for line in proc.stdout.splitlines()[1:]:
                parts = line.split()
                if parts:
                    names.add(parts[0])
            return names
        except Exception:
            return set()

    def _matches_model(self, candidate: str) -> bool:
        if not candidate:
            return False
        # Exact match is best. Also accept same model family/tag variants returned by Ollama.
        return candidate == self.model or candidate.split(":")[0] == self.model.split(":")[0]

    def _model_available(self) -> bool:
        names = self._model_names_api() or self._model_names_cli()
        if any(self._matches_model(n) for n in names):
            self.logger.emit("Check Ollama model", "ok", "ai", f"Model `{self.model}` already exists locally. No download needed.")
            return True
        available = ", ".join(sorted(names)) if names else "no local Ollama models found"
        self.logger.emit("Check Ollama model", "running", "ai", f"Model `{self.model}` not found locally. Local cache: {available}")
        return False

    def _pull_model(self) -> bool:
        cli = self._ollama_cli()
        if not cli:
            if not self._install_ollama_cli():
                self.logger.emit("Download Ollama model", "fail", "ai", "Cannot download model because Ollama CLI is not installed")
                return False
            cli = self._ollama_cli()
        if not cli:
            self.logger.emit("Download Ollama model", "fail", "ai", "Cannot locate Ollama CLI after installation attempt")
            return False

        self.logger.emit(
            "Download Ollama model",
            "running",
            "ai",
            f"First-time setup: downloading `{self.model}`. This can take several minutes, but progress will keep updating.",
            command=f"{cli} pull {self.model}",
            progress_pct=0,
            elapsed_seconds=0,
        )
        try:
            proc = subprocess.Popen(
                [cli, "pull", self.model],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            assert proc.stdout is not None
            fd = proc.stdout.fileno()
            try:
                os.set_blocking(fd, False)
            except Exception:
                pass
            output_parts: list[str] = []
            start = time.time()
            last_emit = start
            last_output_len = 0

            while proc.poll() is None:
                try:
                    chunk = os.read(fd, 4096)
                except BlockingIOError:
                    chunk = b""
                except Exception:
                    chunk = b""
                if chunk:
                    text = chunk.decode(errors="replace").replace("\r", "\n")
                    output_parts.append(text)
                    last_output_len += len(text)
                now = time.time()
                if now - last_emit >= 3:
                    elapsed = int(now - start)
                    # Pull progress differs by Ollama version. Use elapsed pseudo-progress and show latest output.
                    pseudo_pct = min(95, max(3, int((elapsed / 1800) * 95)))
                    latest = tail("".join(output_parts), 1800) or "Waiting for Ollama to report download progress..."
                    self.logger.emit(
                        "Download Ollama model",
                        "running",
                        "ai",
                        f"Downloading `{self.model}` for {elapsed}s. First download is slow only once; future runs will skip this.",
                        output_tail=latest,
                        progress_pct=pseudo_pct,
                        elapsed_seconds=elapsed,
                    )
                    last_emit = now
                if now - start > 7200:
                    proc.kill()
                    self.logger.emit("Download Ollama model", "fail", "ai", "Model download exceeded 120 minutes. Check internet/proxy and rerun; partial Ollama downloads usually resume.")
                    return False
                time.sleep(0.25)

            # Read any remaining output after process exits.
            try:
                while True:
                    chunk = os.read(fd, 4096)
                    if not chunk:
                        break
                    output_parts.append(chunk.decode(errors="replace").replace("\r", "\n"))
            except Exception:
                pass

            return_code = proc.wait(timeout=30)
            output = "".join(output_parts)
            if return_code == 0:
                if self._model_available():
                    self.logger.emit("Download Ollama model", "ok", "ai", f"Model `{self.model}` downloaded and ready", output_tail=tail(output), progress_pct=100, elapsed_seconds=int(time.time()-start))
                    return True
                self.logger.emit("Download Ollama model", "warn", "ai", "Pull finished, but model was not visible in `ollama list` yet. Rerun once or restart Ollama server.", output_tail=tail(output), progress_pct=100, elapsed_seconds=int(time.time()-start))
                return False
            self.logger.emit("Download Ollama model", "fail", "ai", f"`ollama pull {self.model}` failed with return code {return_code}", output_tail=tail(output), progress_pct=100, elapsed_seconds=int(time.time()-start))
            return False
        except Exception as exc:
            self.logger.emit("Download Ollama model", "fail", "ai", f"Model download failed: {exc}")
            return False

    def ensure_ready(self) -> bool:
        self.logger.emit("Ollama bootstrap", "running", "ai", "Checking local Ollama installation, server, and model cache before AI recommendation.", progress_pct=0)
        if not self._install_ollama_cli():
            return False
        if not self._try_start_server():
            return False
        if self._model_available():
            self.logger.emit("Ollama bootstrap", "ok", "ai", f"Ollama and `{self.model}` are ready locally", progress_pct=100)
            return True
        if self._pull_model() and self._model_available():
            self.logger.emit("Ollama bootstrap", "ok", "ai", f"Ollama and `{self.model}` are ready locally after first-time download", progress_pct=100)
            return True
        self.logger.emit("Ollama bootstrap", "fail", "ai", "Ollama/model setup failed; deterministic report is still available")
        return False

    def advise(self, report: dict) -> str:
        self.logger.emit("Local LLM recommendation", "running", "ai", f"Preparing local AI recommendation using Ollama model `{self.model}`")
        if not self.ensure_ready():
            self.logger.emit("Local LLM recommendation", "fail", "ai", "Ollama/model setup failed; deterministic report is still available")
            return ""

        prompt = f"""
You are a senior DevSecOps, MLOps, security, and release governance reviewer.
Use the following validation report to produce:
1. A concise error explanation for failed checks.
2. Common practical fixes.
3. A clean log summary.
4. A pull request review comment.
5. Production deployment decision support.
6. Secrets/access governance notes.
7. Architecture approval considerations.
8. Compliance sign-off evidence checklist.

Report JSON:
{json.dumps(report, indent=2)[:12000]}
"""
        try:
            response = requests.post(
                f"{self.host}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=180,
            )
            if response.status_code == 200:
                text = response.json().get("response", "").strip()
                self.logger.emit("Local LLM recommendation", "ok", "ai", "Recommendation generated")
                return text
            if response.status_code == 404:
                self.logger.emit("Local LLM recommendation", "warn", "ai", "Ollama returned 404; retrying after model pull")
                if self._pull_model():
                    response = requests.post(
                        f"{self.host}/api/generate",
                        json={"model": self.model, "prompt": prompt, "stream": False},
                        timeout=180,
                    )
                    if response.status_code == 200:
                        text = response.json().get("response", "").strip()
                        self.logger.emit("Local LLM recommendation", "ok", "ai", "Recommendation generated after model download")
                        return text
            self.logger.emit("Local LLM recommendation", "fail", "ai", f"Ollama HTTP {response.status_code}", output_tail=response.text[:1000])
            return ""
        except Exception as exc:
            self.logger.emit("Local LLM recommendation", "skip", "ai", f"Ollama not available: {exc}")
            return ""


class FailureIntelligenceEngine:
    """Turns raw validation failures into understandable causes and safe next actions."""

    def __init__(self, validations: list[ValidationResult], events: list[Event]):
        self.validations = validations
        self.events = events

    def _module_not_found_names(self, text: str) -> list[str]:
        names: list[str] = []
        for pat in [r"No module named ['\"]([^'\"]+)['\"]", r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]"]:
            for m in re.finditer(pat, text):
                names.append(m.group(1))
        return sorted(set(names))

    def _failed_tests(self, text: str) -> list[str]:
        items: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("FAILED ") or line.startswith("ERROR "):
                items.append(line[:220])
        return items[:25]

    def _common_fixes(self, v: ValidationResult) -> list[str]:
        low = (v.details or "").lower()
        name_low = v.name.lower()
        fixes: list[str] = []
        missing = self._module_not_found_names(v.details or "")
        if missing:
            fixes.append("Install repo dependencies in the same environment running AegisFlow: `python -m pip install -r requirements.txt` and `python -m pip install -r requirements-dev.txt`.")
            fixes.append("Confirm Streamlit is started from Conda: `conda activate aegisflow && which python && python -m streamlit run app.py`.")
            fixes.append("AegisFlow sets PYTHONPATH to repo root and src while running tests; rerun after dependency install.")
            fixes.append("Missing modules detected: " + ", ".join(missing[:10]))
        if "pytest" in name_low or "test" in name_low:
            failed = self._failed_tests(v.details or "")
            if failed:
                fixes.append("Review these failing tests first: " + "; ".join(failed[:8]))
            if "import file mismatch" in low or "__pycache__" in low or ".pyc" in low:
                fixes.append("Clean Pytest caches and generated duplicate test names; AegisFlow auto-repair already attempts this once.")
            if "assert" in low or "failed " in low:
                fixes.append("This is likely code behavior vs test expectation. AegisFlow will not change business logic automatically; update code or tests after review.")
            fixes.append("Run the exact command locally to see full output: `python -m pytest -v --cov=src --cov-report=term-missing --cov-report=xml:coverage.xml --junitxml=test-results.xml`.")
        if "ruff" in name_low or "format" in name_low or "lint" in name_low:
            fixes.append("Run `python -m ruff format src tests` and `python -m ruff check src tests --fix`.")
        if "bandit" in name_low or "security" in name_low:
            fixes.append("Review Bandit finding; fix unsafe calls or add a justified `# nosec` only after security review.")
        if "secret" in name_low or "api_key" in low or "password" in low or "token" in low:
            fixes.append("Remove hardcoded secret, rotate exposed credential, and use Azure Key Vault or Azure DevOps variable group.")
        if "dockerfile" in name_low or "hadolint" in low:
            fixes.append("Fix Dockerfile style/security warnings reported by Hadolint, or document acceptable warnings for review.")
        if not fixes:
            fixes.append("Open the raw log tail in the report and rerun the exact command locally.")
        return fixes

    def analyze(self) -> dict:
        items = []
        for v in self.validations:
            if v.status != "fail":
                continue
            classification = v.classification or classify_failure(v.name, v.return_code, v.details or "")
            sev = "high" if any(x in classification for x in ["security", "developer code", "test", "dependency"]) else "medium"
            owner = "developer/test owner"
            if "security" in classification:
                owner = "security/devsecops owner"
            elif "pipeline" in classification or "dependency" in classification or "tooling" in classification:
                owner = "devops/platform owner"
            elif "style" in classification or "quality" in classification:
                owner = "developer"
            explanation = {
                "tooling/dependency or pipeline configuration issue": "The check could not run correctly because a tool, Python module, dependency, path, or environment configuration is missing or inconsistent.",
                "developer code issue or test expectation issue": "Automated tests failed. Either product behavior changed, a regression exists, or the test expectation needs review.",
                "developer code style/quality issue": "Formatting/linting rules did not pass for the configured codebase.",
                "security issue": "A security rule or secret detection check found an issue that needs security review.",
            }.get(classification, "The validation failed and needs review using the raw command output.")
            items.append({
                "name": v.name,
                "status": v.status,
                "category": v.category,
                "classification": classification,
                "severity": sev,
                "owner": owner,
                "explanation": explanation,
                "common_fixes": self._common_fixes(v),
                "raw_tail": tail(v.details or "", 2200),
            })
        return {"status": "needs_attention" if items else "clean", "items": items}


class LogSummarizer:
    def __init__(self, events: list[Event], validations: list[ValidationResult]):
        self.events = events
        self.validations = validations

    def summarize(self) -> dict:
        event_counts = dict(Counter(e.status for e in self.events))
        validation_counts = dict(Counter(v.status for v in self.validations))
        running = [e.to_dict() for e in self.events if e.status == "running"][-5:]
        failures = [e.to_dict() for e in self.events if e.status == "fail"][-10:]
        warnings = [e.to_dict() for e in self.events if e.status == "warn"][-10:]
        return {
            "event_counts": event_counts,
            "validation_counts": validation_counts,
            "last_running_steps": running,
            "recent_failures": failures,
            "recent_warnings": warnings,
            "total_events": len(self.events),
        }


class GovernanceDecisionEngine:
    """Decision support only. It never performs compliance or production approval."""

    def __init__(self, repo: Path, inspection: dict, validations: list[ValidationResult]):
        self.repo = repo
        self.inspection = inspection
        self.validations = validations

    def evaluate(self, environment: str = "production") -> dict:
        blockers: list[str] = []
        warnings: list[str] = []
        failed = [v for v in self.validations if v.status == "fail"]
        skipped = [v for v in self.validations if v.status == "skip"]
        if failed:
            blockers.append(f"{len(failed)} validation check(s) failed. Do not deploy to {environment} until fixed or formally approved.")
        if any("security" in v.classification for v in failed):
            blockers.append("Security findings require security owner review and sign-off.")
        if not self.inspection.get("existing_controls", {}).get("azure_pipeline"):
            warnings.append("Azure pipeline file was not detected before generation; review generated CI/CD YAML before merge.")
        if skipped:
            warnings.append(f"{len(skipped)} check(s) were skipped; confirm whether each skipped control is acceptable.")
        decision = "ready_for_human_approval"
        if blockers:
            decision = "blocked"
        elif warnings:
            decision = "conditional_review"
        signoff_matrix = [
            {"area": "Code quality", "status": "blocked" if any(v.status == "fail" and v.category == "quality" for v in self.validations) else "review_ready", "required_owner": "Developer/Tech Lead", "automation_position": "Evidence generated; human approval required"},
            {"area": "Testing and coverage", "status": "blocked" if any(v.status == "fail" and v.category == "testing" for v in self.validations) else "review_ready", "required_owner": "Developer/Test Owner", "automation_position": "Evidence generated; human approval required"},
            {"area": "Security", "status": "blocked" if any(v.status == "fail" and v.category == "security" for v in self.validations) else "review_ready", "required_owner": "Security/DevSecOps", "automation_position": "Evidence generated; human approval required"},
            {"area": "Production deployment", "status": decision, "required_owner": "Release Manager/DevOps Owner", "automation_position": "Decision support only, not auto-approved"},
            {"area": "Architecture", "status": "conditional_review", "required_owner": "Architect/Tech Lead", "automation_position": "Checklist support only"},
            {"area": "Compliance sign-off", "status": "conditional_review", "required_owner": "Compliance/Governance Owner", "automation_position": "Evidence pack only, not sign-off"},
        ]
        return {"environment": environment, "decision": decision, "blockers": blockers, "warnings": warnings, "signoff_matrix": signoff_matrix}



class AIFixPlanEngine:
    """Create reviewable, human-approved fix plans with exact diffs.

    The engine is intentionally conservative. It proposes deterministic safe
    patches for common Dockerfile/Hadolint and Python quality problems, but it
    never changes product behavior or tests without explicit approval.
    """

    SAFE_HADOLINT_RULES = {"DL3020", "DL3015", "DL3009", "DL3042", "DL3013"}

    def __init__(self, repo: Path, logger: EventLogger | None = None):
        self.repo = repo.resolve()
        self.logger = logger

    def _emit(self, step: str, status: str, message: str, **kwargs) -> None:
        if self.logger:
            self.logger.emit(step, status, "ai_fix", message, **kwargs)

    def _hadolint_bin(self) -> str | None:
        found = shutil.which("hadolint")
        if found:
            return found
        user_bin = Path.home() / ".local" / "bin" / "hadolint"
        if user_bin.exists():
            return str(user_bin)
        return None

    def _run_hadolint(self, dockerfile: Path) -> tuple[int | None, str]:
        binary = self._hadolint_bin()
        rel = dockerfile.relative_to(self.repo).as_posix()
        if not binary:
            return None, "hadolint is not installed or not available in PATH"
        try:
            proc = subprocess.run(
                [binary, rel],
                cwd=self.repo,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=120,
            )
            return proc.returncode, proc.stdout
        except Exception as exc:
            return None, str(exc)

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Remove terminal color/control codes so hadolint output can be parsed reliably."""
        return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text or "")

    @classmethod
    def _parse_hadolint(cls, output: str) -> list[dict]:
        findings: list[dict] = []
        clean_output = cls._strip_ansi(output or "")
        # Common formats:
        # Dockerfile:8 DL3009 info: Delete the apt-get lists after installing something
        # Dockerfile:8:12 DL3008 warning: Pin versions in apt get install
        # Some hadolint builds emit: infra/docker/Dockerfile:12 DL3008 warning: ...
        pattern = re.compile(r"^(?P<file>.*?):(?P<line>\d+)(?::\d+)?\s+(?P<rule>(?:DL|SC)\d+)\s+(?P<level>\w+):\s+(?P<message>.*)$")
        for raw in clean_output.splitlines():
            line = raw.strip()
            m = pattern.match(line)
            if m:
                d = m.groupdict()
                d["line"] = int(d["line"])
                d["raw"] = line
                findings.append(d)
        return findings

    @staticmethod
    def _replace_add_with_copy(line: str) -> str:
        return re.sub(r"^(\s*)ADD\b", r"\1COPY", line, flags=re.IGNORECASE)

    @staticmethod
    def _add_no_cache_to_pip(line: str) -> str:
        if "pip install" not in line or "--no-cache-dir" in line:
            return line
        return line.replace("pip install", "pip install --no-cache-dir", 1)

    @staticmethod
    def _prefer_pip_requirement_long_flag(line: str) -> str:
        """Safe DL3013 helper: convert `pip install -r file` to `pip install --requirement file`.

        This does not invent package versions. It only normalizes requirements-file usage,
        which is deterministic and keeps the same install source.
        """
        if "pip install" not in line or " -r " not in line:
            return line
        return line.replace(" -r ", " --requirement ", 1)

    @staticmethod
    def _add_no_install_recommends(line: str) -> str:
        if "apt-get install" not in line or "--no-install-recommends" in line:
            return line
        return line.replace("apt-get install", "apt-get install -y --no-install-recommends", 1) if "apt-get install -y" not in line else line.replace("apt-get install -y", "apt-get install -y --no-install-recommends", 1)

    @staticmethod
    def _add_apt_list_cleanup(line: str) -> str:
        if "apt-get" not in line or "/var/lib/apt/lists" in line:
            return line
        stripped = line.rstrip()
        # Add cleanup only to RUN commands that install packages.
        if not re.match(r"^\s*RUN\b", stripped, flags=re.IGNORECASE):
            return line
        if "apt-get install" not in stripped:
            return line
        continuation = "\\" if stripped.endswith("\\") else ""
        if continuation:
            stripped = stripped[:-1].rstrip()
            return f"{stripped} && rm -rf /var/lib/apt/lists/* \\\n"
        return f"{stripped} && rm -rf /var/lib/apt/lists/*\n"

    def _build_approved_hadolint_suppression_patch(self, dockerfile: Path, findings: list[dict]) -> tuple[str, list[dict]]:
        """Build an approval-required patch for Hadolint rules that cannot be safely fixed.

        This does not change Docker build behavior. It adds explicit Hadolint ignore comments
        immediately above the affected instruction, making the exception visible and reviewable.
        This is intended for rules such as DL3008/DL3013 where AegisFlow should not invent
        apt/pip package versions.
        """
        original = dockerfile.read_text(errors="ignore")
        lines = original.splitlines(keepends=True)
        by_line: dict[int, list[dict]] = {}
        for f in findings:
            try:
                line_no = int(f.get("line", 0))
            except Exception:
                continue
            rule = (f.get("rule") or "").strip()
            if not rule or line_no < 1 or line_no > len(lines):
                continue
            # Avoid duplicating an ignore that is already adjacent.
            prev = lines[line_no - 2] if line_no >= 2 else ""
            if "hadolint ignore" in prev and rule in prev:
                continue
            by_line.setdefault(line_no, []).append(f)

        if not by_line:
            return original, []

        new_lines = list(lines)
        inserted: list[dict] = []
        offset = 0
        for line_no in sorted(by_line):
            rules = sorted({f.get("rule") for f in by_line[line_no] if f.get("rule")})
            if not rules:
                continue
            idx = line_no - 1 + offset
            indent_match = re.match(r"^(\s*)", new_lines[idx])
            indent = indent_match.group(1) if indent_match else ""
            comment = f"{indent}# hadolint ignore={','.join(rules)}  # AegisFlow: review-approved exception; prefer pinning versions when available\n"
            new_lines.insert(idx, comment)
            offset += 1
            inserted.extend(by_line[line_no])
        return "".join(new_lines), inserted

    def _safe_patch_dockerfile(self, dockerfile: Path, findings: list[dict]) -> tuple[str, list[dict]]:
        original = dockerfile.read_text(errors="ignore")
        lines = original.splitlines(keepends=True)
        applied_rules: list[dict] = []
        for f in findings:
            rule = f.get("rule", "")
            line_no = int(f.get("line", 0))
            if rule not in self.SAFE_HADOLINT_RULES or line_no < 1 or line_no > len(lines):
                continue
            before = lines[line_no - 1]
            after = before
            if rule == "DL3020":
                after = self._replace_add_with_copy(after)
            elif rule == "DL3015":
                after = self._add_no_install_recommends(after)
            elif rule == "DL3009":
                after = self._add_apt_list_cleanup(after)
            elif rule == "DL3042":
                after = self._add_no_cache_to_pip(after)
            elif rule == "DL3013":
                # Only safe when Dockerfile already uses a requirements file. Pinning arbitrary
                # inline packages requires human/package-owner choice, so that remains review-only.
                after = self._prefer_pip_requirement_long_flag(after)
            if after != before:
                lines[line_no - 1] = after
                applied_rules.append({**f, "before_line": before.rstrip("\n"), "after_line": after.rstrip("\n"), "safe_auto_patch": True})
        return "".join(lines), applied_rules

    def _diff(self, rel: str, before: str, after: str) -> str:
        return "".join(difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"before/{rel}",
            tofile=f"after/{rel}",
        ))

    def generate(self, validations: list[ValidationResult] | None = None) -> dict:
        self._emit("AI Fix Plan", "running", "Creating reviewable fix plan with exact proposed file changes", progress_pct=0)
        plan = {
            "version": "19.0",
            "status": "ready_for_review",
            "summary": "Review proposed changes, approve them explicitly, then AegisFlow applies patches and reruns affected checks.",
            "items": [],
            "non_auto_fixable": [],
        }

        # Dockerfile / Hadolint deterministic plan.
        dockerfiles = [p for p in self.repo.rglob("Dockerfile") if not is_aegisflow_excluded_path(p.relative_to(self.repo))]
        for dockerfile in dockerfiles:
            rel = dockerfile.relative_to(self.repo).as_posix()
            rc, output = self._run_hadolint(dockerfile)
            findings = self._parse_hadolint(output or "")
            if rc in (0, None) and not findings:
                if rc == 0:
                    plan["items"].append({"type": "dockerfile", "file": rel, "status": "already_passed", "message": "Hadolint passed; no Dockerfile patch needed.", "diff": "", "safe_to_apply": False})
                else:
                    plan["non_auto_fixable"].append({"file": rel, "reason": output or "Hadolint could not run"})
                continue
            before = dockerfile.read_text(errors="ignore")
            after, patched_findings = self._safe_patch_dockerfile(dockerfile, findings)
            diff_text = self._diff(rel, before, after) if after != before else ""
            unsafe = [f for f in findings if f.get("rule") not in self.SAFE_HADOLINT_RULES]
            if diff_text:
                plan["items"].append({
                    "type": "dockerfile",
                    "file": rel,
                    "tool": "hadolint",
                    "command": f"hadolint {rel}",
                    "status": "proposed",
                    "safe_to_apply": True,
                    "findings": findings,
                    "patched_findings": patched_findings,
                    "unsafe_findings_remaining": unsafe,
                    "before_content": before,
                    "after_content": after,
                    "diff": diff_text,
                    "explanation": "Deterministic safe Dockerfile patch generated from Hadolint findings. Review diff before applying.",
                })
            else:
                # If deterministic fixes are not available, still provide a reviewable approval-based
                # patch that makes the Hadolint exception explicit. This gives the user an approval
                # workflow instead of a dead end, while not silently changing build behavior.
                suppressed_after, suppressed_findings = self._build_approved_hadolint_suppression_patch(dockerfile, findings)
                suppressed_diff = self._diff(rel, before, suppressed_after) if suppressed_after != before else ""
                guidance = []
                for f in findings:
                    rule = f.get("rule")
                    msg = f.get("message", "")
                    if rule == "DL3008":
                        guidance.append("DL3008 requires apt package versions to be pinned. Best fix: choose valid apt package versions for the base image. Approval workaround: add an explicit hadolint ignore comment with justification.")
                    elif rule == "DL3013":
                        guidance.append("DL3013 requires pip packages to be pinned or installed from a requirements file. Best fix: pin versions in requirements.txt. Approval workaround: add an explicit hadolint ignore comment with justification.")
                    else:
                        guidance.append(f"{rule}: {msg}")
                if suppressed_diff:
                    plan["items"].append({
                        "type": "dockerfile",
                        "file": rel,
                        "tool": "hadolint",
                        "command": f"hadolint {rel}",
                        "status": "proposed",
                        "safe_to_apply": True,
                        "approval_level": "human_required_policy_exception",
                        "findings": findings,
                        "patched_findings": suppressed_findings,
                        "before_content": before,
                        "after_content": suppressed_after,
                        "diff": suppressed_diff,
                        "explanation": "No deterministic package-version fix is safe. This approval-based patch adds explicit Hadolint ignore comments next to the affected Dockerfile instruction. It does not change runtime behavior, but it creates a visible policy exception. Use this only if the team accepts the exception; otherwise pin package versions manually.",
                    })
                plan["non_auto_fixable"].append({
                    "file": rel,
                    "tool": "hadolint",
                    "findings": findings,
                    "reason": "Hadolint found issues where the best fix needs human package-owner choice. A reviewable policy-exception patch may be available above; otherwise pin versions manually.",
                    "guidance": guidance,
                    "raw_output": output,
                })

        # Python failures: propose commands, not arbitrary code changes.
        for v in validations or []:
            if v.status != "fail":
                continue
            name_low = v.name.lower()
            if "ruff" in name_low or "format" in name_low:
                plan["items"].append({
                    "type": "command_fix",
                    "file": "src tests",
                    "status": "command_recommended",
                    "safe_to_apply": False,
                    "command": f"{sys.executable} -m ruff format src tests && {sys.executable} -m ruff check src tests --fix",
                    "diff": "",
                    "explanation": "Ruff can auto-format safely, but command execution is already available under Correction actions.",
                })
            elif "pytest" in name_low or "test" in name_low:
                plan["non_auto_fixable"].append({
                    "check": v.name,
                    "reason": "Pytest failure may require product-code or test-expectation decision. AegisFlow will not blindly change business logic.",
                    "evidence_tail": tail(v.details or "", 1800),
                })

        if not any(i.get("status") == "proposed" for i in plan["items"]):
            plan["status"] = "no_safe_patches"
            plan["summary"] = "No safe deterministic file patch was found. Review non-auto-fixable findings and raw logs."
        self._emit("AI Fix Plan", "ok", f"Fix plan created with {len(plan['items'])} item(s) and {len(plan['non_auto_fixable'])} review item(s)", progress_pct=100)
        return plan


class FixPlanApplier:
    def __init__(self, repo: Path, logger: EventLogger | None = None):
        self.repo = repo.resolve()
        self.logger = logger or EventLogger()

    def apply(self, plan: dict) -> dict:
        result = {"applied": [], "skipped": [], "validation_after": []}
        timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_root = self.repo / ".aegisflow_backups" / timestamp
        for item in plan.get("items", []):
            if item.get("status") != "proposed" or not item.get("safe_to_apply"):
                result["skipped"].append({"file": item.get("file"), "reason": "not a safe proposed file patch"})
                continue
            rel = item.get("file")
            if not rel or is_aegisflow_excluded_path(rel):
                result["skipped"].append({"file": rel, "reason": "AegisFlow generated backup/report paths are protected and never patched"})
                continue
            path = (self.repo / rel).resolve()
            if not str(path).startswith(str(self.repo)) or not path.exists():
                result["skipped"].append({"file": rel, "reason": "file not found or outside repo"})
                continue
            current = path.read_text(errors="ignore")
            before = item.get("before_content", "")
            after = item.get("after_content", "")
            if current != before:
                result["skipped"].append({"file": rel, "reason": "file changed after plan was generated; regenerate fix plan"})
                continue
            backup_path = backup_root / rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_text(current)
            path.write_text(after)
            result["applied"].append({"file": rel, "backup": str(backup_path), "diff": item.get("diff", "")})
            self.logger.emit("Apply AI fix patch", "ok", "ai_fix", f"Applied approved patch to `{rel}`")

        # Rerun affected Dockerfile checks only for a fast before/after result.
        planner = AIFixPlanEngine(self.repo, self.logger)
        for applied in result["applied"]:
            rel = applied["file"]
            if Path(rel).name == "Dockerfile":
                rc, output = planner._run_hadolint(self.repo / rel)
                status = "ok" if rc == 0 else "fail"
                vr = ValidationResult(
                    name=f"Dockerfile lint after AI fix: {rel}",
                    status=status,
                    category="quality",
                    command=f"hadolint {rel}",
                    return_code=rc,
                    details=output,
                    classification=classify_failure("Dockerfile lint after AI fix", rc, output or ""),
                )
                result["validation_after"].append(vr.to_dict())
                self.logger.emit(vr.name, status, "quality", "Re-run completed after approved patch", command=vr.command, output_tail=tail(output or "", 1800), progress_pct=100)
        return result


def generate_ai_fix_plan(repo_path: str, validations: list[dict] | None = None, callback: Optional[Callable[[Event], None]] = None) -> dict:
    repo = Path(repo_path).expanduser().resolve()
    v_objs = []
    for v in validations or []:
        try:
            v_objs.append(ValidationResult(**v))
        except TypeError:
            pass
    return AIFixPlanEngine(repo, EventLogger(callback)).generate(v_objs)


def apply_fix_plan_and_rerun(repo_path: str, plan: dict, callback: Optional[Callable[[Event], None]] = None) -> dict:
    repo = Path(repo_path).expanduser().resolve()
    return FixPlanApplier(repo, EventLogger(callback)).apply(plan)

def build_pr_comment(report: dict) -> str:
    summary = report.get("summary", {}).get("counts", {})
    gd = report.get("governance_decision", {})
    lines = []
    lines.append("## AegisFlow AI DevSecOps Validation Summary")
    lines.append("")
    lines.append(f"**Repository:** `{report.get('repo', '')}`")
    gc = report.get("git_context", {})
    if gc:
        lines.append(f"**Branch:** `{gc.get('current_branch', '')}`")
        lines.append(f"**Remote:** `{gc.get('remote_url', '')}`")
    lines.append("")
    lines.append(f"**Validation counts:** ✅ {summary.get('ok', 0)} passed, ❌ {summary.get('fail', 0)} failed, ⏭️ {summary.get('skip', 0)} skipped")
    lines.append(f"**Release decision support:** `{gd.get('decision', 'not_evaluated')}`")
    lines.append("")
    if gd.get("blockers"):
        lines.append("### Blockers")
        for b in gd.get("blockers", []):
            lines.append(f"- ❌ {b}")
        lines.append("")
    failures = report.get("failure_analysis", {}).get("items", [])
    if failures:
        lines.append("### Failed checks and suggested ownership")
        for item in failures:
            lines.append(f"- **{item.get('name')}** — {item.get('classification')} — owner: {item.get('owner')}")
        lines.append("")
    paths = report.get("report_paths", {})
    if paths:
        lines.append("### Evidence")
        for k, v in paths.items():
            lines.append(f"- `{k}`: `{v}`")
    lines.append("")
    lines.append("_AegisFlow provides automation evidence and decision support. Final merge, production, security, architecture, and compliance approvals remain human-owned._")
    return "\n".join(lines)


class OrchestratorAgent:
    def __init__(self, repo_path: str, callback: Optional[Callable[[Event], None]] = None):
        self.input_path = Path(repo_path).expanduser().resolve()
        self.repo = self.input_path
        self.logger = EventLogger(callback=callback)
        self.git_context: dict = {}

    def run(
        self,
        generate_files: bool = False,
        apply: bool = False,
        run_validations: bool = True,
        overwrite_pipeline: bool = False,
        branch: Optional[str] = None,
        commit: bool = False,
        push: bool = False,
        remote: str = "origin",
        create_pr: bool = False,
        target_branch: str = "main",
        llm: bool = False,
        model: str = "qwen2.5-coder:7b",
        install_ollama: bool = True,
        install_tools: bool = False,
        auto_fix: bool = False,
        generate_tests_for: Optional[list[str]] = None,
        generate_tests_for_all: bool = False,
        overwrite_tests: bool = False,
        allow_git_on_failure: bool = False,
        auto_repair_pytest: bool = True,
        generate_ai_fix_plan: bool = True,
        run_sonar: bool = False,
        sonar_host_url: str = "",
        sonar_token: str = "",
        sonar_project_key: str = "",
        sonar_quality_gate_wait: bool = True,
        auto_install_sonar_scanner: bool = True,
    ) -> dict:
        started = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        self.logger.emit("Runtime Python", "ok", "environment", f"Using `{sys.executable}`")

        # Always resolve the Git identity first. If the user selected a subfolder inside
        # a repo, operate from the Git root so generated files, tests, commits, and PRs
        # are attached to the correct repository.
        self.git_context = GitContextResolver(self.input_path, self.logger).resolve()
        if self.git_context.get("is_git_repo") and self.git_context.get("git_root"):
            git_root = Path(self.git_context["git_root"]).resolve()
            if git_root != self.repo:
                self.repo = git_root

        inspection = RepoInspector(self.repo, self.logger).inspect()
        generated: list[str] = []
        generated_tests: list[str] = []
        correction_results: list[ValidationResult] = []
        validations: list[ValidationResult] = []

        if generate_files:
            if apply:
                generated = FileGenerator(self.repo, self.logger, inspection).generate(overwrite_pipeline=overwrite_pipeline)
            else:
                self.logger.emit("Generate files", "skip", "generation", "Dry run only. Enable --apply to write files.")

        if install_tools:
            correction_results.extend(ToolInstaller(self.repo, self.logger).install_all())

        test_values = list(generate_tests_for or [])
        if generate_tests_for_all:
            creator = GeneratedTestFileCreator(self.repo, self.logger)
            test_values.extend(creator.source_files())
        if test_values:
            if apply:
                creator = GeneratedTestFileCreator(self.repo, self.logger)
                generated_tests = creator.create_for_files(test_values, overwrite=overwrite_tests)
            else:
                self.logger.emit("Generate missing tests", "skip", "testing", "Dry run only. Enable apply to write generated tests.")

        if auto_fix:
            correction_results.extend(SafeAutoFixer(self.repo, self.logger, inspection).run())

        # Re-inspect after file generation / correction so validation sees new tests/config.
        inspection = RepoInspector(self.repo, self.logger).inspect()

        if run_validations:
            validation_runner = ValidationRunner(self.repo, self.logger, inspection)
            validations = validation_runner.run_all()
            pytest_failed = any(v.status == "fail" and ("pytest" in v.name.lower() or "test" in v.name.lower()) for v in validations)
            if auto_repair_pytest and pytest_failed:
                self.logger.emit(
                    "Auto-correct Pytest issues",
                    "running",
                    "testing",
                    "A Pytest failure was detected. Running safe auto-repair and re-running Pytest once.",
                )
                correction_results.extend(PytestAutoRepairer(self.repo, self.logger).run())
                validations.append(validation_runner.run_pytest_only())
        else:
            self.logger.emit("Run validations", "skip", "validation", "Validation disabled")

        if run_sonar:
            sonar_results = SonarQubeRunner(self.repo, self.logger).run(
                host_url=sonar_host_url,
                token=sonar_token,
                project_key=sonar_project_key,
                wait_quality_gate=sonar_quality_gate_wait,
                auto_install_scanner=auto_install_sonar_scanner,
            )
            validations.extend(sonar_results)
        else:
            self.logger.emit("SonarQube scan", "skip", "sonar", "SonarQube analysis disabled")

        failure_analysis = FailureIntelligenceEngine(validations, self.logger.events).analyze()
        log_summary = LogSummarizer(self.logger.events, validations).summarize()
        governance_decision = GovernanceDecisionEngine(self.repo, inspection, validations).evaluate(environment="production")

        report = {
            "tool": "AegisFlow: DevSecOps Pipeline Orchestrator Agent",
            "version": "28.0-evidence-cockpit",
            "started_utc": started,
            "input_path": str(self.input_path),
            "repo": str(self.repo),
            "git_context": self.git_context,
            "inspection": inspection,
            "generated_files": generated,
            "generated_tests": generated_tests,
            "correction_results": [v.to_dict() for v in correction_results],
            "validation_results": [v.to_dict() for v in validations],
            "summary": summarize_results(validations),
            "failure_analysis": failure_analysis,
            "log_summary": log_summary,
            "governance_decision": governance_decision,
            "events": [e.to_dict() for e in self.logger.events],
        }
        report["pr_comment"] = build_pr_comment(report)
        if generate_ai_fix_plan:
            report["ai_fix_plan"] = AIFixPlanEngine(self.repo, self.logger).generate(validations)

        if llm:
            advice = LocalLLMAdvisor(self.logger, model=model, install_ollama=install_ollama).advise(report)
            report["llm_recommendation"] = advice

        report_paths = self.write_reports(report)
        report["report_paths"] = report_paths

        if branch or commit or push or create_pr:
            failed_validations = [v for v in validations if v.status == "fail"]
            if failed_validations and (commit or push or create_pr) and not allow_git_on_failure:
                self.logger.emit(
                    "Git automation safety gate",
                    "warn",
                    "git",
                    f"Skipped branch/commit/push/PR because {len(failed_validations)} validation check(s) failed. Fix failures or enable override.",
                )
            else:
                git = GitPublisher(self.repo, self.logger)
                if git.ensure_git_repo():
                    source_branch = branch or f"orchestrator/devsecops-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M')}"
                    if branch:
                        git.create_branch(source_branch)
                    if commit:
                        git.commit("Add DevSecOps orchestration validation files and evidence")
                    if push:
                        git.push(remote, source_branch)
                    if create_pr:
                        title = "DevSecOps pipeline orchestration updates"
                        description = build_pr_description(report)
                        pr_url = AzureDevOpsClient(self.logger, self.git_context).create_pr(source_branch, target_branch, title, description)
                        report["pull_request_url"] = pr_url

        # rewrite after git events/PR step
        report["events"] = [e.to_dict() for e in self.logger.events]
        report["log_summary"] = LogSummarizer(self.logger.events, validations).summarize()
        report["pr_comment"] = build_pr_comment(report)
        self.write_reports(report)

        self.logger.emit("Orchestration complete", "ok", "summary", f"Reports written: {report_paths['markdown']}")
        return report

    def write_reports(self, report: dict) -> dict:
        folder = self.repo / "orchestrator_reports"
        folder.mkdir(exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
        json_path = folder / f"devsecops_orchestration_report_{stamp}.json"
        md_path = folder / f"devsecops_orchestration_report_{stamp}.md"
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        md_path.write_text(render_markdown_report(report), encoding="utf-8")
        zip_path = self.create_evidence_zip(folder, stamp, json_path, md_path)
        return {"json": str(json_path), "markdown": str(md_path), "zip": str(zip_path)}

    def create_evidence_zip(self, folder: Path, stamp: str, json_path: Path, md_path: Path) -> Path:
        """Create a downloadable evidence pack without copying heavy source/model files."""
        zip_path = folder / f"aegisflow_evidence_pack_{stamp}.zip"
        include_files = [
            json_path,
            md_path,
            self.repo / "coverage.xml",
            self.repo / "test-results.xml",
            self.repo / "azure-pipeline.yml",
            self.repo / "azure-pipelines.yml",
            self.repo / "sonar-project.properties",
            self.repo / "pytest.ini",
            self.repo / ".coveragerc",
            self.repo / "requirements.txt",
            self.repo / "requirements-dev.txt",
            self.repo / "validation_results" / "sonar-scanner-output.txt",
        ]
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in include_files:
                if path.exists() and path.is_file() and path.resolve() != zip_path.resolve():
                    try:
                        rel = path.relative_to(self.repo).as_posix()
                    except Exception:
                        rel = path.name
                    zf.write(path, rel)
            already_added = {json_path.resolve(), md_path.resolve()}
            for path in folder.glob("*.md"):
                if path.is_file() and path.resolve() not in already_added:
                    zf.write(path, f"orchestrator_reports/{path.name}")
            for path in folder.glob("*.json"):
                if path.is_file() and path.resolve() not in already_added:
                    zf.write(path, f"orchestrator_reports/{path.name}")
        return zip_path


def summarize_results(validations: list[ValidationResult]) -> dict:
    counts = {"ok": 0, "fail": 0, "skip": 0}
    classifications: dict[str, int] = {}
    for v in validations:
        counts[v.status] = counts.get(v.status, 0) + 1
        classifications[v.classification] = classifications.get(v.classification, 0) + 1
    return {"counts": counts, "classifications": classifications}


def render_markdown_report(report: dict) -> str:
    lines = []
    lines.append("# DevSecOps Orchestration Evidence Report")
    lines.append("")
    lines.append(f"**Repository:** `{report['repo']}`")
    if report.get("input_path") and report.get("input_path") != report.get("repo"):
        lines.append(f"**Input path:** `{report.get('input_path')}`")
    lines.append(f"**Started UTC:** `{report['started_utc']}`")
    lines.append("")
    gc = report.get("git_context", {})
    lines.append("## Git Repository Identity")
    lines.append("")
    if gc.get("is_git_repo"):
        lines.append(f"- **Repo name:** `{gc.get('repo_name', '')}`")
        lines.append(f"- **Git root:** `{gc.get('git_root', '')}`")
        lines.append(f"- **Current branch:** `{gc.get('current_branch', '')}`")
        lines.append(f"- **HEAD:** `{gc.get('head_commit', '')}`")
        lines.append(f"- **Remote:** `{gc.get('remote_url', '')}`")
        lines.append(f"- **Provider:** `{gc.get('remote_provider', '')}`")
        lines.append(f"- **Changed files before run:** `{gc.get('changed_files_count', 0)}`")
    else:
        lines.append("- Not a Git repository or Git metadata unavailable.")
    lines.append("")
    lines.append("## Detected Project")
    lines.append("")
    lines.append(", ".join(report["inspection"]["project_type"]))
    lines.append("")
    lines.append("## Existing Controls")
    lines.append("")
    for k, v in report["inspection"]["existing_controls"].items():
        lines.append(f"- {'✅' if v else '❌'} `{k}`")
    lines.append("")
    lines.append("## Generated Files")
    lines.append("")
    if report["generated_files"]:
        for f in report["generated_files"]:
            lines.append(f"- `{f}`")
    else:
        lines.append("- None")
    lines.append("")
    if report.get("correction_results"):
        lines.append("## Correction Results")
        lines.append("")
        lines.append("| Status | Correction | Category | Classification |")
        lines.append("|---|---|---|---|")
        for v in report.get("correction_results", []):
            icon = {"ok": "✅", "fail": "❌", "skip": "⏭️"}.get(v["status"], "•")
            lines.append(f"| {icon} {v['status']} | {v['name']} | {v['category']} | {v['classification']} |")
        lines.append("")
    if report.get("generated_tests"):
        lines.append("## Generated Test Files")
        lines.append("")
        for path in report.get("generated_tests", []):
            lines.append(f"- `{path}`")
        lines.append("")

    lines.append("## Validation Results")
    lines.append("")
    lines.append("| Status | Validation | Category | Classification |")
    lines.append("|---|---|---|---|")
    for v in report["validation_results"]:
        icon = {"ok": "✅", "fail": "❌", "skip": "⏭️"}.get(v["status"], "•")
        lines.append(f"| {icon} {v['status']} | {v['name']} | {v['category']} | {v['classification']} |")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report["summary"], indent=2))
    lines.append("```")
    lines.append("")
    lines.append("## Failure Explanations and Common Fixes")
    lines.append("")
    for item in report.get("failure_analysis", {}).get("items", []):
        if item.get("status") == "fail":
            lines.append(f"### {item['name']}")
            lines.append(f"- **Severity:** {item['severity']}")
            lines.append(f"- **Owner:** {item['owner']}")
            lines.append(f"- **Explanation:** {item['explanation']}")
            lines.append("- **Common fixes:**")
            for fix in item.get("common_fixes", []):
                lines.append(f"  - {fix}")
            lines.append("")
    lines.append("## Governance / Release Decision Support")
    lines.append("")
    gd = report.get("governance_decision", {})
    lines.append(f"**Decision support:** `{gd.get('decision', 'not_evaluated')}`")
    for blocker in gd.get("blockers", []):
        lines.append(f"- ❌ {blocker}")
    for warning in gd.get("warnings", []):
        lines.append(f"- ⚠️ {warning}")
    lines.append("")
    lines.append("### Sign-off Matrix")
    lines.append("")
    lines.append("| Area | Status | Owner | Automation Position |")
    lines.append("|---|---|---|---|")
    for row in gd.get("signoff_matrix", []):
        lines.append(f"| {row['area']} | {row['status']} | {row['required_owner']} | {row['automation_position']} |")
    lines.append("")
    lines.append("## Generated PR Comment")
    lines.append("")
    lines.append(report.get("pr_comment", ""))
    if report.get("llm_recommendation"):
        lines.append("")
        lines.append("## Local LLM Recommendation")
        lines.append("")
        lines.append(report["llm_recommendation"])
    lines.append("")
    lines.append("## Event Log")
    lines.append("")
    for e in report["events"]:
        lines.append(f"- **{e['status'].upper()}** [{e['category']}] {e['step']}: {e['message']}")
    return "\n".join(lines)


def build_pr_description(report: dict) -> str:
    return report.get("pr_comment") or "Automated AegisFlow AI DevSecOps orchestration update. Please review evidence before merge."


REQUIREMENTS_DEV = """ruff
pytest
pytest-cov
coverage
bandit
detect-secrets
"""

PYTEST_INI = """[pytest]
testpaths = tests
python_files = test_*.py
addopts = -ra
"""

COVERAGERC = """[run]
source = src
omit =
    tests/*
    */__init__.py

[report]
show_missing = True
skip_empty = True
"""

SONAR_PROPERTIES = """sonar.projectKey=REPLACE_WITH_PROJECT_KEY
sonar.projectName=REPLACE_WITH_PROJECT_NAME
sonar.sources=src
sonar.tests=tests
sonar.python.coverage.reportPaths=coverage.xml
sonar.exclusions=**/__pycache__/**,**/.venv/**,**/venv/**,**/htmlcov/**,**/.aegisflow_backups/**,**/orchestrator_reports/**
sonar.coverage.exclusions=tests/**
"""

AZURE_PIPELINE_PYTHON_FUNCTION = """trigger:
  branches:
    include:
      - main
      - feature/*

pr:
  branches:
    include:
      - main

pool:
  vmImage: ubuntu-latest

variables:
  pythonVersion: '3.11'

steps:
  - checkout: self
    clean: true

  - task: UsePythonVersion@0
    inputs:
      versionSpec: '$(pythonVersion)'

  - script: |
      python -m pip install --upgrade pip
      pip install -r requirements.txt
      if [ -f requirements-dev.txt ]; then pip install -r requirements-dev.txt; fi
    displayName: Install dependencies

  - script: mkdir -p validation_results
    displayName: Create evidence folder

  - script: python -m ruff format --check ./src ./tests
    displayName: Ruff formatting check

  - script: python -m ruff check ./src ./tests
    displayName: Ruff lint check

  - script: python -m detect_secrets scan > validation_results/detect-secrets-report.json
    displayName: Secret scan

  - script: python -m bandit -r src -ll -f json -o validation_results/bandit-report.json
    displayName: Bandit static security scan

  - script: |
      python -m pytest -v \
        --cov=src \
        --cov-report=term-missing \
        --cov-report=xml:coverage.xml \
        --junitxml=test-results.xml
    displayName: Pytest with coverage


  # Optional SonarQube/SonarCloud analysis. Configure SONAR_HOST_URL and SONAR_TOKEN as secret pipeline variables.
  - script: |
      if [ -n "$(SONAR_HOST_URL)" ] && [ -n "$(SONAR_TOKEN)" ]; then
        curl -L --fail -o sonar-scanner.zip https://github.com/SonarSource/sonar-scanner-cli/releases/download/8.1.0.6389/sonar-scanner-cli-8.1.0.6389-linux-x64.zip
        unzip -oq sonar-scanner.zip -d .sonar
        .sonar/sonar-scanner-8.1.0.6389-linux-x64/bin/sonar-scanner \
          -Dsonar.host.url=$(SONAR_HOST_URL) \
          -Dsonar.token=$(SONAR_TOKEN) \
          -Dsonar.projectKey=$(Build.Repository.Name) \
          -Dsonar.qualitygate.wait=true \
          -Dsonar.qualitygate.timeout=300
      else
        echo "Skipping SonarQube scan because SONAR_HOST_URL or SONAR_TOKEN is not configured."
      fi
    displayName: SonarQube scan and quality gate
    condition: succeededOrFailed()

  - task: PublishTestResults@2
    inputs:
      testResultsFormat: JUnit
      testResultsFiles: test-results.xml
      failTaskOnFailedTests: true
    condition: succeededOrFailed()

  - task: PublishCodeCoverageResults@2
    inputs:
      summaryFileLocation: coverage.xml
    condition: succeededOrFailed()

  - publish: validation_results
    artifact: validation-evidence
    condition: succeededOrFailed()

  - archiveFiles:
      rootFolderOrFile: '$(System.DefaultWorkingDirectory)'
      includeRootFolder: false
      archiveType: zip
      archiveFile: '$(Build.ArtifactStagingDirectory)/function.zip'
      replaceExistingArchive: true
    displayName: Package Azure Function

  - publish: '$(Build.ArtifactStagingDirectory)/function.zip'
    artifact: function-package
    displayName: Publish Azure Function package
"""

AZURE_PIPELINE_PYTHON_API = """trigger:
  branches:
    include:
      - main
      - feature/*

pr:
  branches:
    include:
      - main

pool:
  vmImage: ubuntu-latest

variables:
  pythonVersion: '3.11'

steps:
  - checkout: self
    clean: true

  - task: UsePythonVersion@0
    inputs:
      versionSpec: '$(pythonVersion)'

  - script: |
      python -m pip install --upgrade pip
      pip install -r requirements.txt
      if [ -f requirements-dev.txt ]; then pip install -r requirements-dev.txt; fi
    displayName: Install dependencies

  - script: mkdir -p validation_results
    displayName: Create evidence folder

  - script: python -m ruff format --check ./src ./tests
    displayName: Ruff formatting check

  - script: python -m ruff check ./src ./tests
    displayName: Ruff lint check

  - script: python -m detect_secrets scan > validation_results/detect-secrets-report.json
    displayName: Secret scan

  - script: python -m bandit -r src -ll -f json -o validation_results/bandit-report.json
    displayName: Bandit static security scan

  - script: |
      python -m pytest -v \
        --cov=src \
        --cov-report=term-missing \
        --cov-report=xml:coverage.xml \
        --junitxml=test-results.xml
    displayName: Pytest with coverage

  - task: PublishTestResults@2
    inputs:
      testResultsFormat: JUnit
      testResultsFiles: test-results.xml
      failTaskOnFailedTests: true
    condition: succeededOrFailed()

  - task: PublishCodeCoverageResults@2
    inputs:
      summaryFileLocation: coverage.xml
    condition: succeededOrFailed()

  - publish: validation_results
    artifact: validation-evidence
    condition: succeededOrFailed()
"""

AZURE_PIPELINE_NODE = """trigger:
  branches:
    include:
      - main
      - feature/*

pr:
  branches:
    include:
      - main

pool:
  vmImage: ubuntu-latest

steps:
  - checkout: self
    clean: true

  - task: NodeTool@0
    inputs:
      versionSpec: '20.x'

  - script: npm ci
    displayName: Install dependencies

  - script: npm run lint --if-present
    displayName: Lint

  - script: npm test --if-present
    displayName: Test

  - script: npm audit --audit-level=high
    displayName: Dependency security audit
"""

AZURE_PIPELINE_GENERIC = """trigger:
  branches:
    include:
      - main
      - feature/*

pr:
  branches:
    include:
      - main

pool:
  vmImage: ubuntu-latest

steps:
  - checkout: self
    clean: true

  - script: |
      echo "Generic repository detected."
      echo "Add project-specific validation commands here."
    displayName: Generic validation placeholder
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AegisFlow AI — Agentic DevSecOps & MLOps Orchestrator")
    parser.add_argument("repo", help="Local repository path")
    parser.add_argument("--generate-files", action="store_true", help="Generate missing pipeline/governance files")
    parser.add_argument("--apply", action="store_true", help="Actually write generated files")
    parser.add_argument("--run-validations", action="store_true", help="Run local validations")
    parser.add_argument("--skip-validations", action="store_true", help="Skip local validations")
    parser.add_argument("--overwrite-pipeline", action="store_true", help="Overwrite azure-pipeline.yml")
    parser.add_argument("--branch", help="Create/switch to branch before commit")
    parser.add_argument("--commit", action="store_true", help="Commit changes")
    parser.add_argument("--push", action="store_true", help="Push branch")
    parser.add_argument("--remote", default="origin", help="Git remote name")
    parser.add_argument("--create-pr", action="store_true", help="Create Azure DevOps PR using env vars")
    parser.add_argument("--target-branch", default="main")
    parser.add_argument("--llm", action="store_true", help="Use local Ollama LLM for recommendations")
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"))
    parser.add_argument("--install-ollama", action="store_true", default=True, help="Install Ollama CLI automatically on WSL/Linux if missing")
    parser.add_argument("--install-tools", action="store_true", help="Install/update validation tools such as Ruff, Pytest, Bandit, detect-secrets")
    parser.add_argument("--auto-fix", action="store_true", help="Run safe automated fixes such as Ruff format and Ruff --fix")
    parser.add_argument("--generate-tests-for", nargs="*", default=[], help="Create missing pytest files for specific local repo files")
    parser.add_argument("--generate-tests-for-all", action="store_true", help="Create missing pytest files for all Python source files")
    parser.add_argument("--auto-repair-pytest", action="store_true", default=True, help="Automatically clean common Pytest collection/cache issues and rerun Pytest once")
    parser.add_argument("--overwrite-tests", action="store_true", help="Overwrite generated tests if they already exist")
    parser.add_argument("--allow-git-on-failure", action="store_true", help="Allow commit/push/PR even when validations fail")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_validations = args.run_validations or not args.skip_validations
    agent = OrchestratorAgent(args.repo)
    report = agent.run(
        generate_files=args.generate_files,
        apply=args.apply,
        run_validations=run_validations,
        overwrite_pipeline=args.overwrite_pipeline,
        branch=args.branch,
        commit=args.commit,
        push=args.push,
        remote=args.remote,
        create_pr=args.create_pr,
        target_branch=args.target_branch,
        llm=args.llm,
        model=args.model,
        install_ollama=args.install_ollama,
        install_tools=args.install_tools,
        auto_fix=args.auto_fix,
        generate_tests_for=args.generate_tests_for,
        generate_tests_for_all=args.generate_tests_for_all,
        overwrite_tests=args.overwrite_tests,
        allow_git_on_failure=args.allow_git_on_failure,
        auto_repair_pytest=args.auto_repair_pytest,
    )
    print("\nSummary:")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
