from __future__ import annotations

import json
import os
import subprocess
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import streamlit as st
import requests

from agent import Event, OrchestratorAgent, get_git_context, apply_fix_plan_and_rerun


st.set_page_config(page_title="AegisFlow: DevSecOps Pipeline Orchestrator Agent", page_icon="🛡️", layout="wide")

THEME_PRESETS = {
    "Azure Clean Light": {
        "page_bg": "#f8fafc",
        "sidebar_bg": "#ffffff",
        "sidebar_text": "#0f172a",
        "hero_from": "#e0f2fe",
        "hero_to": "#ffffff",
        "hero_text": "#0f172a",
        "hero_muted": "#475569",
        "accent": "#2563eb",
        "accent_2": "#0891b2",
        "chip_bg": "#eff6ff",
        "chip_text": "#1d4ed8",
        "chip_border": "#bfdbfe",
        "button": "#2563eb",
        "button_hover": "#1d4ed8",
        "border": "#e2e8f0",
        "card": "#ffffff",
        "soft": "#f1f5f9",
    },
    "Enterprise Navy": {
        "page_bg": "#f6f8fb",
        "sidebar_bg": "#0f172a",
        "sidebar_text": "#f8fafc",
        "hero_from": "#0f172a",
        "hero_to": "#1e293b",
        "hero_text": "#ffffff",
        "hero_muted": "#cbd5e1",
        "accent": "#38bdf8",
        "accent_2": "#14b8a6",
        "chip_bg": "rgba(56, 189, 248, .12)",
        "chip_text": "#e0f2fe",
        "chip_border": "rgba(125, 211, 252, .35)",
        "button": "#0ea5e9",
        "button_hover": "#0284c7",
        "border": "#dbe3ef",
        "card": "#ffffff",
        "soft": "#eef6ff",
    },
    "Minimal White": {
        "page_bg": "#ffffff",
        "sidebar_bg": "#f8fafc",
        "sidebar_text": "#111827",
        "hero_from": "#ffffff",
        "hero_to": "#f8fafc",
        "hero_text": "#111827",
        "hero_muted": "#4b5563",
        "accent": "#111827",
        "accent_2": "#64748b",
        "chip_bg": "#f3f4f6",
        "chip_text": "#374151",
        "chip_border": "#e5e7eb",
        "button": "#111827",
        "button_hover": "#374151",
        "border": "#e5e7eb",
        "card": "#ffffff",
        "soft": "#f9fafb",
    },
    "Teal Professional": {
        "page_bg": "#f7fbfb",
        "sidebar_bg": "#ffffff",
        "sidebar_text": "#12333a",
        "hero_from": "#ccfbf1",
        "hero_to": "#ffffff",
        "hero_text": "#12333a",
        "hero_muted": "#3f5f66",
        "accent": "#0f766e",
        "accent_2": "#0e7490",
        "chip_bg": "#ecfeff",
        "chip_text": "#0e7490",
        "chip_border": "#a5f3fc",
        "button": "#0f766e",
        "button_hover": "#115e59",
        "border": "#d6eeee",
        "card": "#ffffff",
        "soft": "#effdfb",
    },
}

with st.sidebar:
    st.header("Dashboard style")
    theme_choice = st.selectbox(
        "Color theme",
        list(THEME_PRESETS.keys()),
        index=0,
        help="Change the dashboard colors without touching the code.",
    )

p = THEME_PRESETS[theme_choice]

CUSTOM_CSS = f"""
<style>
:root {{
  --aegis-page-bg: {p["page_bg"]};
  --aegis-sidebar-bg: {p["sidebar_bg"]};
  --aegis-sidebar-text: {p["sidebar_text"]};
  --aegis-hero-from: {p["hero_from"]};
  --aegis-hero-to: {p["hero_to"]};
  --aegis-hero-text: {p["hero_text"]};
  --aegis-hero-muted: {p["hero_muted"]};
  --aegis-accent: {p["accent"]};
  --aegis-accent-2: {p["accent_2"]};
  --aegis-chip-bg: {p["chip_bg"]};
  --aegis-chip-text: {p["chip_text"]};
  --aegis-chip-border: {p["chip_border"]};
  --aegis-button: {p["button"]};
  --aegis-button-hover: {p["button_hover"]};
  --aegis-border: {p["border"]};
  --aegis-card: {p["card"]};
  --aegis-soft: {p["soft"]};
  --aegis-ok: #16a34a;
  --aegis-bad: #dc2626;
  --aegis-warn: #d97706;
}}

html, body, [data-testid="stAppViewContainer"] {{
  background: var(--aegis-page-bg) !important;
}}
.block-container {{padding-top: 1.5rem; max-width: 1440px;}}

[data-testid="stSidebar"] {{
  background: var(--aegis-sidebar-bg) !important;
  border-right: 1px solid var(--aegis-border);
}}
[data-testid="stSidebar"] * {{color: var(--aegis-sidebar-text) !important;}}
[data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea {{
  color: #111827 !important;
  background: #ffffff !important;
  border: 1px solid var(--aegis-border) !important;
  border-radius: 10px !important;
}}
[data-testid="stSidebar"] label p {{font-weight: 600 !important;}}

.stButton > button {{
  background: var(--aegis-button) !important;
  color: #ffffff !important;
  border: 0 !important;
  border-radius: 12px !important;
  padding: .65rem 1.1rem !important;
  font-weight: 700 !important;
  box-shadow: 0 10px 22px rgba(15, 23, 42, .14);
}}
.stButton > button:hover {{
  background: var(--aegis-button-hover) !important;
  color: #ffffff !important;
}}

.aegis-hero {{
  padding: 30px 34px;
  border-radius: 28px;
  background: linear-gradient(135deg, var(--aegis-hero-from) 0%, var(--aegis-hero-to) 100%);
  color: var(--aegis-hero-text);
  border: 1px solid var(--aegis-border);
  box-shadow: 0 18px 42px rgba(15, 23, 42, .08);
  margin-bottom: 18px;
}}
.aegis-hero h1 {{font-size: 42px; letter-spacing: -1.2px; margin-bottom: 8px; color: var(--aegis-hero-text);}}
.aegis-hero p {{font-size: 16px; color: var(--aegis-hero-muted); margin-bottom: 0;}}
.aegis-logo {{
  display: inline-flex; align-items: center; justify-content: center;
  width: 42px; height: 42px; border-radius: 14px;
  background: var(--aegis-chip-bg); border: 1px solid var(--aegis-chip-border);
  margin-right: 10px;
}}
.aegis-chip {{
  display: inline-block; padding: 7px 12px; border-radius: 999px; margin: 12px 8px 0 0;
  background: var(--aegis-chip-bg); color: var(--aegis-chip-text); border: 1px solid var(--aegis-chip-border);
  font-size: 13px; font-weight: 600;
}}
.metric-card {{
  padding: 18px; border-radius: 20px; background: var(--aegis-card); border: 1px solid var(--aegis-border);
  box-shadow: 0 10px 28px rgba(15, 23, 42, .06); min-height: 108px;
}}
.metric-card .label {{color:#64748b; font-size: 13px; text-transform: uppercase; letter-spacing: .06em;}}
.metric-card .value {{font-size: 30px; font-weight: 800; margin-top: 7px; color:#0f172a;}}
.metric-card.ok {{border-left: 5px solid var(--aegis-ok);}} 
.metric-card.fail {{border-left: 5px solid var(--aegis-bad);}} 
.metric-card.skip {{border-left: 5px solid var(--aegis-warn);}} 
.stage-card {{
  padding: 14px 16px; border-radius: 16px; border: 1px solid var(--aegis-border); background: var(--aegis-card);
  margin-bottom: 10px; box-shadow: 0 8px 20px rgba(15, 23, 42, .04);
}}
.stage-card b {{color:#0f172a;}}
.small-muted {{color:#64748b; font-size: 13px;}}
.download-card {{
  padding: 16px; border-radius: 18px; border: 1px solid var(--aegis-chip-border); background: var(--aegis-chip-bg);
}}
.coverage-tile {{
  border: 1px solid #d1d5db;
  background: #fafafa;
  border-radius: 8px;
  padding: 18px;
  min-height: 128px;
}}
.coverage-tile .title {{
  color: #64748b;
  font-size: 20px;
  margin-bottom: 12px;
}}
.coverage-big {{
  font-size: 58px;
  line-height: 1;
  font-weight: 800;
  color: #60646c;
  margin-right: 12px;
}}
.coverage-kv {{
  font-size: 14px;
  color: #111827;
  line-height: 1.6;
}}
.coverage-bar-bg {{
  height: 12px;
  background: #e5e7eb;
  border-radius: 2px;
  overflow: hidden;
}}
.coverage-bar-fill {{
  height: 12px;
  background: linear-gradient(90deg, #16a34a, #22c55e);
}}
/* Two-line Streamlit tabs: wrap instead of horizontal scrollbar */
div[data-testid="stTabs"] div[role="tablist"],
[data-baseweb="tab-list"] {{
  display: flex !important;
  flex-wrap: wrap !important;
  overflow-x: visible !important;
  overflow-y: visible !important;
  gap: 8px 22px !important;
  column-gap: 22px !important;
  row-gap: 8px !important;
  white-space: normal !important;
  border-bottom: 1px solid var(--aegis-border) !important;
  scrollbar-width: none !important;
  padding-bottom: 8px !important;
}}

div[data-testid="stTabs"] div[role="tablist"]::-webkit-scrollbar,
[data-baseweb="tab-list"]::-webkit-scrollbar {{
  display: none !important;
}}

div[data-testid="stTabs"] button[role="tab"],
[data-baseweb="tab"] {{
  flex: 0 0 auto !important;
  padding: 10px 12px !important;
  margin-right: 0 !important;
  border-radius: 10px 10px 0 0 !important;
  min-width: max-content !important;
}}

div[data-testid="stTabs"] button[role="tab"] p,
[data-baseweb="tab"] p {{
  white-space: nowrap !important;
  font-size: 0.94rem !important;
  font-weight: 500 !important;
}}

[data-baseweb="tab-highlight"] {{background-color: var(--aegis-accent) !important;}}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

st.markdown(
    """
