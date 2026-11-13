from agents.pr_author import describe_material_changes


def test_description_uses_actual_changed_files_and_no_planned_timeout_claims():
    title, body = describe_material_changes(["frontend/app.py", "frontend/app.py"], "1 file changed, 1 insertion(+), 1 deletion(-)", True)
    assert "frontend/app.py" in title
    assert body.count("- `frontend/app.py`") == 1
    assert "10 seconds" not in body
    assert "Draft:" in body
    assert "1 insertion(+)" in body


async def test_rejected_attempts_cannot_create_a_random_pr():
    from unittest.mock import patch
    from agents.pr_author import agent_pr_author
    with patch("tools.github_client.prepare_repo_for_push") as prepare:
        result = await agent_pr_author({"patches": [{"file": "app.py", "applied": False}]})
    assert not result["pr_url"]
    assert "all patch attempts were rejected" in result["pr_error"]
    prepare.assert_not_called()
