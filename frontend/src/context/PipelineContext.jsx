/* eslint-disable react-refresh/only-export-components */
import { createContext, useReducer } from 'react';

export const PipelineContext = createContext();

const initialState = {
  status: 'QUEUED',
  task_id: null,
  repo_url: null,
  completed_nodes: [],
  findings: [],
  dependency_findings: [],
  static_findings: [],
  investigated_issues: [],
  repair_plan: null,
  approval_payload: null,
  patches: [],
  validation_results: [],
  security_verification: null,
  confidence: null,
  approval_state: null,
  approval_decision: null,
  pr_url: null,
  pr_error: null,
  retry_count: 0,
  security_retry_state: 0,
  llm_waiting_state: false,
  last_completed_node: null,
  rag_status: null,
  last_sequence: null,
  pipeline_error: null,
  agents: [],
  awaiting_approval: false,
  current_stage: null,
  current_agent: null,
  approval_token_loading: false,
  approval_token_ready: false,
  token_recovery_required: false,
  token_ready_cycle_id: null,
  token_ready_fix_id: null
};

function pipelineReducer(state, action) {
  const TERMINAL_STATES = ['COMPLETED', 'FAILED', 'NEEDS_REVIEW'];
  if (
    TERMINAL_STATES.includes(state.status) && 
    action.type !== 'HYDRATE_STATE' && 
    action.type !== 'SET_APPROVAL_TOKEN' &&
    action.type !== 'AGENT_START'
  ) {
    return state;
  }
  
  switch (action.type) {
    case 'AGENT_START':
      return { ...initialState, status: 'RUNNING' };
    case 'FETCH_TOKEN_START':
      return { ...state, approval_token_loading: true, approval_token_ready: false };
    case 'FETCH_TOKEN_SUCCESS':
      return { 
        ...state, 
        approval_token_loading: false, 
        approval_token_ready: true, 
        token_recovery_required: false,
        token_ready_cycle_id: action.payload?.cycleId || null,
        token_ready_fix_id: action.payload?.fixId || null
      };
    case 'FETCH_TOKEN_ERROR':
      return { ...state, approval_token_loading: false, approval_token_ready: false };
    case 'REQUIRE_RECOVERY':
      return { ...state, approval_token_loading: false, approval_token_ready: false, token_recovery_required: true };
    case 'HYDRATE_STATE':
      return {
        ...state,
        ...action.payload
      };
    case 'AGENT_COMPLETE': {
      const AGENT_ORDER = [
        'repo_mapper', 'dependency_analyzer', 'static_analysis',
        'bug_investigator', 'repair_planner', 'code_generator',
        'validator', 'security_verifier', 'pr_author'
      ];
      const completedAgent = action.payload.agent;
      if (state.completed_nodes.includes(completedAgent)) {
        return state;
      }
      const idx = AGENT_ORDER.indexOf(completedAgent);
      let nextAgent = state.current_agent;
      if (idx >= 0 && idx < AGENT_ORDER.length - 1) {
          nextAgent = AGENT_ORDER[idx + 1];
      }
      return {
        ...state,
        last_completed_node: completedAgent,
        current_agent: nextAgent,
        agents: state.agents.some(a => a.agent === completedAgent) ? state.agents : [...state.agents, action.payload],
        completed_nodes: [...state.completed_nodes, completedAgent]
      };
    }
    case 'SET_STATUS':
      return { 
        ...state, 
        status: action.payload.status,
        llm_waiting_state: action.payload.status === 'RUNNING' ? false : state.llm_waiting_state,
        next_retry: action.payload.status === 'RUNNING' ? null : state.next_retry,
        reset_time: action.payload.status === 'RUNNING' ? null : state.reset_time,
        pipeline_error: action.payload.status === 'RUNNING' ? null : state.pipeline_error
      };
    case 'APPROVAL_REQUIRED': {
      const isNewCycle = (action.payload.approval_cycle_id !== undefined && action.payload.approval_cycle_id !== state.approval_cycle_id);
      const isNewFix = (action.payload.approval_payload?.fix_id !== undefined && action.payload.approval_payload?.fix_id !== state.approval_payload?.fix_id);
      const resetTokenState = isNewCycle || isNewFix;
      return { 
        ...state, 
        status: action.payload.status || state.status,
        approval_payload: action.payload.approval_payload !== undefined ? action.payload.approval_payload : state.approval_payload,
        approval_state: action.payload.approval_state !== undefined ? action.payload.approval_state : state.approval_state,
        awaiting_approval: action.payload.awaiting_approval !== undefined ? action.payload.awaiting_approval : state.awaiting_approval,
        approval_cycle_id: action.payload.approval_cycle_id !== undefined ? action.payload.approval_cycle_id : state.approval_cycle_id,
        approval_decision_loading: false,
        ...(resetTokenState && {
            approval_token_loading: false,
            approval_token_ready: false,
            token_recovery_required: false,
            token_ready_cycle_id: null,
            token_ready_fix_id: null
        })
      };
    }
    case 'APPROVAL_DECISION_START':
      return { ...state, approval_decision_loading: true };
    case 'APPROVAL_DECISION_END':
      return { ...state, approval_decision_loading: false };
    case 'APPROVAL_RESOLVED':
      // Validate identity
      if (action.payload.approval_cycle_id && state.approval_cycle_id && action.payload.approval_cycle_id !== state.approval_cycle_id) return state;
      if (action.payload.fix_id && state.approval_payload?.fix_id && action.payload.fix_id !== state.approval_payload.fix_id) return state;

      return { 
        ...state, 
        status: action.payload.status || state.status,
        approval_payload: action.payload.approval_payload !== undefined ? action.payload.approval_payload : state.approval_payload,
        approval_state: action.payload.approval_state !== undefined ? action.payload.approval_state : state.approval_state,
        approval_decision: action.payload.approval_decision !== undefined ? action.payload.approval_decision : action.payload.decision !== undefined ? action.payload.decision : state.approval_decision,
        awaiting_approval: action.payload.awaiting_approval !== undefined ? action.payload.awaiting_approval : state.awaiting_approval,
        approval_token_loading: false,
        approval_token_ready: false,
        token_recovery_required: false,
        token_ready_cycle_id: null,
        token_ready_fix_id: null,
        approval_decision_loading: false
      };
    case 'SET_PR':
      return { 
        ...state, 
        pr_url: action.payload.pr_url,
        pr_error: action.payload.pr_error,
        confidence: action.payload.confidence
      };
    case 'SET_ERROR':
      return { 
        ...state, 
        status: action.payload.status || 'FAILED',
        pipeline_error: action.payload.pipeline_error 
      };
    case 'SET_LLM_WAITING':
      return {
        ...state,
        status: action.payload.status || 'WAITING_FOR_LLM_CAPACITY',
        llm_waiting_state: action.payload.llm_waiting_state !== undefined ? action.payload.llm_waiting_state : true,
        retry_count: action.payload.retry_count !== undefined ? action.payload.retry_count : state.retry_count,
        next_retry: action.payload.next_retry !== undefined ? action.payload.next_retry : state.next_retry,
        pipeline_error: action.payload.pipeline_error !== undefined ? action.payload.pipeline_error : state.pipeline_error,
        model: action.payload.model !== undefined ? action.payload.model : state.model,
        reset_time: action.payload.reset_time !== undefined ? action.payload.reset_time : state.reset_time,
        last_error: action.payload.last_error !== undefined ? action.payload.last_error : state.last_error
      };

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
