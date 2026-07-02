import React, { useState, useEffect, useCallback } from 'react';
import { Activity, Key, ShieldAlert, Zap, Clock, Lock } from 'lucide-react';
import ThemeToggle from './components/ThemeToggle';

export default function App() {
  const [secret, setSecret] = useState(localStorage.getItem('adminSecret') || '');
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('adminSecret'));
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  const fetchUsage = useCallback(async () => {
    try {
      const res = await fetch('/admin/token-usage', {
        headers: { 'x-admin-token': secret }
      });
      if (res.status === 401) {
        setIsAuthenticated(false);
        localStorage.removeItem('adminSecret');
        setError('Invalid Admin Secret');
        return;
      }
      if (!res.ok) throw new Error('Network response was not ok');
      const json = await res.json();
      setData(json);
      setError(null);
      setLastRefreshed(new Date());
    } catch (err) {
      setError(err.message);
    }
  }, [secret]);

  useEffect(() => {
    if (isAuthenticated) {
      fetchUsage();
      const interval = setInterval(fetchUsage, 30000);
      return () => clearInterval(interval);
    }
  }, [isAuthenticated, fetchUsage]);

  const handleLogin = (e) => {
    e.preventDefault();
    localStorage.setItem('adminSecret', secret);
    setIsAuthenticated(true);
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    setSecret('');
    localStorage.removeItem('adminSecret');
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
          <p className="text-muted-foreground text-center mb-8">Enter the master secret to access token observability.</p>
          
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <input
                type="password"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder="Admin Secret"
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
            <h1 className="text-xl font-bold text-foreground tracking-tight">Token Observability</h1>
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
            icon={<Zap className="w-6 h-6 text-yellow-500" />}
            title="Total Tokens Used" 
            value={data.summary.total_tokens_used.toLocaleString()} 
            sub={`of ${data.summary.total_budget.toLocaleString()} daily budget`}
          />
          <StatCard 
            icon={<Key className="w-6 h-6 text-blue-500" />}
            title="Active Primary Keys" 
            value={`${data.summary.active_primary_keys} / ${Object.keys(data.primary_keys).length}`}
            sub="Currently in round-robin"
          />
          <StatCard 
            icon={<ShieldAlert className={`w-6 h-6 ${data.summary.emergency_engaged ? 'text-destructive' : 'text-emerald-500'}`} />}
            title="Emergency Key" 
            value={data.summary.emergency_engaged ? 'ACTIVE' : 'Standby'}
            sub={data.emergency_key.available ? "Loaded and ready" : "Not configured"}
            alert={data.summary.emergency_engaged}
          />
          <StatCard 
            icon={<Activity className="w-6 h-6 text-primary" />}
            title="System Status" 
            value={data.summary.active_primary_keys > 0 || (data.emergency_key.available && !(data.emergency_key.percent_used >= 100)) ? 'Operational' : 'Exhausted'}
            sub="Pipeline availability"
          />
        </div>

        {/* Primary Keys */}
        <div className="glass-panel rounded-3xl p-6 sm:p-8">
          <h2 className="text-xl font-bold text-foreground mb-6 flex items-center gap-2">
            Primary Key Pool
          </h2>
          <div className="space-y-6">
            {Object.entries(data.primary_keys).map(([idx, keyData]) => (
              <KeyProgress key={idx} index={idx} data={keyData} />
            ))}
          </div>
        </div>

        {/* Emergency Key */}
        <div className={`glass-panel rounded-3xl p-6 sm:p-8 transition-colors duration-500 ${data.summary.emergency_engaged ? 'border-destructive/50 bg-destructive/10' : ''}`}>
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-foreground flex items-center gap-2">
              Emergency Reserve
            </h2>
            {data.summary.emergency_engaged && (
              <span className="px-3 py-1 bg-destructive/20 text-destructive rounded-full text-xs font-bold uppercase tracking-widest animate-pulse">
                Engaged
              </span>
            )}
          </div>
          {data.emergency_key.available ? (
            <KeyProgress index="E" data={data.emergency_key} isEmergency />
          ) : (
            <p className="text-muted-foreground text-sm">No emergency key configured in environment.</p>
          )}
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

function KeyProgress({ index, data, isEmergency }) {
  const percent = data.percent_used;
  let color = 'bg-emerald-500';
  let lightColor = 'bg-emerald-100';
  let textColor = 'text-emerald-700';
  
  if (percent >= 85) {
    color = 'bg-destructive';
    lightColor = 'bg-destructive/20';
    textColor = 'text-destructive';
  } else if (percent >= 60) {
    color = 'bg-amber-500';
    lightColor = 'bg-amber-100';
    textColor = 'text-amber-700';
  }

  const isExhausted = data.status === 'exhausted' || percent >= 100;

  return (
    <div>
      <div className="flex justify-between items-end mb-2">
        <div className="flex items-center gap-3">
          <span className={`w-8 h-8 flex items-center justify-center rounded-xl font-bold text-sm ${isEmergency ? 'bg-primary/20 text-primary' : 'bg-muted text-foreground'}`}>
            {isEmergency ? 'E' : parseInt(index) + 1}
          </span>
          <div>
            <span className="text-sm font-semibold text-foreground">{isEmergency ? 'Emergency Key' : `Key #${parseInt(index) + 1}`}</span>
            {isExhausted && <span className="ml-2 text-xs font-bold text-destructive uppercase tracking-wider">Exhausted</span>}
          </div>
        </div>
        <div className="text-right">
          <span className="text-sm font-bold text-foreground">{data.tokens_used.toLocaleString()}</span>
          <span className="text-sm text-muted-foreground"> / {data.budget.toLocaleString()}</span>
        </div>
      </div>
      <div className="h-3 w-full bg-muted rounded-full overflow-hidden">
        <div 
          className={`h-full ${color} transition-all duration-1000 ease-out`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
    </div>
  );
}
