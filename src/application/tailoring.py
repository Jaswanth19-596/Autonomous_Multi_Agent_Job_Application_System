"""Grounded LaTeX resume tailoring and cover-letter generation."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MASTER_RESUME = ROOT / "user_details" / "master_resume.tex"
TAILORED_DIR = ROOT / "user_details" / "tailored"
PROJECTS_DIR = ROOT / "user_details" / "projects"
RESUME_TAILORING_PROMPT = ROOT / "prompts" / "resume_tailoring_systemprompt.md"


class TailoringError(ValueError):
    """Raised when a tailored LaTeX artifact cannot be safely produced."""


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "application"


def _latex_from_response(raw: str) -> str:
    fenced = re.search(r"```latex\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
    source = (fenced.group(1) if fenced else raw).strip()
    if not source.startswith("\\documentclass") or not source.endswith("\\end{document}"):
        raise TailoringError("The tailoring model did not return one complete LaTeX document.")
    if "[INSERT " in source or "TODO" in source:
        raise TailoringError("The generated LaTeX still contains an unresolved placeholder.")
    return source + "\n"


def validate_latex(source: str) -> None:
    """Catch structural errors before invoking a compiler."""
    if source.count("\\begin{document}") != 1 or source.count("\\end{document}") != 1:
        raise TailoringError("The generated source must contain exactly one document body.")
    if source.count("{") != source.count("}"):
        raise TailoringError("The generated source has unbalanced braces.")
    # Dynamic shell/input primitives would undermine reproducible local builds.
    if re.search(r"\\(?:input|include|write18|openout)\b", source):
        raise TailoringError("The generated source contains a disallowed external-file or shell command.")


def _find_latex_command(name: str) -> str | None:
    """Find TeX binaries even when a long-running macOS app has a stale PATH."""
    if resolved := shutil.which(name):
        return resolved
    candidates = [Path("/Library/TeX/texbin") / name]
    texlive = Path("/usr/local/texlive")
    if texlive.exists():
        candidates.extend(texlive.glob(f"*/bin/universal-darwin/{name}"))
    return next((str(path) for path in candidates if path.is_file() and os.access(path, os.X_OK)), None)


def _load_resume_tailoring_prompt(path: Path = RESUME_TAILORING_PROMPT) -> str:
    """Load the editable resume-tailoring instructions for each request."""
    try:
        prompt = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise TailoringError(f"Could not read the resume-tailoring prompt at {path}: {exc}") from exc
    if not prompt:
        raise TailoringError(f"The resume-tailoring prompt at {path} is empty.")
    return prompt


def _load_project_catalog(projects_dir: Path = PROJECTS_DIR) -> str:
    """Return every project file as a clearly delimited model input.

    Project selection belongs to the tailoring model, so the catalog is neither
    ranked nor filtered here. Empty files are retained as catalog entries so a
    missing description is visible instead of silently excluding a project.
    """
    if not projects_dir.is_dir():
        raise TailoringError(f"No projects directory found at {projects_dir}.")

    project_files = sorted(
        path for path in projects_dir.iterdir() if path.is_file() and not path.name.startswith(".")
    )
    if not project_files:
        raise TailoringError(f"No project files found in {projects_dir}.")

    entries = []
    for path in project_files:
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise TailoringError(f"Could not read project file {path}: {exc}") from exc
        entries.append(
            f"--- PROJECT FILE: {path.name} ---\n"
            f"{content or '[No project description was supplied in this file.]'}\n"
            "--- END PROJECT FILE ---"
        )
    return "\n\n".join(entries)


async def request_latex(
    *,
    document_kind: str,
    master_resume: str,
    job_description: str,
    company: str,
    title: str,
    project_catalog: str | None = None,
) -> str:
    """Request a complete, compile-ready tailored LaTeX document."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openrouter import ChatOpenRouter

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise TailoringError("OPENROUTER_API_KEY is required to create tailored documents.")
    model_name = os.environ.get("OPENROUTER_TAILORING_MODEL") or os.environ.get("OPENROUTER_MODEL")
    if not model_name:
        raise TailoringError("Set OPENROUTER_TAILORING_MODEL to the high-quality model for document tailoring.")
    model = ChatOpenRouter(model=model_name, api_key=api_key)
    if document_kind == "resume":
        if not project_catalog:
            raise TailoringError("A complete project catalog is required for resume tailoring.")
        system = _load_resume_tailoring_prompt()
        projects_section = f"""
PROJECT CATALOG — REVIEW EVERY ENTRY BEFORE SELECTING PROJECTS:
{project_catalog}
"""
    else:
        system = """You are an expert cover-letter writer and LaTeX code generator. Write a one-page tailored cover letter grounded solely in MASTER RESUME. Use a clean conventional LaTeX layout with hyperref for URLs if needed. Do not invent metrics, tools, dates, employers, projects, responsibilities, certifications, or experience. Escape LaTeX special characters in ordinary text. Return only one raw, compile-ready LaTeX document inside an optional ```latex code block. It must start with \\documentclass and end with \\end{document}. Do not include explanation, Markdown outside the optional code block, placeholders, shell escape commands, \\input, or \\include."""
        projects_section = ""
    prompt = f"""Document type: {document_kind}
Company: {company}
Target role: {title}

TARGET JOB DESCRIPTION:
{job_description}

MASTER RESUME LATEX:
{master_resume}

{projects_section}
"""
    response = await model.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)])
    source = _latex_from_response(str(response.content))
    validate_latex(source)
    return source


