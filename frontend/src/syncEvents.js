/** Fired when a background sync finishes so pages can refetch data. */
export const SYNC_COMPLETE_EVENT = 'sa-hub-sync-complete'

export function notifySyncComplete() {
  window.dispatchEvent(new Event(SYNC_COMPLETE_EVENT))
}
