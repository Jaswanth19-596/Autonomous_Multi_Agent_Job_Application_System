import pytest

from src.application.tailoring import (
    TailoringError,
    _load_project_catalog,
    _latex_from_response,
    _repair_known_presentation_error,
    validate_latex,
)


SOURCE = r"""\documentclass[10pt]{article}
\usepackage[hidelinks]{hyperref}
\begin{document}
Ada Lovelace -- Data Engineer
\begin{itemize}
\item Built Python data pipelines for analytics.
\end{itemize}
\end{document}
"""


def test_tailoring_accepts_one_complete_latex_document():
    source = _latex_from_response(f"```latex\n{SOURCE}```")

    validate_latex(source)
    assert source.startswith("\\documentclass")
    assert source.endswith("\\end{document}\n")


def test_tailoring_rejects_incomplete_or_external_latex():
    with pytest.raises(TailoringError, match="complete LaTeX"):
        _latex_from_response("Here is your resume")
    with pytest.raises(TailoringError, match="disallowed"):
        validate_latex(SOURCE.replace("\\begin{document}", "\\input{secret}\n\\begin{document}"))


def test_tailoring_rejects_unresolved_placeholders():
    with pytest.raises(TailoringError, match="placeholder"):
        _latex_from_response(SOURCE.replace("Ada Lovelace", "[INSERT USER BASE RESUME / PROFILE DETAILS HERE]"))


def test_tailoring_repairs_uppercased_color_token_without_changing_content():
    source = SOURCE.replace("\\begin{document}", "\\usepackage{xcolor}\n\\definecolor{primary}{RGB}{1,2,3}\n\\begin{document}")

    repaired = _repair_known_presentation_error(source, "Package xcolor Error: Undefined color `PRIMARY'.")

    assert repaired is not None
    assert "\\definecolor{PRIMARY}{HTML}{1F4E79}" in repaired
    assert "Ada Lovelace" in repaired


def test_project_catalog_includes_every_project_file_and_marks_empty_entries(tmp_path):
    (tmp_path / "relevant.md").write_text("# Relevant Project\nBuilt a search system.", encoding="utf-8")
    (tmp_path / "empty_project.md").write_text("", encoding="utf-8")
    (tmp_path / ".ignored.md").write_text("hidden", encoding="utf-8")

    catalog = _load_project_catalog(tmp_path)

    assert "--- PROJECT FILE: relevant.md ---" in catalog
    assert "Built a search system." in catalog
    assert "--- PROJECT FILE: empty_project.md ---" in catalog
    assert "[No project description was supplied in this file.]" in catalog
    assert ".ignored.md" not in catalog