<div class="aegis-hero">
  <h1><span class="aegis-logo">🛡️</span>AegisFlow: DevSecOps Pipeline Orchestrator Agent</h1>
  <p>Agentic DevSecOps pipeline cockpit — local repo → PR validation → CI/CD checks → SonarQube quality gate → evidence pack → deployment readiness.</p>
  <span class="aegis-chip">CI/CD cockpit</span>
  <span class="aegis-chip">Security gates</span>
  <span class="aegis-chip">Coverage evidence</span>
  <span class="aegis-chip">AI explanations</span>
  <span class="aegis-chip">Downloadable evidence pack</span>
  <span class="aegis-chip">Industry use cases</span>
</div>
""",
    unsafe_allow_html=True,
)



def download_button_for_path(label: str, path_value: str | None, mime: str) -> None:
    if not path_value:
        st.info(f"{label}: not generated")
        return
    path = Path(path_value)
    if not path.exists():
        st.warning(f"{label}: file not found at {path}")
        return
    st.download_button(
        label=label,
        data=path.read_bytes(),
        file_name=path.name,
        mime=mime,
        use_container_width=True,
    )


def human_file_size(num_bytes: int) -> str:
    value = float(num_bytes or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


def robust_download_button(label: str, path_value: str | None, mime: str, default_ext: str = "") -> None:
    """Streamlit download helper that shows file size/path and always supplies a real extension.

    This fixes the confusing browser behaviour where a download may appear as a generic
    file or remain as an unconfirmed download when the filename is missing/unclear.
    """
    if not path_value:
        st.info(f"{label}: not generated yet")
        return
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        st.warning(f"{label}: file not found at `{path}`")
        return
    data = path.read_bytes()
    file_name = path.name
    if default_ext and not file_name.lower().endswith(default_ext.lower()):
        file_name = f"{file_name}{default_ext}"
    st.caption(f"{file_name} • {human_file_size(len(data))}")
    st.download_button(
        label=label,
        data=data,
        file_name=file_name,
        mime=mime,
        key=f"download_{label}_{path.name}_{path.stat().st_mtime_ns}",
        use_container_width=True,
    )


def get_zip_manifest(zip_path_value: str | None) -> list[dict]:
    if not zip_path_value:
        return []
    zip_path = Path(zip_path_value)
    if not zip_path.exists() or not zipfile.is_zipfile(zip_path):
        return []
    rows: list[dict] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            rows.append({
                "file": info.filename,
                "size": human_file_size(info.file_size),
                "compressed": human_file_size(info.compress_size),
            })
    return rows


def parse_cobertura_coverage(path_value: str | None) -> dict:
    """Parse coverage.xml generated by pytest-cov/Cobertura."""
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
        line_rate = float(root.attrib.get("line-rate", 0.0) or 0.0) * 100
        branch_rate = root.attrib.get("branch-rate")
        lines_valid = int(float(root.attrib.get("lines-valid", 0) or 0))
        lines_covered = int(float(root.attrib.get("lines-covered", 0) or 0))
        files = []
        total_classes = 0
        for cls in root.findall(".//class"):
            total_classes += 1
            filename = cls.attrib.get("filename") or cls.attrib.get("name") or "unknown"
            class_rate = float(cls.attrib.get("line-rate", 0.0) or 0.0) * 100
            line_nodes = cls.findall(".//line")
            coverable = len(line_nodes)
            covered = 0
            for line in line_nodes:
                try:
                    if int(line.attrib.get("hits", 0) or 0) > 0:
                        covered += 1
                except ValueError:
                    pass
            uncovered = max(coverable - covered, 0)
            percentage = round((covered / coverable) * 100, 2) if coverable else round(class_rate, 2)
            files.append({
                "Name": filename,
                "Covered": covered,
                "Uncovered": uncovered,
                "Coverable": coverable,
                "Percentage": percentage,
            })
        return {
            "line_coverage_%": round(line_rate, 2),
            "lines_covered": lines_covered,
            "lines_valid": lines_valid,
            "uncovered_lines": max(lines_valid - lines_covered, 0),
            "branch_rate": branch_rate,
            "classes": total_classes,
            "files_count": len(files),
            "files": files,
        }
    except Exception as exc:
        return {"error": str(exc)}


def parse_junit_results(path_value: str | None) -> dict:
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.exists():
        return {}
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore"))
        if root.tag == "testsuites":
            tests = int(root.attrib.get("tests", 0) or 0)
            failures = int(root.attrib.get("failures", 0) or 0)
            errors = int(root.attrib.get("errors", 0) or 0)
            skipped = int(root.attrib.get("skipped", 0) or 0)
        else:
            tests = int(root.attrib.get("tests", 0) or 0)
            failures = int(root.attrib.get("failures", 0) or 0)
            errors = int(root.attrib.get("errors", 0) or 0)
            skipped = int(root.attrib.get("skipped", 0) or 0)
        return {
            "tests": tests,
            "passed": max(tests - failures - errors - skipped, 0),
            "failures": failures,
            "errors": errors,
            "skipped": skipped,
        }
    except Exception as exc:
        return {"error": str(exc)}


def read_file_preview(path_value: str | None, limit: int = 12000) -> str:
    if not path_value:
        return "Not generated."
    path = Path(path_value)
    if not path.exists() or not path.is_file():
        return f"File not found: {path}"
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) > limit:
        return text[:limit] + "\n\n... preview truncated ..."
    return text



def render_azure_devops_style_coverage(coverage: dict) -> None:
    """Render coverage.xml as an Azure DevOps-like coverage cockpit."""
    if not coverage or coverage.get("error"):
        return

    line_pct = coverage.get("line_coverage_%", 0) or 0
    covered = coverage.get("lines_covered", 0) or 0
    coverable = coverage.get("lines_valid", 0) or 0
    uncovered = coverage.get("uncovered_lines", 0) or 0
    files = coverage.get("files", []) or []
    classes = coverage.get("classes", len(files))
    branch_rate_raw = coverage.get("branch_rate")
    try:
        branch_pct = round(float(branch_rate_raw) * 100, 2) if branch_rate_raw not in {None, ""} else None
    except Exception:
        branch_pct = None

    st.markdown("### Azure DevOps-style code coverage view")
    st.caption("This renders the same `coverage.xml` evidence that Azure DevOps publishes under Pipeline Run → Code Coverage.")
    c1, c2, c3, c4 = st.columns([1.0, 1.85, 1.65, 1.3])
    with c1:
        st.markdown(f'''
<div class="coverage-tile">
  <div class="title">Information</div>
  <div class="coverage-kv"><b>Parser:</b> Cobertura</div>
  <div class="coverage-kv"><b>Assemblies:</b> 1</div>
  <div class="coverage-kv"><b>Classes:</b> {classes}</div>
  <div class="coverage-kv"><b>Files:</b> {coverage.get("files_count", len(files))}</div>
</div>
''', unsafe_allow_html=True)
    with c2:
        st.markdown(f'''
<div class="coverage-tile">
  <div class="title">Line coverage</div>
  <div style="display:flex; align-items:center; gap:14px;">
    <div class="coverage-big">{line_pct:.0f}%</div>
    <div class="coverage-kv">
      <b>Covered lines:</b> {covered}<br/>
      <b>Uncovered lines:</b> {uncovered}<br/>
      <b>Coverable lines:</b> {coverable}<br/>
      <b>Line coverage:</b> {line_pct:.1f}%
    </div>
  </div>
</div>
''', unsafe_allow_html=True)
    with c3:
        if branch_pct is None or branch_pct == 0:
            branch_html = '<div class="coverage-big">N/A</div><div class="coverage-kv"><b>Covered branches:</b> 0<br/><b>Total branches:</b> 0<br/><b>Branch coverage:</b> N/A</div>'
        else:
            branch_html = f'<div class="coverage-big">{branch_pct:.0f}%</div><div class="coverage-kv"><b>Branch coverage:</b> {branch_pct:.1f}%</div>'
        st.markdown(f'''
<div class="coverage-tile">
  <div class="title">Branch coverage</div>
  <div style="display:flex; align-items:center; gap:14px;">{branch_html}</div>
</div>
''', unsafe_allow_html=True)
    with c4:
        st.markdown('''
<div class="coverage-tile">
  <div class="title">Method coverage</div>
  <div class="coverage-kv" style="margin-top:22px;">Method coverage is not emitted by the current Python Cobertura report.</div>
</div>
''', unsafe_allow_html=True)

    if files:
        st.markdown("#### Coverage by file")
        header = st.columns([3.8, 1, 1, 1, 2.1])
        header[0].markdown("**Name**")
        header[1].markdown("**Covered**")
        header[2].markdown("**Uncovered**")
        header[3].markdown("**Coverable**")
        header[4].markdown("**Percentage**")
        for row in files:
            pct = float(row.get("Percentage", 0) or 0)
            cols = st.columns([3.8, 1, 1, 1, 2.1])
            cols[0].write(row.get("Name", ""))
            cols[1].write(row.get("Covered", 0))
            cols[2].write(row.get("Uncovered", 0))
            cols[3].write(row.get("Coverable", 0))
            cols[4].markdown(f'''
<div style="display:flex; align-items:center; gap:10px;">
  <span style="min-width:54px;">{pct:.1f}%</span>
  <div class="coverage-bar-bg" style="flex:1;"><div class="coverage-bar-fill" style="width:{max(0,min(100,pct))}%;"></div></div>
</div>
''', unsafe_allow_html=True)

def render_evidence_dashboard(report: dict) -> None:
    """Best-effort evidence cockpit: downloads + visible contents + previews.

    The goal is that a user should not need to open the ZIP to understand what evidence
    was produced. The dashboard shows the same important evidence inline and still offers
    download buttons for audit/share.
    """
    paths = report.get("report_paths", {}) or {}
    repo = Path(report.get("repo", "")) if report.get("repo") else None
    coverage_path = str(repo / "coverage.xml") if repo else None
    junit_path = str(repo / "test-results.xml") if repo else None
    sonar_output = str(repo / "validation_results" / "sonar-scanner-output.txt") if repo else None

    st.subheader("Download evidence")
    st.markdown(
        """
<div class="download-card">
  <b>Evidence pack contents are also shown below.</b><br/>
  The ZIP is for audit/share. The dashboard previews coverage, tests, validation results, Sonar logs, and report files directly.
