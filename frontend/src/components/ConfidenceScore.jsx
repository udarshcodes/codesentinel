

export default function ConfidenceScore({ score }) {
  if (score == null || isNaN(score)) return null
  let colorClass = 'text-green-400'
  let bgClass = 'bg-green-400/10'
  let label = 'High Confidence'
  
  if (score < 80) {
    colorClass = 'text-yellow-400'
    bgClass = 'bg-yellow-400/10'
    label = 'Medium Confidence'
  }
  if (score < 50) {
    colorClass = 'text-destructive'
    bgClass = 'bg-destructive/10'
    label = 'Low Confidence'
  }

  return (
    <div className={`p-4 rounded-[1.5rem] border border-border bg-card shadow-lg flex items-center justify-between`}>
      <div>
        <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-1">Fix Confidence Score</h3>
        <p className={`text-lg font-bold ${colorClass}`}>{label}</p>
      </div>
      <div className={`text-3xl font-bold ${colorClass} ${bgClass} px-4 py-2 rounded-xl`}>
        {(score ?? 0).toFixed(1)}%
      </div>
    </div>
  )
}