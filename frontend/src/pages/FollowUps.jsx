import { useState, useEffect } from 'react'
import { CheckCircle, Clock, Mail } from 'lucide-react'
import { get, patch } from '../api.js'

function urgencyColor(days) {
  if (days >= 21) return 'var(--accent)'
  if (days >= 14) return 'var(--amber)'
  return 'var(--text-muted)'
}

export default function FollowUps() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    setLoading(true)
    get('/follow-ups?resolved=false')
      .then(data => { setItems(data); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const resolve = async (id) => {
    await patch(`/follow-ups/${id}/resolve`)
    setItems(prev => prev.filter(i => i.id !== id))
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">Follow-Ups</div>
          <div className="page-subtitle">Emails sent with no reply in 7+ days</div>
        </div>
      </div>

      {loading ? (
        <div style={{ color: 'var(--text-muted)', padding: '40px 0' }}>Loading...</div>
      ) : items.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">✅</div>
          <div>No pending follow-ups — you're on top of everything.</div>
        </div>
      ) : (
        <div>
          {items.map(item => (
            <div key={item.id} className="follow-up-card">
              <div className="fu-left">
                <div className="fu-source">
                  <Mail size={12} />
                  <span>{item.source}</span>
                </div>
                <div className="fu-subject">{item.subject}</div>
                <div className="fu-contact">{item.contact_name || item.contact_email}</div>
              </div>
              <div className="fu-right">
                <div className="fu-days" style={{ color: urgencyColor(item.days_waiting) }}>
                  <Clock size={12} />
                  <span>{item.days_waiting}d waiting</span>
                </div>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => resolve(item.id)}
                >
                  <CheckCircle size={12} />
                  Resolve
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
