import { Shield, ChevronRight } from 'lucide-react'

export default function MultiRepoSection() {
  const repos = [
    { name: 'github.com/udarshcodes/codesentinel', status: 'Analyzing', color: 'text-[#8B5CF6]', bg: 'bg-[#8B5CF6]/10', border: 'border-[#8B5CF6]/30', dot: 'bg-[#8B5CF6]' },
    { name: 'github.com/udarshcodes/identity', status: 'Needs Review', color: 'text-[#F59E0B]', bg: 'bg-[#F59E0B]/10', border: 'border-[#F59E0B]/30', dot: 'bg-[#F59E0B]' },
    { name: 'github.com/udarshcodes/frontend', status: 'Complete', color: 'text-[#22C55E]', bg: 'bg-[#22C55E]/10', border: 'border-[#22C55E]/30', dot: 'bg-[#22C55E]' },
    { name: 'github.com/udarshcodes/backend', status: 'Complete', color: 'text-[#22C55E]', bg: 'bg-[#22C55E]/10', border: 'border-[#22C55E]/30', dot: 'bg-[#22C55E]' },
    { name: 'github.com/udarshcodes/mobile', status: 'Complete', color: 'text-[#22C55E]', bg: 'bg-[#22C55E]/10', border: 'border-[#22C55E]/30', dot: 'bg-[#22C55E]' }
  ]

  return (
    <section className="w-full py-24 md:py-32 bg-[#050505]">
      <div className="max-w-[1400px] mx-auto px-6 grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-center">
        
        {/* Left: Typography */}
        <div className="flex flex-col">
          <h2 className="text-4xl md:text-5xl font-bold tracking-tighter leading-tight text-[#FAFAFA] mb-6">
            Scale across your<br />
            <span className="text-[#A1A1AA]">entire organization.</span>
          </h2>
          <div className="w-12 h-1 bg-[#8B5CF6] mb-8"></div>
          <p className="text-lg text-[#A1A1AA] leading-relaxed max-w-lg mb-8">
            Security doesn&apos;t happen in a single repository. CodeSentinel supports organization wide batch analysis, letting you remediate vulnerabilities across your entire microservice architecture simultaneously.
          </p>
          <div className="bg-[#0A0A0A] border border-[#242428] rounded-md p-4 max-w-md font-mono text-sm">
            <span className="text-[#71717A]">$</span> <span className="text-[#FAFAFA]">codesentinel analyze</span> <span className="text-[#8B5CF6]">github.com/udarshcodes/*</span>
          </div>
        </div>

        {/* Right: Realistic Repository List */}
        <div className="w-full">
          <div className="border border-[#242428] rounded-xl overflow-hidden bg-[#0A0A0A] shadow-2xl">
            
            <div className="p-4 border-b border-[#242428] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Shield className="w-4 h-4 text-[#71717A]" />
                <span className="text-[#FAFAFA] font-semibold text-sm">Organization Scan</span>
              </div>
              <span className="text-[#A1A1AA] text-xs font-mono">5 repositories</span>
            </div>

            <div className="flex flex-col divide-y divide-[#242428]">
              {repos.map((repo) => (
                <div key={repo.name} className="p-4 hover:bg-[#0D0D0F] transition-colors flex items-center justify-between group cursor-default">
                  <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                    <span className="text-[#FAFAFA] font-mono text-sm">{repo.name}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className={`px-2 py-1 rounded text-xs font-bold uppercase tracking-wider flex items-center gap-1.5 border ${repo.bg} ${repo.border} ${repo.color}`}>
                      <div className={`w-1.5 h-1.5 rounded-full ${repo.dot} ${repo.status === 'Analyzing' ? 'animate-pulse' : ''}`}></div>
                      {repo.status}
                    </div>
                    <ChevronRight className="w-4 h-4 text-[#242428] group-hover:text-[#A1A1AA] transition-colors hidden sm:block" />
                  </div>
                </div>
              ))}
            </div>

          </div>
        </div>

      </div>
    </section>
  )
}
