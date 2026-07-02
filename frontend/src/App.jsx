import { useState } from 'react'
import PipelineDashboard from './components/PipelineDashboard'
import ThemeToggle from './components/ThemeToggle'

function App() {
  const [repoUrlInput, setRepoUrlInput] = useState('')
  const [activeTaskId, setActiveTaskId] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState(null)
  const [batchTasks, setBatchTasks] = useState([])

  const [isPipelineRunning, setIsPipelineRunning] = useState(false)

  const startAnalysis = async (e) => {
    e.preventDefault()
    if (!repoUrlInput) return
    
    setErrorMsg(null)
    setIsSubmitting(true)
    setIsPipelineRunning(true)
    try {
      const apiUrl = import.meta.env.VITE_API_URL || '';
      const res = await fetch(`${apiUrl}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: repoUrlInput })
      })
      
      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`)
      }
      
      const data = await res.json()
      
      if (data.task_ids && data.task_ids.length > 0) {
        const tasks = data.task_ids.map((id, index) => ({
          task_id: id,
          repo_url: data.repo_urls[index]
        }))
        setBatchTasks(tasks)
        setActiveTaskId(tasks[0].task_id)
      } else {
        setBatchTasks([])
        setActiveTaskId(data.task_id || null)
      }
    } catch (error) {
      console.error(error)
      setErrorMsg('Failed to start analysis. Is the backend running?')
      setIsPipelineRunning(false)
    } finally {
      setIsSubmitting(false)
    }
  }



  return (
    <div className="container mx-auto px-4 pt-12 pb-4 relative z-10 min-h-screen flex flex-col">


      {/* Admin Dashboard Link and Theme Toggle */}
      <div className="absolute top-6 right-6 sm:top-8 sm:right-8 z-50 animate-fade-in-down flex items-center gap-4">
        <ThemeToggle />
        <a 
          href="https://codesentinel-api.kindhill-aee3896c.southeastasia.azurecontainerapps.io/admin/" 
          target="_blank" 
          rel="noopener noreferrer"
          className="flex items-center gap-2 bg-card/80 backdrop-blur-md border border-border hover:border-primary text-foreground hover:bg-accent px-5 py-2.5 rounded-full font-semibold shadow-sm hover:shadow transition-all"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Admin Dashboard
        </a>
      </div>

      <header className="mb-16 animate-fade-in-down flex flex-col md:flex-row items-center justify-center gap-8 mt-12 md:mt-0">
        <img src="/logo.jpg" alt="CodeSentinel Logo" className="w-32 h-32 md:w-48 md:h-48 rounded-full shadow-2xl object-cover shrink-0" />
        <div className="flex flex-col text-center md:text-left">
          <h1 className="text-5xl md:text-6xl font-bold text-primary mb-4 tracking-tight">
            CodeSentinel
          </h1>
          <p className="text-xl md:text-2xl text-muted-foreground font-light tracking-wide uppercase">
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
              className="flex-1 bg-background border border-input rounded-full px-6 py-4 focus:outline-none focus:ring-2 focus:ring-primary text-foreground placeholder-muted-foreground text-lg transition-all"
              value={repoUrlInput}
              onChange={(e) => setRepoUrlInput(e.target.value)}
              disabled={isSubmitting || isPipelineRunning}
              required
            />
            <button 
              type="submit"
              disabled={isSubmitting || isPipelineRunning}
              className="bg-primary hover:opacity-90 disabled:bg-muted disabled:text-muted-foreground px-10 py-4 rounded-full font-bold text-lg text-primary-foreground transition-all duration-200 shadow-lg"
            >
              {(isSubmitting || isPipelineRunning) ? (
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
          {errorMsg && (
            <div className="mt-4 p-4 bg-destructive/10 text-destructive rounded-xl border border-destructive/20">
              {errorMsg}
            </div>
          )}
        </div>

        {batchTasks.length > 1 && (
          <div className="flex gap-2 mb-4 overflow-x-auto pb-2 max-w-6xl mx-auto">
            {batchTasks.map(task => (
              <button
                key={task.task_id}
                onClick={() => setActiveTaskId(task.task_id)}
                className={`px-4 py-2 rounded-full whitespace-nowrap text-sm font-medium transition-all ${activeTaskId === task.task_id ? 'bg-primary text-primary-foreground shadow-md' : 'bg-card text-muted-foreground border border-border hover:border-primary'}`}
              >
                {task.repo_url.split('/').pop()}
              </button>
            ))}
          </div>
        )}

        {/* Dynamic Dashboards */}
        {batchTasks.length > 0 ? (
          batchTasks.map(task => (
            <PipelineDashboard 
              key={task.task_id} 
              taskId={task.task_id} 
              hidden={activeTaskId !== task.task_id}
              onComplete={() => setIsPipelineRunning(false)}
            />
          ))
        ) : activeTaskId ? (
          <PipelineDashboard 
            taskId={activeTaskId} 
            hidden={false} 
            onComplete={() => setIsPipelineRunning(false)}
          />
        ) : null}
      </main>
      
      {/* Footer */}
      <footer className="mt-auto pt-12 pb-4 text-center border-t border-border">
        <div className="flex flex-col gap-4">
          <p className="text-base font-medium tracking-wide text-muted-foreground">
            <span className="text-primary">Languages Supported:</span> HTML &bull; CSS &bull; Python &bull; JavaScript &bull; TypeScript &bull; Go &bull; Java &bull; Rust
          </p>
          <p className="text-sm font-medium tracking-wider text-muted-foreground uppercase">
            &copy; {new Date().getFullYear()} CodeSentinel &bull; CREATED BY UDARSH GOYAL
          </p>
        </div>
      </footer>
    </div>
  )
}

export default App