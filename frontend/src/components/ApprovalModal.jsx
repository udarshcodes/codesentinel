

export default function ApprovalModal({ isOpen, agentData, onApprove, onReject }) {
  if (!isOpen || !agentData) return null

  // agentData.fix should be the repair_plan array
  const fixes = Array.isArray(agentData.fix) ? agentData.fix : []
  const highRiskFixes = fixes.filter(f => f.risk === 'high-risk')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm">
      <div className="bg-white border border-red-500/50 !rounded-[2.5rem] shadow-2xl p-6 max-w-2xl w-full mx-4">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-red-500/20 rounded-full">
            <svg className="w-6 h-6 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-slate-900">Human Approval Required</h2>
        </div>
        
        <p className="text-slate-600 mb-6">
          The Repair Planner agent has proposed <span className="font-bold text-red-600">high-risk changes</span>. 
          Please review the proposed plan before the pipeline continues.
        </p>

        <div className="space-y-4 mb-6 max-h-60 overflow-y-auto pr-2">
          {highRiskFixes.map((fix, i) => (
            <div key={i} className="p-4 rounded-xl bg-slate-50 border border-slate-200">
              <div className="flex justify-between items-start mb-2">
                <span className="font-mono text-sm text-blue-600">Issue #{fix.issue_id}</span>
                <span className="px-2 py-1 text-xs font-bold uppercase tracking-wider text-red-600 bg-red-100 rounded-lg">High Risk</span>
              </div>
              <p className="text-sm text-slate-800">{fix.action}</p>
              {fix.reasoning && (
                <p className="text-xs text-slate-500 mt-2 italic">Reasoning: {fix.reasoning}</p>
              )}
            </div>
          ))}
        </div>

        <div className="flex justify-end gap-3 mt-6 pt-4 border-t border-slate-200">
          <button 
            onClick={onReject}
            className="px-6 py-2 rounded-xl font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors"
          >
            Reject & Stop
          </button>
          <button 
            onClick={onApprove}
            className="px-6 py-2 rounded-lg font-medium bg-red-600 hover:bg-red-700 text-white transition-colors shadow-lg shadow-red-500/20"
          >
            Approve & Continue
          </button>
        </div>
      </div>
    </div>
  )
}