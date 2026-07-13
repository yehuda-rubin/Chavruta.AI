import type { Citation } from '../types'
import { CitationCard } from './CitationCard'
import { Icon } from './Icon'
import { useLang } from '../i18n'

interface Props {
  citations: Citation[]
  activeCitationRef: string | null
  onCitationCardToggle: (ref: string | null) => void
  onCloseMobile?: () => void // Callback for closing the drawer on mobile
}

/** Left-hand panel (RTL) / Right-hand panel (LTR) displaying related sources, matching screen.png. */
export function SourcesPanel({ citations, activeCitationRef, onCitationCardToggle, onCloseMobile }: Props) {
  const { t } = useLang()

  const displayCitations = citations
  const activeRef = activeCitationRef

  return (
    <aside className="flex flex-col h-full bg-transparent w-full max-w-full">
      {/* Panel Header */}
      <div className="p-4 flex items-center justify-between shrink-0 bg-transparent">
        
        {/* Left Side (RTL): Minimalist expand/fullscreen arrow icon */}
        <button className="p-1 rounded hover:bg-background/80 text-text-muted hover:text-primary transition-all cursor-pointer">
          <Icon name="open_in_full" size={20} />
        </button>

        {/* Right Side (RTL): Title */}
        <div className="flex items-center gap-2">
          <h3 className="font-serif text-lg font-bold text-primary">
            {t('relatedSources')}
          </h3>
        </div>
        
        {/* Mobile close button inside the drawer */}
        {onCloseMobile && (
          <button
            onClick={onCloseMobile}
            className="p-1 rounded text-text-muted hover:bg-background/80 hover:text-primary transition-all md:hidden"
            title={t('close')}
          >
            <Icon name="close" size={20} />
          </button>
        )}
      </div>

      {/* Sources list */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3.5 bg-transparent">
        {displayCitations.length === 0 && (
          <p className="text-text-muted/70 text-xs text-center mt-6">{t('noSources')}</p>
        )}
        {displayCitations.map((c, i) => {
          const isCardActive = activeRef === c.ref
          return (
            <CitationCard
              key={`${c.ref}-${i}`}
              citation={c}
              isActive={isCardActive}
              onToggle={() => {
                onCitationCardToggle(isCardActive ? null : c.ref)
              }}
            />
          )
        })}
      </div>

      {/* Footer: add source (mockup #5) */}
      <div className="p-4 shrink-0">
        <button className="w-full py-2.5 rounded-full grad text-white font-bold text-sm hover:opacity-95 transition shadow-glass flex items-center justify-center gap-2 cursor-pointer">
          <Icon name="add_circle" size={18} />
          {t('addSource')}
        </button>
      </div>
    </aside>
  )
}
