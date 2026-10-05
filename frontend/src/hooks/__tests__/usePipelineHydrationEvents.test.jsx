/* global global */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePipeline } from '../usePipeline';
import { PipelineContext } from '../../context/PipelineContext';

vi.mock('../../services/credentialStore', () => ({
  credentialStore: {
    getViewToken: vi.fn(),
    hasCurrentToken: vi.fn(),
    setCurrentToken: vi.fn(),
    getCurrentToken: vi.fn(),
    clearCurrentToken: vi.fn(),
    clearStaleTokens: vi.fn()
  }
}));

describe('usePipeline Historical Agent Hydration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('hydrates COMPLETED task with historical agents and derives completed_nodes properly', async () => {
    const dispatch = vi.fn();
    const state = { status: 'QUEUED' };

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        task_id: 'task123',
        status: 'COMPLETED',
        repo_url: 'https://github.com/udarshcodes/portfolio',
        pipeline_state: {
          status: 'COMPLETED',
          last_completed_node: 'pr_author',
          pr_url: '...'
        },
        agents: [
          { agent: 'repo_mapper' },
          { agent: 'dependency_analyzer' },
          { agent: 'repo_mapper' }, // test duplicates
          { agent: 'static_analysis' },
          { agent: 'bug_investigator' },
          { agent: 'repair_planner' },
          { agent: 'code_generator' },
          { agent: 'validator' },
          { agent: 'security_verifier' },
          { agent: 'pr_author' }
        ]
      })
    });

    const mockEventSource = vi.fn().mockImplementation(function() {
      return {
        addEventListener: vi.fn(),
        close: vi.fn()
      };
    });
    global.EventSource = mockEventSource;

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    renderHook(() => usePipeline('task123'), { wrapper });

    await act(async () => {
      await new Promise(r => setTimeout(r, 20));
    });

    const hydrateCalls = dispatch.mock.calls.filter(c => c[0].type === 'HYDRATE_STATE');
    expect(hydrateCalls.length).toBe(1);
    
    const payload = hydrateCalls[0][0].payload;
    expect(payload.status).toBe('COMPLETED');
    expect(payload.last_completed_node).toBe('pr_author');
    
    // Check that completed_nodes was properly derived
    expect(payload.completed_nodes).toBeDefined();
    expect(payload.completed_nodes).toEqual([
      'repo_mapper',
      'dependency_analyzer',
      'repo_mapper',
      'static_analysis',
      'bug_investigator',
      'repair_planner',
      'code_generator',
      'validator',
      'security_verifier',
      'pr_author'
    ]);
    
    // SSE is not required for a terminal task
    expect(mockEventSource).not.toHaveBeenCalled();
  });

  it('hydrates RUNNING task with missing pipeline_state safely', async () => {
    const dispatch = vi.fn();
    const state = { status: 'QUEUED' };

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        task_id: 'task-456',
        status: 'RUNNING',
        agents: [
          { agent: 'repo_mapper' }
        ]
        // pipeline_state is missing
      })
    });

    // Mock stream capability request for a RUNNING task
    global.fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ capability: 'mock-cap' })
    });

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    renderHook(() => usePipeline('task-456'), { wrapper });

    await act(async () => {
      await new Promise(r => setTimeout(r, 20));
    });

    const hydrateCalls = dispatch.mock.calls.filter(c => c[0].type === 'HYDRATE_STATE');
    expect(hydrateCalls.length).toBe(1);
    
    const payload = hydrateCalls[0][0].payload;
    expect(payload.status).toBe('RUNNING');
    expect(payload.agents).toEqual([{ agent: 'repo_mapper' }]);
    expect(payload.completed_nodes).toEqual(['repo_mapper']);
  });
});
