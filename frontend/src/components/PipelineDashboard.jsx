import { useEffect, useState } from 'react'
import ApprovalModal from './ApprovalModal'
import PRSummary from './PRSummary'
import PipelineView from './PipelineView'
import FindingsPanel from './FindingsPanel'
import DiffViewer from './DiffViewer'
import { usePipeline } from '../hooks/usePipeline'
import { useApproval } from '../hooks/useApproval'
import { PipelineProvider } from '../context/PipelineContext'

function DashboardInner({ taskId, onComplete }) {
  const pipelineState = usePipeline(taskId)
  const approval = useApproval(taskId)

  const isComplete = pipelineState.status === 'complete'

  const [isPRVisible, setIsPRVisible] = useState(false)

  useEffect(() => {
    if (isComplete && onComplete) {
      onComplete()
    }
  }, [isComplete, onComplete])

  useEffect(() => {
    if (isComplete && (pipelineState.pr_url || pipelineState.pr_error)) {
      const prElement = document.getElementById('pr-summary')
      if (!prElement) return

      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            setIsPRVisible(entry.isIntersecting)
          })
        },
        { threshold: 0.1 }
      )
      observer.observe(prElement)
      return () => observer.disconnect()
    }
  }, [isComplete, pipelineState.pr_url, pipelineState.pr_error])

  const syntheticEvents = [
    ...pipelineState.agents.map(a => ({ event: 'agent_complete', data: a })),
    ...(pipelineState.awaiting_approval ? [{ event: 'approval_required' }] : []),
    ...(pipelineState.status === 'complete' ? [{ event: 'pipeline_complete' }] : [])
  ];

  const handleApprove = async () => {
    await approval.approve()
  }

  const handleReject = async () => {
    await approval.reject()
  }

  return (
    <>
      <ApprovalModal 
        isOpen={approval.awaitingApproval} 
        agentData={approval.currentFix} 
        onApprove={handleApprove} 
        onReject={handleReject} 
      />

      {pipelineState.status !== 'idle' && (
        <PipelineView events={syntheticEvents} />
      )}

      {pipelineState.agents.length > 0 && (
        <>
          <FindingsPanel events={syntheticEvents} />
          <DiffViewer events={syntheticEvents} />
        </>
      )}

      {isComplete && (pipelineState.pr_url || pipelineState.pr_error) && (
        <>
          <PRSummary 
            prUrl={pipelineState.pr_url} 
            confidenceScore={pipelineState.confidence_score}
            prError={pipelineState.pr_error}
          />
          <button
            onClick={() => document.getElementById('pr-summary')?.scrollIntoView({ behavior: 'smooth' })}
            className={`fixed bottom-8 left-1/2 transform -translate-x-1/2 bg-primary text-primary-foreground px-6 py-3 rounded-full shadow-2xl hover:opacity-90 transition-all duration-300 z-50 flex items-center gap-2 font-medium ${isPRVisible ? 'opacity-0 translate-y-10 pointer-events-none' : 'opacity-100 translate-y-0'}`}
          >
            <svg className="w-5 h-5 animate-bounce" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
            Scroll to PR Generation
          </button>
        </>
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
