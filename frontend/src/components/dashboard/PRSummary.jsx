import ConfidenceScore from './ConfidenceScore'
import { CheckCircle2, XCircle, GitPullRequest, AlertTriangle, ShieldCheck, Beaker } from 'lucide-react'

export default function PRSummary({ state }) {
  if (!state) return null;
  const { status, pr_url, pr_error, pipeline_error, confidence_score } = state;

  if (!pr_url && !pr_error && !confidence_score && status !== 'FAILED' && status !== 'COMPLETED' && status !== 'NEEDS_REVIEW') {
    return null;
  }

  const totalFindings = (state.dependency_findings?.length || 0) + (state.static_findings?.length || 0);
  const patchesGenerated = state.patches?.length || 0;
  const patchesApplied = state.patches?.filter(p => p.applied)?.length || 0;
  const patchesRejected = state.patches?.filter(p => !p.applied)?.length || 0;
  
  const modifiedFiles = new Set(
    (state.patches || []).filter(p => p.applied && p.file).map(p => p.file)
  ).size;

  const validationResults = state.validation_results || [];
  const validationRan = validationResults.length > 0;
  const allTestsPassed = validationRan && validationResults.every(v => v.passed);
  
  const securityVerified = state.security_verified === true;
  const needsReview = (validationRan && !allTestsPassed) || !securityVerified;

  let title = "Analysis Complete";
  let description = "CodeSentinel has finished the analysis and remediation pipeline.";
  let isError = false;
  let isWarning = false;
  let Icon = CheckCircle2;

  if (status === 'FAILED') {
    title = "Analysis Failed";
    description = pipeline_error || "The pipeline encountered a fatal error and halted.";
    isError = true;
    Icon = XCircle;
  } else if (pr_error) {
    title = "Pull Request Generation Failed";
    description = "The AI remediation completed, but pushing the branch or opening the PR failed.";
    isError = true;
    Icon = XCircle;
  } else if (status === 'NEEDS_REVIEW' || needsReview) {
    title = "Completed with Review Required";
    description = "The pipeline finished, but manual review is required for unverified patches.";
    isWarning = true;
    Icon = AlertTriangle;
  }

  const bgColorClass = isError ? 'bg-[#EF4444]/10' : (isWarning ? 'bg-[#F59E0B]/10' : 'bg-[#22C55E]/10');
  const iconColorClass = isError ? 'text-[#EF4444]' : (isWarning ? 'text-[#F59E0B]' : 'text-[#22C55E]');
  const borderClass = isError ? 'border-[#EF4444]/30' : (isWarning ? 'border-[#F59E0B]/30' : 'border-[#22C55E]/30');

  const validationStatus = validationRan ? (allTestsPassed ? "Verified" : "Review Required") : "Skipped";
  const securityStatus = securityVerified ? "Verified" : "Review Required";

  return (
    <div id="pr-summary" className={`bg-card border p-8 mt-8 max-w-6xl w-full mx-auto rounded-[1.5rem] shadow-sm transition-colors duration-500 ${borderClass}`}>
      <div className="flex items-center gap-4 mb-8">
        <div className={`p-3 rounded-full ${bgColorClass}`}>
          <Icon className={`w-8 h-8 ${iconColorClass}`} />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-foreground">{title}</h2>
          <p className="text-muted-foreground text-sm mt-1">
            {description}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {confidence_score !== undefined && confidence_score !== null && (
          <ConfidenceScore score={confidence_score} />
        )}
        
        <div className="bg-background rounded-xl p-6 border border-border flex flex-col justify-center">
          <h3 className="text-sm font-medium text-foreground mb-4">Pipeline Summary</h3>
          <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <div className="text-muted-foreground">Findings detected:</div>
            <div className="font-medium text-foreground">{totalFindings}</div>
            
            <div className="text-muted-foreground">Patches generated:</div>
            <div className="font-medium text-foreground">{patchesGenerated}</div>
            
            <div className="text-muted-foreground">Patches applied:</div>
            <div className="font-medium text-foreground">{patchesApplied}</div>
            
            <div className="text-muted-foreground">Patches rejected:</div>
            <div className="font-medium text-foreground">{patchesRejected}</div>
            
            <div className="text-muted-foreground">Files modified:</div>
            <div className="font-medium text-foreground">{modifiedFiles}</div>
          </div>
        </div>
      </div>

      <div className="bg-background rounded-xl p-6 border border-border mb-6">
        <h3 className="text-sm font-medium text-foreground mb-4">Verification Status</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className={`p-4 rounded-lg border flex items-start gap-3 ${validationStatus === 'Verified' ? 'bg-[#22C55E]/5 border-[#22C55E]/20 text-[#22C55E]' : validationStatus === 'Review Required' ? 'bg-[#F59E0B]/5 border-[#F59E0B]/20 text-[#F59E0B]' : 'bg-muted border-border text-muted-foreground'}`}>
            <Beaker className="w-5 h-5 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-sm">Testing & Validation</div>
              <div className="text-xs opacity-80 mt-1">{validationStatus}</div>
            </div>
          </div>
          <div className={`p-4 rounded-lg border flex items-start gap-3 ${securityStatus === 'Verified' ? 'bg-[#22C55E]/5 border-[#22C55E]/20 text-[#22C55E]' : 'bg-[#F59E0B]/5 border-[#F59E0B]/20 text-[#F59E0B]'}`}>
            <ShieldCheck className="w-5 h-5 shrink-0 mt-0.5" />
            <div>
              <div className="font-semibold text-sm">Security Verification</div>
              <div className="text-xs opacity-80 mt-1">{securityStatus}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-background rounded-xl p-6 border border-border">
        {pr_url ? (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
            <div>
              <h3 className={`text-lg font-semibold mb-1 ${needsReview ? 'text-[#F59E0B]' : 'text-foreground'}`}>
                {needsReview ? 'Draft Pull Request Created' : 'Pull Request Ready'}
              </h3>
              <p className="text-sm text-muted-foreground">
                {needsReview 
                  ? 'CodeSentinel has created a Draft Pull Request. Manual review is required before merging due to unverified patches.' 
                  : 'CodeSentinel has successfully pushed the verified patches and opened a Pull Request.'}
              </p>
            </div>
            <a 
              href={pr_url} 
              target="_blank" 
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 bg-primary hover:bg-[#A855F7] text-white px-6 py-3 rounded-md font-medium transition-colors shadow-[0_4px_14px_0_rgba(139,92,246,0.25)] whitespace-nowrap"
            >
              <GitPullRequest className="w-5 h-5" />
              View Pull Request
            </a>
          </div>
        ) : (
          <div>
            <h3 className={`text-lg font-semibold mb-2 flex items-center gap-2 ${iconColorClass}`}>
              <Icon className="w-5 h-5" />
              {title}
            </h3>
            <p className="text-sm text-muted-foreground mb-4">
              {description}
            </p>
            {pr_error && (
              <div className="bg-[#EF4444]/5 rounded-lg p-4 mb-4 border border-[#EF4444]/20">
                <p className="font-mono text-sm text-[#EF4444] whitespace-pre-wrap">{pr_error}</p>
              </div>
            )}
            {pipeline_error && !pr_error && (
              <div className={`${bgColorClass} rounded-lg p-4 mb-4 border ${borderClass}`}>
                <p className={`font-mono text-sm ${iconColorClass} whitespace-pre-wrap`}>{pipeline_error}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

