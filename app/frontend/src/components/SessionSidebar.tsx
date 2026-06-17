import type { Session } from '../types'

interface Props {
  sessions: Session[]
  activeId: string | null
  onSelect: (sid: string) => void
  onNew: () => void
  onDelete: (sid: string) => void
}

function relativeTime(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'עכשיו'
  if (mins < 60) return `לפני ${mins} דק׳`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `לפני ${hours} ש׳`
  const days = Math.floor(hours / 24)
  return `לפני ${days} ימים`
}

export function SessionSidebar({ sessions, activeId, onSelect, onNew, onDelete }: Props) {
  return (
    <aside className="w-64 shrink-0 flex flex-col border-r border-slate-800 bg-slate-950 h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-4 border-b border-slate-800">
        <span className="text-lg font-semibold text-slate-100 he">חברותא.AI</span>
        <button
          onClick={onNew}
          title="שיחה חדשה"
          className="text-slate-400 hover:text-white hover:bg-slate-800 rounded-md p-1.5 transition-colors text-lg leading-none"
        >
          ✏
        </button>
      </div>

      {/* Session list */}
      <nav className="flex-1 overflow-y-auto py-2">
        {sessions.length === 0 && (
          <p className="text-slate-600 text-xs text-center mt-8 he px-4">
            אין שיחות עדיין
          </p>
        )}

        {sessions.map(s => (
          <div
            key={s.id}
            className={`group flex items-center gap-2 px-3 py-2.5 mx-2 rounded-lg cursor-pointer transition-colors ${
              activeId === s.id
                ? 'bg-indigo-900/50 text-slate-100'
                : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
            }`}
            onClick={() => onSelect(s.id)}
          >
            <span className="flex-1 truncate text-sm he text-right leading-snug">
              {s.first_q}
            </span>

            <div className="flex items-center gap-1 shrink-0">
              <span className="text-xs text-slate-600 group-hover:hidden">
                {relativeTime(s.created_at)}
              </span>
              <button
                onClick={e => { e.stopPropagation(); onDelete(s.id) }}
                className="hidden group-hover:block text-slate-600 hover:text-red-400 transition-colors text-xs p-0.5"
                title="מחק שיחה"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-slate-800 text-xs text-slate-600 he text-right">
        כל תשובה מצוטטת ממקורות
      </div>
    </aside>
  )
}
