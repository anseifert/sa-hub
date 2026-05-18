import { useState, useEffect, useCallback } from 'react'
import { Search, ChevronDown, ChevronRight } from 'lucide-react'
import { get } from '../api.js'

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function AccountRow({ account }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <>
      <tr className="account-row" onClick={() => setExpanded(!expanded)} style={{ cursor: 'pointer' }}>
        <td>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            <div className="company-logo">{account.company[0].toUpperCase()}</div>
            <strong>{account.company}</strong>
          </div>
        </td>
        <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
          {account.domain || '—'}
        </td>
        <td>
          <span className="chip">{account.contact_count} contacts</span>
        </td>
        <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
          {formatDate(account.last_activity)}
        </td>
      </tr>
      {expanded && account.contacts?.map(c => (
        <tr key={c.id} className="contact-sub-row">
          <td style={{ paddingLeft: 48 }}>
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>{c.name || c.email}</span>
          </td>
          <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-dim)' }}>{c.email}</td>
          <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{c.title || '—'}</td>
          <td style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
            {formatDate(c.last_contact)}
          </td>
        </tr>
      ))}
    </>
  )
}

export default function Accounts() {
  const [accounts, setAccounts] = useState([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    get(`/accounts?q=${encodeURIComponent(q)}&limit=100`)
      .then(data => { setAccounts(data.accounts); setTotal(data.total); setLoading(false) })
      .catch(() => setLoading(false))
  }, [q])

  useEffect(() => {
    const t = setTimeout(load, 300)
    return () => clearTimeout(t)
  }, [load])

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">Accounts</div>
          <div className="page-subtitle">{total} accounts · click to expand contacts</div>
        </div>
        <div style={{ position: 'relative' }}>
          <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            className="search-bar"
            style={{ paddingLeft: 30 }}
            placeholder="Search company, domain..."
            value={q}
            onChange={e => setQ(e.target.value)}
          />
        </div>
      </div>

      {loading ? (
        <div style={{ padding: '40px 0', color: 'var(--text-muted)' }}>Loading...</div>
      ) : accounts.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">🏢</div>
          <div>{q ? 'No accounts match.' : 'No accounts yet — sync Gmail to populate.'}</div>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Account</th>
              <th>Domain</th>
              <th>Contacts</th>
              <th>Last Activity</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map(a => <AccountRow key={a.id} account={a} />)}
          </tbody>
        </table>
      )}
    </div>
  )
}
