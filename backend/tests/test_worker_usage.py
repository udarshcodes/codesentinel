from tools.worker_usage import merge_usage, aggregate_usage


def test_resumed_worker_snapshot_does_not_count_the_same_attempt_twice():
    previous = {"code_generator": {"calls": 2, "prompt_tokens": 20, "completion_tokens": 4, "model_used": ["model"]}}
    attempt = {"code_generator": {"calls": 1, "prompt_tokens": 10, "completion_tokens": 2, "model_used": ["model"]}}
    first = merge_usage(previous, attempt)
    assert first["code_generator"]["calls"] == 3
    assert merge_usage(previous, attempt) == first
    assert previous["code_generator"]["calls"] == 2
    attempt["code_generator"]["calls"] = 2
    assert merge_usage(previous, attempt)["code_generator"]["calls"] == 4


def test_admin_aggregates_latest_snapshots_and_ignores_legacy_jobs():
    result = aggregate_usage([{}, {"llm_telemetry": {"code_generator": {"calls": 2, "prompt_tokens": 10}}, "worker_cache_metrics": {"hits": 1}},
                              {"llm_telemetry": {"code_generator": {"calls": 3, "completion_tokens": 5}}}])
    assert result["agents"]["code_generator"]["calls"] == 5
    assert result["agents"]["code_generator"]["prompt_tokens"] == 10
    assert result["cache"]["hits"] == 1
    assert result["reported_jobs"] == 2


def test_admin_reads_latest_persisted_job_usage_not_its_own_process_counters():
    import json
    import uuid
    from api.job_manager import JobManager
    from api.db import get_connection
    task = str(uuid.uuid4())
    agent = "test_agent_" + task
    JobManager.create_job(task, "https://github.com/example/repo")
    for calls in (2, 3):
        conn = get_connection()
        conn.execute("UPDATE jobs SET pipeline_state = ? WHERE task_id = ?", (json.dumps({"llm_telemetry": {agent: {"calls": calls, "prompt_tokens": 10}}}), task))
        conn.commit()
        conn.close()
    assert JobManager.get_worker_usage()["agents"][agent]["calls"] == 3
