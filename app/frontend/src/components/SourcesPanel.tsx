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

const MOCK_CITATIONS: Citation[] = [
  {
    ref: 'בבא מציעא ב\' ע"א',
    text_he: '"שניים אוחזין בטלית, זה אומר אני מצאתיה וזה אומר אני מצאתיה..."',
    text_en: '"Two hold a garment, this one says I found it and that one says I found it..."',
    commentator: "Gemara",
    deep_link: "https://www.sefaria.org/Bava_Metzia.2a"
  },
  {
    ref: 'רש"י על ב\' ע"א',
    text_he: '"תקנת חכמים היא שיהו נשבעין, כדי שלא יהיה כל אחד ואחד תוקף..."',
    text_en: '"It is a rabbinic decree that they should swear, so that everyone does not grab..."',
    commentator: "Rashi",
    deep_link: "https://www.sefaria.org/Rashi_on_Bava_Metzia.2a"
  },
  {
    ref: 'רמב"ם, הלכות גזילה',
    text_he: 'פרק ט׳ הלכה א׳: דיני חלוקת אבידה בשניים אוחזין...',
    text_en: 'Chapter 9 Halacha 1: Laws of dividing a lost item held by two...',
    commentator: "Rambam",
    deep_link: "https://www.sefaria.org/Mishneh_Torah%2C_Robbery_and_Lost_Property.9"
  },
  {
    ref: 'תוספות ד"ה "ויחלוקו"',
    text_he: 'הקשה ר״י, למה לא אמרינן יהא מונח עד שיבוא אליהו?',
    text_en: 'Rabbi Isaac asked, why do we not say it should be left until Elijah comes?',
    commentator: "Tosafot",
    deep_link: "https://www.sefaria.org/Tosafot_on_Bava_Metzia.2a"
  }
]

/** Left-hand panel (RTL) / Right-hand panel (LTR) displaying related sources, matching screen.png. */
export function SourcesPanel({ citations, activeCitationRef, onCitationCardToggle, onCloseMobile }: Props) {
  const { t, lang } = useLang()
  
  // Use mock citations from screen.png by default if no actual search result citations are present
  const displayCitations = citations.length > 0 ? citations : MOCK_CITATIONS
  
  // If showing mock data, make Rashi the active expanded card by default to match screen.png
  const activeRef = activeCitationRef || (citations.length === 0 ? 'רש"י על ב\' ע"א' : null)

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
            title={lang === 'he' ? 'סגור' : 'Close'}
          >
            <Icon name="close" size={20} />
          </button>
        )}
      </div>

      {/* Sources list */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3.5 bg-transparent">
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
