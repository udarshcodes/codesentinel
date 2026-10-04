export default function Footer() {
  const languages = ['Python', 'JavaScript', 'TypeScript', 'Java', 'Go', 'Rust', 'HTML', 'CSS']

  return (
    <footer className="w-full bg-[#050505] border-t border-[#242428] pt-16 pb-8 text-sm">
      <div className="max-w-[1400px] mx-auto px-6 grid grid-cols-1 md:grid-cols-4 gap-12 mb-16">
        
        {/* Brand & Mission */}
        <div className="md:col-span-2">
          <div className="flex items-center gap-3 mb-6">
            <img src="/logo.jpg" alt="CodeSentinel" className="w-[28px] h-[28px] rounded-full object-cover border border-[#242428]" />
            <span className="font-bold text-[#FAFAFA] text-lg">CodeSentinel</span>
          </div>
          <p className="text-[#A1A1AA] max-w-sm leading-relaxed">
            Autonomous AI vulnerability remediation. Built for engineers who want secure infrastructure without technical debt.
          </p>
        </div>
        
        {/* Product Navigation */}
        <div className="flex flex-col gap-4">
          <h4 className="font-semibold text-[#FAFAFA]">Product</h4>
          <a href="#features" className="text-[#A1A1AA] hover:text-[#FAFAFA] transition-colors">Features</a>
          <a href="#workflow" className="text-[#A1A1AA] hover:text-[#FAFAFA] transition-colors">How It Works</a>
          <a href="#languages" className="text-[#A1A1AA] hover:text-[#FAFAFA] transition-colors">Languages</a>
          <a href="#architecture" className="text-[#A1A1AA] hover:text-[#FAFAFA] transition-colors">Architecture</a>
          <a href="https://github.com/udarshcodes/codesentinel" target="_blank" rel="noreferrer" className="text-[#A1A1AA] hover:text-[#FAFAFA] transition-colors">GitHub</a>
          <a href="/admin" target="_blank" rel="noreferrer" className="text-[#A1A1AA] hover:text-[#FAFAFA] transition-colors">Admin Dashboard</a>
        </div>
        
        {/* Supported Languages */}
        <div className="flex flex-col gap-4">
          <h4 className="font-semibold text-[#FAFAFA]">Supported Languages</h4>
          <div className="grid grid-cols-2 gap-y-3 gap-x-4">
            {languages.map(lang => (
              <span key={lang} className="text-[#A1A1AA] hover:text-[#FAFAFA] transition-colors cursor-default">
                {lang}
              </span>
            ))}
          </div>
        </div>

      </div>

      <div className="max-w-[1400px] mx-auto px-6 border-t border-[#242428] pt-8 flex items-center justify-between">
        <p className="text-[#71717A]">&copy; {new Date().getFullYear()} CodeSentinel. All rights reserved.</p>

      </div>
    </footer>
  )
}
