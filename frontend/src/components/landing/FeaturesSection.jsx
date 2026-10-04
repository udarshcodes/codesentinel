export default function FeaturesSection() {
  return (
    <section id="features" className="w-full py-24 md:py-32 bg-[#050505]">
      <div className="max-w-[1400px] mx-auto px-6">
        
        {/* Top Magazine Feature */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
          
          <div className="bg-[#0A0A0A] border border-[#242428] rounded-xl p-10 md:p-14 flex flex-col justify-center">
            <h3 className="text-3xl md:text-4xl font-bold tracking-tighter text-[#FAFAFA] mb-6">
              Autonomous Remediation
            </h3>
            <p className="text-[#A1A1AA] text-lg leading-relaxed mb-8 max-w-md">
              CodeSentinel does not stop at finding a vulnerability. It investigates the issue, plans a repair, generates a patch and validates the result.
            </p>
            <div className="flex items-center gap-2 text-[#8B5CF6] font-mono text-sm uppercase tracking-wider font-bold">
              Full Loop Execution
            </div>
          </div>
          
          <div className="bg-[#0D0D0F] border border-[#242428] rounded-xl p-10 md:p-14 flex flex-col items-center justify-center overflow-hidden relative group">
            <div className="absolute inset-0 bg-[#8B5CF6]/5 opacity-0 group-hover:opacity-100 transition-opacity duration-700"></div>
            <div className="flex flex-col items-center gap-4 z-10 w-full max-w-[280px]">
              <div className="w-full bg-[#050505] border border-[#242428] p-3 rounded-lg text-center text-xs font-mono text-[#FAFAFA]">Detection</div>
              <div className="w-px h-6 bg-[#242428]"></div>
              <div className="w-full bg-[#0A0A0A] border border-[#8B5CF6] p-3 rounded-lg text-center text-xs font-mono text-[#8B5CF6] shadow-[0_0_15px_rgba(139,92,246,0.15)]">Investigation</div>
              <div className="w-px h-6 bg-[#242428]"></div>
              <div className="w-full bg-[#0A0A0A] border border-[#8B5CF6] p-3 rounded-lg text-center text-xs font-mono text-[#8B5CF6] shadow-[0_0_15px_rgba(139,92,246,0.15)]">Generation</div>
              <div className="w-px h-6 bg-[#242428]"></div>
              <div className="w-full bg-[#050505] border border-[#242428] p-3 rounded-lg text-center text-xs font-mono text-[#22C55E]">Validation</div>
            </div>
          </div>

        </div>

        {/* Lower Features Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          
          <div className="bg-[#0A0A0A] border border-[#242428] rounded-xl p-8">
            <h4 className="text-[#FAFAFA] font-bold mb-3">21 Analysis Modules</h4>
            <p className="text-[#71717A] text-sm leading-relaxed">Integrated support for industry standard SAST and dependency scanners, orchestrated into a single normalized pipeline.</p>
          </div>
          
          <div className="bg-[#0A0A0A] border border-[#242428] rounded-xl p-8">
            <h4 className="text-[#FAFAFA] font-bold mb-3">RAG Fix Memory</h4>
            <p className="text-[#71717A] text-sm leading-relaxed">Retrieval Augmented Generation learns from your previously merged PRs to suggest patches that match your team&apos;s exact style.</p>
          </div>
          
          <div className="bg-[#0A0A0A] border border-[#242428] rounded-xl p-8">
            <h4 className="text-[#FAFAFA] font-bold mb-3 flex justify-between items-center">
              Human Approval
              <span className="w-2 h-2 rounded-full bg-[#F59E0B]"></span>
            </h4>
            <p className="text-[#71717A] text-sm leading-relaxed">High risk architectural changes are automatically paused for human review before any code is generated or executed.</p>
          </div>
          
          <div className="bg-[#0A0A0A] border border-[#242428] rounded-xl p-8 lg:col-span-2 flex flex-col md:flex-row gap-8 items-center justify-between">
            <div>
              <h4 className="text-[#FAFAFA] font-bold mb-3">Confidence Scoring & Rescanning</h4>
              <p className="text-[#71717A] text-sm leading-relaxed max-w-md">Every generated patch is subjected to a targeted security rescan and build validation. Fixes are scored deterministically based on test passing rates and vulnerability elimination before a PR is ever opened.</p>
            </div>
            <div className="shrink-0 text-5xl font-bold text-[#FAFAFA]">
              98<span className="text-[#8B5CF6]">.4%</span>
            </div>
          </div>

          <div className="bg-[#0A0A0A] border border-[#242428] rounded-xl p-8">
            <h4 className="text-[#FAFAFA] font-bold mb-3">Real time Telemetry</h4>
            <p className="text-[#71717A] text-sm leading-relaxed">Watch the autonomous agents process your repository in real time through Server Sent Events (SSE).</p>
          </div>

        </div>

      </div>
    </section>
  )
}
