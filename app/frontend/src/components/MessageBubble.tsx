import type { Message, Citation } from '../types'
import { Icon } from './Icon'
import { useLang, type StringKey } from '../i18n'
import React from 'react'

interface Props {
  message: Message
  activeCitationRef: string | null
  onCitationClick: (citations: Citation[], ref: string) => void
}

const BOOK_TRANSLATION: Record<string, string> = {
  'בראשית': 'genesis',
  'שמות': 'exodus',
  'ויקרא': 'leviticus',
  'במדבר': 'numbers',
  'דברים': 'deuteronomy',
  'רשי': 'rashi',
  'רמבם': 'rambam',
  'רמבנם': 'ramban',
  'תוספות': 'tosafot',
  'בבאקמא': 'bavakamma',
  'בבאמציעא': 'bavametzia',
  'בבאבתרא': 'bavabatra',
  'ברכות': 'berakhot',
  'שבת': 'shabbat',
  'עירובין': 'eruvin',
  'פסחים': 'pesahim',
  'יומא': 'yoma',
  'סוכה': 'sukkah',
  'ביצה': 'beitzah',
  'ראש השנה': 'roshhashanah',
  'תענית': 'taanit',
  'מגילה': 'megillah',
  'מועדקטן': 'moedkatan',
  'חגיגה': 'hagigah',
  'יבמות': 'yevamot',
  'כתובות': 'ketubot',
  'נדרים': 'nedarim',
  'נזיר': 'nazir',
  'סוטה': 'sotah',
  'גיטין': 'gittin',
  'קידושין': 'kiddushin',
  'סנהדרין': 'sanhedrin',
  'מכות': 'makkot',
  'שבועות': 'shevuot',
  'עבודהזרה': 'avodahzarah',
  'הוריות': 'horayot',
}

