export const AGENT_ORDER = [
  'repo_mapper',
  'dependency_analyzer',
  'static_analysis',
  'bug_investigator',
  'repair_planner',
  'code_generator',
  'validator',
  'security_verifier',
  'pr_author'
];

export function reconstructProgress(state) {
  let completedAgents = new Set(state.completed_nodes || []);
  let currentAgent = null;
  const isError = state.status === 'FAILED';
  const isPaused = state.status === 'WAITING_FOR_APPROVAL';
  const isWaitingLLM = state.status === 'WAITING_FOR_LLM_CAPACITY';

  const lastCompleted = state.last_completed_node;
  let lastCompletedIdx = -1;

  if (lastCompleted) {
    lastCompletedIdx = AGENT_ORDER.indexOf(lastCompleted);
  }

  // 1. If we have a last_completed_node, ensure it and all predecessors are marked completed
  // (unless it's skipped, but codesentinel pipeline is strictly sequential so if a node is
  // completed, all its predecessors must have been completed or skipped. For robustness, 
  // we just mark them all completed as requested: "If last_completed_node is repo_mapper, 
  // then repo_mapper must be Verified... If pr_author, all nine agents must be Verified."
  if (lastCompletedIdx >= 0) {
    for (let i = 0; i <= lastCompletedIdx; i++) {
      completedAgents.add(AGENT_ORDER[i]);
    }
  }

  // 2. Determine currentAgent
  if (state.status !== 'COMPLETED' && state.status !== 'NEEDS_REVIEW') {
    if (lastCompletedIdx >= 0 && lastCompletedIdx < AGENT_ORDER.length - 1) {
      currentAgent = AGENT_ORDER[lastCompletedIdx + 1];
    } else if (!lastCompleted && (state.status === 'RUNNING' || state.status === 'DISPATCHING' || isError || isWaitingLLM)) {
      currentAgent = AGENT_ORDER[0];
    }
  }

  // Overrides for specific paused states
  if (isPaused) {
    currentAgent = 'repair_planner';
  }

  // 3. Compute furthestIndex and skipped agents
  const skippedAgents = new Set();
  let furthestIndex = -1;
  if (currentAgent) {
    furthestIndex = AGENT_ORDER.indexOf(currentAgent);
  }
  
  completedAgents.forEach(agent => {
    const idx = AGENT_ORDER.indexOf(agent);
    if (idx > furthestIndex) {
      furthestIndex = idx;
    }
  });

  AGENT_ORDER.forEach((agent, index) => {
    if (index < furthestIndex && !completedAgents.has(agent)) {
      skippedAgents.add(agent);
    }
  });

  return {
    completedAgents,
    currentAgent,
    skippedAgents,
    isError,
    isPaused,
    isWaitingLLM
  };
}
