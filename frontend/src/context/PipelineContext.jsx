/* eslint-disable react-refresh/only-export-components */
import { createContext, useReducer } from 'react';

export const PipelineContext = createContext();

const initialState = {
  status: 'idle',
  agents: [],
  findings: [],
  patches: [],
  confidence_score: null,
  pr_url: null,
  pr_error: null,
  awaiting_approval: false,
  current_fix: null
};

function pipelineReducer(state, action) {
  switch (action.type) {
    case 'AGENT_START':
      return { ...initialState, status: 'running' };
    case 'AGENT_COMPLETE':
      return { ...state, agents: [...state.agents, action.payload] };
    case 'FINDINGS_UPDATED':
      return { ...state, findings: action.payload };
    case 'PATCHES_UPDATED':
      return { ...state, patches: action.payload };
    case 'APPROVAL_REQUIRED':
      return { ...state, awaiting_approval: true, current_fix: action.payload };
    case 'APPROVAL_RESOLVED':
      return { ...state, awaiting_approval: false, current_fix: null };

    case 'PIPELINE_COMPLETE':
      return { 
        ...state, 
        status: 'complete', 
        confidence_score: action.payload.confidence_score, 
        pr_url: action.payload.pr_url,
        pr_error: action.payload.pr_error 
      };
    case 'PIPELINE_ERROR':
      return { ...state, status: 'error', pipeline_error: action.payload?.error };

    case 'RESET':
      return initialState;
    default:
      return state;
  }
}

export function PipelineProvider({ children }) {
  const [state, dispatch] = useReducer(pipelineReducer, initialState);

  return (
    <PipelineContext.Provider value={{ state, dispatch }}>
      {children}
    </PipelineContext.Provider>
  );
}
