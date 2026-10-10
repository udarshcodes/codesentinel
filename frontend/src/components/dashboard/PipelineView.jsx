import { CheckCircle2, CircleDashed, Loader2, AlertCircle, ShieldAlert } from 'lucide-react'
import { AGENT_ORDER, reconstructProgress, getAgentStatus } from '../../utils/pipelineProgress'

const AGENT_LABELS = {
  repo_mapper: 'Repository Mapping',
  dependency_analyzer: 'Dependency Analysis',
  static_analysis: 'Static Analysis',
  bug_investigator: 'Bug Investigation',
  repair_planner: 'Repair Planning',
  code_generator: 'Code Generation',
  validator: 'Testing & Validation',
  security_verifier: 'Security Verification',
  pr_author: 'PR Generation'
}

export default function PipelineView({ state }) {
  const {
    completedAgents,
    currentAgent,
    skippedAgents,
    isError,
    isPaused,
    isWaitingLLM
  } = reconstructProgress(state);

  let executedCount = 0;
  let verifiedCount = 0;
  let reviewCount = 0;
  let failedCount = 0;

  AGENT_ORDER.forEach((agentKey) => {
    const isCompleted = completedAgents.has(agentKey)
    const isSkipped = skippedAgents.has(agentKey)
    const isActive = currentAgent === agentKey && !isError && !isPaused
    const isAgentPaused = currentAgent === agentKey && isPaused
    const isAgentError = currentAgent === agentKey && isError
    const { statusType } = getAgentStatus(agentKey, state, { isCompleted, isActive, isSkipped, isAgentPaused, isAgentError });
    
    if (isCompleted || isAgentError) {
      executedCount++;
    }
    if (statusType === 'success') {
      verifiedCount++;
    } else if (statusType === 'warning') {
      reviewCount++;
    } else if (statusType === 'error') {
      failedCount++;
    }
  });

  return (
    <div className="bg-card border border-border p-6 sm:p-8 w-full max-w-6xl mx-auto mb-8 rounded-[1.5rem] shadow-sm">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between mb-8 gap-4">
        <h2 className="text-xl font-semibold text-foreground flex items-center gap-3">
          <Loader2 className={`w-5 h-5 text-primary ${!isError && currentAgent ? 'animate-spin' : ''}`} />
          Autonomous Agent Mesh
        </h2>
        <div className="flex flex-wrap gap-3 text-xs">
          <span className="px-2 py-1 bg-muted text-muted-foreground rounded-md font-medium">{executedCount} Executed</span>
          {verifiedCount > 0 && <span className="px-2 py-1 bg-[#22C55E]/10 text-[#22C55E] rounded-md font-medium">{verifiedCount} Verified</span>}
          {reviewCount > 0 && <span className="px-2 py-1 bg-[#F59E0B]/10 text-[#F59E0B] rounded-md font-medium">{reviewCount} Review Req</span>}
          {failedCount > 0 && <span className="px-2 py-1 bg-[#EF4444]/10 text-[#EF4444] rounded-md font-medium">{failedCount} Failed</span>}
        </div>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {AGENT_ORDER.map((agentKey) => {
          const isCompleted = completedAgents.has(agentKey)
          const isSkipped = skippedAgents.has(agentKey)
          const isActive = currentAgent === agentKey && !isError && !isPaused
          const isAgentPaused = currentAgent === agentKey && isPaused
          const isAgentError = currentAgent === agentKey && isError
          
          let cardStyle = 'bg-background border-border text-muted-foreground'
          let icon = <CircleDashed className="w-5 h-5 opacity-40" />
          
          const { displayStatus, statusType } = getAgentStatus(agentKey, state, { isCompleted, isActive, isSkipped, isAgentPaused, isAgentError });

          if (statusType === 'success') {
            cardStyle = 'bg-[#22C55E]/10 border-[#22C55E]/20 text-[#22C55E]'
            icon = <CheckCircle2 className="w-5 h-5" />
          } else if (statusType === 'warning') {
            cardStyle = 'bg-[#F59E0B]/10 border-[#F59E0B]/30 text-[#F59E0B]'
            icon = <AlertCircle className="w-5 h-5" />
          } else if (statusType === 'error') {
            cardStyle = 'bg-[#EF4444]/10 border-[#EF4444]/30 text-[#EF4444]'
            icon = <ShieldAlert className="w-5 h-5" />
          } else if (isActive) {
            cardStyle = 'bg-primary/10 border-primary text-primary shadow-[0_0_15px_rgba(139,92,246,0.15)]'
            icon = <Loader2 className="w-5 h-5 animate-spin" />
          } else if (isSkipped) {
            cardStyle = 'bg-background border-border text-muted-foreground opacity-50'
          }

          return (
            <div key={agentKey} className={`relative flex items-center gap-4 p-4 rounded-xl border transition-all duration-500 ${cardStyle}`}>
              <div className="shrink-0">
                {icon}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className={`text-sm font-medium truncate ${isActive ? 'text-primary' : (isCompleted || statusType !== 'pending') ? 'text-foreground' : 'text-muted-foreground'}`}>
                  {AGENT_LABELS[agentKey]}
                </h3>
                <p className="text-xs truncate opacity-70" title={displayStatus}>
                  {displayStatus}
                </p>
              </div>
            </div>
          )
        })}
      </div>

      {isError && (
        <div className="mt-8 p-6 bg-[#EF4444]/10 border border-[#EF4444]/20 rounded-xl flex items-start gap-4 text-[#EF4444]">
          <ShieldAlert className="w-6 h-6 shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-lg mb-1">Pipeline Execution Failed</h3>
            <p className="opacity-90 whitespace-pre-wrap font-mono text-sm">
              {state.pipeline_error || 'An unexpected error occurred during analysis.'}
            </p>
          </div>
        </div>
      )}

      {state.status === 'NEEDS_REVIEW' && (
        <div className="mt-8 p-6 bg-[#F59E0B]/10 border border-[#F59E0B]/20 rounded-xl flex items-start gap-4 text-[#F59E0B]">
          <ShieldAlert className="w-6 h-6 shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-lg mb-1">Pipeline Review Required</h3>
            <p className="opacity-90 whitespace-pre-wrap font-mono text-sm">
              {state.pr_error || 'The pipeline requires manual review to proceed or abort.'}
            </p>
          </div>
        </div>
      )}

      {isWaitingLLM && (
        <div className="mt-8 p-6 bg-[#F59E0B]/10 border border-[#F59E0B]/20 rounded-xl flex items-start gap-4 text-[#F59E0B]">
          <AlertCircle className="w-6 h-6 shrink-0 mt-0.5" />
          <div>
            <h3 className="font-semibold text-lg mb-1">LLM Capacity Exhausted</h3>
            <p className="opacity-90 whitespace-pre-wrap font-mono text-sm">
              {state.pipeline_error || 'The system has reached the LLM rate limits. The pipeline is paused and will automatically resume when capacity is available.'}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

