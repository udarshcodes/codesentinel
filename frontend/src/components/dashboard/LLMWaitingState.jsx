import { Clock, RefreshCw } from 'lucide-react'

export default function LLMWaitingState({ pipelineState }) {
  if (pipelineState.status !== 'WAITING_FOR_LLM_CAPACITY') return null;

  return (
    <div className="bg-yellow-500/10 border border-yellow-500/30 p-8 mt-8 max-w-6xl w-full mx-auto rounded-[1.5rem] shadow-sm transition-colors duration-500">
      <div className="flex flex-col md:flex-row items-center gap-6">
        <div className="p-4 rounded-full bg-yellow-500/20">
          <Clock className="w-10 h-10 text-yellow-500 animate-pulse" />
        </div>
        <div className="flex-1 text-center md:text-left">
          <h2 className="text-2xl font-bold text-foreground mb-2">Waiting for Model Capacity</h2>
          <p className="text-muted-foreground mb-4">
            {pipelineState.pipeline_error || "The pipeline is temporarily paused due to LLM provider rate limits."}
          </p>
          
          <div className="flex flex-wrap items-center justify-center md:justify-start gap-4">
            {pipelineState.retry_count > 0 && (
              <span className="inline-flex items-center gap-2 bg-background px-4 py-2 rounded-lg border text-sm font-medium">
                <RefreshCw className="w-4 h-4 text-muted-foreground" />
                Retry Attempt: {pipelineState.retry_count}
              </span>
            )}
            
            {pipelineState.next_retry && (
              <span className="inline-flex items-center gap-2 bg-background px-4 py-2 rounded-lg border text-sm font-medium">
                Resuming automatically at: {new Date(pipelineState.next_retry).toLocaleTimeString()}
              </span>
            )}
            
            {pipelineState.model && (
              <span className="inline-flex items-center gap-2 bg-background px-4 py-2 rounded-lg border text-sm font-medium">
                Model: {pipelineState.model}
              </span>
            )}
            
          </div>
        </div>
      </div>
    </div>
  )
}
