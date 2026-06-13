import React from 'react'
import ConfidenceScore from './ConfidenceScore'

export default function PRSummary({ prUrl, confidenceScore, prError }) {
  // Show when pipeline is complete (we have a score or a pr result)
  if (!prUrl && !prError && !confidenceScore) return null

  return (
    <div className={`glass-panel p-8 mt-8 max-w-6xl w-full mx-auto animate-fade-in-up !rounded-[2.5rem] ${prUrl ? 'border-green-300' : 'border-amber-300'}`}>
      <div className="flex items-center gap-4 mb-6">
        <div className={`p-3 rounded-full ${prUrl ? 'bg-green-100' : 'bg-amber-100'}`}>
          {prUrl ? (
            <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          ) : (
            <svg className="w-8 h-8 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
            </svg>
          )}
        </div>
        <div>
          <h2 className="text-3xl font-bold text-slate-900">Pipeline Complete!</h2>
          <p className="text-slate-600">
            {prUrl
              ? 'All fixes have been generated, validated, and pushed.'
              : 'Analysis complete. See details below.'}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <ConfidenceScore score={confidenceScore || 0} />
      </div>

      <div className="bg-slate-50 rounded-[1.5rem] p-6 border border-slate-200">
        {prUrl ? (
          <>
            <h3 className="text-lg font-semibold text-slate-900 mb-2">Pull Request Ready</h3>
            <p className="text-slate-600 mb-4">
              The agent has successfully opened a structured Pull Request containing the validated unified diffs.
            </p>
            <a 
              href={prUrl} 
              target="_blank" 
              rel="noreferrer"
              className="inline-flex items-center gap-2 bg-slate-900 hover:bg-slate-800 border border-slate-700 text-white px-6 py-3 rounded-lg font-medium transition-colors"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
              View Pull Request on GitHub
            </a>
          </>
        ) : (
          <>
            <h3 className="text-lg font-semibold text-amber-600 mb-2">⚠️ Pull Request Could Not Be Created</h3>
            <p className="text-slate-600 mb-2">
              The analysis and code generation completed, but the PR could not be pushed to GitHub.
            </p>
            {prError && (
              <div className="bg-amber-50 rounded-lg p-4 mt-3 border border-amber-200">
                <p className="text-sm text-amber-700 font-mono">{prError}</p>
              </div>
            )}
            <p className="text-slate-500 text-sm mt-3">
              💡 <strong>Tip:</strong> Make sure your <code className="text-blue-600">GITHUB_TOKEN</code> in <code className="text-blue-600">.env</code> has <em>repo</em> write permissions. 
              Go to <a href="https://github.com/settings/tokens" target="_blank" rel="noreferrer" className="text-blue-600 underline">GitHub Token Settings</a> and ensure the token has the <code className="text-blue-600">repo</code> scope enabled.
            </p>
          </>
        )}
      </div>
    </div>
  )
}