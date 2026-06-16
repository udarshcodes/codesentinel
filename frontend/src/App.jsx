import { useState } from 'react'
import ApprovalModal from './components/ApprovalModal'
import PRSummary from './components/PRSummary'
import PipelineView from './components/PipelineView'
import FindingsPanel from './components/FindingsPanel'
import DiffViewer from './components/DiffViewer'
import { usePipeline } from './hooks/usePipeline'
import { useApproval } from './hooks/useApproval'

function App() {
  const [repoUrlInput, setRepoUrlInput] = useState('')
  const [activeTaskId, setActiveTaskId] = useState(null)

  const pipelineState = usePipeline(activeTaskId)
  const approval = useApproval(activeTaskId)

  const isAnalyzing = pipelineState.status === 'running'
  const isComplete = pipelineState.status === 'complete' || pipelineState.status === 'validating_failed'

  const syntheticEvents = [
    ...pipelineState.agents.map(a => ({ event: 'agent_complete', data: a })),
    ...(pipelineState.status === 'awaiting_approval' ? [{ event: 'approval_required' }] : []),
    ...(pipelineState.status === 'complete' || pipelineState.status === 'validating_failed' ? [{ event: 'pipeline_complete' }] : [])
  ];

  const startAnalysis = async (e) => {
    e.preventDefault()
    if (!repoUrlInput) return
    
    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: repoUrlInput })
      })
      const data = await res.json()
      // Use the UUID returned by the backend, fallback to URL if missing
      setActiveTaskId(data.task_id || repoUrlInput)
    } catch (error) {
      console.error(error)
    }
  }

  const handleApprove = async () => {
    await approval.approve()
  }

  const handleReject = async () => {
    await approval.reject()
  }

  return (
    <div className="container mx-auto px-4 pt-12 pb-4 relative z-10 min-h-screen flex flex-col">
      <ApprovalModal 
        isOpen={approval.awaitingApproval} 
        agentData={approval.currentFix} 
        onApprove={handleApprove} 
        onReject={handleReject} 
      />

      {/* Admin Dashboard Link */}
      <div className="absolute top-6 right-6 sm:top-8 sm:right-8 z-50 animate-fade-in-down">
        <a 
          href="/admin" 
          target="_blank" 
          rel="noopener noreferrer"
          className="flex items-center gap-2 bg-white/80 backdrop-blur-md border border-slate-200 hover:border-slate-400 text-slate-600 hover:text-slate-900 px-5 py-2.5 rounded-full font-semibold shadow-sm hover:shadow transition-all"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Admin Dashboard
        </a>
      </div>

      <header className="mb-16 animate-fade-in-down flex flex-col md:flex-row items-center justify-center gap-8 mt-12 md:mt-0">
        <img src="/logo.jpg" alt="CodeSentinel Logo" className="w-32 h-32 md:w-48 md:h-48 rounded-full shadow-2xl shadow-rose-500/20 object-cover shrink-0" />
        <div className="flex flex-col text-center md:text-left">
          <h1 className="text-5xl md:text-6xl font-bold bg-gradient-to-r from-rose-500 to-red-400 bg-clip-text text-transparent mb-4 tracking-tight">
            CodeSentinel
          </h1>
          <p className="text-xl md:text-2xl text-slate-500 font-light tracking-wide uppercase">
            Autonomous AI Code Review & Remediation
          </p>
        </div>
      </header>

      <main className="flex-1">
        {/* URL Input Form */}
        <div className="glass-panel p-8 mb-8 max-w-6xl mx-auto !rounded-[2.5rem]">
          <form onSubmit={startAnalysis} className="flex gap-4">
            <input 
              type="url" 
              placeholder="https://github.com/username/repo"
              className="flex-1 bg-white border border-slate-300 rounded-full px-6 py-4 focus:outline-none focus:ring-2 focus:ring-rose-500 text-slate-900 placeholder-slate-400 text-lg transition-all"
              value={repoUrlInput}
              onChange={(e) => setRepoUrlInput(e.target.value)}
              disabled={isAnalyzing}
              required
            />
            <button 
              type="submit"
              disabled={isAnalyzing}
              className="bg-rose-500 hover:bg-rose-600 disabled:bg-slate-400 px-10 py-4 rounded-full font-bold text-lg text-white transition-all duration-200 shadow-lg shadow-rose-500/30 hover:shadow-rose-500/50"
            >
              {isAnalyzing ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Analyzing...
                </span>
              ) : 'Analyze'}
            </button>
          </form>
        </div>

        {/* Beautiful Dynamic Components */}
        {pipelineState.agents.length > 0 && (
          <>
            <PipelineView events={syntheticEvents} />
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
      </main>
      
      {/* Footer */}
      <footer className="mt-auto pt-12 pb-4 text-center border-t border-slate-200">
        <div className="flex flex-col gap-4">
          <p className="text-base font-medium tracking-wide text-slate-500">
            <span className="text-rose-500">Languages Supported:</span> HTML &bull; CSS &bull; Python &bull; JavaScript &bull; TypeScript &bull; Go &bull; Java &bull; Rust
          </p>
          <p className="text-sm font-medium tracking-wider text-slate-500 uppercase">
            &copy; {new Date().getFullYear()} CodeSentinel &bull; CREATED BY UDARSH GOYAL
          </p>
        </div>
      </footer>
    </div>
  )
}

export default App