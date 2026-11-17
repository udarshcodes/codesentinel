"""Distinguish finishing execution from delivering a verified repair."""


def has_unresolved_advisories(state):
    return any(issue.get('remediation_mode') == 'manual_review' and
               str(issue.get('severity', '')).lower() in {'high', 'critical'}
               for issue in state.get('investigated_issues', []))


def pipeline_outcome(state):
    if state.get('scanners_failed') or state.get('pipeline_error') or has_unresolved_advisories(state):
        return 'NEEDS_REVIEW'
    patches = state.get('patches') or []
    if not patches:
        return 'NEEDS_REVIEW' if state.get('repair_plan') else 'COMPLETED'
    latest = (state.get('validation_results') or [{}])[-1]
    if (latest.get('passed') is not True or latest.get('tests_executed') is not True
            or latest.get('infrastructure_error') or latest.get('suite_failed') or latest.get('build_failed')
            or state.get('security_verified') is not True or not state.get('pr_url') or state.get('pr_error')):
        return 'NEEDS_REVIEW'
    return 'COMPLETED'
