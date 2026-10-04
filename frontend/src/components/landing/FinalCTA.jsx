import { ArrowRight } from 'lucide-react'

export default function FinalCTA({ startAnalysis }) {
  return (
    <section className="w-full py-32 md:py-48 bg-[#050505] flex justify-center items-center">
      <div className="max-w-[1400px] mx-auto px-6 flex flex-col items-center text-center">
        
        <h2 className="text-5xl md:text-7xl font-bold tracking-tighter leading-[1.1] text-[#FAFAFA] mb-10 max-w-3xl">
          Stop triaging.<br />
          <span className="text-[#8B5CF6]">Start shipping secure code.</span>
        </h2>
        
        <button 
          onClick={startAnalysis}
          className="bg-[#FAFAFA] hover:bg-[#E4E4E7] text-[#050505] px-8 py-4 rounded-md font-bold text-lg transition-colors flex items-center gap-2"
        >
          Analyze your repository <ArrowRight className="w-5 h-5" />
        </button>

      </div>
    </section>
  )
}
