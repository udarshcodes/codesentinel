export default function AgentsSection() {
  const agents = [
    { name: 'Repo Mapper', stage: 'Context Gathering', desc: 'Analyzes project structure and dependency graphs.' },
    { name: 'Bug Investigator', stage: 'Vulnerability Triage', desc: 'Determines root cause and impact.' },
    { name: 'Repair Planner', stage: 'Remediation Strategy', desc: 'Selects the safest architectural approach.' },
    { name: 'Code Generator', stage: 'Patch Synthesis', desc: 'Writes the context aware code diff.' },
    { name: 'PR Author', stage: 'Ship', desc: 'Documents the fix and opens the PR.' },
  ]

  return (
    <section className="w-full py-24 md:py-32 bg-[#0A0A0A] border-t border-b border-[#242428]">
      <div className="max-w-[1400px] mx-auto px-6 grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-center">
        
        {/* Left: Typography */}
        <div className="flex flex-col">
          <h2 className="text-4xl md:text-5xl font-bold tracking-tighter leading-tight text-[#FAFAFA] mb-6">
            A team of specialized agents.<br />
            <span className="text-[#A1A1AA]">One remediation pipeline.</span>
          </h2>
          <div className="w-12 h-1 bg-[#8B5CF6] mb-8"></div>
          <p className="text-lg text-[#A1A1AA] leading-relaxed max-w-lg">
            Instead of a single monolithic LLM prompt, CodeSentinel uses a LangGraph orchestrated mesh of specialized agents. Each agent handles a precise stage of the investigation, repair, and validation lifecycle.
          </p>
        </div>

        {/* Right: Orchestration Diagram */}
        <div className="w-full">
          <div className="relative py-8">
            
            {/* Central Pipeline Spine */}
            <div className="absolute top-0 bottom-0 left-[28px] w-1 bg-[#242428]"></div>
            <div className="absolute top-0 bottom-1/2 left-[28px] w-1 bg-[#8B5CF6] shadow-[0_0_15px_rgba(139,92,246,0.5)]"></div>
            
            <div className="flex flex-col gap-6 relative z-10">
              {agents.map((agent, idx) => {
                const isActive = idx < 3; // Example: first 3 are purple
                return (
                  <div key={agent.name} className="flex items-center gap-8 group">
                    {/* Node */}
                    <div className={`w-14 h-14 rounded-md flex items-center justify-center border-2 bg-[#050505] transition-colors shrink-0 ${isActive ? 'border-[#8B5CF6] shadow-[0_0_15px_rgba(139,92,246,0.2)]' : 'border-[#242428]'}`}>
                      <div className={`w-3 h-3 rounded-full ${isActive ? 'bg-[#8B5CF6]' : 'bg-[#242428]'}`}></div>
                    </div>
                    
                    {/* Connection Line */}
                    <div className={`hidden sm:block absolute left-[56px] w-8 h-px ${isActive ? 'bg-[#8B5CF6]' : 'bg-[#242428]'}`}></div>
                    
                    {/* Agent Card */}
                    <div className="flex-1 bg-[#0D0D0F] border border-[#242428] rounded-lg p-4 group-hover:border-[#71717A] transition-colors">
                      <div className="flex justify-between items-start mb-1">
                        <h4 className="text-[#FAFAFA] font-bold font-mono text-sm">{agent.name}</h4>
                        <span className="text-[10px] uppercase tracking-wider font-bold text-[#71717A] bg-[#242428] px-2 py-0.5 rounded">{agent.stage}</span>
                      </div>
                      <p className="text-[#A1A1AA] text-xs">{agent.desc}</p>
                    </div>
                  </div>
                )
              })}
            </div>

          </div>
        </div>

      </div>
    </section>
  )
}
