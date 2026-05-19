import { useEffect, useState } from 'react'
import { CheckCircle, AlertCircle, Clock } from 'lucide-react'
import { get } from '../api.js'

function SyncStatus({ label, sync }) {
  if (!sync) return null
  const ok = sync.status === 'success'
  return (
    <div
      style={{
        marginTop: 8,
        fontSize: 11,
        fontFamily: 'var(--font-mono)',
        color: ok ? 'var(--green)' : 'var(--accent)',
        lineHeight: 1.5,
      }}
    >
      {label}: {sync.status}
      {sync.message ? ` — ${sync.message}` : ''}
    </div>
  )
}

export default function Connect({ authStatus: initialStatus }) {
  const [authStatus, setAuthStatus] = useState(initialStatus)

  useEffect(() => {
    get('/auth/status').then(setAuthStatus).catch(() => {})
  }, [])

  const google = authStatus?.google
  const slack = authStatus?.slack
  const driveSync = authStatus?.drive_sync
  const gmailSync = authStatus?.gmail_sync
  const onePagerSync = authStatus?.one_pager_sync

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <div className="page-title">Connections</div>
          <div className="page-subtitle">Manage data source integrations</div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 560 }}>

        {/* Google */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 16 }}>G</span>
                <strong>Google Workspace</strong>
                {google
                  ? <CheckCircle size={13} style={{ color: 'var(--green)' }} />
                  : <AlertCircle size={13} style={{ color: 'var(--accent)' }} />
                }
              </div>
              <div style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.6 }}>
                Gmail (contacts, follow-ups) + Google Drive (docs for one-pager).<br />
                Scopes: <code>gmail.readonly</code>, <code>drive.readonly</code>
                {authStatus?.google_redirect_uri && (
                  <>
                    <br /><br />
                    Register in Google Cloud Console → OAuth client → Authorized redirect URIs:
                    <br />
                    <code style={{ wordBreak: 'break-all' }}>{authStatus.google_redirect_uri}</code>
                  </>
                )}
              </div>
            </div>
            {!google && (
              <a href="/api/auth/google" className="btn btn-primary" style={{ whiteSpace: 'nowrap' }}>
                Connect
              </a>
            )}
            {google && (
              <span style={{ color: 'var(--green)', fontSize: 12, fontFamily: 'var(--font-mono)' }}>Connected</span>
            )}
          </div>
          {google && (
            <>
              <SyncStatus label="Gmail sync" sync={gmailSync} />
              <SyncStatus label="Drive sync" sync={driveSync} />
              <SyncStatus label="One-pager" sync={onePagerSync} />
            </>
          )}
        </div>

        {/* Slack */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 16 }}>#</span>
                <strong>Slack</strong>
                {slack
                  ? <CheckCircle size={13} style={{ color: 'var(--green)' }} />
                  : <Clock size={13} style={{ color: 'var(--amber)' }} />
                }
              </div>
              <div style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.6 }}>
                Corporate Slack requires IT approval to install a custom app.<br />
                Once approved, add <code>SLACK_BOT_TOKEN</code> to your <code>.env</code> and restart.<br />
                <br />
                Required scopes: <code>channels:history</code>, <code>channels:read</code>,{' '}
                <code>groups:history</code>, <code>im:history</code>, <code>users:read</code>
              </div>
            </div>
            <span style={{ color: 'var(--amber)', fontSize: 12, fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
              Pending IT
            </span>
          </div>
        </div>

        {/* Setup instructions */}
        <div className="card" style={{ borderColor: 'var(--border)', background: 'var(--bg)' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.8 }}>
            <div style={{ marginBottom: 8, color: 'var(--text)', fontSize: 12 }}>Setup Checklist</div>
            <div>1. Create a Google Cloud project at console.cloud.google.com</div>
            <div>2. Enable Gmail API + Google Drive API (Docs API not required)</div>
            <div>3. Create OAuth 2.0 credentials (Web application)</div>
            <div style={{ paddingLeft: 12 }}>→ Redirect URI: <code>http://localhost:3000/api/auth/google/callback</code> (not LAN IPs — see README)</div>
            <div>4. Copy credentials to <code>.env</code></div>
            <div>5. Remote via VPN: SSH tunnel to localhost (see README)</div>
            <div>6. Run <code>docker compose up</code></div>
            <div>7. Click Connect Google above</div>
          </div>
        </div>
      </div>
    </div>
  )
}