</div>
""",
        unsafe_allow_html=True,
    )
    d1, d2, d3 = st.columns(3)
    with d1:
        robust_download_button("⬇️ Download evidence ZIP", paths.get("zip"), "application/zip", ".zip")
    with d2:
        robust_download_button("⬇️ Download Markdown report", paths.get("markdown"), "text/markdown", ".md")
    with d3:
        robust_download_button("⬇️ Download JSON report", paths.get("json"), "application/json", ".json")

    with st.expander("Download troubleshooting / local file paths", expanded=False):
        st.write("If your browser download does not start, the files are already written locally in the repo under `orchestrator_reports/`.")
        st.json(paths)
        if paths.get("zip"):
            st.code(f'cp "{paths.get("zip")}" /mnt/c/Users/AnubhaAnubha/Downloads/', language="bash")

    st.subheader("Evidence overview")
    summary = report.get("summary", {}) or {}
    counts = summary.get("counts", {}) or {}
    coverage = parse_cobertura_coverage(coverage_path)
    junit = parse_junit_results(junit_path)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Validations passed", counts.get("ok", 0))
    c2.metric("Validations failed", counts.get("fail", 0))
    c3.metric("Validations skipped", counts.get("skip", 0))
    c4.metric("Line coverage", f"{coverage.get('line_coverage_%', 'N/A')}%" if coverage else "N/A")
    c5.metric("Tests passed", junit.get("passed", "N/A") if junit else "N/A")

    render_azure_devops_style_coverage(coverage)

    st.subheader("Evidence pack contents")
    manifest = get_zip_manifest(paths.get("zip"))
    if manifest:
        st.dataframe(manifest, use_container_width=True, hide_index=True)
    else:
        st.warning("Evidence ZIP manifest is not available yet. Run orchestrator again or check the path above.")

    st.subheader("Coverage evidence")
    st.caption("This is the local/Azure DevOps coverage evidence generated by `pytest --cov=src --cov-report=xml:coverage.xml`.")
    if coverage:
        if coverage.get("error"):
            st.warning(f"Could not parse coverage.xml: {coverage['error']}")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Line coverage", f"{coverage['line_coverage_%']}%")
            m2.metric("Covered lines", coverage.get("lines_covered", 0))
            m3.metric("Uncovered lines", coverage.get("uncovered_lines", 0))
            if coverage.get("files"):
                st.dataframe(coverage["files"], use_container_width=True, hide_index=True)
    else:
        st.info("coverage.xml was not found in the repo. Run Pytest with coverage first.")

    st.subheader("Test evidence")
    if junit:
        if junit.get("error"):
            st.warning(f"Could not parse test-results.xml: {junit['error']}")
        else:
            t1, t2, t3, t4 = st.columns(4)
            t1.metric("Total tests", junit.get("tests", 0))
            t2.metric("Passed", junit.get("passed", 0))
            t3.metric("Failures", junit.get("failures", 0))
            t4.metric("Errors", junit.get("errors", 0))
    else:
        st.info("test-results.xml was not found in the repo.")

    st.subheader("Validation result table")
    validations = report.get("validation_results", []) or []
    if validations:
        st.dataframe([
            {
                "status": v.get("status"),
                "category": v.get("category"),
                "check": v.get("name"),
                "classification": v.get("classification"),
                "message": v.get("message", ""),
            }
            for v in validations
        ], use_container_width=True, hide_index=True)

    st.subheader("Evidence file previews")
    ptab1, ptab2, ptab3, ptab4, ptab5 = st.tabs(["Markdown report", "JSON report", "coverage.xml", "test-results.xml", "Sonar output"])
    with ptab1:
        st.code(read_file_preview(paths.get("markdown")), language="markdown")
    with ptab2:
        st.code(read_file_preview(paths.get("json")), language="json")
    with ptab3:
        st.code(read_file_preview(coverage_path), language="xml")
    with ptab4:
        st.code(read_file_preview(junit_path), language="xml")
    with ptab5:
        st.code(read_file_preview(sonar_output), language="text")



ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
BROKEN_ANSI_RE = re.compile(r"�\[[0-9?;:]*[A-Za-z]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_llm_text(text: str) -> str:
    """Remove terminal/spinner control sequences that can appear from local model CLIs."""
    if not text:
        return ""
    text = ANSI_RE.sub("", text)
    text = BROKEN_ANSI_RE.sub("", text)
    text = CONTROL_RE.sub("", text)
    # If terminal escape bytes were already decoded as replacement characters, remove the worst leftovers.
    text = text.replace("�", "")
    # Collapse excessive blank lines but keep readable paragraphs.
    lines = [line.rstrip() for line in text.splitlines()]
    compact = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                compact.append("")
            blank = True
        else:
            compact.append(line)
            blank = False
    return "\n".join(compact).strip()


def deterministic_chat_answer(question: str, context: dict) -> str:
    q = question.lower()
    failures = context.get("failed_validations") or []
    plan = context.get("ai_fix_plan") or {}
    proposed = [i for i in plan.get("items", []) if i.get("status") == "proposed"]
    review_only = plan.get("review_only") or []

    docker_failures = [f for f in failures if "docker" in (f.get("name", "").lower()) or "hadolint" in (f.get("tool", "").lower())]
    pytest_failures = [f for f in failures if "pytest" in (f.get("name", "").lower()) or f.get("category") == "testing"]

    if "docker" in q or "hadolint" in q or docker_failures:
        msg = ["**Dockerfile issue:** Hadolint found Dockerfile best-practice problems in `infra/docker/Dockerfile`. This is why the Dockerfile check failed."]
        if proposed:
            msg.append("**Fix available:** Open **AI Fix Plan**, review the exact diff, tick approval, then click **Apply approved fix plan and rerun affected validation**.")
        elif review_only:
            msg.append("**No automatic safe patch was applied:** the finding is review-only. For rules like `DL3008`/`DL3013`, AegisFlow should not invent package versions blindly because that can break Docker builds.")
            msg.append("Best options: pin exact package versions if your team knows them, or approve a documented Hadolint exception with justification.")
        else:
            msg.append("No patch was generated in the last run. Rerun with **Generate reviewable fix plan with exact diffs** enabled.")
        msg.append("Run manually for exact rule output: `hadolint infra/docker/Dockerfile`.")
        return "\n\n".join(msg)

    if "pytest" in q or "test" in q or pytest_failures:
        msg = ["**Pytest issue:** one or more tests failed or the test environment is not correctly configured."]
        msg.append("AegisFlow can safely fix cache/import/tooling problems, but it should not blindly change product logic or test expectations.")
        msg.append("Check **Live Progress** for the failed test names and raw output. Common fixes are installing repo requirements, using the correct Conda Python, setting `PYTHONPATH`, or updating the code/test if behavior changed intentionally.")
        return "\n\n".join(msg)

    if proposed:
        return f"There are **{len(proposed)} proposed patch(es)**. Go to **AI Fix Plan**, review the diff, approve it, and apply. AegisFlow will rerun the affected validation and show before/after results."

    return "I checked the last run context. Use **AI Error Intelligence** for failure explanation and **AI Fix Plan** for approval-based patches. If no patch is available, the issue likely needs human decision such as version pinning, test expectation, secrets, or architecture approval."


def aegisflow_chat_answer(question: str, report: dict | None, model_name: str = "qwen2.5-coder:7b") -> str:
    """Local chat assistant for the last AegisFlow run.

    v20 uses Ollama's HTTP API instead of `ollama run` so terminal progress/spinner
    escape sequences do not corrupt the chat response.
    """
    question = (question or "").strip()
    if not question:
        return "Ask me about a failed check, Dockerfile lint, Pytest errors, PR readiness, or what fix to approve."
    context = {}
    if report:
        context = {
            "summary": report.get("summary"),
            "governance_decision": report.get("governance_decision"),
            "failed_validations": [v for v in report.get("validations", []) if v.get("status") == "fail"][:8],
            "ai_fix_plan": report.get("ai_fix_plan"),
            "git_context": report.get("git_context"),
        }

    fallback = deterministic_chat_answer(question, context)
    prompt = f"""You are AegisFlow AI, a DevSecOps orchestration assistant.
Answer using the run context. Be direct, practical, and concise.
Explain what failed, why, whether a patch is available, and what button/action the user should click next.
Never output terminal escape codes. Do not claim deployment/security/compliance approval is complete; human approval is needed.

Run context JSON:
{json.dumps(context, indent=2)[:9000]}

