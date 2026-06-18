import React, { useState, useEffect } from 'react';
import { Activity, Key, ShieldAlert, Zap, Clock, Lock } from 'lucide-react';

export default function App() {
  const [secret, setSecret] = useState(localStorage.getItem('adminSecret') || '');
  const [isAuthenticated, setIsAuthenticated] = useState(!!localStorage.getItem('adminSecret'));
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  const fetchUsage = async () => {
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
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchUsage();
      const interval = setInterval(fetchUsage, 30000);
      return () => clearInterval(interval);
    }
  }, [isAuthenticated, secret]);

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
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="glass-panel p-8 max-w-md w-full rounded-3xl animate-in fade-in zoom-in duration-500">
          <div className="flex justify-center mb-6">
            <div className="bg-slate-900 p-4 rounded-2xl">
              <Lock className="w-8 h-8 text-white" />
            </div>
          </div>
          <h1 className="text-2xl font-bold text-center text-slate-900 mb-2">CodeSentinel Admin</h1>
          <p className="text-slate-500 text-center mb-8">Enter the master secret to access token observability.</p>
          
          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <input
                type="password"
                value={secret}
                onChange={(e) => setSecret(e.target.value)}
                placeholder="Admin Secret"
                className="w-full px-4 py-3 rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-900 bg-slate-50/50 transition-all"
                required
              />
            </div>
            {error && <p className="text-red-500 text-sm text-center font-medium">{error}</p>}
            <button
              type="submit"
              className="w-full py-3 px-4 bg-slate-900 hover:bg-slate-800 text-white font-semibold rounded-xl transition-colors shadow-lg shadow-slate-900/20"
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
      <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 gap-4">
        <div className="w-12 h-12 border-4 border-slate-200 border-t-slate-900 rounded-full animate-spin"></div>
        <p className="text-slate-500 font-medium animate-pulse">Fetching telemetry...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 pb-12">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-slate-900 p-2 rounded-lg">
              <Activity className="w-5 h-5 text-white" />
            </div>
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Token Observability</h1>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm text-slate-500 bg-slate-100 px-3 py-1.5 rounded-full">
              <Clock className="w-4 h-4" />
              <span>Refreshed: {lastRefreshed?.toLocaleTimeString()}</span>
            </div>
            <button onClick={handleLogout} className="text-sm font-medium text-slate-500 hover:text-slate-900 transition-colors">
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
            icon={<ShieldAlert className={`w-6 h-6 ${data.summary.emergency_engaged ? 'text-red-500' : 'text-emerald-500'}`} />}
            title="Emergency Key" 
            value={data.summary.emergency_engaged ? 'ACTIVE' : 'Standby'}
            sub={data.emergency_key.available ? "Loaded and ready" : "Not configured"}
            alert={data.summary.emergency_engaged}
          />
          <StatCard 
            icon={<Activity className="w-6 h-6 text-indigo-500" />}
            title="System Status" 
            value={data.summary.active_primary_keys > 0 || (data.emergency_key.available && !(data.emergency_key.percent_used >= 100)) ? 'Operational' : 'Exhausted'}
            sub="Pipeline availability"
          />
        </div>

        {/* Primary Keys */}
        <div className="glass-panel rounded-3xl p-6 sm:p-8">
          <h2 className="text-xl font-bold text-slate-900 mb-6 flex items-center gap-2">
            Primary Key Pool
          </h2>
          <div className="space-y-6">
            {Object.entries(data.primary_keys).map(([idx, keyData]) => (
              <KeyProgress key={idx} index={idx} data={keyData} />
            ))}
          </div>
        </div>

        {/* Emergency Key */}
        <div className={`glass-panel rounded-3xl p-6 sm:p-8 transition-colors duration-500 ${data.summary.emergency_engaged ? 'border-red-200 bg-red-50/50' : ''}`}>
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
              Emergency Reserve
            </h2>
            {data.summary.emergency_engaged && (
              <span className="px-3 py-1 bg-red-100 text-red-600 rounded-full text-xs font-bold uppercase tracking-widest animate-pulse">
                Engaged
              </span>
            )}
          </div>
          {data.emergency_key.available ? (
            <KeyProgress index="E" data={data.emergency_key} isEmergency />
          ) : (
            <p className="text-slate-500 text-sm">No emergency key configured in environment.</p>
          )}
        </div>

      </main>
    </div>
  );
}

function StatCard({ icon, title, value, sub, alert }) {
  return (
    <div className={`glass-panel p-6 rounded-3xl transition-all duration-300 hover:shadow-2xl hover:-translate-y-1 ${alert ? 'ring-2 ring-red-500/50' : ''}`}>
      <div className="flex items-center gap-4 mb-4">
        <div className={`p-3 rounded-2xl ${alert ? 'bg-red-100' : 'bg-slate-100'}`}>
          {icon}
        </div>
        <h3 className="text-sm font-medium text-slate-500">{title}</h3>
      </div>
      <div className="space-y-1">
        <p className="text-3xl font-bold text-slate-900">{value}</p>
        <p className="text-sm text-slate-500 font-medium">{sub}</p>
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
    color = 'bg-red-500';
    lightColor = 'bg-red-100';
    textColor = 'text-red-700';
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
          <span className={`w-8 h-8 flex items-center justify-center rounded-xl font-bold text-sm ${isEmergency ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-700'}`}>
            {isEmergency ? 'E' : parseInt(index) + 1}
          </span>
          <div>
            <span className="text-sm font-semibold text-slate-900">{isEmergency ? 'Emergency Key' : `Key #${parseInt(index) + 1}`}</span>
            {isExhausted && <span className="ml-2 text-xs font-bold text-red-500 uppercase tracking-wider">Exhausted</span>}
          </div>
        </div>
        <div className="text-right">
          <span className="text-sm font-bold text-slate-900">{data.tokens_used.toLocaleString()}</span>
          <span className="text-sm text-slate-500"> / {data.budget.toLocaleString()}</span>
        </div>
      </div>
      <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden">
        <div 
          className={`h-full ${color} transition-all duration-1000 ease-out`}
          style={{ width: `${Math.min(percent, 100)}%` }}
        />
      </div>
    </div>
  );
}
