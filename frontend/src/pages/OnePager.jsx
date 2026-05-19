import { useState, useEffect, useCallback } from 'react'
import './pages.css'
import { Pin, PinOff, Edit3, Check, X, Clock, RefreshCw } from 'lucide-react'
import { get, patch, post } from '../api.js'
import { SYNC_COMPLETE_EVENT } from '../syncEvents.js'

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
              : <span className="text-muted">Run Sync Now to populate this section…</span>
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
  const [generating, setGenerating] = useState(false)
  const [syncStatus, setSyncStatus] = useState(null)

  const loadSections = useCallback(() => {
    return get('/one-pager')
      .then(data => { setSections(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const loadSyncStatus = useCallback(() => {
    get('/auth/status')
      .then(s => setSyncStatus(s?.one_pager_sync))
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadSections()
    loadSyncStatus()
    const onSync = () => {
      loadSections()
      loadSyncStatus()
    }
    window.addEventListener(SYNC_COMPLETE_EVENT, onSync)
    return () => window.removeEventListener(SYNC_COMPLETE_EVENT, onSync)
  }, [loadSections, loadSyncStatus])

  const handleRegenerate = async () => {
    setGenerating(true)
    try {
      const res = await post('/one-pager/generate')
      if (!res?.ok) {
        setGenerating(false)
        return
      }
      const poll = async (n = 0) => {
        if (n > 90) {
          setGenerating(false)
          loadSections()
          loadSyncStatus()
          return
        }
        const { running } = await get('/sync/status').catch(() => ({ running: false }))
        if (!running) {
          setGenerating(false)
          loadSections()
          loadSyncStatus()
          return
        }
        setTimeout(() => poll(n + 1), 2000)
      }
      poll()
    } catch {
      setGenerating(false)
    }
  }

  const hasContent = sections.some(s => s.content?.trim())

  if (loading) return <div className="page"><div className="text-muted">Loading...</div></div>

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">One-Pager</div>
          <div className="page-subtitle">
            Refreshed on sync · Pin sections to preserve edits
          </div>
          {syncStatus?.status === 'error' && (
            <div style={{ marginTop: 8, fontSize: 12, color: 'var(--accent)' }}>
              Last generation failed: {syncStatus.message}
            </div>
          )}
        </div>
        <button
          className="btn btn-primary btn-sm"
          onClick={handleRegenerate}
          disabled={generating}
          type="button"
        >
          <RefreshCw size={13} className={generating ? 'spin' : ''} />
          {generating ? 'Generating…' : 'Regenerate'}
        </button>
      </div>

      {sections.length === 0 ? (
        <div className="empty">
          <div className="empty-icon">📄</div>
          <div>Connect Google and run Sync Now to build your one-pager.</div>
        </div>
      ) : (
        <>
          {!hasContent && (
            <div className="card" style={{ marginBottom: 12, fontSize: 13, color: 'var(--text-muted)' }}>
              Sections appear after sync finishes the one-pager step (last in the pipeline).
              Use <strong>Regenerate</strong> or <strong>Sync Now</strong> in the sidebar.
            </div>
          )}
          {sections.map(s => (
            <Section key={s.section_key} section={s} onUpdate={(key, changes) => {
              setSections(prev => prev.map(x => x.section_key === key ? { ...x, ...changes } : x))
            }} />
          ))}
        </>
      )}
    </div>
  )
}
