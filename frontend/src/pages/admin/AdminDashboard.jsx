import { useState, useEffect } from 'react';
import { Activity, Key, ShieldAlert, Clock, Lock, Server } from 'lucide-react';
import ThemeToggle from '../../components/dashboard/ThemeToggle';

export default function AdminDashboard() {
  const [secret, setSecret] = useState('');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  useEffect(() => {

    let isMounted = true;
    const fetchUsage = async () => {
      try {
        const apiUrl = import.meta.env.VITE_API_URL || '';
        const res = await fetch(`${apiUrl}/api/v1/admin/telemetry`, { credentials: 'include' });
        if (!isMounted) return;
        
        if (res.status === 401) {
          setIsAuthenticated(false);
          return;
        }
        
        if (!res.ok) throw new Error('Network error');
        
        const json = await res.json();
        if (json.status === 'error') {
            throw new Error(json.message || json.error || 'Failed to fetch telemetry data');
        }
        setData(json);
        setIsAuthenticated(true);
        setError(null);
        setLastRefreshed(new Date());
      } catch (err) {
        if (isMounted) setError(err.message);
      }
    };

    fetchUsage();
    const interval = setInterval(() => {
      if (isAuthenticated) fetchUsage();
    }, 30000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [isAuthenticated]);

  const handleLogin = async (e) => {
    e.preventDefault();
    try {
      const apiUrl = import.meta.env.VITE_API_URL || '';
      const res = await fetch(`${apiUrl}/api/v1/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ secret })
      });
      if (res.ok) {
        setIsAuthenticated(true);
        setError(null);
      } else {
        setError('Invalid Admin Secret');
      }
    } catch {
      setError('Connection failed');
    }
  };

  const handleLogout = async () => {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || '';
      await fetch(`${apiUrl}/api/v1/admin/logout`, { method: 'POST', credentials: 'include' });
    } catch(err) {
      console.error(err);
    }
    setIsAuthenticated(false);
    setSecret('');
    setData(null);
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
        <div className="absolute top-6 right-6">
          <ThemeToggle />
        </div>
        <div className="glass-panel p-8 max-w-md w-full rounded-3xl animate-in fade-in zoom-in duration-500">
          <div className="flex justify-center mb-6">
            <div className="bg-primary p-4 rounded-2xl">
              <Lock className="w-8 h-8 text-primary-foreground" />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-center text-foreground mb-2">CodeSentinel Admin</h1>
          <p className="text-muted-foreground text-center mb-8">Authenticate to view pipeline telemetry.</p>
          
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label htmlFor="adminSecret" className="sr-only">Admin Secret</label>
              <input
                id="adminSecret"
                type="password"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-input focus:outline-none focus:ring-2 focus:ring-primary bg-muted/50 text-foreground transition-all"
                required
              />
            </div>
            {error && <p className="text-destructive text-sm text-center font-medium">{error}</p>}
            <button
              type="submit"
              className="w-full py-3 px-4 bg-primary hover:opacity-90 text-primary-foreground font-semibold rounded-xl transition-colors shadow-lg shadow-primary/20"
            >
              Authenticate
            </button>
          </form>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-background gap-4">
        <div className="w-12 h-12 border-4 border-border border-t-primary rounded-full animate-spin"></div>
        <p className="text-muted-foreground font-medium animate-pulse">Fetching telemetry...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background pb-12">
      {/* Header */}
      <header className="bg-card border-b border-border sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-primary p-2 rounded-lg">
              <Activity className="w-5 h-5 text-primary-foreground" />
            </div>
            <h1 className="text-xl font-bold text-foreground tracking-tight">CodeSentinel Telemetry</h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted px-3 py-1.5 rounded-full">
              <Clock className="w-4 h-4" />
              <span>Refreshed: {lastRefreshed?.toLocaleTimeString()}</span>
            </div>
            <ThemeToggle />
            <button onClick={handleLogout} className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
              Lock
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-8 space-y-8">
        
        {/* Stat Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard 
            icon={<Server className="w-6 h-6 text-blue-500" />}
            title="Total Models" 
            value={data.overview?.total_models ?? 0}
            sub="Active LLM endpoints"
          />
          <StatCard 
            icon={<Key className="w-6 h-6 text-yellow-500" />}
            title="Credential Pool" 
            value={data.overview?.total_keys ?? 0}
            sub="Total backend keys"
          />
          <StatCard 
            icon={<ShieldAlert className={`w-6 h-6 text-emerald-500`} />}
            title="Pipeline Health" 
            value={(data.pipeline_health || 'UNKNOWN').toUpperCase()}
            sub="General stability"
          />
          <StatCard 
            icon={<Activity className="w-6 h-6 text-primary" />}
            title="System Status" 
            value={data.overview?.status || 'UNKNOWN'}
            sub="Worker availability"
          />
          <StatCard 
            icon={<Server className="w-6 h-6 text-indigo-500" />}
            title="Global Cache" 
            value={
              <div className="flex gap-2 items-center mt-1">
                <span className="text-emerald-500 text-sm">Hits: {data.overview?.cache_metrics?.hits || 0}</span>
                <span className="text-amber-500 text-sm">Misses: {data.overview?.cache_metrics?.misses || 0}</span>
              </div>
            }
            sub="Response Caching"
          />
        </div>

        {/* Model Telemetry */}
        <div className="glass-panel rounded-3xl p-6 sm:p-8">
          <h2 className="text-xl font-bold text-foreground mb-6 flex items-center gap-2">
            Model Health & Usage
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {Object.entries(data.models || {}).map(([model, mData]) => (
              <div key={model} className="bg-muted rounded-2xl p-4 border border-border/50">
                <h3 className="font-semibold text-foreground mb-4 text-sm truncate">{model}</h3>
                <div className="space-y-3">
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-muted-foreground">Requests</span>
                    <span className="font-medium text-foreground">{mData.requests?.toLocaleString() || 0}</span>
                  </div>
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-muted-foreground">Tokens</span>
                    <span className="font-medium text-foreground">{mData.tokens?.toLocaleString() || 0}</span>
                  </div>
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-muted-foreground">Failures</span>
                    <span className="font-medium text-foreground">{mData.failures || 0}</span>
                  </div>
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-muted-foreground">Status</span>
                    <span className={`font-semibold uppercase text-xs ${mData.rate_limit_status === 'ok' ? 'text-emerald-500' : 'text-amber-500'}`}>{mData.rate_limit_status || 'UNKNOWN'}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Credential Telemetry */}
        <div className="glass-panel rounded-3xl p-6 sm:p-8">
            <h2 className="text-xl font-bold text-foreground mb-6 flex items-center gap-2">
              Credential Health
            </h2>
            <div className="space-y-8">
              {Object.entries(data.credentials || {}).map(([keyId, keyData]) => (
                <div key={keyId} className="space-y-4">
                  <h3 className="font-semibold text-foreground border-b border-border pb-2">{keyId}</h3>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {Object.entries(keyData || {}).map(([model, st]) => (
                       <div key={model} className={`rounded-xl p-3 border ${st.status === 'exhausted' ? 'border-destructive/30 bg-destructive/5' : 'border-border bg-card'} text-sm`}>
                         <div className="flex justify-between items-center mb-2">
                           <span className="text-muted-foreground truncate max-w-[120px]" title={model}>{model.split('/').pop()}</span>
                           <span className={`text-xs font-bold uppercase ${st.status === 'active' ? 'text-emerald-500' : st.status === 'rate_limited' ? 'text-amber-500' : 'text-destructive'}`}>
                             {st.status || 'UNKNOWN'}
                           </span>
                         </div>
                         <div className="flex justify-between items-center">
                           <span className="text-muted-foreground text-xs">Tokens:</span>
                           <span className="font-medium text-xs">{st.tokens?.toLocaleString() || 0}</span>
                         </div>
                         <div className="flex justify-between items-center mt-1">
                           <span className="text-muted-foreground text-xs">Failures:</span>
                           <span className="font-medium text-xs">{st.failures || 0}</span>
                         </div>
                       </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
        </div>

      </main>
    </div>
  );
}

function StatCard({ icon, title, value, sub, alert }) {
  return (
    <div className={`glass-panel p-6 rounded-3xl transition-all duration-300 hover:shadow-2xl hover:-translate-y-1 ${alert ? 'ring-2 ring-destructive/50' : ''}`}>
      <div className="flex items-center gap-4 mb-4">
        <div className={`p-3 rounded-2xl ${alert ? 'bg-destructive/10' : 'bg-muted'}`}>
          {icon}
        </div>
        <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
      </div>
      <div className="space-y-1">
        <p className="text-3xl font-bold text-foreground">{value}</p>
        <p className="text-sm text-muted-foreground font-medium">{sub}</p>
      </div>
    </div>
  );
}
