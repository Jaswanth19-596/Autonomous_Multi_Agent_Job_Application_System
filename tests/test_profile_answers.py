import json
from pathlib import Path

from src.application import profile_answers
from src.data.user_profile import UserProfile


def test_save_application_answer_adds_a_confirmed_profile_answer(tmp_path, monkeypatch):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(profile_answers, "USER_PROFILE_PATH", profile_path)

    saved = profile_answers.save_application_answer("Need sponsorship?", "No")

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert saved == "No"
    assert profile["application_answers"]["need sponsorship?"]["question"] == "Need sponsorship?"
    assert profile["application_answers"]["need sponsorship?"]["answer"] == "No"


def test_save_application_answer_updates_the_same_normalized_question(tmp_path, monkeypatch):
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(profile_answers, "USER_PROFILE_PATH", profile_path)

    profile_answers.save_application_answer("Need sponsorship?", "No")
    profile_answers.save_application_answer("  need   sponsorship? ", "No, now or later")

    answers = json.loads(profile_path.read_text(encoding="utf-8"))["application_answers"]
    assert list(answers) == ["need sponsorship?"]
    assert answers["need sponsorship?"]["answer"] == "No, now or later"


def test_profile_prompt_includes_confirmed_application_answers(tmp_path):
    source_profile = Path("data/user_profile.json")
    profile_data = json.loads(source_profile.read_text(encoding="utf-8"))
    profile_data["application_answers"] = {
        "need sponsorship?": {
            "question": "Need sponsorship?",
            "answer": "No",
            "updated_at": "2026-08-14T00:00:00+00:00",
        }
    }
    profile_path = tmp_path / "user_profile.json"
    profile_path.write_text(json.dumps(profile_data), encoding="utf-8")

    prompt = UserProfile.build_user_profile(str(profile_path))

    assert "Confirmed application answers:" in prompt
    assert "Need sponsorship?: No" in prompt


def test_interactive_answer_tool_saves_the_terminal_response(monkeypatch):
    from src.agent.tools import ask_for_profile_answer

    saved = {}
    monkeypatch.setattr("builtins.input", lambda _: "I do not want to answer")
    monkeypatch.setattr(
        "src.agent.tools.save_application_answer",
        lambda question, answer: saved.update(question=question, answer=answer) or answer,
    )

    result = ask_for_profile_answer.invoke(
        {"question": "Voluntary Self-Identification of Disability"}
    )

    assert saved == {
        "question": "Voluntary Self-Identification of Disability",
        "answer": "I do not want to answer",
    }
    assert "saved to user_profile.json" in result


def test_detached_profile_answer_waits_for_the_remote_selection(monkeypatch):
    import asyncio

    from src.agent import tools as agent_tools
    from src.runtime import services
    from src.runtime.services import AgentRuntime

    class DetachedInput:
        @staticmethod
        def isatty():
            return False

    saved = {}
    runtime = AgentRuntime()
    monkeypatch.setattr(services, "_runtime", runtime)
    monkeypatch.setattr(agent_tools.sys, "stdin", DetachedInput())
    monkeypatch.setattr(agent_tools, "_show_profile_question", lambda *_: None)
    monkeypatch.setattr(
        agent_tools,
        "save_application_answer",
        lambda question, answer: saved.update(question=question, answer=answer) or answer,
    )

    async def scenario():
        waiting = asyncio.create_task(
            agent_tools._ask_for_profile_answer_async("Can you travel?", ["Yes", "No"])
        )
        await asyncio.sleep(0)
        question_id = runtime.inputs._question_id
        assert question_id is not None
        assert runtime.inputs.resolve_question_option(question_id, 1)
        return await waiting

    result = asyncio.run(scenario())

    assert saved == {"question": "Can you travel?", "answer": "No"}
    assert "'No'" in result
