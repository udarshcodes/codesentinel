import { AlertTriangle, ShieldCheck, XOctagon, Loader2 } from 'lucide-react'

export default function ApprovalModal({ isOpen, agentData, onApprove, onReject, error, tokenLoading, tokenReady, tokenRecoveryRequired, onRecover }) {
  if (!isOpen || !agentData) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-fade-in-up">
      <div className="bg-card border border-border w-full max-w-2xl rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        
        {error && (
          <div className="bg-destructive/10 border-b border-destructive/20 p-4 text-sm text-destructive font-medium flex items-center gap-2">
            <XOctagon className="w-5 h-5" />
            {error}
          </div>
        )}
        
        {!tokenLoading && !tokenReady && !error && !tokenRecoveryRequired && (
          <div className="bg-destructive/10 border-b border-destructive/20 p-4 text-sm text-destructive font-medium flex items-center gap-2">
            <XOctagon className="w-5 h-5" />
            Failed to fetch security credentials. Please refresh the page to request a new token.
          </div>
        )}

        {tokenRecoveryRequired && (
          <div className="bg-[#F59E0B]/10 border-b border-[#F59E0B]/20 p-4 text-sm text-[#F59E0B] font-medium flex items-center gap-2">
            <AlertTriangle className="w-5 h-5" />
            Active credentials already exist but were lost from this session. You must recover them before proceeding.
          </div>
        )}

        <div className="p-6 border-b border-border bg-[#F59E0B]/10 flex items-center gap-4">
          <div className="p-3 bg-[#F59E0B]/20 rounded-full">
            <AlertTriangle className="w-6 h-6 text-[#F59E0B]" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-foreground">Human Approval Required</h2>
            <p className="text-sm text-[#F59E0B] font-medium mt-0.5">CodeSentinel identified High risk changes and paused execution.</p>
          </div>
        </div>

        <div className="p-6 overflow-y-auto space-y-6">
          <div>
            <div className="flex justify-between items-center mb-2">
              <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Target Issue</h3>
              <span className="text-xs text-muted-foreground font-mono bg-secondary/50 px-2 py-1 rounded">ID: {agentData.fix_id || 'unknown'}</span>
            </div>
            <p className="text-sm text-foreground bg-background border border-border p-3 rounded-lg leading-relaxed">
              {agentData.issue_summary || 'Not provided.'}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Assessed Risk</h3>
              <div className="bg-background border border-border p-3 rounded-lg flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-[#F59E0B]"></div>
                <span className="text-sm text-foreground font-medium">{agentData.risk_level || 'Not provided'}</span>
              </div>
            </div>
            <div>
              <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Required Action</h3>
              <div className="bg-background border border-border p-3 rounded-lg">
                <span className="text-sm text-foreground font-medium">{agentData.proposed_action || 'Not provided'}</span>
              </div>
            </div>
          </div>

          <div>
            <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">AI Reasoning</h3>
            <div className="bg-background border border-border p-4 rounded-lg">
              <p className="text-sm text-muted-foreground leading-relaxed">
                {agentData.reasoning || 'Not provided.'}
              </p>
            </div>
          </div>
        </div>

        <div className="p-6 border-t border-border bg-secondary/30 flex items-center justify-between gap-3">
          <div className="text-sm text-muted-foreground flex items-center gap-2">
            {tokenLoading && (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Securing approval credentials...</span>
              </>
            )}
            {!tokenLoading && tokenReady && (
              <span className="text-[#10B981] flex items-center gap-1">
                <ShieldCheck className="w-4 h-4" /> Ready
              </span>
            )}
            {!tokenLoading && tokenRecoveryRequired && (
              <span className="text-[#F59E0B] flex items-center gap-1">
                <AlertTriangle className="w-4 h-4" /> Recovery Required
              </span>
            )}
          </div>
          <div className="flex gap-3">
            {tokenRecoveryRequired ? (
              <button
                onClick={onRecover}
                disabled={tokenLoading}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-medium bg-[#F59E0B] text-white hover:bg-[#D97706] transition-colors shadow focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ShieldCheck className="w-4 h-4" />
                Recover Credentials
              </button>
            ) : (
              <>
                <button
                  onClick={onReject}
                  disabled={tokenLoading || !tokenReady}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-medium border border-border bg-background text-foreground hover:bg-accent transition-colors focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <XOctagon className="w-4 h-4 text-muted-foreground" />
                  Reject & Stop
                </button>
                <button
                  onClick={onApprove}
                  disabled={tokenLoading || !tokenReady}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md text-sm font-medium bg-primary text-white hover:bg-[#A855F7] transition-colors shadow-[0_4px_14px_0_rgba(139,92,246,0.25)] focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ShieldCheck className="w-4 h-4" />
                  Approve & Continue
                </button>
              </>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}
