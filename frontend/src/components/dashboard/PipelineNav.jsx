import React from 'react'

export default function PipelineNav() {
  const scrollTo = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <div className="sticky top-0 z-40 bg-background/80 backdrop-blur-md border-b border-border w-full py-3 px-6 mb-8 shadow-sm flex items-center justify-center gap-4 sm:gap-8 overflow-x-auto whitespace-nowrap text-sm font-medium">
      <button onClick={() => scrollTo('pipeline-overview')} className="text-muted-foreground hover:text-foreground transition-colors">Overview</button>
      <button onClick={() => scrollTo('findings-section')} className="text-muted-foreground hover:text-foreground transition-colors">Findings</button>
      <button onClick={() => scrollTo('patches-section')} className="text-muted-foreground hover:text-foreground transition-colors">Patches</button>
      <button onClick={() => scrollTo('pr-summary')} className="text-muted-foreground hover:text-foreground transition-colors">Pull Request</button>
    </div>
  )
}
