export default function ArchitectureSection() {
  return (
    <section id="architecture" className="w-full py-24 md:py-32 bg-[#050505]">
      <div className="max-w-[1400px] mx-auto px-6">
        
        <div className="mb-16 md:mb-24 flex flex-col">
          <h2 className="text-4xl md:text-5xl font-bold tracking-tighter text-[#FAFAFA] mb-6">
            Engineering Architecture
          </h2>
          <div className="w-12 h-1 bg-[#8B5CF6] mb-8"></div>
          <p className="text-lg text-[#A1A1AA] max-w-2xl">
            CodeSentinel is built on a scalable, asynchronous architecture designed to handle deep repository analysis without blocking.
          </p>
        </div>

        {/* Technical Diagram Container */}
        <div className="w-full border border-[#242428] rounded-xl bg-[#0A0A0A] p-8 md:p-16 overflow-x-auto">
          <div className="min-w-[900px] flex flex-col gap-16">
            
            {/* Top Layer: Frontend & External */}
            <div className="grid grid-cols-3 gap-8">
              <div className="col-span-1">
                <div className="text-xs font-bold text-[#71717A] tracking-widest uppercase mb-4">Frontend</div>
                <div className="border border-[#242428] bg-[#0D0D0F] p-5 rounded-lg">
                  <div className="text-[#FAFAFA] font-bold mb-3">React Client</div>
                  <div className="flex gap-2 text-xs font-mono text-[#A1A1AA]">
                    <span className="bg-[#242428] px-2 py-1 rounded">Vite</span>
                    <span className="bg-[#242428] px-2 py-1 rounded">Tailwind</span>
                  </div>
                </div>
              </div>
              <div className="col-span-1 flex items-center justify-center">
                <div className="w-full h-px bg-[#242428] relative">
                  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[#0A0A0A] px-3 text-xs text-[#71717A] font-mono">SSE Telemetry</div>
                </div>
              </div>
              <div className="col-span-1">
                <div className="text-xs font-bold text-[#71717A] tracking-widest uppercase mb-4">External Source</div>
                <div className="border border-[#242428] bg-[#0D0D0F] p-5 rounded-lg flex items-center justify-center">
                  <div className="text-[#FAFAFA] font-bold">GitHub Repositories</div>
                </div>
              </div>
            </div>

            {/* Middle Layer: Core Services */}
            <div className="grid grid-cols-3 gap-8">
              <div className="col-span-1">
                <div className="text-xs font-bold text-[#71717A] tracking-widest uppercase mb-4">Knowledge Base</div>
                <div className="border border-[#242428] bg-[#0D0D0F] p-5 rounded-lg">
                  <div className="text-[#FAFAFA] font-bold mb-3">Vector Store</div>
                  <div className="flex gap-2 text-xs font-mono text-[#A1A1AA]">
                    <span className="bg-[#242428] px-2 py-1 rounded">ChromaDB</span>
                    <span className="bg-[#242428] px-2 py-1 rounded">Embeddings</span>
                  </div>
                </div>
              </div>
              <div className="col-span-1">
                <div className="text-xs font-bold text-[#8B5CF6] tracking-widest uppercase mb-4">Orchestrator</div>
                <div className="border-2 border-[#8B5CF6] bg-[#8B5CF6]/5 p-5 rounded-lg shadow-[0_0_20px_rgba(139,92,246,0.1)]">
                  <div className="text-[#FAFAFA] font-bold mb-3">FastAPI Backend</div>
                  <div className="flex gap-2 text-xs font-mono text-[#A1A1AA]">
                    <span className="bg-[#242428] px-2 py-1 rounded">SQLite</span>
                    <span className="bg-[#242428] px-2 py-1 rounded">Uvicorn</span>
                  </div>
                </div>
              </div>
              <div className="col-span-1">
                <div className="text-xs font-bold text-[#71717A] tracking-widest uppercase mb-4">CI/CD</div>
                <div className="border border-[#242428] bg-[#0D0D0F] p-5 rounded-lg">
                  <div className="text-[#FAFAFA] font-bold mb-3">Validation</div>
                  <div className="flex gap-2 text-xs font-mono text-[#A1A1AA]">
                    <span className="bg-[#242428] px-2 py-1 rounded">GitHub Actions</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Bottom Layer: Workers & Scanners */}
            <div className="grid grid-cols-2 gap-8">
              <div className="col-span-1">
                <div className="text-xs font-bold text-[#8B5CF6] tracking-widest uppercase mb-4">AI Worker Mesh</div>
                <div className="border border-[#242428] bg-[#0D0D0F] p-5 rounded-lg">
                  <div className="text-[#FAFAFA] font-bold mb-3">LangGraph Agents</div>
                  <div className="flex flex-wrap gap-2 text-xs font-mono text-[#8B5CF6]">
                    <span className="bg-[#8B5CF6]/10 border border-[#8B5CF6]/30 px-2 py-1 rounded">Repo Mapper</span>
                    <span className="bg-[#8B5CF6]/10 border border-[#8B5CF6]/30 px-2 py-1 rounded">Bug Investigator</span>
                    <span className="bg-[#8B5CF6]/10 border border-[#8B5CF6]/30 px-2 py-1 rounded">Repair Planner</span>
                    <span className="bg-[#8B5CF6]/10 border border-[#8B5CF6]/30 px-2 py-1 rounded">Code Generator</span>
                  </div>
                </div>
              </div>
              <div className="col-span-1">
                <div className="text-xs font-bold text-[#71717A] tracking-widest uppercase mb-4">Static Analysis Subsystems</div>
                <div className="border border-[#242428] bg-[#0D0D0F] p-5 rounded-lg">
                  <div className="text-[#FAFAFA] font-bold mb-3">SAST & Dependency Scanners</div>
                  <div className="flex flex-wrap gap-2 text-xs font-mono text-[#A1A1AA]">
                    <span className="bg-[#242428] px-2 py-1 rounded">Semgrep</span>
                    <span className="bg-[#242428] px-2 py-1 rounded">Bandit</span>
                    <span className="bg-[#242428] px-2 py-1 rounded">ESLint</span>
                    <span className="bg-[#242428] px-2 py-1 rounded">Pylint</span>
                    <span className="bg-[#242428] px-2 py-1 rounded">Go Vet</span>
                    <span className="bg-[#242428] px-2 py-1 rounded">Cargo Clippy</span>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>

      </div>
    </section>
  )
}
