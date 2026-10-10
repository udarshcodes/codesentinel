import { useState, useMemo } from 'react'
import { ShieldAlert, FileCode2, ChevronDown, ChevronRight, CheckCircle2, AlertCircle, Search } from 'lucide-react'

export default function FindingsPanel({ state }) {
  const [selectedId, setSelectedId] = useState(null)
  const [filterSeverity, setFilterSeverity] = useState('all')
  const [filterCategory, setFilterCategory] = useState('all')
  const [filterStatus, setFilterStatus] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')

  const allIssues = useMemo(() => {
    let issues = []
    
    const resolveStatus = (issueId, initialStatus) => {
      if (!issueId && issueId !== 0) return initialStatus
      
      const patch = state.patches?.find(p => p.issue_id === issueId || p.issue === issueId)
      if (patch) {
        if (!patch.applied) return 'Rejected'
        
        const validation = state.validation_results?.find(v => v.issue_id === issueId || v.issue_description === issueId || v.patch === patch.patch_text)
        if (validation) {
          return validation.passed ? 'Fixed' : 'Needs Review'
        }
        return 'Applied'
      }
      
      const isTerminal = ['COMPLETED', 'NEEDS_REVIEW'].includes(state.status)
      if (isTerminal && initialStatus === 'Identified') return 'Unresolved'
      if (isTerminal && initialStatus === 'Confirmed') return 'Unresolved'
      
      return initialStatus
    }

    const hasInvestigated = state.investigated_issues?.length > 0;

    if (hasInvestigated) {
      state.investigated_issues.forEach((issue, idx) => {
        const id = issue.id !== undefined ? issue.id : `investigated-${idx}`
        
        // Derive title from original finding if generic
        let title = issue.title || 'Investigated Issue';
        if (title === 'Vulnerability' || title === 'Investigated Issue') {
           title = issue.original_finding?.rule || issue.original_finding?.title || title;
        }

        // Improve category mapping
        let category = issue.category || 'Code Quality';
        if (title.toLowerCase().includes('css') || title.toLowerCase().includes('selector')) category = 'Code Quality';
        else if (title.toLowerCase().includes('security') || issue.severity?.toLowerCase() === 'critical') category = 'Security';
        else if (title.toLowerCase().includes('dependency') || title.toLowerCase().includes('outdated')) category = 'Dependency';

        issues.push({
          id,
          title,
          severity: issue.severity?.toLowerCase() || 'high',
          category,
          description: issue.description || issue.root_cause || issue.original_finding?.issue || 'No description provided.',
          file: issue.affected_files?.[0] || issue.file || issue.original_finding?.file || 'unknown',
          line: issue.line || issue.location || issue.original_finding?.line || 'unknown',
          status: resolveStatus(id, 'Confirmed'),
          evidence: issue.evidence || issue.original_finding?.evidence || '',
          remediation: issue.remediation || issue.suggested_fix || ''
        })
      })
    } else {
      const rawFindings = [...(state.static_findings || []), ...(state.dependency_findings || [])];
      rawFindings.forEach((f, idx) => {
        const id = f.id !== undefined ? f.id : `raw-${idx}-${f.file}`
        
        let title = f.title || f.rule || 'Static Finding';
        let category = f.category || 'Code Quality';
        if (title.toLowerCase().includes('css') || title.toLowerCase().includes('selector')) category = 'Code Quality';
        else if (title.toLowerCase().includes('security') || f.severity?.toLowerCase() === 'critical') category = 'Security';
        else if (title.toLowerCase().includes('dependency') || title.toLowerCase().includes('outdated')) category = 'Dependency';

        issues.push({
          id,
          title,
          severity: f.severity?.toLowerCase() || 'low',
          category,
          description: f.description || f.issue || 'No description provided.',
          file: f.file || 'unknown',
          line: f.line || 'unknown',
          status: resolveStatus(id, 'Identified'),
          evidence: f.evidence || '',
          remediation: f.remediation || f.suggested_fix || ''
        })
      })
    }

    // Deduplicate by ID just in case
    const unique = [];
    const seen = new Set();
    for (const issue of issues) {
      if (!seen.has(issue.id)) {
        seen.add(issue.id);
        unique.push(issue);
      }
    }
    return unique;
  }, [state])

  const filteredIssues = useMemo(() => {
    return allIssues.filter(issue => {
      const matchSeverity = filterSeverity === 'all' || issue.severity === filterSeverity;
      const matchCategory = filterCategory === 'all' || issue.category.toLowerCase().includes(filterCategory.toLowerCase());
      const matchStatus = filterStatus === 'all' || issue.status.toLowerCase() === filterStatus.toLowerCase();
      const matchSearch = searchQuery === '' || 
        issue.title.toLowerCase().includes(searchQuery.toLowerCase()) || 
        issue.file.toLowerCase().includes(searchQuery.toLowerCase());
      
      return matchSeverity && matchCategory && matchStatus && matchSearch;
    })
  }, [allIssues, filterSeverity, filterCategory, filterStatus, searchQuery])

  if (allIssues.length === 0) return null

  const counts = {
    total: allIssues.length,
    high: allIssues.filter(i => i.severity === 'high' || i.severity === 'critical').length,
    medium: allIssues.filter(i => i.severity === 'medium').length,
    low: allIssues.filter(i => i.severity === 'low').length,
    resolved: allIssues.filter(i => i.status === 'Fixed').length,
    review: allIssues.filter(i => i.status === 'Needs Review').length,
    isRemediationCandidates: state.investigated_issues?.length > 0
  }

  const getSeverityBadge = (severity) => {
    const s = severity?.toLowerCase() || 'low'
    switch (s) {
      case 'critical':
      case 'high':
        return <span className="bg-[#EF4444]/10 text-[#EF4444] border border-[#EF4444]/30 px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider">High</span>
      case 'medium':
        return <span className="bg-[#F59E0B]/10 text-[#F59E0B] border border-[#F59E0B]/30 px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider">Medium</span>
      default:
        return <span className="bg-muted text-muted-foreground border border-border px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider">Low</span>
    }
  }
  
  const getStatusBadge = (status) => {
    const s = status.toLowerCase()
    if (s === 'fixed') return <span className="flex items-center gap-1.5 text-sm font-medium text-[#22C55E]"><CheckCircle2 className="w-4 h-4"/> Fixed</span>
    if (s === 'needs review') return <span className="flex items-center gap-1.5 text-sm font-medium text-[#F59E0B]"><AlertCircle className="w-4 h-4"/> Needs Review</span>
    if (s === 'rejected' || s === 'unresolved') return <span className="flex items-center gap-1.5 text-sm font-medium text-[#EF4444]"><div className="w-1.5 h-1.5 rounded-full bg-[#EF4444]"></div> {status}</span>
    return <span className="flex items-center gap-1.5 text-sm font-medium text-foreground"><div className="w-1.5 h-1.5 rounded-full bg-primary/50"></div> {status}</span>
  }

  const categories = [...new Set(allIssues.map(i => i.category))]

  return (
    <div id="findings-section" className="bg-card border border-border w-full max-w-6xl mx-auto mb-8 rounded-[1.5rem] shadow-sm overflow-hidden">
      <div className="p-6 border-b border-border bg-secondary/20">
        <div className="flex items-center gap-3 mb-6">
          <ShieldAlert className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold text-foreground">
            {counts.isRemediationCandidates ? 'Remediation Candidates' : 'Detected Findings'}
          </h2>
          <span className="bg-muted text-muted-foreground px-2.5 py-0.5 rounded-full text-xs font-bold ml-2" title="Matches the count in the final summary">
            {counts.total} Total
          </span>
        </div>
        
        <div className="flex flex-wrap gap-4 text-sm mb-6 bg-background p-4 rounded-xl border border-border">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs uppercase tracking-wider font-semibold mb-1">High/Critical</span>
            <span className="font-medium text-[#EF4444]">{counts.high}</span>
          </div>
          <div className="w-px h-8 bg-border"></div>
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs uppercase tracking-wider font-semibold mb-1">Medium</span>
            <span className="font-medium text-[#F59E0B]">{counts.medium}</span>
          </div>
          <div className="w-px h-8 bg-border"></div>
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs uppercase tracking-wider font-semibold mb-1">Low</span>
            <span className="font-medium text-foreground">{counts.low}</span>
          </div>
          <div className="w-px h-8 bg-border"></div>
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs uppercase tracking-wider font-semibold mb-1">Resolved</span>
            <span className="font-medium text-[#22C55E]">{counts.resolved}</span>
          </div>
          <div className="w-px h-8 bg-border"></div>
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs uppercase tracking-wider font-semibold mb-1">Needs Review</span>
            <span className="font-medium text-[#F59E0B]">{counts.review}</span>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-4 items-center">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input 
              type="text" 
              placeholder="Search findings..." 
              className="w-full bg-background border border-border rounded-lg pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="flex gap-2 w-full sm:w-auto">
            <select className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none" value={filterSeverity} onChange={e => setFilterSeverity(e.target.value)}>
              <option value="all">All Severities</option>
              <option value="high">High/Critical</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <select className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none" value={filterCategory} onChange={e => setFilterCategory(e.target.value)}>
              <option value="all">All Categories</option>
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <select className="bg-background border border-border rounded-lg px-3 py-2 text-sm focus:outline-none" value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
              <option value="all">All Statuses</option>
              <option value="identified">Identified</option>
              <option value="confirmed">Confirmed</option>
              <option value="fixed">Fixed</option>
              <option value="needs review">Needs Review</option>
              <option value="unresolved">Unresolved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
        </div>
      </div>

      <div className="divide-y divide-border">
        {Object.entries(
          filteredIssues.reduce((acc, issue) => {
            const group = issue.file || 'unknown';
            if (!acc[group]) acc[group] = [];
            acc[group].push(issue);
            return acc;
          }, {})
        ).map(([file, issuesInFile]) => (
          <div key={file} className="bg-card">
            <div className="px-6 py-3 bg-secondary/10 border-b border-border flex items-center justify-between sticky top-0 z-10 backdrop-blur-sm">
              <div className="flex items-center gap-2 font-mono text-sm text-foreground font-semibold">
                <FileCode2 className="w-4 h-4 text-primary" />
                {file}
              </div>
              <div className="text-xs font-medium text-muted-foreground bg-background px-2 py-1 rounded-md border border-border">
                {issuesInFile.length} {issuesInFile.length === 1 ? 'Finding' : 'Findings'}
              </div>
            </div>
            <div className="divide-y divide-border/50">
              {issuesInFile.map((issue) => {
                const isSelected = selectedId === issue.id
                return (
                  <div key={issue.id} className="flex flex-col hover:bg-accent/30 transition-colors">
                    <button 
                      onClick={() => setSelectedId(isSelected ? null : issue.id)}
                      className="w-full text-left px-6 py-4 flex flex-col sm:flex-row sm:items-center gap-4 focus:outline-none"
                    >
                      <div className="flex items-center gap-4 w-full sm:w-auto shrink-0">
                        {isSelected ? <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" /> : <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />}
                        <div className="w-20 shrink-0">{getSeverityBadge(issue.severity)}</div>
                        <div className="w-32 truncate text-sm text-muted-foreground hidden sm:block" title={issue.category}>{issue.category}</div>
                      </div>
                      <div className="flex-1 min-w-0">
                        <span className={`text-sm font-medium ${isSelected ? 'text-primary' : 'text-foreground'}`}>
                          {issue.title}
                        </span>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground font-mono mt-1">
                          <span className="truncate">Line {issue.line}</span>
                        </div>
                      </div>
                      <div className="shrink-0 mt-2 sm:mt-0">
                        {getStatusBadge(issue.status)}
                      </div>
                    </button>
                    
                    {isSelected && (
                      <div className="px-6 pb-6 pt-2 text-sm border-t border-border/50 bg-background/50">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mt-4">
                          <div>
                            <h4 className="font-semibold text-foreground mb-2">Description</h4>
                            <p className="text-muted-foreground whitespace-pre-wrap">{issue.description}</p>
                            
                            {issue.evidence && (
                              <>
                                <h4 className="font-semibold text-foreground mt-4 mb-2">Evidence</h4>
                                <pre className="bg-[#080808] p-3 rounded-lg text-xs font-mono text-[#E4E4E7] overflow-x-auto border border-[#242428] whitespace-pre-wrap">
                                  {issue.evidence}
                                </pre>
                              </>
                            )}
                          </div>
                          <div>
                            <h4 className="font-semibold text-foreground mb-2">Location</h4>
                            <p className="text-muted-foreground font-mono text-xs break-all mb-4 bg-muted p-2 rounded-md border border-border">
                              {issue.file}{issue.line !== 'unknown' ? ` (Line: ${issue.line})` : ''}
                            </p>
                            
                            {issue.remediation && (
                              <>
                                <h4 className="font-semibold text-foreground mb-2">Suggested Fix</h4>
                                <p className="text-muted-foreground whitespace-pre-wrap mb-4">{issue.remediation}</p>
                              </>
                            )}
                            
                            <h4 className="font-semibold text-foreground mb-2">State Resolution</h4>
                            <div className="text-muted-foreground text-xs space-y-1">
                              <div>Detection: <span className="font-medium text-foreground">Verified</span></div>
                              <div>Remediation applied: <span className="font-medium text-foreground">{['Fixed', 'Needs Review'].includes(issue.status) ? 'Yes' : 'No'}</span></div>
                              <div>Validation passed: <span className="font-medium text-foreground">{issue.status === 'Fixed' ? 'Yes' : (issue.status === 'Needs Review' ? 'No' : 'N/A')}</span></div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
        {filteredIssues.length === 0 && (
          <div className="p-8 text-center text-muted-foreground text-sm">
            No findings match the current filters.
          </div>
        )}
      </div>
    </div>
  )
}

