import React from 'react'
import ApprovalModal from './ApprovalModal'
import PRSummary from './PRSummary'
import PipelineView from './PipelineView'
import FindingsPanel from './FindingsPanel'
import DiffViewer from './DiffViewer'
import { usePipeline } from '../hooks/usePipeline'
import { useApproval } from '../hooks/useApproval'
import { PipelineProvider } from '../context/PipelineContext'

function DashboardInner({ taskId }) {
  const pipelineState = usePipeline(taskId)
  const approval = useApproval(taskId)

  const isComplete = pipelineState.status === 'complete' || pipelineState.status === 'validating_failed'

  const syntheticEvents = [
    ...pipelineState.agents.map(a => ({ event: 'agent_complete', data: a })),
    ...(pipelineState.awaiting_approval ? [{ event: 'approval_required' }] : []),
    ...(pipelineState.status === 'complete' || pipelineState.status === 'validating_failed' ? [{ event: 'pipeline_complete' }] : [])
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
        <PRSummary 
          prUrl={pipelineState.pr_url} 
          confidenceScore={pipelineState.confidence_score}
          prError={pipelineState.pr_error}
        />
      )}
    </>
  )
}

export default function PipelineDashboard({ taskId, hidden }) {
  return (
    <div style={{ display: hidden ? 'none' : 'block' }}>
      <PipelineProvider>
        <DashboardInner taskId={taskId} />
      </PipelineProvider>
    </div>
  )
}
