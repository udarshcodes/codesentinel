export default function SecuritySection() {
  return (
    <section className="w-full py-24 md:py-32 bg-[#0A0A0A] border-t border-b border-[#242428]">
      <div className="max-w-[1400px] mx-auto px-6 grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-center">
        
        {/* Left: Typography */}
        <div className="flex flex-col">
          <h2 className="text-4xl md:text-5xl font-bold tracking-tighter leading-tight text-[#FAFAFA] mb-6">
            AI writes the fix.<br />
            <span className="text-[#8B5CF6]">Verification proves it.</span>
          </h2>
          <div className="w-12 h-1 bg-[#8B5CF6] mb-8"></div>
          <p className="text-lg text-[#A1A1AA] leading-relaxed max-w-lg mb-8">
            Large Language Models hallucinate. CodeSentinel does not guess. Every generated patch is built, tested, and rescanned before it ever reaches a Pull Request.
          </p>
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-4 text-[#A1A1AA] font-mono text-sm">
              <span className="text-[#8B5CF6] font-bold">1</span> AI generated patch
            </div>
            <div className="w-px h-4 bg-[#242428] ml-2"></div>
            <div className="flex items-center gap-4 text-[#A1A1AA] font-mono text-sm">
              <span className="text-[#FAFAFA] font-bold">2</span> Build validation
            </div>
            <div className="w-px h-4 bg-[#242428] ml-2"></div>
            <div className="flex items-center gap-4 text-[#A1A1AA] font-mono text-sm">
              <span className="text-[#FAFAFA] font-bold">3</span> Test execution
            </div>
            <div className="w-px h-4 bg-[#242428] ml-2"></div>
            <div className="flex items-center gap-4 text-[#A1A1AA] font-mono text-sm">
              <span className="text-[#FAFAFA] font-bold">4</span> Targeted security recheck
            </div>
            <div className="w-px h-4 bg-[#242428] ml-2"></div>
            <div className="flex items-center gap-4 text-[#A1A1AA] font-mono text-sm">
              <span className="text-[#FAFAFA] font-bold">5</span> Confidence score & PR
            </div>
          </div>
        </div>

        {/* Right: Code Diff */}
        <div className="w-full bg-[#050505] border border-[#242428] rounded-xl overflow-hidden shadow-2xl">
          
          <div className="p-4 border-b border-[#242428] bg-[#0A0A0A] flex justify-between items-center">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[#EF4444] animate-pulse"></span>
              <span className="text-[#FAFAFA] text-xs font-mono font-bold uppercase tracking-wider">Example: Vulnerability Detected</span>
            </div>
            <span className="text-[#A1A1AA] text-xs font-mono">src/auth/login.py</span>
          </div>
          <div className="p-4 border-b border-[#242428] bg-[#0D0D0F]">
            <span className="text-[#EF4444] text-sm font-semibold">SQL Injection Vector</span>
          </div>

          <div className="bg-[#050505] font-mono text-sm overflow-x-auto">
            <div className="flex text-[#71717A] bg-[#EF4444]/10">
              <div className="w-12 text-right pr-4 py-1 select-none border-r border-[#242428] text-[#EF4444]">−</div>
              <div className="pl-4 py-1 text-[#FAFAFA] whitespace-pre">
                <span className="text-[#A1A1AA]">query = f</span>&quot;SELECT * FROM users WHERE username=&apos;<span className="text-[#EF4444]">&#123;username&#125;</span>&apos; AND password=&apos;<span className="text-[#EF4444]">&#123;password&#125;</span>&apos;&quot;
              </div>
            </div>
            <div className="flex text-[#71717A] bg-[#22C55E]/10">
              <div className="w-12 text-right pr-4 py-1 select-none border-r border-[#242428] text-[#22C55E]">+</div>
              <div className="pl-4 py-1 text-[#FAFAFA] whitespace-pre flex items-center relative group">
                <span className="text-[#A1A1AA]">query = </span>&quot;SELECT * FROM users WHERE username=? AND password=?&quot;
                <span className="absolute right-4 text-xs font-bold text-[#8B5CF6] uppercase tracking-wider opacity-0 group-hover:opacity-100 transition-opacity">AI Remediation</span>
              </div>
            </div>
            <div className="flex text-[#71717A] bg-[#22C55E]/10">
              <div className="w-12 text-right pr-4 py-1 select-none border-r border-[#242428] text-[#22C55E]">+</div>
              <div className="pl-4 py-1 text-[#FAFAFA] whitespace-pre">
                <span className="text-[#A1A1AA]">db.execute(</span>query, (username, password)<span className="text-[#A1A1AA]">)</span>
              </div>
            </div>
          </div>

          <div className="p-4 border-t border-[#242428] bg-[#0A0A0A] flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div className="flex gap-4 text-xs font-mono">
              <div className="flex items-center gap-1.5 text-[#22C55E]">
                <div className="w-1.5 h-1.5 rounded-full bg-[#22C55E]"></div>
                Build Passed
              </div>
              <div className="flex items-center gap-1.5 text-[#22C55E]">
                <div className="w-1.5 h-1.5 rounded-full bg-[#22C55E]"></div>
                Tests Passed
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-[#A1A1AA] text-xs font-mono uppercase tracking-wider">Confidence</span>
              <span className="text-[#FAFAFA] font-bold">94.7<span className="text-[#8B5CF6]">%</span></span>
            </div>
          </div>

        </div>

      </div>
    </section>
  )
}