User question: {question}
"""
    try:
        response = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={"model": model_name, "prompt": prompt, "stream": False},
            timeout=60,
        )
        if response.ok:
            payload = response.json()
            text = clean_llm_text(payload.get("response", ""))
            # If output is empty or still looks corrupted, use deterministic answer.
            if text and len(text) > 20 and text.count("�") < 3:
                return text
    except Exception:
        pass
    return fallback

def render_metric_cards(summary: dict) -> None:
    counts = summary.get("counts", {}) if summary else {}
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="metric-card ok"><div class="label">Passed</div><div class="value">{counts.get("ok", 0)}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card fail"><div class="label">Failed</div><div class="value">{counts.get("fail", 0)}</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card skip"><div class="label">Skipped</div><div class="value">{counts.get("skip", 0)}</div></div>', unsafe_allow_html=True)
    with c4:
        decision = st.session_state.get("last_decision", "not run")
        st.markdown(f'<div class="metric-card"><div class="label">Release support</div><div class="value" style="font-size:20px;">{decision}</div></div>', unsafe_allow_html=True)


def _is_noise_path(rel: str) -> bool:
    noise_parts = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "node_modules", "htmlcov", "orchestrator_reports", "dist", "build"}
    return any(part in noise_parts for part in rel.split("/"))

def prefetch_repository(path_text: str) -> dict:
    """Fast local preflight. It does not modify anything."""
    result = {"ok": False, "message": "No repo path provided"}
    if not path_text or not path_text.strip():
        return result
    try:
        input_path = Path(path_text.strip()).expanduser().resolve()
        if not input_path.exists():
            return {"ok": False, "message": f"Path does not exist: {input_path}"}
        git_context = get_git_context(str(input_path))
        root = Path(git_context.get("git_root") or input_path).expanduser().resolve()
        all_files = []
        for f in root.rglob("*"):
            if f.is_file():
                rel = f.relative_to(root).as_posix()
                if not _is_noise_path(rel):
                    all_files.append(rel)
        all_files.sort()
        ext_counts = Counter((Path(x).suffix.lower() or "[no extension]") for x in all_files)
        py_sources = [x for x in all_files if x.endswith(".py") and not (x.startswith("tests/") or "/tests/" in x or Path(x).name.startswith("test_"))]
        test_files = [x for x in all_files if x.endswith(".py") and (x.startswith("tests/") or "/tests/" in x or Path(x).name.startswith("test_"))]
        config_names = {"azure-pipeline.yml", "azure-pipelines.yml", "sonar-project.properties", "pytest.ini", ".coveragerc", "requirements.txt", "requirements-dev.txt", "pyproject.toml", "Dockerfile", "host.json", "function.json", ".gitignore"}
        config_files = [x for x in all_files if Path(x).name in config_names or x.startswith(".github/workflows/") or "/function.json" in x]
        source_to_test = []
        test_set = set(test_files)
        for src in py_sources[:1000]:
            stem = Path(src).stem
            likely = [f"tests/test_{stem}.py", f"tests/generated/{Path(src).parent.as_posix()}/test_{stem}.py"]
            source_to_test.append({"source_file": src, "test_status": "exists" if any(x in test_set for x in likely) else "missing_or_custom", "expected_test": likely[0]})
        return {
            "ok": True,
            "root": str(root),
            "git_context": git_context,
            "total_files": len(all_files),
            "extension_counts": dict(ext_counts.most_common(20)),
            "all_files": all_files,
            "all_files_sample": all_files[:500],
            "python_source_count": len(py_sources),
            "test_file_count": len(test_files),
            "config_files": config_files[:200],
            "source_to_test_sample": source_to_test[:200],
        }
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _read_repo_text(root: Path, rel: str, max_chars: int = 200_000) -> str:
    try:
        path = root / rel
        if path.exists() and path.is_file():
            return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""
    return ""


def _status(ok: bool, pass_label: str = "Pass", fail_label: str = "Fail") -> str:
    return f"✅ {pass_label}" if ok else f"❌ {fail_label}"


def _has_file(files: set[str], *names: str) -> bool:
    return any(name in files for name in names)


def _result_status(report: dict, keyword: str) -> str | None:
    keyword = keyword.lower()
    for key in ("validation_results", "validations", "correction_results"):
        for item in report.get(key, []) or []:
            text = " ".join([str(item.get("name", "")), str(item.get("category", "")), str(item.get("message", ""))]).lower()
            if keyword in text:
                return item.get("status")
    for e in report.get("events", []) or []:
        text = " ".join([str(e.get("step", "")), str(e.get("category", "")), str(e.get("message", "")), str(e.get("command", ""))]).lower()
        if keyword in text:
            return e.get("status")
    return None


def _event_contains(report: dict, keyword: str) -> bool:
    keyword = keyword.lower()
    for e in report.get("events", []) or []:
        text = " ".join([str(e.get("step", "")), str(e.get("category", "")), str(e.get("message", "")), str(e.get("command", ""))]).lower()
        if keyword in text:
            return True
    return False


def _ok_from_report(report: dict, *keywords: str) -> bool:
    for keyword in keywords:
        status = _result_status(report, keyword)
        if status in {"ok", "pass", "passed"}:
            return True
    return False


def compute_acceptance_criteria(prefetch: dict, report: dict | None = None) -> list[dict]:
    """Map the user story checklist to a dashboard-ready status table.

    This intentionally separates automated proof from manual/cloud-only proof. The dashboard
    should not claim production deployment, Azure branch policies, or human approvals are
    complete unless those signals are actually present.
    """
    report = report or {}
    rows: list[dict] = []
    if not prefetch or not prefetch.get("ok"):
        return rows

    root = Path(prefetch.get("root", "."))
    files = set(prefetch.get("all_files") or prefetch.get("all_files_sample") or [])

    def add(category: str, item: str, status: str, evidence: str, next_action: str = "") -> None:
        rows.append({
            "Category": category,
            "Acceptance criterion": item,
            "Status": status,
            "Evidence shown to user": evidence,
            "Next action": next_action,
        })

    gitignore = _read_repo_text(root, ".gitignore")
    req = _read_repo_text(root, "requirements.txt").lower()
    req_dev = _read_repo_text(root, "requirements-dev.txt").lower()
    params = _read_repo_text(root, "src/conf/parameters.yaml")
    sonar = _read_repo_text(root, "sonar-project.properties") or _read_repo_text(root, ".sonarqube.properties")
    az_func_cfg = _read_repo_text(root, "azure-function.config.yml")
    pipeline = _read_repo_text(root, "azure-pipelines.yml") or _read_repo_text(root, "azure-pipeline.yml")

    root_unwanted = [f for f in files if "/" not in f and (f in {"Dockerfile", ".dockerignore", "local.settings.json"} or f.endswith("_old.py") or f.lower() in {"sample_input.jpg", "test.jpg"})]
    root_sample_data = [f for f in files if "/" not in f and Path(f).suffix.lower() in {".jpg", ".jpeg", ".png", ".csv", ".xlsx", ".xls", ".parquet"}]
    vscode = [f for f in files if f.startswith(".vscode/")]
    old_py = [f for f in files if f.endswith("_old.py") or f.endswith(".old.py")]

    add("Repo cleanup", "Delete root Dockerfile/.dockerignore/local.settings.json/sample files/old files/.vscode", _status(not root_unwanted and not root_sample_data and not vscode and not old_py), f"Unwanted root files: {root_unwanted or 'none'}; sample data: {root_sample_data or 'none'}; .vscode files: {len(vscode)}", "Remove or keep only with justification; never commit local.settings.json.")
    add("Repo cleanup", "local.settings.json must be gitignored and not committed", _status("local.settings.json" not in files and "local.settings.json" in gitignore), f"local.settings.json committed: {'yes' if 'local.settings.json' in files else 'no'}; .gitignore contains it: {'yes' if 'local.settings.json' in gitignore else 'no'}", "Add local.settings.json to .gitignore and remove from Git if tracked.")

    add("Structure", "Move all source code to src/", _status(any(f.startswith("src/") and f.endswith(".py") for f in files)), f"Python source count: {prefetch.get('python_source_count', 0)}", "Move source files under src/.")
    add("Structure", "Move all test files to tests/", _status(any(f.startswith("tests/") and f.endswith(".py") for f in files)), f"Test file count: {prefetch.get('test_file_count', 0)}", "Move test files under tests/.")
    add("Structure", "Move conf/ inside src/", _status(any(f.startswith("src/conf/") for f in files)), f"src/conf files found: {[f for f in files if f.startswith('src/conf/')][:8] or 'none'}", "Move parameters/model config under src/conf/.")
    add("Structure", "Required Azure Function files exist", _status(_has_file(files, "src/__init__.py") and _has_file(files, "src/function.json") and _has_file(files, "host.json")), f"src/__init__.py={_has_file(files,'src/__init__.py')}, src/function.json={_has_file(files,'src/function.json')}, host.json={_has_file(files,'host.json')}", "Create missing Azure Function entry/trigger/host files.")

    old_import_hits = []
    for f in files:
        if f.endswith(".py") and not f.startswith((".git/", ".aegisflow_backups/", "orchestrator_reports/")):
            txt = _read_repo_text(root, f, max_chars=50_000)
            if "svc_schedule_opt.src" in txt:
                old_import_hits.append(f)
    add("Imports", "Replace old module paths with src imports", _status(not old_import_hits), f"Old import pattern files: {old_import_hits or 'none detected'}", "Review imports if project had a different old package name.")
    add("Imports", "Run func start locally to confirm no import errors", "🧑‍💻 Manual / not run" if not _event_contains(report, "func start") else "✅ Pass", "AegisFlow currently uses compile/pytest; func start requires Azure Functions Core Tools and local settings.", "Run `func start` manually or enable an Azure Functions local-start check.")

    hardcoded_path = bool(re.search(r"([A-Za-z]:\\|/mnt/c/|/Users/|/home/)", params or ""))
    add("Configuration", "parameters.yaml exists and uses relative paths", _status(bool(params) and not hardcoded_path), f"src/conf/parameters.yaml exists: {bool(params)}; hardcoded local path detected: {hardcoded_path}", "Replace machine-specific paths with paths relative to function root.")

    prod_dev_tools = [tool for tool in ["pytest", "ruff", "jupyter", "bandit", "detect-secrets", "pip-audit"] if re.search(rf"(^|\n)\s*{re.escape(tool)}([=<>~!\[]|\s|$)", req)]
    dev_has_tools = any(tool in req_dev for tool in ["pytest", "ruff", "pyyaml", "requests"])
    add("Dependencies", "requirements.txt contains production packages only", _status(bool(req) and not prod_dev_tools), f"Dev tools found in requirements.txt: {prod_dev_tools or 'none'}", "Move dev/test tools to requirements-dev.txt.")
    add("Dependencies", "requirements-dev.txt contains dev/pipeline tools", _status(bool(req_dev) and dev_has_tools), f"requirements-dev.txt exists: {bool(req_dev)}; dev tools detected: {dev_has_tools}", "Add pytest, ruff, pyyaml, requests, and pipeline-only tools.")

    needed_gitignore = ["local.settings.json", "__pycache__/", "*.pyc", ".venv/", ".pytest_cache/", ".aegisflow_backups/", "orchestrator_reports/"]
    missing_gitignore = [x for x in needed_gitignore if x not in gitignore]
    add("Git hygiene", ".gitignore includes local/settings/cache/generated folders", _status(not missing_gitignore), f"Missing .gitignore entries: {missing_gitignore or 'none'}", "Add missing ignore entries.")

    pipeline_exists = _has_file(files, "azure-pipelines.yml", "azure-pipeline.yml")
    pipeline_name_status = "✅ Pass" if _has_file(files, "azure-pipelines.yml") else ("⚠️ Review" if _has_file(files, "azure-pipeline.yml") else "❌ Fail")
    add("Pipeline files", "azure-pipelines.yml exists", pipeline_name_status, f"Found azure-pipelines.yml={_has_file(files,'azure-pipelines.yml')}, azure-pipeline.yml={_has_file(files,'azure-pipeline.yml')}", "Acceptance criteria says azure-pipelines.yml; rename if your central template expects plural name.")
    central_template = "repo-pipeline-templates" in pipeline and "extends:" in pipeline
    add("Pipeline files", "Pipeline wrapper references central template", "✅ Pass" if central_template else ("⚠️ Review" if pipeline_exists else "❌ Fail"), "Detected central template reference: " + str(central_template), "If required, copy exact azure-pipelines.yml from arth_test_devsecops_cicd.")
    cfg_ok = bool(az_func_cfg) and "function_app_name" in az_func_cfg and "function_app_rg" in az_func_cfg and "{your" not in az_func_cfg
    add("Pipeline files", "azure-function.config.yml has function app name and RG", _status(cfg_ok), f"Config exists: {bool(az_func_cfg)}; required keys present: {'function_app_name' in az_func_cfg and 'function_app_rg' in az_func_cfg}", "Fill exact Azure Function App name and resource group from Azure Portal.")
    sonar_ok = bool(sonar) and "sonar.sources" in sonar and "sonar.tests" in sonar and "sonar.python.coverage.reportPaths" in sonar
    add("Pipeline files", "sonar-project.properties has project/source/test/coverage settings", _status(sonar_ok), f"Sonar config exists: {bool(sonar)}", "Use unique project key, source/test paths, Python version, and coverage.xml path.")

    add("Local verification", "pip install -r requirements-dev.txt passed", _status(_ok_from_report(report, "requirements-dev")), "Shown in Live Progress when install/update tools is enabled.", "Rerun with install repo dependencies enabled.")
    add("Local verification", "ruff check ./src and formatting check passed", _status(_ok_from_report(report, "ruff lint") and _ok_from_report(report, "ruff format")), "Ruff format/lint results shown in Live Progress.", "Run Ruff auto-fix or inspect AI Error Intelligence.")
    add("Local verification", "unit tests and coverage passed", _status(_ok_from_report(report, "pytest")), "Pytest generates test-results.xml and coverage.xml.", "Fix failing tests or coverage threshold issues before PR.")
    add("Local verification", "func start confirms runtime import correctness", "🧑‍💻 Manual / not run" if not _event_contains(report, "func start") else "✅ Pass", "Not automatically run unless Azure Functions Core Tools check is configured.", "Run `func start` locally with local.settings.json.")

    # High-level DevSecOps capability view.
    add("Capability", "Azure DevOps pipeline", "✅ Pass" if pipeline_exists else "❌ Fail", "Pipeline YAML exists/generated.", "Connect/run it in Azure DevOps portal for cloud evidence.")
    add("Capability", "PR validation", "⚠️ Partial" if pipeline_exists else "❌ Fail", "Local PR-readiness checks run; actual PR policies/reviewers are Azure DevOps settings.", "Create PR, link work item, add reviewers, require passing policy.")
    add("Capability", "CI/CD", "⚠️ Partial", "Local CI checks run; CD deploy requires Azure service connection and target function config.", "Use central template for CI/CD cloud execution.")
    sonar_status = _result_status(report, "sonar")
    add("Capability", "SonarQube/static analysis", "✅ Pass" if sonar_status == "ok" else ("⏭️ Skipped" if sonar_status == "skip" else "⚠️ Ready / needs credentials"), f"Sonar status: {sonar_status or 'not found'}; config exists: {bool(sonar)}", "Provide SONAR_HOST_URL and SONAR_TOKEN for actual scan.")
    add("Capability", "Unit testing", _status(_ok_from_report(report, "pytest")), "Pytest with coverage is visible in Live Progress and evidence pack.", "Fix tests before closing story.")
    add("Capability", "Logging/live progress", _status(bool(report.get("events"))), f"Events captured: {len(report.get('events', []) or [])}", "Use evidence report for audit trail.")
    report_paths = report.get("report_paths", {}) or {}
    add("Capability", "Artifact/evidence creation", _status(bool(report_paths.get("zip") or report_paths.get("markdown") or report_paths.get("json"))), f"Report paths: {report_paths or 'not generated'}", "Download evidence pack and attach/link to PR/work item.")
    deploy_seen = _event_contains(report, "deploy") or _event_contains(report, "health check") or _event_contains(report, "azure function")
    add("Capability", "Deployment validation", "⚠️ Partial" if deploy_seen else "🧑‍💻 Manual / cloud-only", "Local dashboard can validate readiness; actual deploy/health/rollback requires Azure DevOps CD and Azure Function endpoint.", "Run Azure CD pipeline and post-deploy health check.")
    add("Capability", "Evidence collection", _status(bool(report_paths)), "Markdown/JSON/ZIP evidence pack and PR comment are generated.", "Attach evidence to PR or Azure DevOps work item.")

    return rows


def render_acceptance_criteria(prefetch: dict, report: dict | None = None) -> None:
    st.subheader("Acceptance criteria checklist")
    st.caption("This tab maps the restructuring user story and DevSecOps checklist into visible pass/fail/manual-review evidence. It helps decide whether the story can be closed.")
    rows = compute_acceptance_criteria(prefetch, report)
    if not rows:
        st.info("Prefetch the repo or run the orchestrator to populate acceptance criteria.")
        return
    pass_count = sum(1 for r in rows if r["Status"].startswith("✅"))
    fail_count = sum(1 for r in rows if r["Status"].startswith("❌"))
    review_count = sum(1 for r in rows if r["Status"].startswith("⚠️") or r["Status"].startswith("🧑") or r["Status"].startswith("⏭️"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Accepted", pass_count)
    c2.metric("Failed", fail_count)
    c3.metric("Manual / review", review_count)
    c4.metric("Total criteria", len(rows))
    if fail_count:
        st.error("Do not close the story yet. One or more mandatory acceptance criteria failed.")
    elif review_count:
        st.warning("Most automated checks are complete, but some criteria still need manual/cloud confirmation before closure.")
    else:
        st.success("All tracked acceptance criteria passed. Final closure still needs PR review/approval if required by process.")
    st.dataframe(rows, use_container_width=True, height=620)
    st.markdown("### Closure rule")
    st.markdown("Close the story only after the repo structure is correct, local validation passes, pipeline/PR evidence is attached, and any cloud-only items such as Azure DevOps policy, SonarQube server scan, deployment health check, and reviewer approval are confirmed.")

def render_prefetch(prefetch: dict) -> None:
    if not prefetch:
        st.info("Paste a local repository path to prefetch repo identity and files.")
        return
    if not prefetch.get("ok"):
        st.warning(prefetch.get("message", "Unable to prefetch repository."))
        return
    gc = prefetch.get("git_context", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Files scanned", prefetch.get("total_files", 0))
    c2.metric("Python sources", prefetch.get("python_source_count", 0))
    c3.metric("Test files", prefetch.get("test_file_count", 0))
    c4.metric("Changed files", gc.get("changed_files_count", 0))
    st.markdown("### Git identity")
    st.table({
        "Field": ["Repo name", "Git root", "Branch", "HEAD", "Remote", "Provider", "Working tree clean"],
        "Value": [gc.get("repo_name", ""), gc.get("git_root", ""), gc.get("current_branch", ""), gc.get("head_commit", ""), gc.get("remote_url", ""), gc.get("remote_provider", ""), gc.get("working_tree_clean", "")],
    })
    left, right = st.columns(2)
    with left:
        st.markdown("### Config / CI/CD files found")
        st.write(prefetch.get("config_files") or "None detected")
        st.markdown("### Extension summary")
        st.json(prefetch.get("extension_counts", {}))
    with right:
        st.markdown("### Source → test precheck")
        st.dataframe(prefetch.get("source_to_test_sample", []), use_container_width=True, height=320)
    with st.expander("All prefetched files sample", expanded=False):
        st.write(prefetch.get("all_files_sample", []))


with st.sidebar:
    st.header("Repository")
    repo_path = st.text_input("Local repository path", value=os.getenv("AEGISFLOW_REPO_PATH", ""), placeholder="/mnt/c/.../your-repo")
    st.caption("Because you are in WSL, use `/mnt/c/Users/...`, not `C:\\Users\\...`.")

    # Streamlit reruns the script on every widget change. Do NOT scan the repo here.
    # Keep preflight cached and refresh it only when the user clicks a button.
    if "prefetch_data" not in st.session_state:
        st.session_state["prefetch_data"] = {}
    if "prefetch_path" not in st.session_state:
        st.session_state["prefetch_path"] = ""

    cached_prefetch = st.session_state.get("prefetch_data", {})
    cached_path = st.session_state.get("prefetch_path", "")
    path_matches_cache = bool(repo_path.strip()) and cached_path == repo_path.strip()
    prefetch_data = cached_prefetch if path_matches_cache else {}

    prefetch_clicked = st.button("🔎 Prefetch repo details", use_container_width=True, help="Scans Git identity and file inventory only when clicked. It does not modify files.")
    if prefetch_clicked:
        if not repo_path.strip():
            st.warning("Paste a local repository path first.")
        else:
            with st.spinner("Prefetching repository identity and files..."):
                prefetch_data = prefetch_repository(repo_path.strip())
                st.session_state["prefetch_data"] = prefetch_data
                st.session_state["prefetch_path"] = repo_path.strip()

    detected_git_context = prefetch_data.get("git_context") if prefetch_data.get("ok") else None
    if detected_git_context and detected_git_context.get("is_git_repo"):
        st.success("Git repo detected")
        st.markdown(f"**Repo:** `{detected_git_context.get('repo_name', '')}`")
        st.markdown(f"**Branch:** `{detected_git_context.get('current_branch', '') or 'detached'}`")
        st.markdown(f"**Remote:** `{detected_git_context.get('remote_url', '') or 'not configured'}`")
        if detected_git_context.get("git_root") != str(Path(repo_path.strip()).expanduser().resolve()):
            st.warning(f"Input is inside a repo. AegisFlow will use Git root: `{detected_git_context.get('git_root')}`")
        changed = detected_git_context.get("changed_files_count", 0)
        if changed:
            st.warning(f"Working tree already has {changed} changed file(s). Review before commit/push.")
    elif repo_path.strip():
        if prefetch_data and not prefetch_data.get("ok"):
            st.warning(prefetch_data.get("message", "Unable to prefetch repository."))
        else:
            st.info("Repo is not scanned yet. Click **Prefetch repo details** or **Run orchestrator**.")

    if prefetch_data and prefetch_data.get("ok"):
        st.caption(f"Prefetched {prefetch_data.get('total_files', 0)} files from repo root.")
        with st.expander("Prefetched repo details", expanded=False):
            st.write(f"Python sources: {prefetch_data.get('python_source_count', 0)}")
            st.write(f"Test files: {prefetch_data.get('test_file_count', 0)}")
            st.write("Config files:")
            st.write(prefetch_data.get("config_files") or [])

    expected_remote_text = st.text_input(
        "Expected repo/remote keyword",
        value="",
        placeholder="optional: gis-key-detection-func or Azure remote URL",
        help="Optional safety check. If provided, AegisFlow blocks modify/git actions unless this text appears in the detected remote URL or repo name.",
    )
    confirm_repo = st.checkbox(
        "I confirm this is the correct Git repository",
        value=False,
        help="Required before AegisFlow applies local changes, commits, pushes, or creates PRs.",
    )
    st.divider()

    st.header("Agent actions")
    generate_files = st.checkbox("Generate missing DevSecOps files", value=True)
    apply_changes = st.checkbox("Apply generated files locally", value=True)
    run_validations = st.checkbox("Run validations", value=True)
    overwrite_pipeline = st.checkbox("Overwrite existing azure-pipeline.yml", value=False)

    st.divider()
    st.header("Correction actions")
    st.caption("Automated safe corrections only. It will explain failures before risky actions.")
    install_tools = st.checkbox("Install/update validation tools + Hadolint", value=True)
    auto_fix = st.checkbox("Apply safe Ruff auto-corrections", value=True)
    auto_repair_pytest = st.checkbox("Auto-correct Pytest collection/cache issues and rerun tests", value=True, help="Cleans __pycache__/.pytest_cache/*.pyc, removes generated __init__ tests, renames duplicate generated test modules, then reruns Pytest once.")

    st.divider()
    st.header("Test generation")
    generate_tests_for_all = st.checkbox("Create missing starter tests for all Python source files", value=True)
    test_files_text = st.text_area(
        "Create missing test for these repo files",
        value="",
        placeholder="src/app.py\nsrc/utils/helpers.py",
        help="Enter one local repo file per line. Existing tests are skipped unless overwrite is selected.",
        height=90,
    )
    overwrite_tests = st.checkbox("Overwrite generated tests if already present", value=False)

    st.divider()
    st.header("SonarQube quality gate")
    run_sonar = st.checkbox("Run SonarQube/SonarCloud scan with coverage", value=True)
    sonar_host_url = st.text_input("SONAR_HOST_URL", value=os.getenv("SONAR_HOST_URL", ""), placeholder="https://sonarqube.company.com or https://sonarcloud.io")
    sonar_token = st.text_input("SONAR_TOKEN", value=os.getenv("SONAR_TOKEN", ""), type="password", help="Use a Sonar token. It is masked in the UI and logs.")
    sonar_project_key = st.text_input("Sonar project key", value=os.getenv("SONAR_PROJECT_KEY", ""), placeholder="Default: detected repo name")
    sonar_quality_gate_wait = st.checkbox("Wait for Sonar quality gate", value=True)
    auto_install_sonar_scanner = st.checkbox("Install SonarScanner CLI automatically if missing", value=True)
    st.caption("AegisFlow first creates coverage.xml from Pytest, then runs SonarScanner to upload coverage and check the quality gate. If host/token are missing, it skips with a clear message.")

    st.divider()
    st.header("AI Fix Plan")
    generate_fix_plan = st.checkbox("Generate reviewable fix plan with exact diffs", value=True, help="Creates proposed safe patches. It does not apply them until you approve from the AI Fix Plan tab.")
    st.caption("Flow: detect failure → propose file diff → approve → apply patch → rerun affected validation.")

    st.divider()
    st.header("Local AI")
    use_llm = st.checkbox("Use local Ollama recommendation", value=True)
    install_ollama = st.checkbox("Install Ollama automatically if missing", value=True)
    model = st.text_input("Ollama model", value="qwen2.5-coder:7b")
    st.caption("If Ollama CLI or the model is missing, AegisFlow will try to install Ollama and run `ollama pull` automatically. First model download can take several minutes.")

    st.divider()
    st.header("Git automation")
    branch = st.text_input("Branch name", value="orchestrator/devsecops-ready")
    do_branch = st.checkbox("Create/switch branch", value=True)
    do_commit = st.checkbox("Commit changes", value=True)
    do_push = st.checkbox("Push branch", value=True)
    remote = st.text_input("Remote", value="origin")
    create_pr = st.checkbox("Create Azure DevOps PR", value=True)
    target_branch = st.text_input("Target branch", value="main")
    allow_git_on_failure = st.checkbox("Override safety gate: allow git actions even if validations fail", value=False)
    st.caption("AutoPilot defaults are enabled, but AegisFlow still requires repo confirmation and blocks commit/push/PR if validations fail unless override is enabled.")

run = st.button("🚀 Run orchestrator", type="primary", use_container_width=False)

tab_repo, tab_acceptance, tab_progress, tab_report, tab_ai, tab_fix, tab_chat, tab_sonar, tab_governance, tab_pr, tab_use_cases = st.tabs([
    "Repo Preflight", "Acceptance Criteria", "Live Progress", "Report & Downloads", "AI Error Intelligence", "AI Fix Plan", "Aegis Chat", "SonarQube", "Governance", "PR Comment", "Industry Use Cases"
])

with tab_repo:
    st.subheader("Repository preflight")
    st.caption("AegisFlow prefetches repo identity, file inventory, CI/CD controls, changed files, and source/test mapping before running.")
    render_prefetch(prefetch_data if repo_path.strip() else {})

with tab_acceptance:
    render_acceptance_criteria(prefetch_data if repo_path.strip() else {}, st.session_state.get("last_report"))

with tab_use_cases:
    st.markdown(Path(__file__).with_name("docs").joinpath("use_cases.md").read_text(encoding="utf-8"))

if run:
    if not repo_path.strip():
        st.error("Please provide a local repository path.")
        st.stop()

    # Run button is the only place where full preflight + orchestration are executed.
    with st.spinner("Running repository preflight before orchestration..."):
        run_prefetch_data = prefetch_repository(repo_path.strip())
        st.session_state["prefetch_data"] = run_prefetch_data
        st.session_state["prefetch_path"] = repo_path.strip()
    current_git_context = run_prefetch_data.get("git_context", {}) if run_prefetch_data.get("ok") else get_git_context(repo_path.strip())
    modify_or_git_action = any([apply_changes, do_branch, do_commit, do_push, create_pr])
    if modify_or_git_action and not confirm_repo:
        st.error("Safety gate: confirm the detected Git repository before applying changes, creating branches, committing, pushing, or creating PRs.")
        st.stop()
    if expected_remote_text.strip() and current_git_context.get("is_git_repo"):
        expected = expected_remote_text.strip().lower()
        haystack = " ".join([
            current_git_context.get("remote_url", ""),
            current_git_context.get("repo_name", ""),
            current_git_context.get("git_root", ""),
        ]).lower()
        if expected not in haystack:
            st.error(f"Safety gate: expected repo/remote keyword `{expected_remote_text}` was not found in detected repo/remote. Detected remote: `{current_git_context.get('remote_url', '')}`")
            st.stop()

    progress_box = tab_progress.container()
    progress_box.subheader("CI/CD execution timeline")
    progress_box.caption("AegisFlow tells you exactly what it is doing, why it is running each check, and what failed. Long-running commands send heartbeat updates so the dashboard does not look stuck.")

    status_placeholder = progress_box.empty()
    progress_placeholder = progress_box.empty()
    command_placeholder = progress_box.empty()
    log_placeholder = progress_box.empty()
    timeline_placeholder = progress_box.container()

    progress_bar = progress_placeholder.progress(0, text="Waiting to start...")
    events: list[dict] = []
    progress_state = {"last_pct": 0, "event_count": 0}

    def callback(event: Event) -> None:
        events.append(event.to_dict())
        progress_state["event_count"] += 1
        icon = {"ok": "✅", "fail": "❌", "skip": "⏭️", "running": "🔄", "warn": "⚠️"}.get(event.status, "•")

        # Show current step prominently at the top of Live Progress.
        status_text = f"{icon} **[{event.category}] {event.step}** — {event.message}"
        if event.status == "fail":
            status_placeholder.error(status_text)
        elif event.status == "ok":
            status_placeholder.success(status_text)
        elif event.status == "warn":
            status_placeholder.warning(status_text)
        else:
            status_placeholder.info(status_text)

        # Prefer real command progress when the agent provides it; otherwise move slowly by event count.
        if event.progress_pct is not None:
            pct = max(0, min(100, int(event.progress_pct)))
        else:
            pct = min(98, progress_state["last_pct"] + (2 if event.status == "running" else 5))
            if event.status in {"ok", "fail", "skip"}:
                pct = max(pct, min(98, progress_state["last_pct"] + 4))
        progress_state["last_pct"] = max(progress_state["last_pct"], pct)
        elapsed = f" • elapsed {event.elapsed_seconds}s" if event.elapsed_seconds is not None else ""
        progress_bar.progress(progress_state["last_pct"], text=f"Current step progress: {progress_state['last_pct']}%{elapsed}")

        if event.command:
            command_placeholder.code(event.command, language="bash")
        if event.output_tail:
            log_placeholder.code(event.output_tail[-2500:], language="text")

        timeline_placeholder.markdown(
            f'<div class="stage-card">{icon} <b>[{event.category}] {event.step}</b><br><span class="small-muted">{event.message}</span></div>',
            unsafe_allow_html=True,
        )

    try:
        agent = OrchestratorAgent(repo_path, callback=callback)
        report = agent.run(
            generate_files=generate_files,
            apply=apply_changes,
            run_validations=run_validations,
            overwrite_pipeline=overwrite_pipeline,
            branch=branch if do_branch else None,
            commit=do_commit,
            push=do_push,
            remote=remote,
            create_pr=create_pr,
            target_branch=target_branch,
            llm=use_llm,
            model=model,
            install_ollama=install_ollama,
            install_tools=install_tools,
            auto_fix=auto_fix,
            generate_tests_for=[line.strip() for line in test_files_text.replace(",", "\n").splitlines() if line.strip()],
            generate_tests_for_all=generate_tests_for_all,
            overwrite_tests=overwrite_tests,
            allow_git_on_failure=allow_git_on_failure,
            auto_repair_pytest=auto_repair_pytest,
            generate_ai_fix_plan=generate_fix_plan,
            run_sonar=run_sonar,
            sonar_host_url=sonar_host_url,
            sonar_token=sonar_token,
            sonar_project_key=sonar_project_key,
            sonar_quality_gate_wait=sonar_quality_gate_wait,
            auto_install_sonar_scanner=auto_install_sonar_scanner,
        )
    except Exception as exc:
        st.exception(exc)
        st.stop()

    st.session_state["last_report"] = report
    progress_bar.progress(100, text="Orchestration finished. Reports and evidence pack are ready.")
    status_placeholder.success("✅ **[summary] Orchestration finished** — Reports and evidence pack are ready.")
    st.session_state["last_decision"] = report.get("governance_decision", {}).get("decision", "not_evaluated")

    with tab_progress:
        st.subheader("CI/CD cockpit")
        render_metric_cards(report.get("summary", {}))
        failed = [v for v in report.get("validation_results", []) if v.get("status") == "fail"]
        if failed:
            st.error("Some checks failed. Open AI Error Intelligence for exact failure, owner, and fix.")
            for v in failed:
                st.markdown(f"- **{v['name']}** → `{v['classification']}`")
        else:
            st.success("No failed validation checks detected. Review skipped checks before production use.")

    with tab_report:
        st.subheader("Summary")
        render_metric_cards(report.get("summary", {}))

        st.subheader("Detected Git repository")
        gc = report.get("git_context", {})
        if gc.get("is_git_repo"):
            st.table({
                "Field": ["Repo name", "Git root", "Current branch", "HEAD", "Remote", "Provider", "Changed files before run"],
                "Value": [gc.get("repo_name", ""), gc.get("git_root", ""), gc.get("current_branch", ""), gc.get("head_commit", ""), gc.get("remote_url", ""), gc.get("remote_provider", ""), gc.get("changed_files_count", 0)],
            })
        else:
            st.warning("No Git repository detected for this path.")

        st.subheader("Detected project")
        st.write(", ".join(report["inspection"]["project_type"]))

        st.subheader("Generated files")
        st.write(report.get("generated_files") or "None")

        st.subheader("Generated test files")
        st.write(report.get("generated_tests") or "None")

        if report.get("correction_results"):
            st.subheader("Correction results")
            st.dataframe([
                {
                    "status": v["status"],
                    "correction": v["name"],
                    "category": v["category"],
                    "classification": v["classification"],
                }
                for v in report.get("correction_results", [])
            ], use_container_width=True)

        st.subheader("Validation results")
        rows = []
        for v in report.get("validation_results", []):
            rows.append({
                "status": v["status"],
                "validation": v["name"],
                "category": v["category"],
                "classification": v["classification"],
            })
        st.dataframe(rows, use_container_width=True)

        render_evidence_dashboard(report)

        st.subheader("Report files")
        paths = report.get("report_paths", {})
        st.json(paths)

        if report.get("pull_request_url"):
            st.success(f"Pull Request created: {report['pull_request_url']}")

        if report.get("llm_recommendation"):
            st.subheader("Local LLM recommendation")
            st.markdown(report["llm_recommendation"])

        with st.expander("Full JSON report"):
            st.code(json.dumps(report, indent=2), language="json")

    with tab_ai:
        st.subheader("Error explanations and common fixes")
        analysis = report.get("failure_analysis", {})
        st.write(analysis.get("overall_status", "not available"))
        for item in analysis.get("items", []):
            if item.get("status") in {"fail", "skip"}:
                symbol = "❌" if item.get("status") == "fail" else "⏭️"
                with st.expander(f"{symbol} {item['name']} — {item['classification']}", expanded=item.get("status") == "fail"):
                    st.markdown(f"**Severity:** {item['severity']}  ")
                    st.markdown(f"**Suggested owner:** {item['owner']}  ")
                    st.markdown(f"**Explanation:** {item['explanation']}")
                    st.markdown("**Common fixes:**")
                    for fix in item.get("common_fixes", []):
                        st.markdown(f"- {fix}")
                    if item.get("evidence_tail"):
                        st.code(item["evidence_tail"], language="text")
        st.subheader("Log summary")
        st.json(report.get("log_summary", {}))


    with tab_sonar:
        st.subheader("SonarQube / SonarCloud cockpit")
        st.caption("Azure DevOps Code Coverage and SonarQube are different views. Code Coverage shows coverage.xml inside Azure DevOps. SonarQube requires SONAR_HOST_URL + SONAR_TOKEN and then publishes coverage, issues, smells, duplication, security hotspots, and the quality gate to SonarQube/SonarCloud.")

        sonar_results = [v for v in report.get("validation_results", []) if v.get("category") == "sonar" or "sonar" in v.get("name", "").lower()]
        sonar_events = [e for e in report.get("events", []) if e.get("category") == "sonar" or "sonar" in e.get("step", "").lower()]

        if not sonar_results and not sonar_events:
            st.warning("No SonarQube step was executed in this run. Enable **Run SonarQube/SonarCloud scan with coverage** in the sidebar, then provide SONAR_HOST_URL and SONAR_TOKEN.")
        else:
            counts = {"ok": 0, "fail": 0, "skip": 0, "warn": 0, "running": 0}
            for item in sonar_results:
                counts[item.get("status", "skip")] = counts.get(item.get("status", "skip"), 0) + 1
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sonar passed", counts.get("ok", 0))
            c2.metric("Sonar failed", counts.get("fail", 0))
            c3.metric("Sonar skipped", counts.get("skip", 0))
            c4.metric("Sonar events", len(sonar_events))

            st.markdown("### Sonar validation results")
            if sonar_results:
                st.dataframe([
                    {
                        "status": v.get("status"),
                        "step": v.get("name"),
                        "classification": v.get("classification"),
                        "message": v.get("message", ""),
                    }
                    for v in sonar_results
                ], use_container_width=True)
            else:
                st.info("Sonar events were found, but no final Sonar validation result was recorded.")

            st.markdown("### Sonar execution log")
            for e in sonar_events[-12:]:
                icon = {"ok": "✅", "fail": "❌", "skip": "⏭️", "running": "🔄", "warn": "⚠️"}.get(e.get("status"), "•")
                with st.expander(f"{icon} {e.get('step', '')} — {e.get('status', '')}", expanded=e.get("status") in {"fail", "skip", "warn"}):
                    st.write(e.get("message", ""))
                    if e.get("command"):
                        st.code(e.get("command"), language="bash")
                    if e.get("output_tail"):
                        st.code(e.get("output_tail"), language="text")

        st.markdown("### What you should see where")
        st.markdown("""
