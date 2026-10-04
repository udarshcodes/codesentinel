import React from 'react'
import ReactDiffViewer from 'react-diff-viewer-continued'
import { Code2, ChevronDown, ChevronRight, FileJson } from 'lucide-react'

export default function DiffViewer({ state }) {
  let patches = state.patches || []

  if (patches.length === 0) return null

  const newStyles = {
    variables: {
      dark: {
        diffViewerBackground: '#080808',
        diffViewerColor: '#E4E4E7',
        addedBackground: 'rgba(34, 197, 94, 0.1)',
        addedColor: '#E4E4E7',
        removedBackground: 'rgba(239, 68, 68, 0.1)',
        removedColor: '#E4E4E7',
        wordAddedBackground: 'rgba(34, 197, 94, 0.25)',
        wordRemovedBackground: 'rgba(239, 68, 68, 0.25)',
        addedGutterBackground: 'rgba(34, 197, 94, 0.05)',
        removedGutterBackground: 'rgba(239, 68, 68, 0.05)',
        gutterBackground: '#050505',
        gutterBackgroundDark: '#0A0A0A',
        highlightBackground: 'rgba(139, 92, 246, 0.15)',
        highlightGutterBackground: 'rgba(139, 92, 246, 0.15)',
        codeFoldGutterBackground: '#0D0D0F',
        codeFoldBackground: '#0A0A0A',
        emptyLineBackground: '#080808',
        gutterColor: '#71717A',
        addedGutterColor: '#22C55E',
        removedGutterColor: '#EF4444',
      }
    },
    line: {
      fontSize: '13px',
      fontFamily: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
    },
    content: {
      width: '100%'
    }
  }

  const parseDiff = (patchStr) => {
    if (!patchStr) return { oldString: '', newString: '' }

    if (patchStr.includes('<<<SEARCH>>>') && patchStr.includes('<<<REPLACE>>>')) {
      const parts = patchStr.split('<<<REPLACE>>>')
      const searchPart = parts[0].split('<<<SEARCH>>>')[1] || ''
      const replacePart = parts[1] ? parts[1].split('<<<')[0] : ''
      return { oldString: searchPart.trim(), newString: replacePart.trim() }
    }

    const lines = patchStr.split('\n')
    let oldVal = []
    let newVal = []
    
    const hasDiffHeaders = patchStr.includes('--- ') || patchStr.includes('+++ ') || patchStr.includes('diff --git')
    if (!hasDiffHeaders && patchStr.trim().length > 0) {
      return { oldString: '', newString: patchStr }
    }

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
        oldVal.push(line)
        newVal.push(line)
      }
    }
    
    return { oldString: oldVal.join('\n'), newString: newVal.join('\n') }
  }

  return (
    <div className="w-full max-w-6xl mx-auto mb-8">
      <div className="flex items-center gap-3 mb-6 px-2">
        <Code2 className="w-5 h-5 text-primary" />
        <h2 className="text-xl font-semibold text-foreground">AI Generated Patches</h2>
      </div>

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
  const [isOpen, setIsOpen] = React.useState(true)
  const { oldString, newString } = parseDiff(patch.diff)
  const [isSplitView, setIsSplitView] = React.useState(() => window.innerWidth >= 768)

  React.useEffect(() => {
    const handleResize = () => setIsSplitView(window.innerWidth >= 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  return (
    <div className="bg-[#080808] border border-[#242428] rounded-xl overflow-hidden shadow-sm">
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-[#0D0D0F] hover:bg-[#121214] px-4 py-3 border-b border-[#242428] flex items-center justify-between transition-colors focus:outline-none"
      >
        <div className="flex items-center gap-3">
          {isOpen ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
          <FileJson className="w-4 h-4 text-primary" />
          <span className="text-sm font-mono text-foreground">{patch.file || 'Patch'}</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs text-primary bg-primary/10 px-2 py-0.5 rounded uppercase tracking-wider font-semibold">
            Generated
          </span>
        </div>
      </button>
      
      {isOpen && (
        <div className="text-left overflow-hidden bg-[#080808]">
          {React.createElement(ReactDiffViewer.default || ReactDiffViewer, {
            oldValue: oldString,
            newValue: newString,
            splitView: isSplitView,
            useDarkTheme: true,
            styles: newStyles,
            hideLineNumbers: false
          })}
        </div>
      )}
    </div>
  )
}
