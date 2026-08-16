import json
import re
from datetime import datetime, timezone
from pathlib import Path


USER_PROFILE_PATH = Path(__file__).resolve().parents[2] / "data" / "user_profile.json"


def _normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", question.strip()).casefold()


def save_application_answer(question: str, answer: str) -> str:
    """Save a user-confirmed application answer in the user profile."""
    clean_question = question.strip()
    clean_answer = answer.strip()
    if not clean_question:
        raise ValueError("Question must not be empty.")
    if not clean_answer:
        raise ValueError("Answer must not be empty.")

    data = json.loads(USER_PROFILE_PATH.read_text(encoding="utf-8"))
    answers = data.setdefault("application_answers", {})
    if not isinstance(answers, dict):
        raise ValueError("user_profile.json field 'application_answers' must be an object.")

    key = _normalize_question(clean_question)
    answers[key] = {
        "question": clean_question,
        "answer": clean_answer,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_profile(data)
    return clean_answer


def _write_profile(data: dict) -> None:
    temporary_path = USER_PROFILE_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary_path.replace(USER_PROFILE_PATH)