- **Azure DevOps → Code Coverage tab:** only shows the Cobertura/Pytest coverage report, like your second screenshot.
- **AegisFlow → SonarQube tab:** shows whether the Sonar scanner ran, skipped, passed, or failed.
- **SonarQube/SonarCloud dashboard:** shows bugs, vulnerabilities, code smells, duplication, coverage trend, and quality gate after a real scan.
- **Azure DevOps PR:** shows Sonar status only if the Azure DevOps Sonar extension/service connection or AegisFlow PR comment integration posts it.
""")
        st.markdown("### Required settings")
        st.code("""export SONAR_HOST_URL=\"https://your-sonarqube-server\"
export SONAR_TOKEN=\"your-sonar-token\"
export SONAR_PROJECT_KEY=\"gis-key-detection-func\"  # optional""", language="bash")

    with tab_governance:
        st.subheader("Production / governance decision support")
        gd = report.get("governance_decision", {})
        decision = gd.get("decision", "not_evaluated")
        if decision == "blocked":
            st.error("Production deployment support decision: BLOCKED")
        elif decision == "conditional_review":
            st.warning("Production deployment support decision: CONDITIONAL REVIEW")
        else:
            st.success("Production deployment support decision: READY FOR HUMAN APPROVAL")
        st.markdown(gd.get("rule", ""))
        if gd.get("blockers"):
            st.markdown("### Blockers")
            for b in gd["blockers"]:
                st.markdown(f"- ❌ {b}")
        if gd.get("warnings"):
            st.markdown("### Warnings")
            for w in gd["warnings"]:
                st.markdown(f"- ⚠️ {w}")
        st.markdown("### Sign-off matrix")
        st.dataframe(gd.get("signoff_matrix", []), use_container_width=True)

    with tab_pr:
        st.subheader("Generated PR comment")
        st.markdown(report.get("pr_comment", ""))
        st.code(report.get("pr_comment", ""), language="markdown")


