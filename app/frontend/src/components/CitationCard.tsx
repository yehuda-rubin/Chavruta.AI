import { useEffect, useRef, useState } from 'react'
import type { Citation } from '../types'
import { Icon } from './Icon'
import { useLang } from '../i18n'

interface Props {
  citation: Citation
  isActive: boolean
  onToggle?: () => void
}

function getCategory(commentator: string, ref: string): 'GEMARA' | 'RASHI' | 'RAMBAM' | 'TOSAFOT' {
  const comm = (commentator || '').toLowerCase()
  const r = (ref || '').toLowerCase()
  
  if (comm.includes('rashi') || comm.includes('רש״י') || comm.includes('רש"י') || comm.includes('רשי')) {
    return 'RASHI'
  }
  if (comm.includes('rambam') || comm.includes('רמב״ם') || comm.includes('רמב"ם') || comm.includes('רמבם') || comm.includes('maimonides') || r.includes('rambam') || r.includes('mishneh torah')) {
    return 'RAMBAM'
  }
  if (comm.includes('tosafot') || comm.includes('תוספות') || comm.includes('תוספ')) {
    return 'TOSAFOT'
  }
  return 'GEMARA'
}

function getCategoryIcon(category: 'GEMARA' | 'RASHI' | 'RAMBAM' | 'TOSAFOT', isActive: boolean): string {
  if (isActive) return 'star_rate'
  if (category === 'GEMARA') return 'description'
  if (category === 'RASHI') return 'star_border'
  if (category === 'RAMBAM') return 'menu_book'
  return 'menu_book' // TOSAFOT
}

function isHebrewText(text: string): boolean {
  const he = (text.match(/[א-ת]/g) || []).length
  const en = (text.match(/[a-zA-Z]/g) || []).length
  return he >= en
}

/** Collapsible accordion source card matching screen.png. */
export function CitationCard({ citation, isActive, onToggle }: Props) {
  const { t, lang } = useLang()
  const [isExpanded, setIsExpanded] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  
  const category = getCategory(citation.commentator, citation.ref)
  const icon = getCategoryIcon(category, isActive)
  const text = lang === 'en' ? citation.text_en : citation.text_he
  const fallbackText = citation.text_he || citation.text_en
  const content = text || fallbackText
  const isHe = isHebrewText(content)

  const href = citation.deep_link || `https://www.sefaria.org/${encodeURIComponent(citation.ref)}`

  // Handle cross-column focus & expansion
  useEffect(() => {
    if (isActive) {
      setIsExpanded(true)
      const timer = setTimeout(() => {
        containerRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
        })
      }, 150)
      return () => clearTimeout(timer)
    }
  }, [isActive])

  function handleCardClick() {
    setIsExpanded(prev => !prev)
    if (onToggle) {
      onToggle()
    }
  }

  return (
    <div
      ref={containerRef}
      className={`rounded-2xl border bg-card/70 select-none overflow-hidden cursor-pointer shadow-glass transition-all duration-300 ${
        isActive
          ? 'border-accent ring-2 ring-accent/40'
          : 'border-white/60 hover:border-accent/40'
      }`}
      onClick={handleCardClick}
    >
      {/* Header section (Always visible) */}
      <div className="p-3.5 flex flex-col gap-2">
        <div className="flex justify-between items-center w-full">
          {/* label-sm metadata on the right (RTL) or left (LTR) */}
          <span className="text-[10px] font-bold text-accent tracking-wider uppercase font-sans">
            {category}
          </span>

          {/* Category Icon (Star or Doc or Book) on the left (RTL) or right (LTR) */}
          <Icon
            name={icon}
            size={16}
            className={isActive ? 'text-accent' : 'text-text-muted'}
            filled={isActive && category === 'RASHI'}
          />
        </div>

        <h4 className="font-serif text-base font-bold text-primary leading-tight">
          {citation.ref}
        </h4>

        {/* Collapsed single line snippet */}
        {!isExpanded && content && (
          <p className="text-xs text-text-muted truncate leading-relaxed">
            {content}
          </p>
        )}
      </div>

      {/* Expanded body section */}
      {isExpanded && (
        <div className="px-3.5 pb-3.5 pt-1 border-t border-border-subtle/30 bg-background/30 animate-fade-in">
          <p className={`p-3 rounded-xs border border-border-subtle/20 bg-background/80 whitespace-pre-wrap mb-3 ${
            isHe
              ? 'font-serif text-base md:text-[17px] leading-relaxed text-text-main/90 font-medium'
              : 'font-sans text-xs md:text-sm leading-relaxed text-text-main'
          }`}>
            {content}
          </p>
          
          <div className="flex justify-between items-center text-xs mt-2">
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className="flex items-center gap-1.5 text-accent hover:text-accent-hover font-semibold transition-colors bg-accent/5 px-2.5 py-1.5 rounded border border-accent/10 hover:border-accent/30"
            >
              <Icon name="open_in_new" size={12} />
              <span>{t('openLibrary')}</span>
            </a>

            {citation.commentator && (
              <span className="text-text-muted text-[10px] italic">
                {`${t('commentator')}: ${citation.commentator}`}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
