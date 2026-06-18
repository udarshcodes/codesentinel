import { useEffect, useContext, useRef } from 'react';
import { PipelineContext } from '../context/PipelineContext';

export function usePipeline(taskId) {
  const { state, dispatch } = useContext(PipelineContext);
  const eventSourceRef = useRef(null);

  useEffect(() => {
    if (!taskId) return;

    let retryTimeout;

    const connectSSE = () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const es = new EventSource(`/api/stream?task_id=${encodeURIComponent(taskId)}`);
      eventSourceRef.current = es;

      dispatch({ type: 'AGENT_START' });

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
        try {
          const data = JSON.parse(e.data);
          dispatch({ type: 'PIPELINE_ERROR', payload: data });
          es.close();
        } catch (err) {
          console.error('Error parsing error event data', err);
        }
      });

      es.onerror = (e) => {
        console.error('SSE connection error, retrying in 3 seconds...');
        es.close();
        retryTimeout = setTimeout(() => {
          connectSSE();
        }, 3000);
      };
    };

    connectSSE();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
      if (retryTimeout) {
        clearTimeout(retryTimeout);
      }
    };
  }, [taskId, dispatch]);

  return state;
}
