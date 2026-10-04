export default function SupportedLanguages() {
  const languages = [
    { name: 'PYTHON', tools: ['BANDIT', 'PYLINT', 'FLAKE8'] },
    { name: 'JAVASCRIPT', tools: ['ESLINT'] },
    { name: 'TYPESCRIPT', tools: ['ESLINT'] },
    { name: 'JAVA', tools: ['STATIC ANALYSIS'] },
    { name: 'GO', tools: ['GO VET'] },
    { name: 'RUST', tools: ['CARGO CLIPPY'] },
    { name: 'HTML', tools: ['SECURITY ANALYSIS'] },
    { name: 'CSS', tools: ['SECURITY ANALYSIS'] },
  ]

  return (
    <section id="languages" className="w-full py-24 md:py-32 bg-[#050505]">
      <div className="max-w-[1400px] mx-auto px-6 grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-start">
        
        {/* Left: Typography */}
        <div className="flex flex-col sticky top-32">
          <h2 className="text-4xl md:text-5xl font-bold tracking-tighter leading-tight text-[#FAFAFA] mb-6">
            Built for the languages<br />
            <span className="text-[#A1A1AA]">you actually ship.</span>
          </h2>
          <div className="w-12 h-1 bg-[#8B5CF6] mb-8"></div>
          <p className="text-lg text-[#A1A1AA] leading-relaxed max-w-lg">
            CodeSentinel combines language specific static analysis with AI powered investigation and remediation.
          </p>
        </div>

        {/* Right: Technical Matrix */}
        <div className="w-full">
          <div className="border border-[#242428] rounded-xl overflow-hidden bg-[#0A0A0A]">
            {languages.map((lang, idx) => (
              <div 
                key={lang.name} 
                className={`flex flex-col sm:flex-row items-start sm:items-center justify-between p-6 hover:bg-[#0D0D0F] transition-colors ${idx !== languages.length - 1 ? 'border-b border-[#242428]' : ''}`}
              >
                <div className="text-[#FAFAFA] font-mono font-bold tracking-wider mb-3 sm:mb-0">
                  {lang.name}
                </div>
                <div className="flex flex-wrap gap-2">
                  {lang.tools.map(tool => (
                    <span 
                      key={tool} 
                      className="bg-[#242428] text-[#A1A1AA] text-xs font-mono font-semibold px-3 py-1.5 rounded"
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </section>
  )
}
