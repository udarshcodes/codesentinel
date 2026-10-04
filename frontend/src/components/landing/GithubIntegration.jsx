import { Check, Shield } from 'lucide-react'

const GithubIcon = ({ className }) => (
  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
    <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.2c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4"/>
    <path d="M9 18c-4.51 2-5-2-7-2"/>
  </svg>
)

export default function GithubIntegration() {
  return (
    <section className="w-full py-24 md:py-32 bg-[#0A0A0A] border-t border-b border-[#242428]">
      <div className="max-w-[1400px] mx-auto px-6 grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-center">
        
        {/* Left: Typography */}
        <div className="flex flex-col">
          <h2 className="text-4xl md:text-5xl font-bold tracking-tighter leading-tight text-[#FAFAFA] mb-6">
            The process ends with a <br />
            <span className="text-[#A1A1AA]">real engineering artifact.</span>
          </h2>
          <div className="w-12 h-1 bg-[#8B5CF6] mb-8"></div>
          <p className="text-lg text-[#A1A1AA] leading-relaxed max-w-lg mb-8">
            CodeSentinel doesn&apos;t just create a ticket in Jira. It completes the engineering lifecycle by opening a structured, verified Pull Request directly in your repository.
          </p>
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-3 text-[#A1A1AA] font-mono text-sm">
              <Check className="w-4 h-4 text-[#22C55E]" /> Detailed issue description
            </div>
            <div className="flex items-center gap-3 text-[#A1A1AA] font-mono text-sm">
              <Check className="w-4 h-4 text-[#22C55E]" /> Validated code patch
            </div>
            <div className="flex items-center gap-3 text-[#A1A1AA] font-mono text-sm">
              <Check className="w-4 h-4 text-[#22C55E]" /> Green CI/CD checks
            </div>
            <div className="flex items-center gap-3 text-[#A1A1AA] font-mono text-sm">
              <Check className="w-4 h-4 text-[#22C55E]" /> High confidence score
            </div>
          </div>
        </div>

        {/* Right: PR Visual Representation */}
        <div className="w-full bg-[#050505] border border-[#242428] rounded-xl overflow-hidden shadow-2xl">
          
          <div className="p-4 border-b border-[#242428] bg-[#0A0A0A] flex items-center gap-3">
            <GithubIcon className="w-5 h-5 text-[#FAFAFA]" />
            <span className="text-[#FAFAFA] font-semibold text-sm">Example: company/payments</span>
            <span className="text-[#A1A1AA] text-sm">#142</span>
          </div>

          <div className="p-6">
            <h3 className="text-xl font-bold text-[#FAFAFA] mb-4">Example: Fix SQL Injection in authentication service</h3>
            
            <div className="flex items-center gap-3 mb-6">
              <span className="bg-[#22C55E]/10 text-[#22C55E] border border-[#22C55E]/30 px-3 py-1 rounded-full text-xs font-semibold flex items-center gap-1.5">
                <Check className="w-3 h-3" /> Open
              </span>
              <span className="text-[#A1A1AA] text-sm font-mono flex items-center gap-2">
                <img src="/logo.jpg" alt="Logo" className="w-4 h-4 rounded-full border border-[#242428]" />
                codesentinel[bot]
              </span>
            </div>

            <div className="bg-[#0A0A0A] border border-[#242428] rounded-lg p-4 mb-6 text-sm text-[#A1A1AA] font-mono space-y-4">
              <p className="text-[#FAFAFA]">This PR resolves a High severity SQL Injection vulnerability detected by Bandit (B608).</p>
              <div className="border-l-2 border-[#242428] pl-3 py-1">
                Remediation: Refactored string based query construction to use parameterized queries across 3 files.
              </div>
              <div className="grid grid-cols-2 gap-4 pt-2">
                <div>
                  <div className="text-[#71717A] text-xs mb-1 uppercase tracking-wider">Confidence Score</div>
                  <div className="text-[#FAFAFA] font-bold">98.4<span className="text-[#8B5CF6]">%</span></div>
                </div>
                <div>
                  <div className="text-[#71717A] text-xs mb-1 uppercase tracking-wider">Files Changed</div>
                  <div className="text-[#FAFAFA] font-bold">+12 <span className="text-[#71717A] font-normal">−8</span></div>
                </div>
              </div>
            </div>

            <div className="space-y-3">
              <div className="flex items-center gap-3 p-3 border border-[#242428] rounded-md bg-[#0D0D0F]">
                <Check className="w-4 h-4 text-[#22C55E]" />
                <span className="text-[#FAFAFA] text-sm font-semibold flex-1">Build</span>
                <span className="text-[#71717A] text-xs font-mono">Successful in 42s</span>
              </div>
              <div className="flex items-center gap-3 p-3 border border-[#242428] rounded-md bg-[#0D0D0F]">
                <Check className="w-4 h-4 text-[#22C55E]" />
                <span className="text-[#FAFAFA] text-sm font-semibold flex-1">Tests</span>
                <span className="text-[#71717A] text-xs font-mono">248 passed</span>
              </div>
              <div className="flex items-center gap-3 p-3 border border-[#8B5CF6]/30 rounded-md bg-[#8B5CF6]/5">
                <Shield className="w-4 h-4 text-[#8B5CF6]" />
                <span className="text-[#FAFAFA] text-sm font-semibold flex-1">Security Rescan</span>
                <span className="text-[#8B5CF6] text-xs font-mono font-bold">0 vulnerabilities</span>
              </div>
            </div>
            
            <div className="text-xs text-[#71717A] italic mt-6 text-center">
              Note: This is an illustrative demonstration of a generated Pull Request.
            </div>
            
          </div>
        </div>

      </div>
    </section>
  )
}