# Persistent AI Fix Plan tab. This remains available after the Streamlit rerun caused by clicking an approval button.
report_for_fix = st.session_state.get("last_report")
with tab_fix:
    st.subheader("AI Fix Plan: review → approve → apply → rerun")
    st.caption("AegisFlow does not silently edit risky files. It shows exact file diffs first, waits for your approval, applies only safe proposed patches, and reruns affected checks.")
    if not report_for_fix:
        st.info("Run the orchestrator first to generate a fix plan from validation results.")
    else:
        plan = report_for_fix.get("ai_fix_plan") or {}
        if not plan:
            st.warning("No AI fix plan was generated for the last run. Enable 'Generate reviewable fix plan with exact diffs' and rerun.")
        else:
            st.markdown(f"**Plan status:** `{plan.get('status', 'unknown')}`")
            st.markdown(plan.get("summary", ""))
            proposed = [i for i in plan.get("items", []) if i.get("status") == "proposed" and i.get("safe_to_apply")]
            non_auto = plan.get("non_auto_fixable", [])

            if proposed:
                st.success(f"{len(proposed)} safe proposed patch(es) are ready for review.")
                for idx, item in enumerate(proposed, start=1):
                    with st.expander(f"Patch {idx}: {item.get('file')} — {item.get('tool', 'deterministic fix')}", expanded=True):
                        st.markdown(item.get("explanation", ""))
                        findings = item.get("patched_findings") or item.get("findings") or []
                        if findings:
                            st.markdown("**Hadolint findings used for this patch:**")
                            for f in findings[:20]:
                                st.markdown(f"- `{f.get('rule')}` line `{f.get('line')}` — {f.get('message')}")
                        st.markdown("**Exact proposed file diff:**")
                        st.code(item.get("diff", "No diff"), language="diff")
                        if item.get("unsafe_findings_remaining"):
                            st.warning("Some Hadolint findings remain review-only because they are not safe to auto-edit deterministically.")
                            st.json(item.get("unsafe_findings_remaining"))

                approve_fix = st.checkbox("I reviewed the diff and approve applying the safe proposed patch(es)", value=False, key="approve_ai_fix_plan")
                apply_clicked = st.button("✅ Apply approved fix plan and rerun affected validation", disabled=not approve_fix, type="primary")
                if apply_clicked:
                    with st.spinner("Applying approved patches and rerunning affected checks..."):
                        apply_events: list[dict] = []
                        def fix_callback(event: Event) -> None:
                            apply_events.append(event.to_dict())
                        result = apply_fix_plan_and_rerun(report_for_fix.get("repo", repo_path), plan, callback=fix_callback)
                        st.session_state["last_fix_apply_result"] = result
                    st.success("Approved fix plan applied. Review before/after result below.")

            else:
                st.info("No safe file patch is available to apply automatically from the last run.")

            if non_auto:
                st.markdown("### Review-only items")
                st.caption("These are not auto-applied because they may require product-code, test-expectation, dependency, security, or architecture decisions.")
                st.json(non_auto)

            result = st.session_state.get("last_fix_apply_result")
            if result:
                st.markdown("### Before/after apply result")
                st.markdown("**Applied patches**")
                st.json(result.get("applied", []))
                if result.get("skipped"):
                    st.markdown("**Skipped patches**")
                    st.json(result.get("skipped", []))
                st.markdown("**Validation after patch**")
                rows = []
                for v in result.get("validation_after", []):
                    rows.append({"status": v.get("status"), "check": v.get("name"), "classification": v.get("classification"), "return_code": v.get("return_code")})
                if rows:
                    st.dataframe(rows, use_container_width=True)
                    for v in result.get("validation_after", []):
                        with st.expander(f"{v.get('name')} raw output", expanded=v.get("status") == "fail"):
                            st.code(v.get("details") or "", language="text")
                else:
                    st.info("No affected validation was rerun, or no safe patch was applied.")


