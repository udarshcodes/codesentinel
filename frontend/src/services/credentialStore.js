class CredentialStore {
  /**
   * Generates a deterministic key for session storage to guarantee cycle isolation.
   */
  _getKey(taskId, cycleId) {
    return `approval_token_${taskId}_${cycleId}`;
  }

  getCurrentToken(taskId, cycleId) {
    if (!taskId || !cycleId) return null;
    return sessionStorage.getItem(this._getKey(taskId, cycleId));
  }

  setCurrentToken(taskId, cycleId, rawToken) {
    if (!taskId || !cycleId || !rawToken) return;
    sessionStorage.setItem(this._getKey(taskId, cycleId), rawToken);
  }

  clearCurrentToken(taskId, cycleId) {
    if (!taskId || !cycleId) return;
    sessionStorage.removeItem(this._getKey(taskId, cycleId));
  }

  hasCurrentToken(taskId, cycleId) {
    return !!this.getCurrentToken(taskId, cycleId);
  }

  clearStaleTokens(taskId, activeCycleId) {
    if (!taskId) return;
    const prefix = `approval_token_${taskId}_`;
    const keysToRemove = [];
    
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      if (key && key.startsWith(prefix)) {
        const cycleId = key.substring(prefix.length);
        if (cycleId !== activeCycleId) {
          keysToRemove.push(key);
        }
      }
    }
    
    keysToRemove.forEach(key => sessionStorage.removeItem(key));
  }

  clearAllTokens(taskId) {
    if (!taskId) return;
    this.clearStaleTokens(taskId, null);
    sessionStorage.removeItem(`view_token_${taskId}`);
  }


  getViewToken(taskId) {
    if (!taskId) return null;
    return sessionStorage.getItem(`view_token_${taskId}`);
  }

  setViewToken(taskId, token) {
    if (!taskId || !token) return;
    sessionStorage.setItem(`view_token_${taskId}`, token);
  }
}

export const credentialStore = new CredentialStore();
