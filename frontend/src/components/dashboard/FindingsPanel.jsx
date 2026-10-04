import { useState } from 'react'
import { ShieldAlert, FileCode2 } from 'lucide-react'

export default function FindingsPanel({ state }) {
  const [selectedId, setSelectedId] = useState(null)

  let allIssues = []
  
  if (state.static_findings && state.static_findings.length > 0) {
    state.static_findings.forEach(f => {
      allIssues.push({
        id: `${f.tool}-${f.rule}-${f.file}-${f.line || 'global'}`,
        title: `[${f.tool || 'Static'}] ${f.rule || 'Finding'}`,
        severity: f.severity || 'low',
        category: f.category || 'Security',
        issue: f.issue || f.description || 'Static analysis finding.',
        file: f.file || 'unknown',
        line: f.line || 'unknown',
        status: 'Identified'
      })
    })
  }

  if (state.investigated_issues && state.investigated_issues.length > 0) {
    allIssues = state.investigated_issues.map(issue => ({
      id: `${issue.id || 'bug'}-${issue.file || 'unknown'}-${issue.line || 'global'}`,
      title: issue.title || 'Investigated Issue',
      severity: issue.severity || 'high',
      category: issue.category || 'Vulnerability',
      issue: issue.root_cause || issue.description || 'No description.',
      file: (issue.affected_files && issue.affected_files.length > 0) ? issue.affected_files[0] : 'Multiple',
      line: issue.line || 'various',
      status: 'Confirmed'
    }))
  }

  if (allIssues.length === 0) return null

  const getSeverityBadge = (severity) => {
    const s = severity?.toLowerCase() || 'low'
    switch (s) {
      case 'critical':
        return <span className="bg-[#EF4444]/10 text-[#EF4444] border border-[#EF4444]/30 px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider">Critical</span>
      case 'high':
        return <span className="bg-[#EF4444]/10 text-[#EF4444] border border-[#EF4444]/30 px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider">High</span>
      case 'medium':
        return <span className="bg-[#F59E0B]/10 text-[#F59E0B] border border-[#F59E0B]/30 px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider">Medium</span>
      default:
        return <span className="bg-muted text-muted-foreground border border-border px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider">Low</span>
    }
  }

  return (
    <div className="bg-card border border-border w-full max-w-6xl mx-auto mb-8 rounded-[1.5rem] shadow-sm overflow-hidden">
      <div className="p-6 border-b border-border bg-secondary/50 flex items-center gap-3">
        <ShieldAlert className="w-5 h-5 text-primary" />
        <h2 className="text-lg font-semibold text-foreground">Security Findings</h2>
        <span className="bg-muted text-muted-foreground px-2.5 py-0.5 rounded-full text-xs font-bold ml-2">
          {allIssues.length}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-border bg-secondary/20">
              <th className="px-6 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Severity</th>
              <th className="px-6 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Category</th>
              <th className="px-6 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Issue</th>
              <th className="px-6 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Location</th>
              <th className="px-6 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {allIssues.map((issue) => {
              const isSelected = selectedId === issue.id
              return (
                <tr 
                  key={issue.id} 
                  onClick={() => setSelectedId(isSelected ? null : issue.id)}
                  className={`cursor-pointer transition-colors hover:bg-accent ${isSelected ? 'bg-primary/5 border-l-2 border-l-primary' : 'border-l-2 border-l-transparent'}`}
                >
                  <td className="px-6 py-4 whitespace-nowrap">
                    {getSeverityBadge(issue.severity)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {issue.category}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-col">
                      <span className={`text-sm font-medium ${isSelected ? 'text-primary' : 'text-foreground'}`}>
                        {issue.title}
                      </span>
                      {isSelected && (
                        <span className="text-sm text-muted-foreground mt-1 line-clamp-2">
                          {issue.issue}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground font-mono">
                      <FileCode2 className="w-4 h-4 opacity-70" />
                      {issue.file.split('/').pop()}:{issue.line}
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                      <div className="w-1.5 h-1.5 rounded-full bg-primary/50"></div>
                      {issue.status}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
