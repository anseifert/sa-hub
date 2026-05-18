import { useState, useEffect } from 'react'
import './pages.css'
import { Pin, PinOff, Edit3, Check, X, Clock } from 'lucide-react'
import { get, patch } from '../api.js'

function Section({ section, onUpdate }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(section.content || '')

  const save = async () => {
    await patch(`/one-pager/${section.section_key}`, { content: draft })
    onUpdate(section.section_key, { content: draft })
    setEditing(false)
  }

  const togglePin = async () => {
    const pinned = !section.pinned
    await patch(`/one-pager/${section.section_key}`, { pinned })
    onUpdate(section.section_key, { pinned })
  }

  const cancel = () => {
    setDraft(section.content || '')
    setEditing(false)
  }

  return (
    <div className={`one-pager-section ${section.pinned ? 'pinned' : ''}`}>
      <div className="section-header">
        <div>
          <span className="section-title">{section.title}</span>
          {section.pinned && <span className="pin-badge">PINNED</span>}
        </div>
        <div className="section-actions">
          {section.last_ai_generated && (
            <span className="last-gen">
              <Clock size={10} />
              {new Date(section.last_ai_generated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          {editing ? (
            <>
              <button className="btn btn-ghost btn-sm" onClick={cancel}><X size={11} /> Cancel</button>
              <button className="btn btn-primary btn-sm" onClick={save}><Check size={11} /> Save</button>
            </>
          ) : (
            <>
              <button className="icon-btn" onClick={() => setEditing(true)} title="Edit"><Edit3 size={13} /></button>
              <button className="icon-btn" onClick={togglePin} title={section.pinned ? 'Unpin' : 'Pin'}>
                {section.pinned ? <PinOff size={13} /> : <Pin size={13} />}
              </button>
            </>
          )}
        </div>
      </div>
      <div className="section-body">
        {editing ? (
          <textarea
            className="section-editor"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            rows={8}
            autoFocus
          />
        ) : (
          <div className="section-content">
            {section.content
              ? section.content.split('\n').map((line, i) => <p key={i}>{line}</p>)
              : <span className="text-muted">Waiting for next sync...</span>
            }
          </div>
        )}
      </div>
    </div>
  )
}

export default function OnePager() {
  const [sections, setSections] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    get('/one-pager')
      .then(data => { setSections(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const handleUpdate = (key, changes) => {
    setSections(prev => prev.map(s => s.section_key === key ? { ...s, ...changes } : s))
  }

  if (loading) return <div className="page"><div className="text-muted">Loading...</div></div>

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">One-Pager</div>
          <div className="page-subtitle">AI-refreshed hourly · Pin sections to preserve edits</div>
        </div>
      </div>

      {sections.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">📄</div>
          <div>No content yet — connect Google and run a sync to generate your one-pager.</div>
        </div>
      ) : (
        sections.map(s => (
          <Section key={s.section_key} section={s} onUpdate={handleUpdate} />
        ))
      )}
    </div>
  )
}