with tab_chat:
    st.subheader("Aegis Chat: ask about this run")
    st.caption("Ask what failed, why it failed, whether AegisFlow can fix it, or which approval/action is needed next. It uses Ollama if available and falls back to deterministic run-context answers.")
    chat_report = st.session_state.get("last_report")
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    for m in st.session_state["chat_history"][-8:]:
        with st.chat_message(m.get("role", "assistant")):
            st.markdown(m.get("content", ""))
    user_q = st.chat_input("Ask AegisFlow about Dockerfile, Pytest, Ollama, PR readiness, or the fix plan...")
    if user_q:
        st.session_state["chat_history"].append({"role": "user", "content": user_q})
        with st.chat_message("user"):
            st.markdown(user_q)
        ans = aegisflow_chat_answer(user_q, chat_report, model)
        st.session_state["chat_history"].append({"role": "assistant", "content": ans})
        with st.chat_message("assistant"):
            st.markdown(ans)



def render_persistent_run_results(report: dict) -> None:
    """Render the last completed run after Streamlit reruns from tab switches/downloads/widgets.

    Streamlit reruns the script on most interactions. The orchestrator result is stored in
    st.session_state['last_report']; this renderer rehydrates every tab from that stored JSON
    so results do not disappear when the user changes tabs or downloads reports.
    """
    if not report:
        return

    with tab_progress:
        st.subheader("CI/CD execution timeline")
        st.caption("Showing the last completed run from session state. Click **Run orchestrator** to execute again.")
        render_metric_cards(report.get("summary", {}))
        events = report.get("events", []) or []
        if events:
            st.success("Last run is loaded. Results remain visible while you switch tabs or download reports.")
            for e in events[-80:]:
                icon = {"ok": "✅", "fail": "❌", "skip": "⏭️", "running": "🔄", "warn": "⚠️"}.get(e.get("status"), "•")
                with st.expander(f"{icon} [{e.get('category','')}] {e.get('step','')} — {e.get('status','')}", expanded=e.get("status") == "fail"):
                    st.write(e.get("message", ""))
                    if e.get("command"):
                        st.code(e.get("command"), language="bash")
                    if e.get("output_tail"):
                        st.code(e.get("output_tail"), language="text")
        else:
            st.info("No event timeline was saved in the last report.")

    with tab_report:
        st.subheader("Summary")
        render_metric_cards(report.get("summary", {}))
        st.info("This tab is restored from the last run. It will not vanish when you switch tabs or click a download button.")

        st.subheader("Where results show")
        st.markdown("""
| Result | Where it appears |
|---|---|
| Pytest/Cobertura coverage | **Azure DevOps → Pipeline run → Code Coverage tab** |
| Test results | **Azure DevOps → Pipeline run → Tests tab** and AegisFlow evidence pack |
| Sonar scan / Quality Gate | **AegisFlow → SonarQube tab** and the external SonarQube/SonarCloud dashboard, if SONAR credentials are configured |
| Evidence pack | **AegisFlow → Report & Downloads** and `orchestrator_reports/` |
""")

        st.subheader("Validation results")
        rows = []
        for v in report.get("validation_results", []):
            rows.append({
                "status": v.get("status"),
                "validation": v.get("name"),
                "category": v.get("category"),
                "classification": v.get("classification"),
            })
        if rows:
            st.dataframe(rows, use_container_width=True)

        render_evidence_dashboard(report)

        with st.expander("Full JSON report", expanded=False):
            st.code(json.dumps(report, indent=2), language="json")

    with tab_ai:
        st.subheader("Error explanations and common fixes")
        analysis = report.get("failure_analysis", {}) or {}
        st.write(analysis.get("overall_status", "not available"))
        items = analysis.get("items", []) or []
        if not items:
            st.info("No failure intelligence items were saved for the last run.")
        for item in items:
            if item.get("status") in {"fail", "skip", "warn"}:
                symbol = "❌" if item.get("status") == "fail" else "⏭️"
                with st.expander(f"{symbol} {item.get('name')} — {item.get('classification')}", expanded=item.get("status") == "fail"):
                    st.markdown(f"**Severity:** {item.get('severity')}  ")
                    st.markdown(f"**Suggested owner:** {item.get('owner')}  ")
                    st.markdown(f"**Explanation:** {item.get('explanation')}")
                    st.markdown("**Common fixes:**")
                    for fix in item.get("common_fixes", []) or []:
                        st.markdown(f"- {fix}")
                    if item.get("evidence_tail"):
                        st.code(item.get("evidence_tail"), language="text")
        st.subheader("Log summary")
        st.json(report.get("log_summary", {}))

    with tab_sonar:
        st.subheader("SonarQube / SonarCloud cockpit")
        st.caption("This is separate from Azure DevOps Code Coverage. Azure Code Coverage is created by pytest → coverage.xml → PublishCodeCoverageResults. SonarQube appears here and in the Sonar server only if the Sonar scan runs with host/token.")
        sonar_results = [v for v in report.get("validation_results", []) if v.get("category") == "sonar" or "sonar" in v.get("name", "").lower()]
        sonar_events = [e for e in report.get("events", []) if e.get("category") == "sonar" or "sonar" in e.get("step", "").lower()]
        if not sonar_results and not sonar_events:
            st.warning("No SonarQube step was executed in the last run. Enable the Sonar scan and provide SONAR_HOST_URL + SONAR_TOKEN.")
        else:
            counts = {"ok": 0, "fail": 0, "skip": 0, "warn": 0, "running": 0}
            for item in sonar_results:
                counts[item.get("status", "skip")] = counts.get(item.get("status", "skip"), 0) + 1
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sonar passed", counts.get("ok", 0))
            c2.metric("Sonar failed", counts.get("fail", 0))
            c3.metric("Sonar skipped", counts.get("skip", 0))
            c4.metric("Sonar events", len(sonar_events))
            if sonar_results:
                st.dataframe([
                    {"status": v.get("status"), "step": v.get("name"), "classification": v.get("classification"), "message": v.get("message", "")}
                    for v in sonar_results
                ], use_container_width=True)
            for e in sonar_events[-12:]:
                icon = {"ok": "✅", "fail": "❌", "skip": "⏭️", "running": "🔄", "warn": "⚠️"}.get(e.get("status"), "•")
                with st.expander(f"{icon} {e.get('step','')} — {e.get('status','')}", expanded=e.get("status") in {"fail", "skip", "warn"}):
                    st.write(e.get("message", ""))
                    if e.get("command"):
                        st.code(e.get("command"), language="bash")
                    if e.get("output_tail"):
                        st.code(e.get("output_tail"), language="text")

        st.markdown("### Azure DevOps Code Coverage vs SonarQube")
        st.markdown("""
- The screenshot with **99% line coverage** is **Azure DevOps → Pipeline run → Code Coverage**.
- SonarQube will show in the **SonarQube tab** only when the scanner actually runs.
- External Sonar results will show in your company **SonarQube/SonarCloud dashboard**.
""")

    with tab_governance:
        st.subheader("Production / governance decision support")
        gd = report.get("governance_decision", {}) or {}
        decision = gd.get("decision", "not_evaluated")
        if decision == "blocked":
            st.error("Production deployment support decision: BLOCKED")
        elif decision == "conditional_review":
            st.warning("Production deployment support decision: CONDITIONAL REVIEW")
        else:
            st.success("Production deployment support decision: READY FOR HUMAN APPROVAL")
        st.markdown(gd.get("rule", ""))
        if gd.get("blockers"):
            st.markdown("### Blockers")
            for b in gd["blockers"]:
                st.markdown(f"- ❌ {b}")
        if gd.get("warnings"):
            st.markdown("### Warnings")
            for w in gd["warnings"]:
                st.markdown(f"- ⚠️ {w}")
        st.markdown("### Sign-off matrix")
        st.dataframe(gd.get("signoff_matrix", []), use_container_width=True)

    with tab_pr:
        st.subheader("Generated PR comment")
        st.markdown(report.get("pr_comment", ""))
        st.code(report.get("pr_comment", ""), language="markdown")


# Keep the completed run visible after Streamlit reruns caused by tab switching,
# download buttons, chat input, sidebar edits, or normal refreshes.
if not run and st.session_state.get("last_report"):
    render_persistent_run_results(st.session_state["last_report"])

