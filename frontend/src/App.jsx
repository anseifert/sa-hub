import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import { FileText, Users, Building2, Bell, RefreshCw, Settings, LogOut } from 'lucide-react'
import OnePager from './pages/OnePager.jsx'
import Contacts from './pages/Contacts.jsx'
import Accounts from './pages/Accounts.jsx'
import FollowUps from './pages/FollowUps.jsx'
import Connect from './pages/Connect.jsx'
import Login from './pages/Login.jsx'
import { get, post, ApiError } from './api.js'
import { notifySyncComplete } from './syncEvents.js'
import './App.css'

function Sidebar({ authStatus, session, onSync, syncing, followUpCount, onLogout }) {
  const nav = [
    { to: '/', icon: FileText, label: 'One-Pager' },
    { to: '/follow-ups', icon: Bell, label: 'Follow-Ups', badge: followUpCount },
    { to: '/contacts', icon: Users, label: 'Contacts' },
    { to: '/accounts', icon: Building2, label: 'Accounts' },
  ]

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="logo">
          <span className="logo-rh">RH</span>
          <span className="logo-text">SA Hub</span>
        </div>
        <div className="connection-status">
          {authStatus?.google ? (
            <span className="status-dot green" title="Google Connected" />
          ) : (
            <span className="status-dot red" title="Google Disconnected" />
          )}
          {authStatus?.slack ? (
            <span className="status-dot green" title="Slack Connected" />
          ) : (
            <span className="status-dot amber" title="Slack Pending" />
          )}
        </div>
      </div>

      <nav className="sidebar-nav">
        {nav.map(({ to, icon: Icon, label, badge }) => (
          <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <Icon size={15} />
            <span>{label}</span>
            {badge > 0 && <span className="badge">{badge}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <NavLink to="/connect" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
          <Settings size={15} />
          <span>Connections</span>
        </NavLink>
        <button
          className={`sync-btn ${syncing ? 'syncing' : ''}`}
          onClick={onSync}
          disabled={syncing}
        >
          <RefreshCw size={13} className={syncing ? 'spin' : ''} />
          {syncing ? 'Syncing...' : 'Sync Now'}
        </button>
        {session?.auth_required && (
          <button type="button" className="sync-btn logout-btn" onClick={onLogout}>
            <LogOut size={13} />
            Sign out
          </button>
        )}
      </div>
    </aside>
  )
}

function AppLayout() {
  const navigate = useNavigate()
  const [authStatus, setAuthStatus] = useState(null)
  const [session, setSession] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [followUpCount, setFollowUpCount] = useState(0)

  useEffect(() => {
    get('/auth/session')
      .then((s) => {
        setSession(s)
        if (s.auth_required && !s.authenticated) {
          navigate('/login', { replace: true })
        }
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) {
          navigate('/login', { replace: true })
        } else {
          setSession({ auth_required: false, authenticated: true })
        }
      })
  }, [navigate])

  useEffect(() => {
    if (!session?.authenticated && session?.auth_required) return
    get('/auth/status').then(setAuthStatus).catch((e) => {
      if (e instanceof ApiError && e.status === 401) navigate('/login', { replace: true })
    })
    get('/follow-ups').then((data) => setFollowUpCount(data.length)).catch(() => {})
  }, [session, navigate])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const res = await post('/sync')
      if (!res?.ok) {
        setSyncing(false)
        return
      }
      const poll = async (attempts = 0) => {
        if (attempts > 120) {
          setSyncing(false)
          return
        }
        try {
          const { running } = await get('/sync/status')
          if (!running) {
            setSyncing(false)
            get('/auth/status').then(setAuthStatus).catch(() => {})
            get('/follow-ups').then((data) => setFollowUpCount(data.length)).catch(() => {})
            notifySyncComplete()
            return
          }
        } catch {
          /* backend busy — keep polling */
        }
        setTimeout(() => poll(attempts + 1), 2000)
      }
      poll()
    } catch {
      setSyncing(false)
    }
  }

  const handleLogout = async () => {
    try {
      await post('/auth/logout')
    } catch {
      /* ignore */
    }
    navigate('/login', { replace: true })
  }

  if (!session) {
    return <div className="login-page"><p className="login-subtitle">Loading…</p></div>
  }

  if (session.auth_required && !session.authenticated) {
    return null
  }

  return (
    <div className="app-layout">
      <Sidebar
        authStatus={authStatus}
        session={session}
        onSync={handleSync}
        syncing={syncing}
        followUpCount={followUpCount}
        onLogout={handleLogout}
      />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<OnePager />} />
          <Route path="/follow-ups" element={<FollowUps />} />
          <Route path="/contacts" element={<Contacts />} />
          <Route path="/accounts" element={<Accounts />} />
          <Route path="/connect" element={<Connect authStatus={authStatus} />} />
        </Routes>
      </main>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/*" element={<AppLayout />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
