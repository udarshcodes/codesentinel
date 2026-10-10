import { useEffect, useState } from 'react'
import ApprovalModal from './ApprovalModal'
import PRSummary from './PRSummary'
import LLMWaitingState from './LLMWaitingState'
import PipelineView from './PipelineView'
import FindingsPanel from './FindingsPanel'
import DiffViewer from './DiffViewer'
import PipelineNav from './PipelineNav'
import { usePipeline } from '../../hooks/usePipeline'
import { useApproval } from '../../hooks/useApproval'
import { PipelineProvider } from '../../context/PipelineContext'

function DashboardInner({ taskId, onComplete }) {
  const pipelineState = usePipeline(taskId)
  const approval = useApproval(taskId)

  const isComplete = pipelineState.status === 'COMPLETED'
  const isTerminal = ['COMPLETED', 'FAILED', 'NEEDS_REVIEW'].includes(pipelineState.status)

  const [isPRVisible, setIsPRVisible] = useState(false)
  const [approvalError, setApprovalError] = useState(null)

  useEffect(() => {
    if (isTerminal && onComplete) {
      onComplete(pipelineState.status)
    }
  }, [isTerminal, onComplete, pipelineState.status])

  useEffect(() => {
    if (isComplete && (pipelineState.pr_url || pipelineState.pr_error)) {
      const prElement = document.getElementById('pr-summary')
      if (!prElement) return

      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            // Use intersectionRatio and boundingClientRect to determine if the element is actually in view
            setIsPRVisible(entry.isIntersecting || entry.boundingClientRect.top < 0)
          })
        },
        { threshold: 0, rootMargin: "-10% 0px -10% 0px" }
      )
      observer.observe(prElement)
      return () => observer.disconnect()
    }
  }, [isComplete, pipelineState.pr_url, pipelineState.pr_error])

  const handleApprove = async () => {
    setApprovalError(null)
    const result = await approval.approve()
    if (!result.success) setApprovalError(result.error)
  }

  const handleReject = async () => {
    setApprovalError(null)
    const result = await approval.reject()
    if (!result.success) setApprovalError(result.error)
  }

  return (
    <>
      <PipelineNav />
      <div id="pipeline-overview">
        <ApprovalModal 
          isOpen={approval.awaitingApproval} 
        agentData={approval.currentFix} 
        onApprove={handleApprove} 
        onReject={handleReject} 
        error={approvalError}
        tokenLoading={approval.tokenLoading}
        tokenReady={approval.tokenReady}
        tokenRecoveryRequired={approval.tokenRecoveryRequired}
        onRecover={approval.recoverToken}
      />

      {pipelineState.status === 'UNAUTHORIZED' && (
        <div className="mt-8 p-6 bg-destructive/10 border border-destructive/20 rounded-xl text-center">
          <h3 className="font-semibold text-lg text-destructive mb-2">Access Denied</h3>
          <p className="text-muted-foreground">You do not have permission to view this pipeline stream. The view token is missing or invalid.</p>
        </div>
      )}

      {pipelineState.status === 'NOT_FOUND' && (
        <div className="mt-8 p-6 bg-destructive/10 border border-destructive/20 rounded-xl text-center">
          <h3 className="font-semibold text-lg text-destructive mb-2">Task Not Found</h3>
          <p className="text-muted-foreground">The requested analysis task could not be found or has expired.</p>
        </div>
      )}

      {pipelineState.status === 'CONNECTION_ERROR' && (
        <div className="mt-8 p-6 bg-[#F59E0B]/10 border border-[#F59E0B]/20 rounded-xl text-center">
          <h3 className="font-semibold text-lg text-[#F59E0B] mb-2">Connection Error</h3>
          <p className="text-muted-foreground">Unable to connect to the backend. Please check your network and refresh the page.</p>
        </div>
      )}

      {pipelineState.status !== 'idle' && pipelineState.status !== 'UNAUTHORIZED' && pipelineState.status !== 'NOT_FOUND' && pipelineState.status !== 'CONNECTION_ERROR' && (
        <PipelineView state={pipelineState} />
      )}
      </div>

      {(pipelineState.findings?.length > 0 || pipelineState.static_findings?.length > 0 || pipelineState.dependency_findings?.length > 0 || pipelineState.patches?.length > 0 || pipelineState.validation_results?.length > 0) && (
        <>
          <FindingsPanel state={pipelineState} />
          <DiffViewer state={pipelineState} />
        </>
      )}

      {(isComplete || pipelineState.status === 'FAILED') && (
        <>
          <PRSummary state={pipelineState} />
          {isPRVisible ? (
            <button
              onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
              className="fixed bottom-6 right-6 sm:bottom-8 sm:right-8 bg-secondary text-secondary-foreground p-3 sm:px-6 sm:py-3 rounded-full shadow-2xl hover:opacity-90 transition-all duration-300 z-50 flex items-center gap-2 font-medium opacity-80 hover:opacity-100 focus:outline-none"
              title="Back to Top"
            >
              <svg className="w-5 h-5 sm:mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
              <span className="hidden sm:inline">Back to Top</span>
            </button>
          ) : (
            <button
              onClick={() => {
                 const prElement = document.getElementById('pr-summary');
                 if (prElement) {
                   const y = prElement.getBoundingClientRect().top + window.scrollY - 100;
                   window.scrollTo({ top: y, behavior: 'smooth' });
                 }
              }}
              className="fixed bottom-6 right-6 sm:bottom-8 sm:right-8 bg-primary text-primary-foreground p-3 sm:px-6 sm:py-3 rounded-full shadow-2xl hover:opacity-90 transition-all duration-300 z-50 flex items-center gap-2 font-medium focus:outline-none"
              title="Scroll to PR Generation"
            >
              <svg className="w-5 h-5 animate-bounce sm:mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
              </svg>
              <span className="hidden sm:inline">Scroll to PR</span>
            </button>
          )}
        </>
      )}

      {pipelineState.status === 'WAITING_FOR_LLM_CAPACITY' && (
        <LLMWaitingState pipelineState={pipelineState} />
      )}
    </>
  )
}

export default function PipelineDashboard({ taskId, hidden, onComplete }) {
  return (
    <div style={{ display: hidden ? 'none' : 'block' }}>
      <PipelineProvider>
        <DashboardInner taskId={taskId} onComplete={onComplete} />
      </PipelineProvider>
    </div>
  )
}
