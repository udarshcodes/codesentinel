const KEY = 'codesentinel_active_analysis'
const validTask = value => typeof value === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(value)

export function readAnalysisSession() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) || 'null')
    const requested = new URLSearchParams(window.location.search).get('task')
    const taskId = validTask(requested) ? requested : saved?.taskId
    if (!validTask(taskId)) return null
    return { taskId, repoUrl: saved?.taskId === taskId ? saved.repoUrl || '' : '', tasks: saved?.tasks || [] }
  } catch { return null }
}

export function saveAnalysisSession(taskId, repoUrl, tasks) {
  if (!validTask(taskId)) return
  try {
    sessionStorage.setItem(KEY, JSON.stringify({taskId, repoUrl, tasks: (tasks || []).map(t => ({task_id: t.task_id, repo_url: t.repo_url}))}))
    const url = new URL(window.location.href)
    url.searchParams.set('task', taskId)
    window.history.replaceState(null, '', url.pathname + url.search + url.hash)
  } catch { /* Storage may be unavailable; never expose capabilities in URLs. */ }
}

export function clearAnalysisSession() {
  try {
    sessionStorage.removeItem(KEY)
    const url = new URL(window.location.href)
    url.searchParams.delete('task')
    window.history.replaceState(null, '', url.pathname + url.search + url.hash)
  } catch { /* Keep the home action available when storage is blocked. */ }
}
