import React from 'react'
import ReactDiffViewer from 'react-diff-viewer-continued'

export default function DiffViewer({ events }) {
  let patches = []

  events.forEach(e => {
    if (e.event === 'agent_complete' && e.data?.agent === 'code_generator') {
      patches = e.data.data.patches || []
    }
  })

  if (patches.length === 0) return null

  const newStyles = {
    line: {
      fontSize: '13px',
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
    }
  }

  // Parse unified diff into old/new strings
  const parseDiff = (patchStr) => {
    const lines = patchStr.split('\n')
    let oldVal = []
    let newVal = []
    
    // Skip diff header (--- a/file +++ b/file)
    let startIndex = 0
    while (startIndex < lines.length && (lines[startIndex].startsWith('---') || lines[startIndex].startsWith('+++') || lines[startIndex].startsWith('diff') || lines[startIndex].startsWith('index'))) {
      startIndex++
    }

    for (let i = startIndex; i < lines.length; i++) {
      const line = lines[i]
      if (line.startsWith('-')) {
        oldVal.push(line.substring(1))
      } else if (line.startsWith('+')) {
        newVal.push(line.substring(1))
      } else if (line.startsWith(' ')) {
        oldVal.push(line.substring(1))
        newVal.push(line.substring(1))
      } else {
        // Context or header
        oldVal.push(line)
        newVal.push(line)
      }
    }
    
    return { oldString: oldVal.join('\n'), newString: newVal.join('\n') }
  }

  return (
    <div className="glass-panel p-6 sm:p-8 w-full max-w-6xl mx-auto mb-8 animate-fade-in-up !rounded-[2.5rem]">
      <h2 className="text-2xl font-bold text-slate-900 mb-6 flex items-center gap-3">
        <svg className="w-6 h-6 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
        Generated Code Patches
      </h2>

      <div className="space-y-4">
        {patches.map((patch, idx) => (
          <PatchItem 
            key={idx} 
            patch={patch} 
            parseDiff={parseDiff} 
            newStyles={newStyles} 
          />
        ))}
      </div>
    </div>
  )
}

function PatchItem({ patch, parseDiff, newStyles }) {
  const [isOpen, setIsOpen] = React.useState(false)
  const { oldString, newString } = parseDiff(patch.diff)

  return (
    <div className="rounded-[1.5rem] overflow-hidden border border-slate-200 shadow-lg shadow-slate-200/50 transition-all duration-300">
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-slate-50 hover:bg-slate-100 px-4 py-4 border-b border-slate-200 flex items-center justify-between transition-colors focus:outline-none"
      >
        <div className="flex items-center gap-3">
          <svg 
            className={`w-5 h-5 text-slate-500 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`} 
            fill="none" 
            viewBox="0 0 24 24" 
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
          <svg className="w-5 h-5 text-slate-500" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" /></svg>
          <span className="text-sm font-mono font-semibold text-slate-900">{patch.file || 'Patch'}</span>
        </div>
        <span className="text-xs text-slate-500 font-mono tracking-wider uppercase">Diff Viewer</span>
      </button>
      
      {isOpen && (
        <div className="bg-white text-left animate-fade-in-down">
          <ReactDiffViewer
            oldValue={oldString}
            newValue={newString}
            splitView={true}
            useDarkTheme={false}
            styles={newStyles}
            hideLineNumbers={false}
          />
        </div>
      )}
    </div>
  )
}