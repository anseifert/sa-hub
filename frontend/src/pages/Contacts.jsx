import { useState, useEffect, useCallback } from 'react'
import { Search, Mail, Building2, User } from 'lucide-react'
import { get } from '../api.js'

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function Contacts() {
  const [contacts, setContacts] = useState([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    get(`/contacts?q=${encodeURIComponent(q)}&limit=100`)
      .then(data => { setContacts(data.contacts); setTotal(data.total); setLoading(false) })
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
          <div className="page-title">Contacts</div>
          <div className="page-subtitle">{total.toLocaleString()} contacts from email history</div>
        </div>
        <div style={{ position: 'relative' }}>
          <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            className="search-bar"
            style={{ paddingLeft: 30 }}
            placeholder="Search name, email, company, title..."
            value={q}
            onChange={e => setQ(e.target.value)}
          />
        </div>
      </div>

      {loading ? (
        <div className="text-muted" style={{ padding: '40px 0', color: 'var(--text-muted)' }}>Loading...</div>
      ) : contacts.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">👥</div>
          <div>{q ? 'No contacts match your search.' : 'No contacts yet — sync Gmail to populate.'}</div>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Company</th>
              <th>Title</th>
              <th>Last Contact</th>
              <th>Emails</th>
            </tr>
          </thead>
          <tbody>
            {contacts.map(c => (
              <tr key={c.id}>
                <td>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div className="avatar">{(c.name || c.email)[0].toUpperCase()}</div>
                    {c.name || <span style={{ color: 'var(--text-muted)' }}>—</span>}
                  </div>
                </td>
                <td>
                  <a href={`mailto:${c.email}`} style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                    {c.email}
                  </a>
                </td>
                <td>{c.company || <span style={{ color: 'var(--text-dim)' }}>—</span>}</td>
                <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{c.title || '—'}</td>
                <td style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
                  {formatDate(c.last_contact)}
                </td>
                <td>
                  <span className="chip">{c.email_count || 0}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