async def repair_latex(*, source: str, compiler_error: str) -> str:
    """Repair compiler errors without changing the documented candidate facts."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openrouter import ChatOpenRouter

    api_key = os.environ.get("OPENROUTER_API_KEY")
    model_name = os.environ.get("OPENROUTER_TAILORING_MODEL") or os.environ.get("OPENROUTER_MODEL")
    if not api_key or not model_name:
        raise TailoringError("A configured tailoring model is required to repair generated LaTeX.")
    model = ChatOpenRouter(model=model_name, api_key=api_key)
    instruction = """Return only corrected, complete LaTeX source in an optional ```latex code block. Fix the supplied compiler error with the smallest possible source change. Preserve all candidate facts, dates, employers, job titles, metrics, text content, page geometry, and document structure. Do not add external-file commands, shell commands, or placeholders."""
    response = await model.ainvoke(
        [
            SystemMessage(content=instruction),
            HumanMessage(content=f"COMPILER ERROR:\n{compiler_error}\n\nLATEX SOURCE:\n{source}"),
        ]
    )
    repaired = _latex_from_response(str(response.content))
    validate_latex(repaired)
    return repaired


def _repair_known_presentation_error(source: str, compiler_error: str) -> str | None:
    """Apply a safe, fact-preserving fix for a common generated color token."""
    if (
        "Undefined color `PRIMARY'" in compiler_error
        and "\\definecolor{PRIMARY}" not in source
        and "\\usepackage{xcolor}" in source
    ):
        return source.replace(
            "\\usepackage{xcolor}",
            "\\usepackage{xcolor}\n\\definecolor{PRIMARY}{HTML}{1F4E79}",
            1,
        )
    return None


def compile_latex(tex_path: Path) -> Path:
    """Compile a self-contained document with an available local LaTeX engine."""
    output_dir = tex_path.parent
    tectonic = _find_latex_command("tectonic")
    latexmk = _find_latex_command("latexmk")
    pdflatex = _find_latex_command("pdflatex")
    # Tectonic downloads only the packages each generated resume needs into a
    # user cache, avoiding manual tlmgr administration of BasicTeX.
    if tectonic:
        command = [tectonic, "--outdir", str(output_dir), str(tex_path)]
    elif latexmk:
        command = [latexmk, "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-outdir=" + str(output_dir), str(tex_path)]
    elif pdflatex:
        command = [pdflatex, "-interaction=nonstopmode", "-halt-on-error", "-output-directory", str(output_dir), str(tex_path)]
    else:
        raise TailoringError("No LaTeX compiler found. Install Tectonic to produce PDFs automatically.")
    result = subprocess.run(command, cwd=output_dir, capture_output=True, text=True, timeout=90)
    pdf_path = tex_path.with_suffix(".pdf")
    if result.returncode != 0 or not pdf_path.exists():
        error = (result.stdout + "\n" + result.stderr).strip()[-1600:]
        raise TailoringError(f"LaTeX compilation failed:\n{error}")
    return pdf_path


@dataclass(frozen=True)
class TailoredDocuments:
    resume_tex: Path
    resume_pdf: Path
    cover_letter_tex: Path | None
    cover_letter_pdf: Path | None


async def _write_and_compile_with_repairs(tex_path: Path, source: str) -> Path:
    """Compile and let the tailoring model repair up to two syntax/package errors."""
    latest = source
    for attempt in range(3):
        tex_path.write_text(latest, encoding="utf-8")
        try:
            return compile_latex(tex_path)
        except TailoringError as exc:
            if attempt == 2 or "LaTeX compilation failed" not in str(exc):
                raise
            latest = _repair_known_presentation_error(latest, str(exc)) or await repair_latex(
                source=latest, compiler_error=str(exc)
            )
    raise AssertionError("unreachable")


async def tailor_documents(
    *,
    job_description: str,
    company: str,
    title: str,
    include_cover_letter: bool = False,
    master_path: Path = MASTER_RESUME,
) -> TailoredDocuments:
    if not master_path.exists():
        raise TailoringError(
            f"No LaTeX master resume found at {master_path}. Add a self-contained master_resume.tex; PDFs are not modified."
        )
    master_resume = master_path.read_text(encoding="utf-8")
    validate_latex(master_resume)
    project_catalog = _load_project_catalog()
    stem = f"{_safe_filename(company)}_{_safe_filename(title)}"
    TAILORED_DIR.mkdir(parents=True, exist_ok=True)

    resume_tex = TAILORED_DIR / f"{stem}_resume.tex"
    resume_source = await request_latex(
        document_kind="resume",
        master_resume=master_resume,
        job_description=job_description,
        company=company,
        title=title,
        project_catalog=project_catalog,
    )
    resume_pdf = await _write_and_compile_with_repairs(resume_tex, resume_source)

    cover_tex = cover_pdf = None
    if include_cover_letter:
        cover_tex = TAILORED_DIR / f"{stem}_cover_letter.tex"
        cover_source = await request_latex(
            document_kind="cover_letter",
            master_resume=master_resume,
            job_description=job_description,
            company=company,
            title=title,
        )
        cover_pdf = await _write_and_compile_with_repairs(cover_tex, cover_source)
    return TailoredDocuments(resume_tex, resume_pdf, cover_tex, cover_pdf)
