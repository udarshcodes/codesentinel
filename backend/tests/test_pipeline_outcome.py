import pytest
from tools.pipeline_outcome import pipeline_outcome
from api.job_manager import JobManager


@pytest.mark.parametrize('updates', [
    {'validation_results': [{'passed': False, 'infrastructure_error': True}]},
    {'security_verified': False}, {'pr_url': ''}, {'pr_error': 'Lockfile is stale'},
    {'scanners_failed': True}, {'validation_results': [{'passed': True, 'tests_executed': False}]},
])
def test_incomplete_repairs_never_report_completed(updates):
    state = {'patches': [{'applied': True}], 'validation_results': [{'passed': True, 'tests_executed': True}],
             'security_verified': True, 'pr_url': 'https://github.com/owner/repo/pull/1'}
    state.update(updates)
    assert pipeline_outcome(state) == 'NEEDS_REVIEW'


def test_clean_repository_does_not_require_an_unnecessary_pull_request():
    assert pipeline_outcome({'patches': []}) == 'COMPLETED'
    assert pipeline_outcome({'patches': [], 'repair_plan': [{'issue_id': 'unfixed'}]}) == 'NEEDS_REVIEW'
    assert pipeline_outcome({'investigated_issues': [{'severity': 'critical', 'remediation_mode': 'manual_review'}]}) == 'NEEDS_REVIEW'


def test_worker_review_event_is_a_fenced_terminal_transition():
    assert JobManager._is_valid_transition('RUNNING', 'NEEDS_REVIEW')
    JobManager._validate_event_semantics('RUNNING', 'NEEDS_REVIEW', 'pipeline_review_required', {}, '{}')
    with pytest.raises(ValueError, match='requires event status NEEDS_REVIEW'):
        JobManager._validate_event_semantics('RUNNING', 'COMPLETED', 'pipeline_review_required', {}, '{}')


def test_review_outcome_is_persisted_and_cannot_be_overwritten():
    from api.job_manager import get_connection
    from datetime import datetime, timezone
    import uuid
    task = 'review-' + uuid.uuid4().hex
    JobManager.create_job(task, 'https://github.com/owner/repo')
    connection = get_connection()
    connection.execute("UPDATE jobs SET status='RUNNING', worker_attempt_id='review-attempt' WHERE task_id=?", (task,))
    connection.commit()
    connection.close()
    JobManager.add_worker_event(task, status='NEEDS_REVIEW', event_name='pipeline_review_required', data={},
                                worker_attempt_id='review-attempt', timestamp=datetime.now(timezone.utc).isoformat())
    assert JobManager.get_job(task)['status'] == 'NEEDS_REVIEW'
    with pytest.raises(ValueError):
        JobManager.add_worker_event(task, status='COMPLETED', event_name='pipeline_complete', data={},
                                    worker_attempt_id='review-attempt', timestamp=datetime.now(timezone.utc).isoformat())
