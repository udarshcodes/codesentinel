

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
  if (!currentAgent && !isError && events.length > 0 && events[events.length - 1].event !== 'pipeline_complete') {
    currentAgent = AGENT_ORDER.find(a => !completedAgents.has(a))
  }

  return (
    <div className="glass-panel p-6 sm:p-8 w-full max-w-6xl mx-auto mb-8 !rounded-[2.5rem]">
      <h2 className="text-2xl font-bold text-slate-900 mb-6 flex items-center gap-3">
        <svg className="w-6 h-6 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
        Live Agent Pipeline
      </h2>
      
      <div className="relative">
        {/* Vertical connecting line */}
        <div className="absolute left-[21px] top-4 bottom-4 w-[2px] bg-slate-200 rounded-full"></div>
        
        <div className="space-y-6">
          {AGENT_ORDER.map((agentKey, index) => {
            const isCompleted = completedAgents.has(agentKey)
            const isActive = currentAgent === agentKey && !isError
            
            let statusColor = 'bg-slate-100 border-slate-300 text-slate-400' // Pending
          
            let glowEffect = ''
            
            if (isCompleted) {
              statusColor = 'bg-green-100 border-green-300 text-green-600'
            } else if (isActive) {
              statusColor = 'bg-blue-100 border-blue-500 text-blue-600'
              glowEffect = 'shadow-[0_0_15px_rgba(59,130,246,0.3)]'
            } else if (isError && currentAgent === agentKey) {
              statusColor = 'bg-red-100 border-red-500 text-red-600'
              glowEffect = 'shadow-[0_0_15px_rgba(239,68,68,0.3)]'
            }

            return (
              <div key={agentKey} className="relative flex items-center gap-4 group">
                <div className={`relative z-10 flex items-center justify-center w-11 h-11 rounded-full border-2 transition-all duration-300 ${statusColor} bg-white ${glowEffect}`}>
                  {isCompleted ? (
                    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                    </svg>
                  ) : isActive ? (
                    <span className="relative flex h-3 w-3">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
                    </span>
                  ) : (
                    <span className="text-xs font-bold">{index + 1}</span>
                  )}
                </div>
                
                <div className={`flex-1 p-4 rounded-3xl border transition-all duration-300 ${
                  isActive ? 'bg-white border-blue-200 shadow-lg shadow-blue-500/10' : 'bg-slate-50 border-slate-200'
                }`}>
                  <h3 className={`text-lg font-semibold transition-colors duration-300 ${
                    isCompleted ? 'text-slate-800' : isActive ? 'text-slate-900' : 'text-slate-400'
                  }`}>
                    {AGENT_LABELS[agentKey]}
                  </h3>
                  
                  {isActive && (
                    <p className="text-sm text-blue-500 mt-1 animate-pulse">
                      Processing codebase...
                    </p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}