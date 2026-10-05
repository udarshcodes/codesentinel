import { useState, useEffect } from 'react'
import { credentialStore } from './services/credentialStore'
import PipelineDashboard from './components/dashboard/PipelineDashboard'
import ThemeToggle from './components/dashboard/ThemeToggle'
import LandingPage from './components/landing/LandingPage'
import AdminDashboard from './pages/admin/AdminDashboard'
import { ArrowLeft } from 'lucide-react'

function App() {
  const [repoUrlInput, setRepoUrlInput] = useState('')
  const [activeTaskId, setActiveTaskId] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState(null)
  const [batchTasks, setBatchTasks] = useState([])
  const [isPipelineRunning, setIsPipelineRunning] = useState(false)


  useEffect(() => {
    if (localStorage.getItem('theme') === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [])


  if (window.location.pathname.startsWith('/admin')) {
    return <AdminDashboard />
  }

  const startAnalysis = async (e) => {
    if (e) e.preventDefault()
    if (!repoUrlInput) return
    
    setErrorMsg(null)
    setIsSubmitting(true)
    setIsPipelineRunning(true)
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s timeout
    
    try {
      const apiUrl = import.meta.env.VITE_API_URL || '';
      const res = await fetch(`${apiUrl}/api/v1/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: repoUrlInput }),
        signal: controller.signal
      })
      
      clearTimeout(timeoutId);
      
      if (!res.ok) {
        throw new Error(`Server returned ${res.status}`)
      }
      
      const data = await res.json()
      
      if (data.tasks && data.tasks.length > 0) {
        setBatchTasks(data.tasks)
        data.tasks.forEach(t => {
          if (t.view_token) credentialStore.setViewToken(t.task_id, t.view_token);
        });
        setActiveTaskId(data.tasks[0].task_id)
      } else {
        setBatchTasks([])
        if (data.view_token && data.task_id) credentialStore.setViewToken(data.task_id, data.view_token);
        setActiveTaskId(data.task_id || null)
      }
    } catch (error) {
      console.error(error)
      if (error.name === 'AbortError') {
        setErrorMsg('Connection timed out. Could not connect to the backend.')
      } else {
        setErrorMsg('Failed to start analysis. Is the backend running?')
      }
      setIsPipelineRunning(false)
    } finally {
      setIsSubmitting(false)
      clearTimeout(timeoutId);
    }
  }


  if (!activeTaskId && batchTasks.length === 0 && !isPipelineRunning) {
    return (
      <LandingPage 
        repoUrlInput={repoUrlInput} 
        setRepoUrlInput={setRepoUrlInput} 
        startAnalysis={startAnalysis} 
        isSubmitting={isSubmitting} 
        errorMsg={errorMsg}
      />
    )
  }


  return (
    <div className="container mx-auto px-4 pt-6 pb-4 relative z-10 min-h-[100dvh] flex flex-col selection:bg-primary/30">
      
      <div className="flex items-center justify-between mb-8">
        <button 
          onClick={() => {
            setActiveTaskId(null)
            setBatchTasks([])
            setIsPipelineRunning(false)
          }}
          className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Home
        </button>

        <div className="flex items-center gap-4">
          <ThemeToggle />
          <a 
            href="/admin"
            className="hidden sm:flex items-center gap-2 bg-card border border-border hover:border-primary text-foreground hover:bg-accent px-4 py-2 rounded-full font-medium transition-all text-sm shadow-sm"
          >
            Admin Dashboard
          </a>
        </div>
      </div>

      <header className="mb-10 animate-fade-in-down flex items-center gap-6">
        <img src="/logo.jpg" alt="CodeSentinel Logo" className="w-16 h-16 rounded-full shadow-lg object-cover shrink-0 border border-border" />
        <div className="flex flex-col">
          <h1 className="text-3xl font-bold text-foreground tracking-tight">
            Analysis Workspace
          </h1>
          <p className="text-sm text-muted-foreground font-mono">
            {repoUrlInput || 'Multiple Repositories'}
          </p>
        </div>
      </header>

      <main className="flex-1">
        {errorMsg && (
          <div className="mb-6 p-4 bg-destructive/10 text-destructive-foreground rounded-xl border border-destructive/20 font-medium">
            {errorMsg}
          </div>
        )}

        {batchTasks.length > 1 && (
          <div className="flex gap-2 mb-6 overflow-x-auto pb-2 scrollbar-thin scrollbar-thumb-border">
            {batchTasks.map(task => (
              <button
                key={task.task_id}
                onClick={() => setActiveTaskId(task.task_id)}
                className={`px-4 py-2 rounded-full whitespace-nowrap text-sm font-medium transition-all ${activeTaskId === task.task_id ? 'bg-primary text-primary-foreground shadow-md border border-primary' : 'bg-card text-muted-foreground border border-border hover:border-primary/50'}`}
              >
                {task.repo_url.split('/').pop()}
              </button>
            ))}
          </div>
        )}

        {isPipelineRunning && !activeTaskId && batchTasks.length === 0 && !errorMsg ? (
          <div className="flex flex-col items-center justify-center p-12 bg-card border border-border rounded-xl shadow-sm text-center min-h-[400px]">
            <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mb-6"></div>
            <h2 className="text-xl font-bold text-foreground mb-2">Creating analysis task</h2>
            <p className="text-muted-foreground">Connecting to analysis worker...</p>
          </div>
        ) : batchTasks.length > 0 ? (
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
      
      <footer className="mt-auto pt-12 pb-4 text-center border-t border-border opacity-50">
        <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">
          &copy; {new Date().getFullYear()} CodeSentinel
        </p>
      </footer>
    </div>
  )
}

export default App