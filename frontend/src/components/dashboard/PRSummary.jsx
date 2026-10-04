import ConfidenceScore from './ConfidenceScore'
import { CheckCircle2, XCircle, GitPullRequest, AlertTriangle } from 'lucide-react'

export default function PRSummary({ prUrl, confidenceScore, prError, status, pipelineError }) {
  if (!prUrl && !prError && !confidenceScore && status !== 'FAILED') return null

  let title = "Pipeline Complete"
  let description = "All autonomous agents have finished successfully."
  let isError = false
  let isWarning = false
  let Icon = CheckCircle2

  if (status === 'FAILED') {
    title = "Pipeline Failed"
    description = pipelineError || "The pipeline encountered an error and halted."
    isError = true
    Icon = XCircle
  } else if (prError) {
    if (prError.includes("validation")) {
      title = "Validation Failed"
      description = "The AI remediation completed, but generated patches failed validation tests."
    } else if (prError.includes("security")) {
      title = "Security Verification Failed"
      description = "The AI remediation completed, but generated patches failed security tests."
    } else {
      title = "Pull Request Generation Failed"
      description = "The AI remediation completed, but pushing the branch or opening the PR failed."
    }
    isError = true
    Icon = XCircle
  } else if (!prUrl) {
    title = "Needs Review"
    description = "The pipeline is waiting for human intervention or encountered an unknown state."
    isWarning = true
    Icon = AlertTriangle
  }

  const bgColorClass = isError ? 'bg-[#EF4444]/10' : (isWarning ? 'bg-yellow-500/10' : 'bg-primary/10')
  const iconColorClass = isError ? 'text-[#EF4444]' : (isWarning ? 'text-yellow-500' : 'text-primary')
  const borderClass = isError ? 'border-[#EF4444]/30' : (isWarning ? 'border-yellow-500/30' : 'border-primary/30')

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

      {confidenceScore !== null && confidenceScore !== undefined && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <ConfidenceScore score={confidenceScore} />
        </div>
      )}

      <div className="bg-background rounded-xl p-6 border border-border">
        {prUrl ? (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
            <div>
              <h3 className="text-lg font-semibold text-foreground mb-1">Pull Request Ready</h3>
              <p className="text-sm text-muted-foreground">
                CodeSentinel has successfully pushed the validated patches and opened a Pull Request.
              </p>
            </div>
            <a 
              href={prUrl} 
              target="_blank" 
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 bg-primary hover:bg-[#A855F7] text-white px-6 py-3 rounded-md font-medium transition-colors shadow-[0_4px_14px_0_rgba(139,92,246,0.25)] whitespace-nowrap"
            >
              <GitPullRequest className="w-5 h-5" />
              View on GitHub
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
            {prError && (
              <div className="bg-[#EF4444]/5 rounded-lg p-4 mb-4 border border-[#EF4444]/20">
                <p className="font-mono text-sm text-[#EF4444] whitespace-pre-wrap">{prError}</p>
              </div>
            )}
            {pipelineError && !prError && (
              <div className={`${bgColorClass} rounded-lg p-4 mb-4 border ${borderClass}`}>
                <p className={`font-mono text-sm ${iconColorClass} whitespace-pre-wrap`}>{pipelineError}</p>
              </div>
            )}
            {!isWarning && (
              <button 
                onClick={() => window.open('https://github.com/udarshcodes/codesentinel', '_blank')}
                className="inline-flex items-center justify-center gap-2 bg-secondary hover:bg-secondary/80 text-secondary-foreground px-4 py-2 rounded-md text-sm font-medium transition-colors"
              >
                View Repository Settings
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
