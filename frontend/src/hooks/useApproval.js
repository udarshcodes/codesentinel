import { useContext, useEffect, useRef } from 'react';
import { PipelineContext } from '../context/PipelineContext';
import { credentialStore } from '../services/credentialStore';

export function useApproval(taskId) {
  const { state, dispatch } = useContext(PipelineContext);
  const latestRequestId = useRef(null);
  const latestDecisionRequestId = useRef(null);
  const abortControllerRef = useRef(null);
  const decisionAbortControllerRef = useRef(null);
  const stateRef = useRef(state);
  
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    if (state.status === 'WAITING_FOR_APPROVAL' && !state.approval_token_ready && !state.token_recovery_required && !state.approval_token_loading) {
      
      const requestId = crypto.randomUUID();
      latestRequestId.current = requestId;
      
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (decisionAbortControllerRef.current) {
        decisionAbortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();
      const signal = abortControllerRef.current.signal;
      
      const requestContext = {
        taskId,
        cycleId: state.approval_cycle_id,
        fixId: state.approval_payload?.fix_id
      };
      
      const issueToken = async () => {
        dispatch({ type: 'FETCH_TOKEN_START' });
        
        const apiUrl = import.meta.env.VITE_API_URL || '';
        const viewToken = credentialStore.getViewToken(taskId);
        try {
          const res = await fetch(`${apiUrl}/api/v1/job/${encodeURIComponent(taskId)}/issue-approval-token`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${viewToken}`
            },
            signal
          });
          
          if (latestRequestId.current !== requestId) return;
          if (stateRef.current.approval_cycle_id !== requestContext.cycleId || 
              stateRef.current.approval_payload?.fix_id !== requestContext.fixId || 
              stateRef.current.status !== 'WAITING_FOR_APPROVAL') return;
          
          if (res.ok) {
            const data = await res.json();
            
            if (latestRequestId.current !== requestId) return;
            if (stateRef.current.approval_cycle_id !== requestContext.cycleId || 
                stateRef.current.approval_payload?.fix_id !== requestContext.fixId || 
                stateRef.current.status !== 'WAITING_FOR_APPROVAL') return;
            
            // We do NOT dispatch APPROVAL_REQUIRED here because issue-approval-token only issues a credential.
            // Dispatching it would wipe out the true pipeline state's approval_payload.
            
            if (data.status === 'active') {
                // If it already existed but we don't have it in session storage, check if it's there
                if (credentialStore.hasCurrentToken(taskId, data.approval_cycle_id)) {
                    dispatch({ type: 'FETCH_TOKEN_SUCCESS', payload: { cycleId: requestContext.cycleId, fixId: requestContext.fixId } });
                } else {
                    dispatch({ type: 'REQUIRE_RECOVERY' });
                }
            } else if (data.status === 'issued') {
                credentialStore.setCurrentToken(taskId, data.approval_cycle_id, data.approval_token);
                dispatch({ type: 'FETCH_TOKEN_SUCCESS', payload: { cycleId: requestContext.cycleId, fixId: requestContext.fixId } });
            }
          } else if (res.status === 409) {
            dispatch({ type: 'REQUIRE_RECOVERY' });
          } else {
            dispatch({ type: 'FETCH_TOKEN_ERROR' });
          }
        } catch (err) {
          if (err.name === 'AbortError') return;
          if (latestRequestId.current !== requestId) return;
          if (stateRef.current.approval_cycle_id !== requestContext.cycleId || 
              stateRef.current.approval_payload?.fix_id !== requestContext.fixId || 
              stateRef.current.status !== 'WAITING_FOR_APPROVAL') return;
          console.error(err);
          dispatch({ type: 'FETCH_TOKEN_ERROR' });
        }
      };
      
      issueToken();

      return () => {
        if (abortControllerRef.current) {
          abortControllerRef.current.abort();
        }
        if (decisionAbortControllerRef.current) {
          decisionAbortControllerRef.current.abort();
        }
      };
    }
  }, [state.status, state.approval_token_ready, state.token_recovery_required, state.approval_token_loading, state.approval_cycle_id, state.approval_payload?.fix_id, taskId, dispatch]);


  const submitDecision = async (decision) => {
    if (state.approval_decision_loading) return { success: false, error: 'Submission in progress' };

    const requestId = crypto.randomUUID();
    latestDecisionRequestId.current = requestId;

    if (decisionAbortControllerRef.current) {
      decisionAbortControllerRef.current.abort();
    }
    decisionAbortControllerRef.current = new AbortController();
    const signal = decisionAbortControllerRef.current.signal;

    const requestContext = {
      taskId,
      cycleId: state.approval_cycle_id,
      fixId: state.approval_payload?.fix_id
    };

    if (stateRef.current.approval_cycle_id !== requestContext.cycleId || 
        stateRef.current.approval_payload?.fix_id !== requestContext.fixId) {
      return { success: false, error: 'Stale approval context' };
    }

    dispatch({ type: 'APPROVAL_DECISION_START' });

    try {
      const apiUrl = import.meta.env.VITE_API_URL || '';
      const cycleId = requestContext.cycleId;
      const token = credentialStore.getCurrentToken(taskId, cycleId) || '';
      const fix_id = requestContext.fixId;
      const response = await fetch(`${apiUrl}/api/v1/approve/${encodeURIComponent(taskId)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ decision, approval_token: token, fix_id, approval_cycle_id: cycleId }),
        signal
      });

      const data = await response.json();

      if (latestDecisionRequestId.current !== requestId) {
        dispatch({ type: 'APPROVAL_DECISION_END' });
        return { success: false, error: 'Stale request' };
      }

      if (stateRef.current.approval_cycle_id !== requestContext.cycleId || 
          stateRef.current.approval_payload?.fix_id !== requestContext.fixId ||
          stateRef.current.status !== 'WAITING_FOR_APPROVAL') {
        dispatch({ type: 'APPROVAL_DECISION_END' });
        return { success: false, error: 'Stale approval context after response' };
      }

      if (response.ok) {
        credentialStore.clearCurrentToken(taskId, cycleId);
        dispatch({ type: 'APPROVAL_RESOLVED', payload: data });
        // The redcuer for APPROVAL_RESOLVED automatically clears approval_decision_loading,
        // but we can explicitly dispatch end anyway just in case:
        dispatch({ type: 'APPROVAL_DECISION_END' });
        return { success: true };
      }
      
      dispatch({ type: 'APPROVAL_DECISION_END' });
      return { success: false, error: data.detail || 'Unknown error' };
    } catch (err) {
      dispatch({ type: 'APPROVAL_DECISION_END' });
      if (err.name === 'AbortError') return { success: false, error: 'Aborted' };
      
      console.error('Error submitting approval decision', err);
      return { success: false, error: err.message };
    }
  };

  const approve = () => submitDecision('approved');
  const reject = () => submitDecision('rejected');

  const recoverToken = async () => {
    const requestId = crypto.randomUUID();
    latestRequestId.current = requestId;
    
    const requestContext = {
      taskId,
      cycleId: state.approval_cycle_id,
      fixId: state.approval_payload?.fix_id
    };

    dispatch({ type: 'FETCH_TOKEN_START' });
    const apiUrl = import.meta.env.VITE_API_URL || '';
    const viewToken = credentialStore.getViewToken(taskId);
    try {
      const res = await fetch(`${apiUrl}/api/v1/job/${encodeURIComponent(taskId)}/recover-credential`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${viewToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ approval_cycle_id: requestContext.cycleId, fix_id: requestContext.fixId })
      });
      
      if (latestRequestId.current !== requestId) return { success: false };
      if (stateRef.current.approval_cycle_id !== requestContext.cycleId || 
          stateRef.current.approval_payload?.fix_id !== requestContext.fixId || 
          stateRef.current.status !== 'WAITING_FOR_APPROVAL') return { success: false };
      if (res.ok) {
        const data = await res.json();
        
        if (latestRequestId.current !== requestId) return { success: false };
        if (stateRef.current.approval_cycle_id !== requestContext.cycleId || 
            stateRef.current.approval_payload?.fix_id !== requestContext.fixId || 
            stateRef.current.status !== 'WAITING_FOR_APPROVAL') return { success: false };

        if (data.status === 'recovered') {
          credentialStore.setCurrentToken(taskId, requestContext.cycleId, data.approval_token);
          dispatch({ type: 'FETCH_TOKEN_SUCCESS', payload: { cycleId: requestContext.cycleId, fixId: requestContext.fixId } });
          return { success: true };
        }
      }
      dispatch({ type: 'FETCH_TOKEN_ERROR' });
      return { success: false };
    } catch (err) {
      if (latestRequestId.current !== requestId) return { success: false };
      if (stateRef.current.approval_cycle_id !== requestContext.cycleId || 
          stateRef.current.approval_payload?.fix_id !== requestContext.fixId || 
          stateRef.current.status !== 'WAITING_FOR_APPROVAL') return { success: false };
          
      console.error('Error recovering token', err);
      dispatch({ type: 'FETCH_TOKEN_ERROR' });
      return { success: false };
    }
  };

  return {
    approve,
    reject,
    recoverToken,
    awaitingApproval: state.status === 'WAITING_FOR_APPROVAL',
    currentFix: state.approval_payload,
    tokenLoading: state.approval_token_loading,
    tokenReady: state.approval_token_ready === true && state.token_ready_cycle_id === state.approval_cycle_id && state.token_ready_fix_id === state.approval_payload?.fix_id,
    tokenRecoveryRequired: state.token_recovery_required
  };
}
