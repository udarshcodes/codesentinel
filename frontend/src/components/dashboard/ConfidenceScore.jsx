export default function ConfidenceScore({ score }) {
  if (score == null || isNaN(score)) return null
  
  const scoreValue = score ?? 0
  const isHigh = scoreValue >= 80

  return (
    <div className="bg-card border border-border p-6 rounded-2xl shadow-sm flex items-center justify-between">
      <div>
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-2">Aggregate Fix Confidence</h3>
        <p className="text-xs text-muted-foreground opacity-80 max-w-[200px] sm:max-w-[250px]">
          Score derived from test suite passage, semantic codebase context alignment, and historical repository fix success rates.
        </p>
      </div>
      
      <div className="flex items-center gap-4">
        <div className="text-right">
          <span className="text-3xl font-bold text-foreground">
            {scoreValue.toFixed(1)}<span className="text-primary">%</span>
          </span>
        </div>
        
        <div className="relative w-16 h-16">
          <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
            {/* Background Track */}
            <path
              className="text-border"
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
            />
            {/* Progress indicator */}
            <path
              className="text-primary transition-all duration-1000 ease-out"
              strokeDasharray={`${scoreValue}, 100`}
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
            />
          </svg>
        </div>
      </div>
    </div>
  )
}
