import type { Session } from '../types'
import { Icon } from './Icon'
import { useLang, type StringKey } from '../i18n'

interface Props {
  sessions: Session[]
  activeId: string | null
  onSelect: (sid: string) => void
  onNew: () => void
  onDelete: (sid: string) => void
  onCloseMobile?: () => void
}

function groupSessions(sessions: Session[], t: (k: StringKey) => string) {
  const today: Session[] = []
  const yesterday: Session[] = []
  const older: Session[] = []

  const now = new Date()
  const todayStr = now.toDateString()
  const y = new Date(now)
  y.setDate(now.getDate() - 1)
  const yStr = y.toDateString()

  sessions.forEach(s => {
    const d = new Date(s.created_at)
    if (isNaN(d.getTime())) { older.push(s); return }
    const ds = d.toDateString()
    if (ds === todayStr) today.push(s)
    else if (ds === yStr) yesterday.push(s)
    else older.push(s)
  })

  return [
    { label: t('recent'), items: today },
    { label: t('yesterday'), items: yesterday },
    { label: t('older'), items: older },
  ].filter(g => g.items.length > 0)
}

/** Right sidebar — faithful port of mockup #5. */
export function SessionSidebar({ sessions, activeId, onSelect, onNew, onDelete, onCloseMobile }: Props) {
  const { t } = useLang()
  const grouped = groupSessions(sessions, t)

  return (
    <aside className="flex flex-col h-full bg-transparent w-full max-w-full p-4">
      {/* Mobile close */}
      {onCloseMobile && (
        <div className="flex justify-end mb-2 md:hidden">
          <button
            onClick={onCloseMobile}
            className="p-1 rounded-xl text-text-muted hover:text-primary"
            title={t('close')}
          >
            <Icon name="close" size={20} />
          </button>
        </div>
      )}

      {/* New discussion */}
      <button
        onClick={() => { onNew(); onCloseMobile?.() }}
        className="w-full grad text-white py-3 rounded-2xl font-serif text-lg font-bold hover:opacity-95 active:scale-[0.98] transition shadow-glass flex items-center justify-center gap-2 cursor-pointer"
      >
        <Icon name="add" size={20} />
        <span>{t('newDiscussion')}</span>
      </button>

      {/* Sessions */}
      <div className="mt-6 flex-1 overflow-y-auto flex flex-col gap-4">
        {grouped.length === 0 && (
          <p className="text-text-muted/70 text-xs text-center mt-6">{t('noSessions')}</p>
        )}
        {grouped.map(group => (
          <div key={group.label} className="flex flex-col gap-1.5">
            <p className="text-[11px] tracking-widest text-text-muted/70 font-bold uppercase px-2 mb-1">
              {group.label}
            </p>
            {group.items.map(s => {
              const active = activeId === s.id
              return (
                <div
                  key={s.id}
                  onClick={() => { onSelect(s.id); onCloseMobile?.() }}
                  className={`group px-4 py-3 rounded-2xl cursor-pointer transition-all flex items-center gap-2 ${
                    active
                      ? 'bg-white/70 text-primary font-bold shadow-glass ring-1 ring-primary/10'
                      : 'text-text-main hover:bg-white/40'
                  }`}
                >
                  <span className="flex-1 text-sm truncate font-medium">{s.first_q}</span>
                  <button
                    onClick={e => { e.stopPropagation(); onDelete(s.id) }}
                    className="opacity-0 group-hover:opacity-100 text-text-muted hover:text-red-500 transition shrink-0 cursor-pointer"
                    title={t('delete')}
                  >
                    <Icon name="close" size={14} />
                  </button>
                </div>
              )
            })}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="mt-auto pt-3 flex flex-col gap-1 text-text-muted text-sm">
        <button className="flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-white/40 transition w-full text-start cursor-pointer">
          <Icon name="settings" size={20} />
          <span>{t('settings')}</span>
        </button>
        <button className="flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-white/40 transition w-full text-start cursor-pointer">
          <Icon name="help_outline" size={20} />
          <span>{t('support')}</span>
        </button>
      </div>
    </aside>
  )
}
