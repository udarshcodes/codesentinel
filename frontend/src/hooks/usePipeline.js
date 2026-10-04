import { useEffect, useRef, useContext } from 'react';
import { PipelineContext } from '../context/PipelineContext';
import { credentialStore } from '../services/credentialStore';

export function usePipeline(taskId) {
  const { state, dispatch } = useContext(PipelineContext);
  const eventSourceRef = useRef(null);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef(null);
  const lastProcessedSequence = useRef(null);
  const MAX_RETRIES = 5;

  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    if (!taskId) return;

    let isMounted = true;


    const fetchState = async (apiUrl, headers) => {
      try {
        const stateRes = await fetch(`${apiUrl}/api/v1/job/${encodeURIComponent(taskId)}/view`, {
          headers
        });
        if (stateRes && stateRes.ok) {
          const stateData = await stateRes.json();
          if (stateData.last_sequence !== undefined && stateData.last_sequence >= 0) {
            lastProcessedSequence.current = stateData.last_sequence;
          }
          if (stateData.pipeline_state) {
            const tStatus = stateData.status || stateData.pipeline_state.status || 'QUEUED';
            dispatch({ type: 'HYDRATE_STATE', payload: {
              status: tStatus,
              task_id: stateData.task_id,
              repo_url: stateData.repo_url,
              agents: stateData.agents || [],
              approval_decision: stateData.approval_decision,
              confidence: stateData.confidence_score ?? stateData.pipeline_state?.confidence_score,
              pr_url: stateData.pipeline_state?.pr_url,
              pr_error: stateData.pipeline_state?.pr_error,
              findings: stateData.pipeline_state?.findings || [],
              dependency_findings: stateData.pipeline_state?.dependency_findings || [],
              static_findings: stateData.pipeline_state?.static_findings || [],
              investigated_issues: stateData.pipeline_state?.investigated_issues || [],
              repair_plan: stateData.pipeline_state?.repair_plan,
              current_fix: stateData.pipeline_state?.current_fix,
              patches: stateData.pipeline_state?.patches || [],
              validation_results: stateData.pipeline_state?.validation_results || [],
              security_verification: stateData.pipeline_state?.security_verification,
              retry_count: stateData.pipeline_state?.retry_count || 0,
              security_retry_state: stateData.pipeline_state?.security_retry_state || 0,
              last_completed_node: stateData.pipeline_state?.last_completed_node,
              rag_status: stateData.pipeline_state?.rag_status,
              llm_waiting_state: stateData.pipeline_state?.llm_waiting_state || false,
              next_retry: stateData.pipeline_state?.next_retry,
              pipeline_error: stateData.pipeline_state?.pipeline_error,
              model: stateData.pipeline_state?.last_llm_model || stateData.last_llm_model,
              reset_time: null,
              last_error: stateData.pipeline_state?.last_llm_error || stateData.last_llm_error,
              awaiting_approval: stateData.pipeline_state?.awaiting_approval || false,
              approval_payload: stateData.pipeline_state?.approval_payload,
              approval_cycle_id: stateData.pipeline_state?.approval_cycle_id
            }});
            
            const activeCycle = stateData.pipeline_state?.approval_cycle_id;
            if (activeCycle || tStatus) {
                credentialStore.clearStaleTokens(taskId, activeCycle);
            }
          }
          return { ok: true, status: stateRes.status, terminalStatus: stateData.status || (stateData.pipeline_state && stateData.pipeline_state.status) || 'QUEUED' };
        }
        return { ok: false, status: stateRes ? stateRes.status : 0 };
      } catch (err) {
        console.error('Failed to fetch state:', err);
        return { ok: false, status: 0 };
      }
    };

    const hydrateAndConnect = async () => {
      let terminalStatus = null;
      try {
        const apiUrl = import.meta.env.VITE_API_URL || '';
        
        // 1. Hydrate persistent state first to avoid empty UI
        const viewToken = credentialStore.getViewToken(taskId);
        const headers = {};
        if (viewToken) headers['Authorization'] = `Bearer ${viewToken}`;

        const stateRes = await fetchState(apiUrl, headers);
        if (stateRes.ok) {
          terminalStatus = stateRes.terminalStatus;
        } else {
            if (stateRes.status === 404) {
                dispatch({ type: 'SET_STATUS', payload: { status: 'NOT_FOUND' } });
                return;
            }
            if (stateRes.status === 401 || stateRes.status === 403) {
                dispatch({ type: 'SET_STATUS', payload: { status: 'UNAUTHORIZED' } });
                return;
            }
        }

        if (!isMounted) return;

        const terminalStates = ['COMPLETED', 'FAILED', 'NEEDS_REVIEW'];
        if (!terminalStatus || !terminalStates.includes(terminalStatus)) {
          // 2. Fetch SSE capability and Connect SSE only if not terminal
          const capRes = await fetch(`${apiUrl}/api/v1/job/${encodeURIComponent(taskId)}/stream-capability`, {
            headers
          });
          if (capRes.ok) {
            const capData = await capRes.json();
            if (capData.capability) {
              connectSSE(apiUrl, capData.capability);
            }
          } else {
             console.error('Failed to get SSE capability', capRes.status);
             if (capRes.status === 401 || capRes.status === 403) {
                dispatch({ type: 'SET_STATUS', payload: { status: 'UNAUTHORIZED' } });
                return; // Abort connection
             }
          }
        }
      } catch (err) {
        console.error('Failed to hydrate state', err);
        dispatch({ type: 'SET_STATUS', payload: { status: 'CONNECTION_ERROR' } });
      }
    };

    const connectSSE = (apiUrl, capability) => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const maxSeq = lastProcessedSequence.current !== null ? lastProcessedSequence.current : '';
      
      const es = new EventSource(`${apiUrl}/api/stream?task_id=${encodeURIComponent(taskId)}&capability=${encodeURIComponent(capability)}&last_event_id=${maxSeq}`);
      eventSourceRef.current = es;

      es.onopen = () => {
        retryCountRef.current = 0; // Reset retries on successful connection
      };

      const handleEvent = (e, callback) => {
        try {
          const parsed = JSON.parse(e.data);
          // 4. CREATE ONE CANONICAL EVENT SCHEMA
          const normalizedEvent = {
            sequence: parsed.sequence,
            event: parsed.event,
            status: parsed.status, // authoritative lifecycle status
            timestamp: parsed.timestamp,
            data: parsed.data || {}
          };
          
          if (normalizedEvent.sequence !== undefined) {
            if (lastProcessedSequence.current !== null && normalizedEvent.sequence <= lastProcessedSequence.current) {
              return;
            }
            lastProcessedSequence.current = normalizedEvent.sequence;
          }
          
          callback(normalizedEvent);
        } catch (err) {
          console.error('Error parsing event data', err);
        }
      };

      es.addEventListener('pipeline_started', (e) => {
        handleEvent(e, (evt) => dispatch({ type: 'SET_STATUS', payload: { status: evt.status || 'STARTING' } }));
      });

      es.addEventListener('status_update', (e) => {
        handleEvent(e, (evt) => dispatch({ type: 'SET_STATUS', payload: { status: evt.status } }));
      });

      es.addEventListener('agent_complete', (e) => {
        handleEvent(e, (evt) => {
            dispatch({
                type: 'AGENT_COMPLETE', 
                payload: { ...evt.data, status: evt.status }
            });
        });
      });

      es.addEventListener('approval_required', (e) => {
        handleEvent(e, (evt) => {
          if (evt.status !== 'WAITING_FOR_APPROVAL') {
            console.warn("Ignoring approval_required event because status is not WAITING_FOR_APPROVAL");
            const apiUrl = import.meta.env.VITE_API_URL || '';
            const viewToken = credentialStore.getViewToken(taskId);
            const headers = {};
            if (viewToken) headers['Authorization'] = `Bearer ${viewToken}`;
            fetchState(apiUrl, headers);
            return;
          }
          const payload = evt.data?.fix || evt.data;
          const cycleId = evt.data?.approval_cycle_id;
          const fixId = evt.data?.fix_id || payload?.fix_id;
          
          if (!payload || !cycleId || !fixId) {
            console.error("Protocol error: approval_required event missing cycle ID or payload identities", evt.data);
            dispatch({ type: 'SET_ERROR', payload: { error: "Recoverable sync error: missing approval state identities" }});
            return;
          }
          dispatch({ type: 'APPROVAL_REQUIRED', payload: { approval_payload: payload, approval_state: 'pending', awaiting_approval: true, status: evt.status, approval_cycle_id: cycleId } });
        });
      });

      es.addEventListener('approval_resolved', (e) => {
        handleEvent(e, (evt) => {
          if (evt.status !== 'WAITING_FOR_DISPATCH' && evt.status !== 'NEEDS_REVIEW') {
            console.warn("Ignoring approval_resolved event because status is invalid");
            const apiUrl = import.meta.env.VITE_API_URL || '';
            const viewToken = credentialStore.getViewToken(taskId);
            const headers = {};
            if (viewToken) headers['Authorization'] = `Bearer ${viewToken}`;
            fetchState(apiUrl, headers);
            return;
          }
          const eventCycleId = evt.data.approval_cycle_id;
          const eventFixId = evt.data.fix_id;
          
          if (stateRef.current.approval_cycle_id && eventCycleId && stateRef.current.approval_cycle_id !== eventCycleId) {
            return;
          }
          if (stateRef.current.approval_payload?.fix_id && eventFixId && stateRef.current.approval_payload.fix_id !== eventFixId) {
            return;
          }
          
          if (eventCycleId) {
            credentialStore.clearCurrentToken(taskId, eventCycleId);
          }
          
          dispatch({ type: 'APPROVAL_RESOLVED', payload: { 
            current_fix: null, 
            decision: evt.data.decision, 
            approval_state: evt.data.decision, 
            awaiting_approval: false, 
            status: evt.status,
            approval_cycle_id: eventCycleId,
            fix_id: eventFixId
          }});
        });
      });

      es.addEventListener('waiting_for_llm_capacity', (e) => {
        handleEvent(e, (evt) => {
          if (evt.status !== 'WAITING_FOR_LLM_CAPACITY') {
            console.warn("Ignoring waiting_for_llm_capacity event because status is not WAITING_FOR_LLM_CAPACITY");
            const apiUrl = import.meta.env.VITE_API_URL || '';
            const viewToken = credentialStore.getViewToken(taskId);
            const headers = {};
            if (viewToken) headers['Authorization'] = `Bearer ${viewToken}`;
            fetchState(apiUrl, headers);
            return;
          }
          dispatch({ type: 'SET_LLM_WAITING', payload: { 
                 pipeline_error: evt.data.reason || evt.data.error, 
                 status: evt.status, 
                 retry_count: evt.data.retry_count, 
                 next_retry: evt.data.next_retry,
                 model: evt.data.model,
                 reset_time: evt.data.reset_time,
                 last_error: evt.data.last_error
          } });
        });
      });

      es.addEventListener('pipeline_complete', (e) => {
        handleEvent(e, (evt) => {
          if (evt.status !== 'COMPLETED') {
            console.warn("Ignoring pipeline_complete event because status is not COMPLETED");
            const apiUrl = import.meta.env.VITE_API_URL || '';
            const viewToken = credentialStore.getViewToken(taskId);
            const headers = {};
            if (viewToken) headers['Authorization'] = `Bearer ${viewToken}`;
            fetchState(apiUrl, headers);
            return;
          }
          dispatch({ type: 'SET_STATUS', payload: { status: evt.status } });
          dispatch({ type: 'SET_PR', payload: {
              confidence: evt.data.confidence_score,
              pr_url: evt.data.pr_url,
              pr_error: evt.data.pr_error
          } });
          es.close();
        });
      });

      es.addEventListener('pipeline_error', (e) => {
        if (e.data) {
          handleEvent(e, (evt) => {
            if (evt.status !== 'FAILED') {
              console.warn("Ignoring pipeline_error event because status is not FAILED");
              const apiUrl = import.meta.env.VITE_API_URL || '';
            const viewToken = credentialStore.getViewToken(taskId);
            const headers = {};
            if (viewToken) headers['Authorization'] = `Bearer ${viewToken}`;
            fetchState(apiUrl, headers);
              return;
            }
            dispatch({ type: 'SET_ERROR', payload: { status: evt.status, pipeline_error: evt.data.error } });
            es.close();
          });
        }
      });

      es.onerror = (err) => {
        console.error('SSE connection error:', err);
        es.close();
        if (retryCountRef.current < MAX_RETRIES) {
          retryCountRef.current += 1;
          const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000);
          console.log(`Reconnecting SSE in ${delay}ms... (Attempt ${retryCountRef.current})`);
          retryTimeoutRef.current = setTimeout(() => {
            if (isMounted) {
              // Re-hydrate to get a new capability before reconnecting
              hydrateAndConnect();
            }
          }, delay);
        } else {
          dispatch({ type: 'SET_ERROR', payload: { pipeline_error: 'Connection lost. Please refresh the page.', status: 'CONNECTION_ERROR' } });
        }
      };
    };

    hydrateAndConnect();

    return () => {
      isMounted = false;
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
    };
  }, [taskId, dispatch]);

  // Clean up the active token if the cycle becomes resolved or reaches a terminal state
  useEffect(() => {
    if (!taskId || !state.approval_cycle_id) return;
    const terminalStates = ['COMPLETED', 'FAILED', 'NEEDS_REVIEW'];
    const isResolved = !state.awaiting_approval || terminalStates.includes(state.status);
    
    if (terminalStates.includes(state.status)) {
      credentialStore.clearAllTokens(taskId);
    } else if (isResolved) {
      credentialStore.clearCurrentToken(taskId, state.approval_cycle_id);
    }
  }, [state.awaiting_approval, state.status, state.approval_cycle_id, taskId]);

  return state;
}
