import json

from src.cli import ui_qna


def test_placeholder_recorder_is_idempotent_even_after_malformed_output(tmp_path, monkeypatch):
    qna_path = tmp_path / "qna.md"
    question = "Voluntary Self-Identification of Disability — disability status"
    qna_path.write_text(
        "f# NEEDS ANSWER\n"
        f"- Question: {question}\n"
        "- Placeholder answer used: I do not want to answer\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ui_qna, "QNA_FILE_PATH", qna_path)

    added = ui_qna.record_placeholder_question(question, "I do not want to answer")

    assert added is False
    assert qna_path.read_text(encoding="utf-8").count("- Question:") == 1


def test_placeholder_recorder_writes_one_canonical_block(tmp_path, monkeypatch):
    qna_path = tmp_path / "qna.md"
    monkeypatch.setattr(ui_qna, "QNA_FILE_PATH", qna_path)

    assert ui_qna.record_placeholder_question("Need sponsorship?", "No") is True
    assert ui_qna.record_placeholder_question("  need   sponsorship? ", "No") is False

    assert qna_path.read_text(encoding="utf-8") == (
        "# NEEDS ANSWER\n"
        "- Question: Need sponsorship?\n"
        "- Placeholder answer used: No\n"
    )


def test_qna_context_includes_only_confirmed_answers(tmp_path, monkeypatch):
    qna_path = tmp_path / "qna.md"
    qna_path.write_text(
        "Preferred name = Ada\n"
        "# NEEDS ANSWER\n"
        "- Question: Disability status\n"
        "- Placeholder answer used: I do not want to answer\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ui_qna, "QNA_FILE_PATH", qna_path)

    context = ui_qna.build_qna_context()

    assert "Preferred name: Ada" in context
    assert "Disability" not in context


def test_pending_questions_are_deduplicated_and_keep_fallback_history(tmp_path, monkeypatch):
    pending_path = tmp_path / "pending_questions.json"
    monkeypatch.setattr(ui_qna, "PENDING_QUESTIONS_FILE_PATH", pending_path)

    first = ui_qna.record_pending_question("Need sponsorship?", "No")
    second = ui_qna.record_pending_question("  need   sponsorship? ", "Not required")

    stored = json.loads(pending_path.read_text(encoding="utf-8"))
    assert first["created"] is True
    assert second == {"created": False, "id": first["id"], "seen_count": 2}
    assert stored["version"] == 1
    assert stored["questions"] == [
        {
            "id": first["id"],
            "question": "Need sponsorship?",
            "normalized_question": "need sponsorship?",
            "status": "pending",
            "placeholder_answers_seen": ["No", "Not required"],
            "first_seen_at": stored["questions"][0]["first_seen_at"],
            "last_seen_at": stored["questions"][0]["last_seen_at"],
            "seen_count": 2,
        }
    ]
