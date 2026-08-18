from src.application.resume_selection import (
    activate_tailored_resume,
    build_tailored_resume_replacement_code,
    clear_active_tailored_resume,
    enforce_tailored_resume_paths,
    tailored_resume_requirement,
)


def test_tailored_resume_replaces_default_upload_paths_in_browser_arguments(tmp_path):
    tailored = tmp_path / "Acme_Data_Engineer_resume.pdf"
    tailored.write_bytes(b"%PDF-test")
    activate_tailored_resume(tailored)

    try:
        args = {
            "paths": ["/Users/jaswanth/mydocs/myprojects/langgraph/user_details/resume.pdf"],
            "code": "await chooser.setFiles('user_details/resume.pdf')",
        }
        enforced = enforce_tailored_resume_paths(args)

        assert enforced["paths"] == [str(tailored.resolve())]
        assert str(tailored.resolve()) in enforced["code"]
        assert "user_details/resume.pdf" not in enforced["code"]
        assert str(tailored.resolve()) in tailored_resume_requirement()
    finally:
        clear_active_tailored_resume()


def test_no_path_is_rewritten_without_an_active_tailored_resume():
    clear_active_tailored_resume()
    args = {"paths": ["user_details/resume.pdf"]}
    assert enforce_tailored_resume_paths(args) == args


def test_simplify_replacement_program_targets_resume_file_inputs(tmp_path):
    tailored = tmp_path / "Acme_Data_Engineer_resume.pdf"
    tailored.write_bytes(b"%PDF-test")

    code = build_tailored_resume_replacement_code(tailored)

    assert "input[type=file]" in code
    assert "setInputFiles(filePath)" in code
    assert str(tailored.resolve()) in code
