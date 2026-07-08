

const AGENT_ORDER = [
  'repo_mapper',
  'dependency_analyzer',
  'static_analysis',
  'bug_investigator',
  'repair_planner',
  'code_generator',
  'validator',
  'security_verifier',
  'pr_author'
]

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

export default function PipelineView({ events }) {
  // Determine which agent is currently active or completed
  const completedAgents = new Set()
  let currentAgent = null
  let isError = false

  events.forEach(e => {
    if (e.event === 'agent_complete' && e.data?.agent) {
      completedAgents.add(e.data.agent)
    }
    if (e.event === 'approval_required') {
      currentAgent = 'repair_planner' // Paused here
    }
    if (e.event === 'error') {
      isError = true
    }
  })

  // The active agent is the first one not in completedAgents
  if (isError) {
    currentAgent = null
  } else if (!currentAgent && !isError && (events.length === 0 || events[events.length - 1].event !== 'pipeline_complete')) {
    currentAgent = AGENT_ORDER.find(a => !completedAgents.has(a))
  }

  // Determine implicitly skipped agents (e.g. if a later agent is active/completed, earlier uncompleted ones were skipped)
  const skippedAgents = new Set()
  let furthestIndex = -1
  if (currentAgent) {
    furthestIndex = AGENT_ORDER.indexOf(currentAgent)
  }
  completedAgents.forEach(agent => {
    const idx = AGENT_ORDER.indexOf(agent)
    if (idx > furthestIndex) {
      furthestIndex = idx
    }
  })

  AGENT_ORDER.forEach((agent, index) => {
    if (index < furthestIndex && !completedAgents.has(agent)) {
      skippedAgents.add(agent)
    }
  })

  return (
    <div className="glass-panel p-6 sm:p-8 w-full max-w-6xl mx-auto mb-8 !rounded-[2.5rem]">
      <h2 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-3">
        <svg className="w-6 h-6 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
        Live Agent Pipeline
      </h2>
      
      <div className="relative">
        {/* Vertical connecting line */}
        <div className="absolute left-[21px] top-4 bottom-4 w-[2px] bg-border rounded-full"></div>
        
        <div className="space-y-6">
          {AGENT_ORDER.map((agentKey, index) => {
            const isCompleted = completedAgents.has(agentKey)
            const isSkipped = skippedAgents.has(agentKey)
            const isActive = currentAgent === agentKey && !isError
            
            let statusColor = 'bg-muted border-border text-muted-foreground' // Pending
          
            let glowEffect = ''
            
            if (isCompleted) {
              statusColor = 'bg-green-500/10 border-green-500/30 text-green-500'
            } else if (isSkipped) {
              statusColor = 'bg-muted border-border text-muted-foreground opacity-60'
            } else if (isActive) {
              statusColor = 'bg-primary/10 border-primary text-primary'
              glowEffect = 'shadow-lg shadow-primary/30'
            } else if (isError && currentAgent === agentKey) {
              statusColor = 'bg-destructive/10 border-destructive text-destructive'
              glowEffect = 'shadow-lg shadow-destructive/30'
            }

            return (
              <div key={agentKey} className="relative flex items-center gap-4 group">
                <div className={`relative z-10 flex items-center justify-center w-11 h-11 rounded-full border-2 transition-all duration-300 ${statusColor} bg-card ${glowEffect}`}>
                  {isCompleted ? (
                    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : isSkipped ? (
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                    </svg>
                  ) : isActive ? (
                    <span className="relative flex h-3 w-3">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span>
                    </span>
                  ) : (
                    <span className="text-xs font-bold">{index + 1}</span>
                  )}
                </div>
                
                <div className={`flex-1 p-4 rounded-3xl border transition-all duration-300 ${
                  isActive ? 'bg-card border-primary/30 shadow-lg shadow-primary/10' : 'bg-muted/30 border-border'
                }`}>
                  <h3 className={`text-lg font-semibold transition-colors duration-300 flex items-center gap-2 ${
                    isCompleted ? 'text-foreground' : isSkipped ? 'text-muted-foreground' : isActive ? 'text-foreground' : 'text-muted-foreground'
                  }`}>
                    {AGENT_LABELS[agentKey]}
                    {isSkipped && <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">Skipped</span>}
                  </h3>
                  
                  {isActive && (
                    <p className="text-sm text-primary mt-1 animate-pulse">
                      Processing codebase...
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {isError && (
        <div className="mt-8 p-6 bg-destructive/10 text-destructive border border-destructive/20 rounded-xl max-w-4xl mx-auto flex items-start gap-4">
          <svg className="w-6 h-6 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <h3 className="font-bold text-lg mb-1">Pipeline Failed</h3>
            <p className="text-destructive/90 whitespace-pre-wrap">
              {events.find(e => e.event === 'error')?.data?.error || 'An unexpected error occurred.'}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}