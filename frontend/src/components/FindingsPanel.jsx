

export default function FindingsPanel({ events }) {
  // Extract findings from static_analysis or bug_investigator events
  let allIssues = []
  
  events.forEach(e => {
    if (e.event === 'agent_complete' && e.data?.agent === 'static_analysis') {
      const sf = e.data?.data?.static_findings || []
      sf.forEach(f => {
        allIssues.push({
          title: `[${f.tool || 'Static'}] ${f.rule || 'Finding'}`,
          severity: f.severity || 'low',
          root_cause: f.issue || f.description || 'Static analysis finding.',
          affected_files: f.file ? [f.file] : []
        })
      })
    }
    if (e.event === 'agent_complete' && e.data?.agent === 'bug_investigator') {
      const bi = e.data?.data?.investigated_issues || []
      if (bi.length > 0) {
        allIssues = bi
      }
    }
  })

  if (allIssues.length === 0) return null

  const getSeverityBadge = (severity) => {
    const s = severity?.toLowerCase() || 'low'
    switch (s) {
      case 'critical':
        return <span className="bg-destructive/20 text-destructive border border-destructive/50 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest shadow-lg">Critical</span>
      case 'high':
        return <span className="bg-orange-500/20 text-orange-400 border border-orange-500/50 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest shadow-lg">High</span>
      case 'medium':
        return <span className="bg-yellow-500/20 text-yellow-400 border border-yellow-500/50 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest">Medium</span>
      default:
        return <span className="bg-blue-500/20 text-blue-400 border border-blue-500/50 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest">Low</span>
    }
  }

  return (
    <div className="glass-panel p-6 sm:p-8 w-full max-w-6xl mx-auto mb-8 animate-fade-in-up !rounded-[2.5rem]">
      <h2 className="text-2xl font-bold text-foreground mb-6 flex items-center gap-3">
        <svg className="w-6 h-6 text-destructive" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        Investigated Findings
      </h2>

      <div className="grid gap-4">
        {allIssues.map((issue, idx) => (
          <div key={idx} className="bg-card hover:bg-accent transition-colors border border-border rounded-[1.5rem] p-5 shadow-lg shadow-border/50 group">
            <div className="flex justify-between items-start mb-3">
              <h3 className="text-lg font-bold text-foreground transition-colors">{issue.title || `Issue #${idx + 1}`}</h3>
              <div>{getSeverityBadge(issue.severity)}</div>
            </div>
            
            <p className="text-muted-foreground text-sm mb-4 leading-relaxed">
              {issue.root_cause || issue.description || 'No description provided.'}
            </p>

            {Array.isArray(issue.affected_files) && issue.affected_files.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Affected Files</p>
                <div className="flex flex-wrap gap-2">
                  {issue.affected_files.map((file, i) => (
                    <span key={i} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-muted border border-border text-xs font-mono text-foreground">
                      <svg className="w-3 h-3 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                      {file}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}