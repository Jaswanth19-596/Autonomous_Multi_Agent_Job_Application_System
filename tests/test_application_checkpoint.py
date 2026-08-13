from src.application_checkpoint import ApplicationCheckpointStore


def test_checkpoint_round_trip_and_sensitive_keys_are_dropped(tmp_path):
    store = ApplicationCheckpointStore(tmp_path)
    saved = store.save({
        "job_id": "4451975420", "ats": "workday", "step": 1,
        "step_name": "My Information", "completed_fields": ["First Name"],
        "pending_fields": ["Country Phone Code"], "password": "never-store",
        "failure_detail": "authorization=Bearer never-store-inline",
        "cookies": {"session": "never-store"}, "demographic_answers": {"x": "y"},
    })
    assert store.load("4451975420") == saved
    serialized = store.path_for("4451975420").read_text(encoding="utf-8")
    assert "never-store" not in serialized
    assert "updated_at" in saved


def test_record_step_preserves_progress_for_resume(tmp_path):
    store = ApplicationCheckpointStore(tmp_path)
    store.record_step("job-1", step=1, completed_fields=["First Name"])
    resumed = store.record_step("job-1", pending_fields=["Country Phone Code"])
    assert resumed["step"] == 1
    assert resumed["pending_fields"] == ["Country Phone Code"]


def test_failure_merge_does_not_erase_verified_progress(tmp_path):
    store = ApplicationCheckpointStore(tmp_path)
    store.record_step("4451975420", ats="workday", url="https://kensho.wd5.myworkdayjobs.com/job",
                      step_name="My Information", resume_uploaded=True,
                      completed_fields=["First Name", "How Did You Hear About Us"])
    merged = store.record_step("4451975420", ats=None, url=None, step_name=None,
                               pending_fields=["Save and Continue"], retryable=True)
    assert merged["ats"] == "workday"
    assert "myworkdayjobs.com" in merged["url"]
    assert merged["step_name"] == "My Information"
    assert merged["pending_fields"] == ["Save and Continue"]
