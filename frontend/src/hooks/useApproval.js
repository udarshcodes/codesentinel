import { useContext } from 'react';
import { PipelineContext } from '../context/PipelineContext';

export function useApproval(taskId) {
  const { state, dispatch } = useContext(PipelineContext);

  const submitDecision = async (decision) => {
    try {
      const actualTaskId = taskId.split('/').pop();
      const response = await fetch(`/api/approve/${encodeURIComponent(actualTaskId)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ decision }),
      });

      if (response.ok) {
        dispatch({ type: 'APPROVAL_RESOLVED' });
        return true;
      }
      return false;
    } catch (err) {
      console.error('Error submitting approval decision', err);
      return false;
    }
  };

  const approve = () => submitDecision('approved');
  const reject = () => submitDecision('rejected');

  return {
    approve,
    reject,
    awaitingApproval: state.awaiting_approval,
    currentFix: state.current_fix
  };
}
