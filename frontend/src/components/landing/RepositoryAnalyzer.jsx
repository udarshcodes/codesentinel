import { ArrowRight, Loader2 } from 'lucide-react'

export default function RepositoryAnalyzer({ repoUrlInput, setRepoUrlInput, startAnalysis, isSubmitting }) {
  return (
    <section id="repo-analyzer" className="w-full py-16 bg-[#050505] border-b border-[#242428] flex justify-center">
      <div className="max-w-[1400px] mx-auto px-6 w-full flex flex-col items-center">
        <div className="w-full max-w-2xl bg-[#0A0A0A] border border-[#242428] rounded-xl p-2 sm:p-4 shadow-2xl flex flex-col sm:flex-row items-center gap-4 transition-all focus-within:border-[#8B5CF6]/50 focus-within:shadow-[0_0_20px_rgba(139,92,246,0.1)]">
          
          <div className="flex-1 w-full flex items-center gap-3 px-4 py-2 sm:py-0">
            <span className="text-[#A1A1AA] font-mono text-lg select-none">❯</span>
            <label htmlFor="repo-url-input" className="sr-only">Repository URL</label>
            <input 
              id="repo-url-input"
              type="text" 
              value={repoUrlInput}
              onChange={(e) => setRepoUrlInput(e.target.value)}
              className="w-full bg-transparent border-none outline-none text-[#FAFAFA] font-mono text-sm sm:text-base"
              disabled={isSubmitting}
            />
          </div>

          <button 
            onClick={startAnalysis}
            disabled={isSubmitting || !repoUrlInput}
            className="w-full sm:w-auto bg-[#FAFAFA] hover:bg-[#E4E4E7] text-[#050505] px-6 py-3 rounded-md font-bold transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 whitespace-nowrap"
          >
            {isSubmitting ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Analyzing...</>
            ) : (
              <>Analyze <ArrowRight className="w-4 h-4" /></>
            )}
          </button>

        </div>
        <p className="mt-4 text-[#71717A] text-xs font-mono">Accepts public GitHub repository URLs.</p>
      </div>
    </section>
  )
}
