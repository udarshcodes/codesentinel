export default function WorkflowSection() {
  const steps = [
    { num: '01', title: 'Repository Mapping', desc: 'Understand the repository structure.' },
    { num: '02', title: 'Dependency Analysis', desc: 'Identify vulnerable dependencies.' },
    { num: '03', title: 'Static Analysis', desc: 'Run security and quality scanners.' },
    { num: '04', title: 'AI Investigation', desc: 'Understand the vulnerability in context.' },
    { num: '05', title: 'Repair Planning', desc: 'Determine the safest remediation.' },
    { num: '06', title: 'Code Generation', desc: 'Generate the patch.' },
    { num: '07', title: 'Validation', desc: 'Build and test the change.' },
    { num: '08', title: 'Security Verification', desc: 'Rescan the modified code.' },
    { num: '09', title: 'Pull Request', desc: 'Open the verified fix.' }
  ]

  return (
    <section id="workflow" className="w-full py-24 md:py-32 bg-[#0A0A0A] border-t border-b border-[#242428] relative overflow-hidden">
      
      {/* Background grid */}
      <div className="absolute inset-0 opacity-[0.03] pointer-events-none" style={{ backgroundImage: 'linear-gradient(#FAFAFA 1px, transparent 1px), linear-gradient(90deg, #FAFAFA 1px, transparent 1px)', backgroundSize: '40px 40px' }}></div>
      
      <div className="max-w-[1400px] mx-auto px-6 relative z-10">
        <div className="mb-16 md:mb-24">
          <h2 className="text-4xl md:text-5xl font-bold tracking-tighter text-[#FAFAFA] mb-6">
            From vulnerability to verified Pull Request.
          </h2>
          <p className="text-lg text-[#A1A1AA] max-w-2xl">
            A completely autonomous pipeline that takes security from an alert on a dashboard to a verified patch ready for review.
          </p>
        </div>

        {/* Technical Process Visualization */}
        <div className="relative">
          {/* Connecting horizontal line (desktop) */}
          <div className="hidden lg:block absolute top-[28px] left-0 right-0 h-px bg-[#242428]"></div>
          {/* Highlight line overlay */}
          <div className="hidden lg:block absolute top-[28px] left-0 right-1/2 h-px bg-gradient-to-r from-transparent via-[#8B5CF6] to-transparent opacity-50"></div>

          {/* Connecting vertical line (mobile) */}
          <div className="block lg:hidden absolute top-0 bottom-0 left-[28px] w-px bg-[#242428]"></div>
          
          <div className="grid grid-cols-1 lg:grid-cols-9 gap-8 lg:gap-4 relative z-10">
            {steps.map((step, idx) => (
              <div key={idx} className="flex lg:flex-col items-start gap-6 lg:gap-6 group">
                <div className="w-14 h-14 rounded-full bg-[#050505] border border-[#242428] flex items-center justify-center font-mono font-bold text-lg text-[#71717A] group-hover:text-[#FAFAFA] group-hover:border-[#8B5CF6] transition-all shadow-[0_0_0_4px_#0A0A0A] shrink-0 z-10">
                  {step.num}
                </div>
                <div className="pt-2 lg:pt-0">
                  <h3 className="text-[#FAFAFA] font-semibold text-sm mb-2">{step.title}</h3>
                  <p className="text-[#71717A] text-xs leading-relaxed max-w-[200px]">{step.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </section>
  )
}
