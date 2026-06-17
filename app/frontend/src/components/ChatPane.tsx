import { useEffect, useRef, useState } from 'react'
import type { Intent, Message } from '../types'
import { MessageBubble } from './MessageBubble'

const INTENTS: { value: Intent; label: string; labelHe: string }[] = [
  { value: 'qa', label: 'Q&A', labelHe: 'שאל שאלה' },
  { value: 'explain', label: 'Explain', labelHe: 'הסבר' },
  { value: 'lesson', label: 'Lesson', labelHe: 'הכן שיעור' },
]

interface Props {
  messages: Message[]
  loading: boolean
  error: string | null
  onSend: (text: string, intent: Intent) => void
}

export function ChatPane({ messages, loading, error, onSend }: Props) {
  const [input, setInput] = useState('')
  const [intent, setIntent] = useState<Intent>('qa')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    onSend(q, intent)
  }

  const isEmpty = messages.length === 0

  return (
    <div className="flex flex-col flex-1 h-full overflow-hidden">
      {/* Intent bar */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-slate-800 bg-slate-950/80 backdrop-blur-sm">
        {INTENTS.map(i => (
          <button
            key={i.value}
            onClick={() => setIntent(i.value)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors he ${
              intent === i.value
                ? 'bg-indigo-600 text-white'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            {i.labelHe}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
        {isEmpty && !loading && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4 -mt-12">
            <div className="text-5xl">🕍</div>
            <h1 className="text-2xl font-semibold text-slate-200 he">חברותא.AI</h1>
            <p className="text-slate-500 text-sm he max-w-sm leading-relaxed">
              חברותא מעוגנת במקורות — כל תשובה מצוטטת מהתנ"ך והמפרשים
            </p>
            <p className="text-slate-600 text-xs en">
              Grounded answers from Tanakh &amp; commentators
            </p>
          </div>
        )}

        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}

        {loading && (
          <div className="flex items-center gap-2 text-slate-500 text-sm he">
            <span className="animate-pulse">●</span>
            <span className="animate-pulse delay-75">●</span>
            <span className="animate-pulse delay-150">●</span>
            <span className="mr-1">מאחזר מקורות…</span>
          </div>
        )}

        {error && (
          <div className="text-red-400 text-xs border border-red-900 rounded px-3 py-2 en">
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 pb-4 pt-2 border-t border-slate-800">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="שאל שאלה בתורה… / Ask a Torah question…"
            dir="auto"
            className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500 transition-colors he"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-4 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-xl text-sm font-medium transition-colors shrink-0"
          >
            ↵
          </button>
        </form>
      </div>
    </div>
  )
}
