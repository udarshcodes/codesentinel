import React, { useMemo } from 'react'
import ReactDiffViewer from 'react-diff-viewer-continued'
import { Code2, ChevronDown, ChevronRight, FileJson, CheckCircle2, AlertCircle, XCircle } from 'lucide-react'

export default function DiffViewer({ state }) {
  const patches = state.patches || []

  const fileGroups = useMemo(() => {
    const groups = {}
    patches.forEach(patch => {
      const file = patch.file || 'unknown'
      if (!groups[file]) {
        groups[file] = {
          file,
          patches: [],
          generated: 0,
          applied: 0,
          rejected: 0
        }
      }
      groups[file].patches.push(patch)
      groups[file].generated++
      if (patch.applied) {
        groups[file].applied++
      } else {
        groups[file].rejected++
      }
    })
    return Object.values(groups)
  }, [patches])

  if (fileGroups.length === 0) return null

  return (
    <div id="patches-section" className="w-full max-w-6xl mx-auto mb-8">
      <div className="flex items-center gap-3 mb-6 px-2">
        <Code2 className="w-5 h-5 text-primary" />
        <h2 className="text-xl font-semibold text-foreground">AI Remediation Patches</h2>
      </div>

      <div className="space-y-4">
        {fileGroups.map((group, idx) => (
          <FilePatchGroup key={idx} group={group} state={state} />
        ))}
      </div>
    </div>
  )
}

function FilePatchGroup({ group, state }) {
  const [isOpen, setIsOpen] = React.useState(false)

  return (
    <div className="bg-card border border-border rounded-xl shadow-sm overflow-hidden">
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-secondary/10 hover:bg-secondary/20 px-6 py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-colors focus:outline-none"
      >
        <div className="flex items-center gap-3 w-full sm:w-auto">
          {isOpen ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
          <FileJson className="w-5 h-5 text-primary" />
          <span className="text-sm font-semibold text-foreground font-mono">{group.file}</span>
        </div>
        <div className="flex items-center gap-3 text-xs sm:text-sm whitespace-nowrap">
          <span className="text-muted-foreground"><strong className="text-foreground">{group.generated}</strong> generated</span>
          <div className="w-1 h-1 rounded-full bg-border"></div>
          <span className="text-[#22C55E]"><strong className="text-[#22C55E]">{group.applied}</strong> applied</span>
          <div className="w-1 h-1 rounded-full bg-border"></div>
          <span className="text-[#EF4444]"><strong className="text-[#EF4444]">{group.rejected}</strong> rejected</span>
        </div>
      </button>
      
      {isOpen && (
        <div className="p-4 sm:p-6 bg-background space-y-4">
          {group.patches.map((patch, idx) => (
            <PatchItem key={idx} patch={patch} state={state} />
          ))}
        </div>
      )}
    </div>
  )
}

function PatchItem({ patch, state }) {
  const [isOpen, setIsOpen] = React.useState(true)
  const [isSplitView, setIsSplitView] = React.useState(() => window.innerWidth >= 768)

  React.useEffect(() => {
    const handleResize = () => setIsSplitView(window.innerWidth >= 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

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

  const { oldString, newString } = parseDiff(patch.diff)
  
  let patchStatus = 'Generated'
  let patchStatusColor = 'text-muted-foreground'
  let patchStatusBg = 'bg-muted'
  let PatchIcon = Code2

  if (patch.applied) {
    const validation = state.validation_results?.find(v => v.patch === patch.patch_text || (patch.issue_id && v.issue_id === patch.issue_id))
    if (validation) {
      if (validation.passed) {
        if (state.security_verification && !state.security_verified) {
          patchStatus = 'Security Review Required'
          patchStatusColor = 'text-[#F59E0B]'
          patchStatusBg = 'bg-[#F59E0B]/10'
          PatchIcon = AlertCircle
        } else {
          patchStatus = 'Validated'
          patchStatusColor = 'text-[#22C55E]'
          patchStatusBg = 'bg-[#22C55E]/10'
          PatchIcon = CheckCircle2
        }
      } else {
        patchStatus = 'Validation Failed'
        patchStatusColor = 'text-[#EF4444]'
        patchStatusBg = 'bg-[#EF4444]/10'
        PatchIcon = XCircle
      }
    } else {
      patchStatus = 'Applied'
      patchStatusColor = 'text-primary'
      patchStatusBg = 'bg-primary/10'
    }
  } else if (patch.applied === false) {
    patchStatus = 'Rejected'
    patchStatusColor = 'text-[#EF4444]'
    patchStatusBg = 'bg-[#EF4444]/10'
    PatchIcon = XCircle
  }

  return (
    <div className="bg-[#080808] border border-[#242428] rounded-xl overflow-hidden shadow-sm">
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-[#0D0D0F] hover:bg-[#121214] px-4 py-3 border-b border-[#242428] flex flex-col sm:flex-row sm:items-center justify-between gap-3 transition-colors focus:outline-none"
      >
        <div className="flex items-center gap-3">
          {isOpen ? <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" /> : <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />}
          <span className="text-sm font-mono text-foreground line-clamp-1 text-left">{patch.issue_description || 'Target block'}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full font-semibold whitespace-nowrap ${patchStatusBg} ${patchStatusColor}`}>
            <PatchIcon className="w-3.5 h-3.5" />
            {patchStatus}
          </span>
        </div>
      </button>
      
      {isOpen && (
        <div className="text-left overflow-x-auto bg-[#080808] w-full max-w-full">
          <div className="min-w-fit">
            {React.createElement(ReactDiffViewer.default || ReactDiffViewer, {
              oldValue: oldString,
              newValue: newString,
              splitView: isSplitView,
              useDarkTheme: true,
              styles: newStyles,
              hideLineNumbers: false
            })}
          </div>
        </div>
      )}
    </div>
  )
}

