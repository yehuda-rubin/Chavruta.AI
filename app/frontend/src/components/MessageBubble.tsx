import { useState } from 'react'
import type { Message } from '../types'
import { CitationCard } from './CitationCard'

function isHebrew(text: string): boolean {
  const he = (text.match(/[א-ת]/g) || []).length
  const en = (text.match(/[a-zA-Z]/g) || []).length
  return he >= en
}

interface Props {
  message: Message
}

export function MessageBubble({ message }: Props) {
  const [showCitations, setShowCitations] = useState(false)
  const isUser = message.role === 'user'
  const hebrew = isHebrew(message.text)

  // User: Hebrew → right, English → left
  // Assistant: always full-width with direction based on language
  const userAlign = isUser
    ? (hebrew ? 'items-end' : 'items-start')
    : ''

  const bubbleBase = isUser
    ? 'max-w-[75%] px-4 py-2.5 rounded-2xl text-sm'
    : 'w-full px-1 py-1 text-sm'

  const bubbleBg = isUser
    ? 'bg-indigo-600 text-white'
    : 'text-slate-200'

  const textDir = hebrew ? 'he' : 'en'

  return (
    <div className={`flex flex-col gap-1 ${isUser ? userAlign : ''}`}>
      {isUser ? (
        <div className={`${bubbleBase} ${bubbleBg}`}>
          <span className={textDir}>{message.text}</span>
        </div>
      ) : (
        <div className={`${bubbleBase} ${bubbleBg} space-y-3`}>
          {/* Answer text */}
          <div className={`leading-relaxed ${hebrew ? 'he text-base' : 'en'}`}>
            {message.text}
          </div>

          {/* Caveats */}
          {message.caveats?.map((c, i) => (
            <div key={i} className="text-amber-400 text-xs border border-amber-800 rounded px-2 py-1 en">
              ⚠️ {c}
            </div>
          ))}

          {/* No source state */}
          {message.grounded === false && !message.citations?.length && (
            <div className="text-slate-500 text-xs border border-slate-700 rounded px-2 py-1 he">
              לא נמצא מקור מעוגן — לא הומצאה תשובה
            </div>
          )}

          {/* Citations toggle */}
          {message.citations?.length > 0 && (
            <div className="space-y-2">
              <button
                onClick={() => setShowCitations(v => !v)}
                className="flex items-center gap-1.5 text-xs text-amber-400 hover:text-amber-300 transition-colors"
              >
                <span>📖</span>
                <span className="he">{showCitations ? 'הסתר מקורות' : `הצג מקורות (${message.citations.length})`}</span>
              </button>

              {showCitations && (
                <div className="space-y-2 mt-1">
                  {message.citations.map((c, i) => (
                    <CitationCard key={i} citation={c} index={i} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
