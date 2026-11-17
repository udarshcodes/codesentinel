import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import LandingPage from '../components/landing/LandingPage';
import DiffViewer from '../components/dashboard/DiffViewer';
import FindingsPanel from '../components/dashboard/FindingsPanel';
import PipelineView from '../components/dashboard/PipelineView';
import PRSummary from '../components/dashboard/PRSummary';
import { credentialStore } from '../services/credentialStore';

vi.mock('../components/landing/Hero', () => ({ default: () => null }));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); });

describe('audit regressions', () => {
  it('shows a failed submission in the real landing page', () => {
    render(<LandingPage repoUrlInput="https://github.com/udarshcodes/setu"
      setRepoUrlInput={() => {}} startAnalysis={() => {}} errorMsg="Connection timed out" />);
    expect(screen.getByRole('alert').textContent).toBe('Connection timed out');
  });

  it('can receive patches after an empty first render', () => {
    const { rerender } = render(<DiffViewer state={{ patches: [] }} />);
    rerender(<DiffViewer state={{ patches: [{ file: 'app.py', applied: true }] }} />);
    expect(screen.getByText('app.py')).toBeTruthy();
  });

  it('retries with the task credential and displays hydrated confidence', async () => {
    credentialStore.setViewToken('task-a', 'token-a');
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal('fetch', fetchMock);
    const { rerender } = render(<PRSummary state={null} />);
    rerender(<PRSummary state={{ task_id: 'task-a', status: 'FAILED', pr_error: 'Push failed', confidence: 85, patches: [{file: 'app.py', applied: true}] }} />);
    expect(screen.getByText('85.0', { exact: false })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Retry Pull Request Creation' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/v1/job/task-a/retry-pr', {
      method: 'POST', headers: { Authorization: 'Bearer token-a' }
    }));
  });
});

it('keeps critical findings in the high filter and requires security before marking fixes resolved', () => {
  render(<FindingsPanel state={{ status: 'COMPLETED', investigated_issues: [
    { id: 1, title: 'Critical issue', severity: 'critical', category: 'security' },
    { id: 2, title: 'High issue', severity: 'high', category: 'Security' }
  ], patches: [{ patch_id: 1, applied: true }], validation_results: [{ passed: true }], security_verified: false }} />);
  const severity = screen.getAllByRole('combobox')[0];
  fireEvent.change(severity, { target: { value: 'high' } });
  expect(screen.getByText('Critical issue')).toBeTruthy();
  expect(screen.getByText('High issue')).toBeTruthy();
  fireEvent.change(screen.getAllByRole('combobox')[2], { target: { value: 'fixed' } });
  expect(screen.queryByText('Critical issue')).toBeNull();
  expect(screen.queryByText('High issue')).toBeNull();
});

it('does not count completed mapping/planning stages as verified repairs', () => {
  render(<PipelineView state={{status: 'COMPLETED', completed_nodes: ['repo_mapper', 'dependency_analyzer', 'repair_planner']}} />);
  expect(screen.queryByText(/Verified$/)).toBeNull();
});

it('reports applied and validation evidence separately from security verification', () => {
  render(<FindingsPanel state={{status: 'COMPLETED', investigated_issues: [{id: 0, title: 'Timeout issue', severity: 'high'}],
    patches: [{patch_id: 0, applied: true}], validation_results: [{passed: true}], security_verified: false}} />);
  fireEvent.click(screen.getByRole('button', {name: /Timeout issue/}));
  expect(screen.getByText('Remediation applied:').textContent).toContain('Yes');
  expect(screen.getByText('Validation passed:').textContent).toContain('Yes');
  expect(screen.queryByText('Fixed')).toBeTruthy(); // Only the filter option, never the issue status.
});

it('does not offer a futile publication retry for invalid persisted patch history', () => {
  render(<PRSummary state={{status: 'COMPLETED', pr_error: 'Patch re-application failed on trusted workspace: search missing'}} />);
  expect(screen.queryByRole('button', {name: 'Retry Pull Request Creation'})).toBeNull();
  expect(screen.getByText(/start a new analysis/)).toBeTruthy();
});

it('renders finite patch group counts and application rate', () => {
  render(<DiffViewer state={{patches: [{file:'app.py',applied:true},{file:'app.py',applied:false}]}} />);
  expect(screen.getByRole('button', {name: /app.py 2 attempts 1 applied 1 rejected/})).toBeTruthy();
  expect(screen.queryByText('NaN')).toBeNull();
  expect(screen.getByText('50.0%')).toBeTruthy();
});


it('shows advisory-only completion without a futile PR retry', () => {
  render(<PRSummary state={{status: 'COMPLETED', pr_error: 'No automatic repairs selected; advisory findings require manual review.', patches: []}} />);
  expect(screen.getAllByText('Analysis complete — no automatic changes').length).toBeGreaterThan(0);
  expect(screen.queryByRole('button', {name: 'Retry Pull Request Creation'})).toBeNull();
});


it('does not show a final PR failure during a repair retry', () => {
  const {container} = render(<PRSummary state={{status:'RUNNING',pr_error:'Temporary repair failure',patches:[]}} />);
  expect(container.textContent).toBe('');
});

it('keeps update advisories filterable without calling them unresolved repairs', () => {
  render(<FindingsPanel state={{status:'COMPLETED', investigated_issues:[{id:0,description:'Outdated dependency: example',severity:'low',affected_files:['package.json'],remediation_mode:'manual_review'}],patches:[]}} />);
  fireEvent.change(screen.getByRole('combobox',{name:'Filter status'}),{target:{value:'advisory'}});
  expect(screen.getByRole('button',{name:/Outdated dependency: example.*Advisory/})).toBeTruthy();
  expect(screen.queryByRole('button',{name:/Outdated dependency: example.*Unresolved/})).toBeNull();
});

it('labels a review-required PR as draft even when retained source fixes pass checks', () => {
  render(<PRSummary state={{status:'NEEDS_REVIEW',pr_url:'https://github.com/example/project/pull/1',
    validation_results:[{passed:true,tests_executed:true}],security_verified:true}} />);
  expect(screen.getByText('Draft Pull Request Created')).toBeTruthy();
  expect(screen.queryByText('Pull Request Ready')).toBeNull();
});

it('keeps unpatched critical dependencies in the review filter and shows the actual reason', () => {
  render(<FindingsPanel state={{status:'NEEDS_REVIEW',investigated_issues:[{
    id:0,description:'Vulnerable package',severity:'critical',category:'quality',affected_files:['pyproject.toml'],
    original_finding:{package:'example'},remediation_mode:'manual_review',remediation_reason:'No compatible clean release exists.'
  }],patches:[]}} />);
  fireEvent.change(screen.getByRole('combobox',{name:'Filter status'}),{target:{value:'needs review'}});
  fireEvent.click(screen.getByRole('button',{name:/Vulnerable package.*Needs Review/}));
  expect(screen.getByText('No compatible clean release exists.')).toBeTruthy();
  expect(screen.queryByText(/A newer version alone/)).toBeNull();
});