function normalize(s: string): string {
  return s
    .toLowerCase()
    .replace(/[\u0591-\u05BD\u05BF-\u05C7]/g, '') // remove Hebrew nikud
    .replace(/[׳״"'\-–,.:;()]/g, '')              // remove punctuation
    .replace(/\s+/g, '')                          // remove spaces
}

function findBestMatch(bracketedText: string, citations: Citation[], index: number): Citation | null {
  if (!citations || citations.length === 0) return null

  // Check for patterns like "מקור 2" or "source 2" or "מקור 2 משמאל"
  const numMatch = bracketedText.match(/(?:מקור|source)\s*(\d+)/i)
  if (numMatch) {
    const idx = parseInt(numMatch[1], 10) - 1
    if (idx >= 0 && idx < citations.length) {
      return citations[idx]
    }
  }

  const cleanBracketed = normalize(bracketedText)
  let bestMatch: Citation | null = null
  let bestScore = 0

  for (const c of citations) {
    let score = 0
    const cleanRef = normalize(c.ref)
    const cleanComm = normalize(c.commentator || '')

    // Check substring overlap
    if (cleanBracketed.includes(cleanRef) || cleanRef.includes(cleanBracketed)) {
      score += 10
    }
    if (cleanComm && (cleanBracketed.includes(cleanComm) || cleanComm.includes(cleanBracketed))) {
      score += 5
    }

    // Check translation dictionary
    for (const [heb, eng] of Object.entries(BOOK_TRANSLATION)) {
      if (cleanBracketed.includes(heb)) {
        if (cleanRef.includes(eng)) {
          score += 15
        }
      }
    }

    if (score > bestScore) {
      bestScore = score
      bestMatch = c
    }
  }

  if (bestScore > 0) {
    return bestMatch
  }

  // Fallback to sequential index
  if (index < citations.length) {
    return citations[index]
  }

  return null
}

function isHebrew(text: string): boolean {
  const he = (text.match(/[א-ת]/g) || []).length
  const en = (text.match(/[a-zA-Z]/g) || []).length
  return he >= en
}

function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function sourceTags(message: Message, t: (k: StringKey) => string): string[] {
  const seen = new Set<string>()
  for (const c of message.citations ?? []) {
    const tag = (c.commentator || '').trim().toLowerCase()
    let displayTag = c.commentator
    if (tag.includes('rashi') || tag.includes('רש')) displayTag = t('tagRashi')
    else if (tag.includes('rambam') || tag.includes('רמב')) displayTag = t('tagRambam')
    else if (tag.includes('tosafot') || tag.includes('תוספ')) displayTag = t('tagTosafot')
    else if (tag.includes('gemara') || tag.includes('גמרא') || tag.includes('talmud')) displayTag = t('tagGemara')

    if (displayTag && !seen.has(displayTag)) seen.add(displayTag)
    if (seen.size >= 4) break
  }
  return [...seen]
}

/** Renders a high-fidelity chat bubble matching screen.png. */
export function MessageBubble({ message, activeCitationRef, onCitationClick }: Props) {
  const { t, lang } = useLang()
  const isUser = message.role === 'user'
  const hebrew = isHebrew(message.text)
  const dirClass = hebrew ? 'he' : 'en'
  const time = formatTime(message.created_at)

  const isRTL = lang === 'he'
  
  // Outer Flex alignment to place User on Right (start in RTL) and AI on Left (end in RTL)
  const alignmentClass = isUser
    ? (isRTL ? 'justify-start' : 'justify-end')
    : (isRTL ? 'justify-end' : 'justify-start')

  // Avatar order inside the flex container:
  // User: always Bubble first, Avatar second [showAvatarFirst = false]
  // AI: always Avatar first, Bubble second [showAvatarFirst = true]
  const showAvatarFirst = !isUser
  
  const tags = isUser ? [] : sourceTags(message, t)

  // Parse text inline to render traditional citations as styled links
  function parseMessageText(text: string, citations: Citation[]) {
    if (isUser || !citations || citations.length === 0) {
      return text
    }

    const regex = /\(([^)]+)\)/g
    const parts: React.ReactNode[] = []
    let lastIndex = 0
    let match
    let citationIndex = 0

    while ((match = regex.exec(text)) !== null) {
      const matchText = match[0]
      const innerText = match[1]
      const matchIndex = match.index

      // Push text segment before the match
      if (matchIndex > lastIndex) {
        parts.push(text.slice(lastIndex, matchIndex))
      }

      // Check if this looks like a Torah citation
      const matchedCitation = findBestMatch(innerText, citations, citationIndex)
      if (matchedCitation) {
        const ref = matchedCitation.ref
        const isActive = activeCitationRef === ref

        parts.push(
          <button
            key={matchIndex}
            onClick={() => onCitationClick(citations, ref)}
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 mx-0.5 rounded font-serif text-sm font-semibold select-none border transition-all cursor-pointer ${
              isActive
                ? 'bg-accent text-white border-accent shadow-xs'
                : 'bg-accent/10 border-accent/20 text-accent hover:bg-accent hover:text-white hover:border-accent'
            }`}
            title={ref}
          >
            <span>{innerText}</span>
          </button>
        )
        citationIndex++
      } else {
        parts.push(matchText)
      }

      lastIndex = regex.lastIndex
    }

    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex))
    }

    return parts
  }

  // Render Avatar
  const avatarEl = isUser ? (
    <div className="h-8.5 w-8.5 shrink-0 rounded-2xl grad flex items-center justify-center shadow-glass">
      <span className="text-white font-serif font-bold text-sm leading-none">{t('userInitial')}</span>
    </div>
  ) : (
    <div className="h-8.5 w-8.5 shrink-0 rounded-2xl bg-card/80 border border-white/60 flex items-center justify-center shadow-glass">
      {/* High-fidelity custom blue-and-gold synagogue icon SVG matching header */}
      <div className="h-6 w-6 shrink-0 flex items-center justify-center">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect width="20" height="20" rx="4" fill="#002045"/>
          <path d="M10 4L5 9V15H15V9L10 4Z" fill="#FFFFFF"/>
          <path d="M9 15V11H11V15H9Z" fill="#002045"/>
          <path d="M10 6L10.7 8L12.7 8.1L11.1 9.4L11.6 11.4L10 10.2L8.4 11.4L8.9 9.4L7.3 8.1L9.3 8L10 6Z" fill="#D97706"/>
        </svg>
      </div>
    </div>
  )

  // Render Bubble
  const bubbleEl = (
    <div className={`grow max-w-[85%] flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
      <div
        className={`p-4 md:p-5 shadow-glass w-full rounded-3xl ${
          isUser
            ? 'grad text-white rounded-tl-md'
            : 'bg-card/70 text-text-main border border-white/60 rounded-tr-md'
        }`}
      >
        {/* Message Text with responsive scholarly font styling */}
        <div className={`whitespace-pre-wrap ${dirClass} ${
          hebrew
            ? 'text-[17px] md:text-[18px] leading-[1.8] font-serif font-medium'
            : 'text-sm md:text-[15px] leading-relaxed font-sans'
        } ${isUser ? 'text-white' : 'text-text-main/95'}`}>
          {parseMessageText(message.text, message.citations ?? [])}
        </div>

        {/* Cited Source Tags at the bottom (mockup style) */}
        {tags.length > 0 && (
          <div className="mt-3.5 flex flex-wrap gap-1.5 justify-end">
            {tags.map(tag => (
              <span
                key={tag}
                className="bg-accent/10 text-accent px-2.5 py-0.5 rounded-full text-[11px] font-bold font-sans tracking-wide"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Caveats */}
        {message.caveats?.map((c, i) => (
          <div
            key={i}
            className="mt-3 text-xs border border-accent/20 bg-accent/[0.02] rounded px-3 py-2 flex items-center gap-1.5 text-accent font-semibold"
          >
            <Icon name="warning" size={16} className="text-accent" />
            <span>{c}</span>
          </div>
        ))}

        {/* Ungrounded notice */}
        {!isUser && message.grounded === false && !message.citations?.length && (
          <div className="mt-3 text-xs border border-border-subtle rounded px-3 py-2 text-text-muted bg-background/50 flex items-center gap-1.5">
            <Icon name="error_outline" size={16} />
            <span>{t('ungrounded')}</span>
          </div>
        )}
      </div>

      {/* Timestamp */}
      <span className="text-[10px] text-text-muted mt-1.5 block px-1 font-sans">
        {isUser ? t('you') : t('aiName')}{time && ` • ${time}`}
      </span>
    </div>
  )

  return (
    <div className={`flex gap-3 items-start w-full animate-fade-in ${alignmentClass}`}>
      {showAvatarFirst ? (
        <>
          {avatarEl}
          {bubbleEl}
        </>
      ) : (
        <>
          {bubbleEl}
          {avatarEl}
        </>
      )}
    </div>
  )
}
