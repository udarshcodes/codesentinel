/* global global */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useApproval } from '../useApproval';
import { PipelineContext } from '../../context/PipelineContext';
import { credentialStore } from '../../services/credentialStore';

vi.mock('../../services/credentialStore', () => ({
  credentialStore: {
    getViewToken: vi.fn(),
    hasCurrentToken: vi.fn(),
    setCurrentToken: vi.fn(),
    getCurrentToken: vi.fn(),
    clearCurrentToken: vi.fn()
  }
}));



describe('useApproval Race Conditions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
    credentialStore.getViewToken.mockReturnValue('mock-view-token');
  });

  it('Stale issueToken response is ignored when cycle changes', async () => {
    let resolveFetch;
    const fetchPromise = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    global.fetch.mockReturnValueOnce(fetchPromise).mockReturnValueOnce(new Promise(() => {}));

    const dispatch = vi.fn();
    const initialState = {
      status: 'WAITING_FOR_APPROVAL',
      approval_token_ready: false,
      token_recovery_required: false,
      approval_cycle_id: 'cycle-A',
      approval_payload: { fix_id: 'fix-A' }
    };

    let state = { ...initialState };
    
    // First render with Cycle A
    const { rerender } = renderHook(() => useApproval('task-1'), {
      wrapper: ({ children }) => (
        <PipelineContext.Provider value={{ state, dispatch }}>
          {children}
        </PipelineContext.Provider>
      )
    });

    expect(dispatch).toHaveBeenCalledWith({ type: 'FETCH_TOKEN_START' });
    expect(global.fetch).toHaveBeenCalledTimes(1);

    // Switch context to Cycle B
    state = {
      ...state,
      approval_cycle_id: 'cycle-B',
      approval_payload: { fix_id: 'fix-B' }
    };
    rerender();
    
    // Resolve the original Cycle A fetch
    await act(async () => {
      resolveFetch({
        ok: true,
        json: async () => ({ status: 'issued', approval_cycle_id: 'cycle-A', approval_token: 'token-A' })
      });
    });

    // Check that FETCH_TOKEN_SUCCESS was NOT dispatched
    const successCalls = dispatch.mock.calls.filter(c => c[0].type === 'FETCH_TOKEN_SUCCESS');
    expect(successCalls.length).toBe(0);
  });

  it('Stale recoverToken response is ignored when cycle changes', async () => {
    let resolveFetch;
    const fetchPromise = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    global.fetch.mockReturnValue(fetchPromise);

    const dispatch = vi.fn();
    let state = {
      status: 'WAITING_FOR_APPROVAL',
      approval_token_ready: false,
      token_recovery_required: false,
      approval_cycle_id: 'cycle-A',
      approval_payload: { fix_id: 'fix-A' }
    };

    const { result, rerender } = renderHook(() => useApproval('task-1'), {
      wrapper: ({ children }) => (
        <PipelineContext.Provider value={{ state, dispatch }}>
          {children}
        </PipelineContext.Provider>
      )
    });

    // Start recovery for Cycle A
    let recoverPromise;
    act(() => {
      recoverPromise = result.current.recoverToken();
    });

    // Switch context to Cycle B
    state = {
      ...state,
      approval_cycle_id: 'cycle-B',
      approval_payload: { fix_id: 'fix-B' }
    };
    rerender();

    // Resolve the original Cycle A recovery fetch
    await act(async () => {
      resolveFetch({
        ok: true,
        json: async () => ({ status: 'recovered', approval_token: 'token-A' })
      });
      const res = await recoverPromise;
      expect(res.success).toBe(false); // Stale response rejected
    });

    // Verify it wasn't saved or dispatched for success
    const successCalls = dispatch.mock.calls.filter(c => c[0].type === 'FETCH_TOKEN_SUCCESS');
    expect(successCalls.length).toBe(0);
  });

  it('Stale submitDecision is rejected AFTER fetch when cycle changes', async () => {
      let resolveFetch;
      global.fetch.mockReturnValue(new Promise(r => resolveFetch = r));
      const dispatch = vi.fn();
      
      let state = {
        status: 'WAITING_FOR_APPROVAL',
        approval_token_ready: true,
        approval_cycle_id: 'cycle-A',
        approval_payload: { fix_id: 'fix-A' }
      };
  
      const { result, rerender } = renderHook(() => useApproval('task-1'), {
        wrapper: ({ children }) => (
          <PipelineContext.Provider value={{ state, dispatch }}>
            {children}
          </PipelineContext.Provider>
        )
      });
      
      let submitPromise;
      act(() => {
          submitPromise = result.current.approve();
      });
      
      // Change state to B while fetch is inflight
      state = {
          ...state,
          approval_cycle_id: 'cycle-B'
      };
      rerender();
      
      // Resolve fetch
      await act(async () => {
          resolveFetch({ ok: true, json: async () => ({}) });
          const res = await submitPromise;
          expect(res.success).toBe(false);
          expect(res.error).toBe('Stale approval context after response');
      });
  });
  
  it('Strict mode double invocation ignores duplicate response', async () => {
      let resolveFetch1, resolveFetch2;
      global.fetch
        .mockReturnValueOnce(new Promise(r => resolveFetch1 = r))
        .mockReturnValueOnce(new Promise(r => resolveFetch2 = r));
        
      const dispatch = vi.fn();
      const state = {
        status: 'WAITING_FOR_APPROVAL',
        approval_token_ready: false,
        token_recovery_required: false,
        approval_cycle_id: 'cycle-A',
        approval_payload: { fix_id: 'fix-A' }
      };
      
      const wrapper = ({ children }) => (
        <React.StrictMode>
          <PipelineContext.Provider value={{ state, dispatch }}>
            {children}
          </PipelineContext.Provider>
        </React.StrictMode>
      );
      
      renderHook(() => useApproval('task-1'), { wrapper });
      
      // Due to StrictMode, it should have mounted twice synchronously, thus calling fetch twice
      // But only ONE success should be dispatched because the first is aborted!
      // Wait, let's just make sure both promises resolve.
      expect(global.fetch).toHaveBeenCalledTimes(2);
      
      // Resolve both
      await act(async () => {
          resolveFetch1({
            ok: true,
            json: async () => ({ status: 'issued', approval_cycle_id: 'cycle-A', approval_token: 'token-A1' })
          });
          resolveFetch2({
            ok: true,
            json: async () => ({ status: 'issued', approval_cycle_id: 'cycle-A', approval_token: 'token-A2' })
          });
      });
      
      // Only one SUCCESS should be dispatched
      const successCalls = dispatch.mock.calls.filter(c => c[0].type === 'FETCH_TOKEN_SUCCESS');
      expect(successCalls.length).toBe(1);
  });

  it('Exact Two Fix Failure: Cycle B automatically triggers token request', async () => {
    let resolveFetchA;
    let resolveFetchB;
    resolveFetchB; // to avoid unused variable
    global.fetch
      .mockReturnValueOnce(new Promise(r => resolveFetchA = r))
      .mockReturnValueOnce(new Promise(r => resolveFetchB = r));

    const dispatch = vi.fn();
    let state = {
      status: 'WAITING_FOR_APPROVAL',
      approval_token_ready: false,
      token_recovery_required: false,
      approval_token_loading: false,
      approval_cycle_id: 'cycle-A',
      approval_payload: { fix_id: 'fix-A' }
    };

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    const { rerender } = renderHook(() => useApproval('task-1'), { wrapper });

    // Cycle A triggers fetch
    expect(global.fetch).toHaveBeenCalledTimes(1);

    // Resolve Cycle A
    await act(async () => {
      resolveFetchA({
        ok: true,
        json: async () => ({ status: 'issued', approval_cycle_id: 'cycle-A', approval_token: 'token-A' })
      });
    });

    // Simulate Cycle B becoming active (status remains WAITING_FOR_APPROVAL, token_ready is reset to false)
    state = {
      ...state,
      approval_cycle_id: 'cycle-B',
      approval_payload: { fix_id: 'fix-B' },
      approval_token_ready: false,
      approval_token_loading: false,
      token_recovery_required: false
    };
    rerender();

    // Cycle B should automatically trigger a NEW fetch!
    expect(global.fetch).toHaveBeenCalledTimes(2);
  });

  it('Exact Stale HTTP Response Race: ignores decision response if cycle changed', async () => {
    let resolveFetchA;
    // Mock the decision fetch
    global.fetch.mockReturnValueOnce(new Promise(r => resolveFetchA = r));
    // Mock the issueToken fetch for Cycle B
    global.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ token: 'mock-b' }) });

    const dispatch = vi.fn();
    let state = {
      status: 'WAITING_FOR_APPROVAL',
      approval_token_ready: true,
      token_recovery_required: false,
      approval_token_loading: false,
      approval_decision_loading: false,
      approval_cycle_id: 'cycle-A',
      approval_payload: { fix_id: 'fix-A' }
    };

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    const { result, rerender } = renderHook(() => useApproval('task-1'), { wrapper });

    let submitPromise;
    act(() => {
      submitPromise = result.current.approve();
    });

    expect(dispatch).toHaveBeenCalledWith({ type: 'APPROVAL_DECISION_START' });

    // Switch state to Cycle B while A's decision is in-flight
    state = {
      ...state,
      approval_cycle_id: 'cycle-B',
      approval_payload: { fix_id: 'fix-B' },
      approval_token_ready: false
    };
    rerender();

    // Resolve A's decision response
    await act(async () => {
      resolveFetchA({
        ok: true,
        json: async () => ({ decision: 'approved', approval_cycle_id: 'cycle-A', fix_id: 'fix-A' })
      });
      const res = await submitPromise;
      expect(res.success).toBe(false);
      expect(res.error).toBe('Stale approval context after response');
    });

    // APPROVAL_RESOLVED should NOT be dispatched
    const resolvedCalls = dispatch.mock.calls.filter(c => c[0].type === 'APPROVAL_RESOLVED');
    expect(resolvedCalls.length).toBe(0);
    // credentialStore.clearCurrentToken should NOT be called
    expect(credentialStore.clearCurrentToken).not.toHaveBeenCalled();
  });

  it('Double Submission Prevention: only one request fires', async () => {
    let resolveFetch;
    global.fetch.mockReturnValueOnce(new Promise(r => resolveFetch = r));

    const dispatch = vi.fn();
    let state = {
      status: 'WAITING_FOR_APPROVAL',
      approval_token_ready: true,
      token_recovery_required: false,
      approval_token_loading: false,
      approval_decision_loading: false, // first one sees false
      approval_cycle_id: 'cycle-A',
      approval_payload: { fix_id: 'fix-A' }
    };

    const wrapper = ({ children }) => (
      <PipelineContext.Provider value={{ state, dispatch }}>
        {children}
      </PipelineContext.Provider>
    );

    const { result, rerender } = renderHook(() => useApproval('task-1'), { wrapper });

    let promise1;
    act(() => {
      promise1 = result.current.approve();
    });
    
    // Simulate state immediately updating (as Reducer would do)
    state = { ...state, approval_decision_loading: true };
    rerender();
    
    let promise2;
    act(() => {
      promise2 = result.current.reject();
    });

    // Expect only one fetch call
    expect(global.fetch).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFetch({ ok: true, json: async () => ({}) });
      const [res1, res2] = await Promise.all([promise1, promise2]);
      
      expect(res1.success).toBe(true);
      expect(res2.success).toBe(false);
      expect(res2.error).toBe('Submission in progress');
    });
  });
});
