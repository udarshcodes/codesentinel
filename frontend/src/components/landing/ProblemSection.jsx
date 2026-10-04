export default function ProblemSection() {
  return (
    <section className="w-full py-24 md:py-32 bg-[#050505]">
      <div className="max-w-[1400px] mx-auto px-6 grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-center">
        
        {/* Left: Typography */}
        <div className="flex flex-col">
          <h2 className="text-4xl md:text-5xl font-bold tracking-tighter leading-tight text-[#FAFAFA] mb-6">
            Your scanners find the bugs.<br />
            <span className="text-[#A1A1AA]">Who fixes them?</span>
          </h2>
          <div className="w-12 h-1 bg-[#8B5CF6] mb-8"></div>
          <p className="text-lg text-[#A1A1AA] leading-relaxed max-w-lg mb-8">
            Modern development teams are drowning in security alerts. SAST, DAST, and dependency scanners generate thousands of findings, but offer zero remediation. 
          </p>
          <p className="text-lg text-[#A1A1AA] leading-relaxed max-w-lg">
            Engineering hours are wasted deciphering alerts, researching fixes, and writing boilerplate patches. CodeSentinel closes the loop by turning detection into autonomous action.
          </p>
        </div>

        {/* Right: Comparison layout */}
        <div className="flex flex-col gap-8">
          
          <div className="flex items-start gap-6 group">
            <div className="w-px h-full bg-[#242428] group-hover:bg-[#8B5CF6] transition-colors mt-2"></div>
            <div className="flex-1">
              <h3 className="text-[#FAFAFA] font-semibold text-xl mb-2">Alert Fatigue</h3>
              <p className="text-[#71717A] leading-relaxed">Security dashboards fill up with issues faster than engineers can triage them, leading to ignored critical vulnerabilities.</p>
            </div>
          </div>
          
          <div className="flex items-start gap-6 group">
            <div className="w-px h-full bg-[#242428] group-hover:bg-[#8B5CF6] transition-colors mt-2"></div>
            <div className="flex-1">
              <h3 className="text-[#FAFAFA] font-semibold text-xl mb-2">Slow Remediation</h3>
              <p className="text-[#71717A] leading-relaxed">It takes days or weeks to schedule, research, and test a fix for a newly disclosed CVE across a large microservice architecture.</p>
            </div>
          </div>

          <div className="flex items-start gap-6 group">
            <div className="w-px h-full bg-[#242428] group-hover:bg-[#8B5CF6] transition-colors mt-2"></div>
            <div className="flex-1">
              <h3 className="text-[#FAFAFA] font-semibold text-xl mb-2">Detection Without Action</h3>
              <p className="text-[#71717A] leading-relaxed">Traditional tools stop at &quot;You have a problem here.&quot; They provide no context aware, repository specific solution.</p>
            </div>
          </div>

        </div>

      </div>
    </section>
  )
}
