import { useEffect, useContext, useRef } from 'react';
import { PipelineContext } from '../context/PipelineContext';

export function usePipeline(taskId) {
  const { state, dispatch } = useContext(PipelineContext);
  const eventSourceRef = useRef(null);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef(null);
  const MAX_RETRIES = 5;

  useEffect(() => {
    if (!taskId) return;

    const connectSSE = () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const es = new EventSource(`/api/stream?task_id=${encodeURIComponent(taskId)}`);
      eventSourceRef.current = es;

      dispatch({ type: 'AGENT_START' });
      retryCountRef.current = 0; // Reset retries on successful connection

      es.addEventListener('agent_complete', (e) => {
        try {
          const data = JSON.parse(e.data);
          dispatch({ type: 'AGENT_COMPLETE', payload: data });
          
          const innerData = data.data || {};
          if (innerData.static_findings) {
            dispatch({ type: 'FINDINGS_UPDATED', payload: innerData.static_findings });
          }
          if (innerData.patches) {
            dispatch({ type: 'PATCHES_UPDATED', payload: innerData.patches });
          }
        } catch (err) {
          console.error('Error parsing agent_complete data', err);
        }
      });

      es.addEventListener('approval_required', (e) => {
        try {
          const data = JSON.parse(e.data);
          dispatch({ type: 'APPROVAL_REQUIRED', payload: data });
        } catch (err) {
          console.error('Error parsing approval_required data', err);
        }
      });


      es.addEventListener('pipeline_complete', (e) => {
        try {
          const data = JSON.parse(e.data);
          dispatch({ type: 'PIPELINE_COMPLETE', payload: data });
          es.close();
        } catch (err) {
          console.error('Error parsing pipeline_complete data', err);
        }
      });

      es.addEventListener('error', (e) => {
        // Server-sent named 'error' events have e.data; native errors don't
        if (e.data) {
          try {
            const data = JSON.parse(e.data);
            dispatch({ type: 'PIPELINE_ERROR', payload: data });
            es.close();
          } catch (err) {
            console.error('Error parsing error event data', err);
          }
        }
        // Native EventSource errors are handled by onerror below
      });

      es.onerror = () => {
        es.close();
        retryCountRef.current += 1;
        if (retryCountRef.current > MAX_RETRIES) {
          console.error('SSE max retries reached, giving up.');
          dispatch({ type: 'PIPELINE_ERROR', payload: { error: 'Connection lost. Please refresh.' } });
          return;
        }
        const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000);
        console.error(`SSE connection error, retry ${retryCountRef.current}/${MAX_RETRIES} in ${delay}ms...`);
        retryTimeoutRef.current = setTimeout(() => {
          connectSSE();
        }, delay);
      };
    };

    connectSSE();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
    };
  }, [taskId, dispatch]);

  return state;
}

