import React, { Suspense, useEffect, useRef } from 'react'
import { ArrowRight } from 'lucide-react'

const Spline = React.lazy(() => import('@splinetool/react-spline'))

export default function Hero() {
  const splineWrapperRef = useRef(null)

  useEffect(() => {
    const wrapper = splineWrapperRef.current
    if (!wrapper) return

    const stopPropagation = (e) => e.stopPropagation()

    // Use native capture phase to intercept wheel/touch events before they reach the Spline canvas
    wrapper.addEventListener('wheel', stopPropagation, { capture: true })
    wrapper.addEventListener('touchmove', stopPropagation, { capture: true })

    return () => {
      wrapper.removeEventListener('wheel', stopPropagation, { capture: true })
      wrapper.removeEventListener('touchmove', stopPropagation, { capture: true })
    }
  }, [])

  return (
    <section className="relative w-full min-h-screen flex items-end bg-hero-bg overflow-hidden">
      {/* Spline 3D Background */}
      <div className="absolute inset-0" ref={splineWrapperRef}>
        <Suspense fallback={<div className="absolute inset-0 bg-hero-bg" />}>
          <Spline
            scene="https://prod.spline.design/Slk6b8kz3LRlKiyk/scene.splinecode"
            className="w-full h-full"
          />
        </Suspense>
      </div>

      {/* Dark overlay */}
      <div className="absolute inset-0 bg-black/30 z-[1] pointer-events-none" />

      {/* Content container */}
      <div className="relative z-10 pointer-events-none w-full max-w-[90%] sm:max-w-md lg:max-w-3xl px-6 md:px-10 pb-10 md:pb-10 pt-32">

        <h1
          className="text-[clamp(3rem,8vw,6rem)] font-bold leading-[1.05] tracking-[-0.05em] text-foreground mb-2 md:mb-4 uppercase animate-in fade-in slide-in-from-bottom-8 duration-700 fill-mode-forwards"
          style={{ animationDelay: '200ms' }}
        >
          Find the vulnerability.<br />
          Fix the vulnerability.<br />
          <span className="text-primary">Ship the fix.</span>
        </h1>

        <p
          className="text-foreground/80 text-[clamp(1.125rem,2.5vw,1.875rem)] font-light mb-3 md:mb-6 animate-in fade-in slide-in-from-bottom-8 duration-700 fill-mode-forwards"
          style={{ animationDelay: '400ms' }}
        >
          Autonomous security remediation for the code you actually ship.
        </p>

        <p
          className="text-muted-foreground text-[clamp(0.875rem,1.5vw,1.25rem)] font-light mb-4 md:mb-8 animate-in fade-in slide-in-from-bottom-8 duration-700 fill-mode-forwards"
          style={{ animationDelay: '550ms' }}
        >
          CodeSentinel maps your repository, finds vulnerabilities, investigates their root causes, generates contextually aware fixes, validates the changes and opens a GitHub Pull Request ready for review.
        </p>

        <div
          className="flex flex-wrap gap-3 font-bold animate-in fade-in slide-in-from-bottom-8 duration-700 fill-mode-forwards"
          style={{ animationDelay: '700ms' }}
        >
          <button
            className="pointer-events-auto bg-primary text-primary-foreground px-6 py-3 md:px-8 md:py-4 text-sm rounded-sm cursor-pointer hover:brightness-110 transition-all active:scale-[0.97] flex items-center gap-2"
            onClick={() => document.getElementById('repo-analyzer')?.scrollIntoView({ behavior: 'smooth' })}
          >
            Analyze Repository <ArrowRight className="w-4 h-4" />
          </button>
          <a
            href="https://github.com/udarshcodes/codesentinel"
            target="_blank"
            rel="noreferrer"
            className="pointer-events-auto bg-white text-background px-6 py-3 md:px-8 md:py-4 text-sm rounded-sm cursor-pointer hover:brightness-90 transition-all active:scale-[0.97]"
          >
            View on GitHub
          </a>
        </div>

        <p
          className="text-muted-foreground/60 text-xs font-light mt-4 md:mt-6 animate-in fade-in slide-in-from-bottom-8 duration-700 fill-mode-forwards"
          style={{ animationDelay: '850ms' }}
        >
          26 ANALYSIS MODULES • 8 SUPPORTED LANGUAGES • RAG FIX MEMORY • GITHUB PRs
        </p>
      </div>
    </section>
  )
}
