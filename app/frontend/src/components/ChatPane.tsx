import { useEffect, useRef, useState } from 'react'
import type { Intent, Message, Citation } from '../types'
import { MessageBubble } from './MessageBubble'
import { Icon } from './Icon'
import { useLang, type Lang, type StringKey } from '../i18n'

// Header order matches the mockup: lesson · explain · qa
const INTENTS: { value: Intent; key: StringKey }[] = [
  { value: 'lesson', key: 'intent_lesson' },
  { value: 'explain', key: 'intent_explain' },
  { value: 'qa', key: 'intent_qa' },
]

interface Props {
  messages: Message[]
  loading: boolean
  error: string | null
  subtitle?: string
  onSend: (text: string, intent: Intent, lang: Lang) => void
  activeCitationRef: string | null
  onCitationClick: (citations: Citation[], ref: string) => void
}

export function ChatPane({
  messages, loading, error, subtitle, onSend, activeCitationRef, onCitationClick,
}: Props) {
  const { t, lang } = useLang()
  const [input, setInput] = useState('')
  const [intent, setIntent] = useState<Intent>('qa')
  const [goalOpen, setGoalOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    onSend(q, intent, lang)
  }

  const isEmpty = messages.length === 0
  const activeIntentKey = INTENTS.find(i => i.value === intent)!.key

  return (
    <section className="grow flex flex-col bg-transparent relative overflow-hidden h-full">
      {/* Header: title + segmented intent control */}
      <header className="h-16 px-5 md:px-7 flex items-center justify-between border-b border-white/60 shrink-0">
        <div className="flex flex-col min-w-0">
          <h2 className="font-serif text-lg font-bold text-primary truncate leading-tight">
            {t('discussionTitle')}
          </h2>
          {subtitle && (
            <p className="text-[10px] text-accent uppercase font-bold tracking-wider truncate mt-0.5">
              {subtitle}
            </p>
          )}
        </div>

        <div className="flex bg-white/50 rounded-full p-1 text-xs font-semibold shrink-0">
          {INTENTS.map(i => (
            <button
              key={i.value}
              onClick={() => setIntent(i.value)}
              className={`px-3 py-1.5 rounded-full transition-all cursor-pointer ${
                intent === i.value ? 'grad text-white shadow-glass' : 'text-text-muted hover:text-text-main'
              }`}
            >
              {t(i.key)}
            </button>
          ))}
        </div>
      </header>

      {/* Messages */}
      <div className="grow overflow-y-auto px-4 md:px-8 py-8 flex flex-col gap-6 w-full max-w-2xl mx-auto">
        {isEmpty && !loading && (
          <div className="flex flex-col items-center justify-center my-auto text-center gap-4 py-10 animate-fade-in">
            <div className="h-14 w-14 rounded-2xl grad flex items-center justify-center shadow-glass">
              <span className="text-2xl" role="img" aria-label="synagogue">🕍</span>
            </div>
            <h1 className="font-serif text-xl font-bold text-primary">{t('appName')}</h1>
            <p className="text-text-muted text-sm max-w-md leading-relaxed font-serif p-4 glass rounded-2xl">
              {t('emptyGreeting')}
            </p>
          </div>
        )}

        {messages.map((m, i) => (
          <MessageBubble
            key={m.id ?? i}
            message={m}
            activeCitationRef={activeCitationRef}
            onCitationClick={onCitationClick}
          />
        ))}

        {loading && (
          <div className="flex items-center gap-2.5 text-accent text-sm font-semibold w-fit">
            <div className="flex gap-1">
              <span className="h-1.5 w-1.5 bg-accent rounded-full animate-bounce [animation-delay:0s]"></span>
              <span className="h-1.5 w-1.5 bg-accent rounded-full animate-bounce [animation-delay:0.15s]"></span>
              <span className="h-1.5 w-1.5 bg-accent rounded-full animate-bounce [animation-delay:0.3s]"></span>
            </div>
            <span>{t('retrieving')}</span>
          </div>
        )}

        {error && (
          <div className="text-red-700 text-sm border border-red-200 bg-red-50/60 rounded-2xl px-4 py-3 flex items-center gap-2">
            <Icon name="error" className="text-red-500 shrink-0" size={16} />
            <span className="font-semibold">{error}</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <footer className="p-5 bg-transparent shrink-0">
        <form
          onSubmit={handleSubmit}
          className="max-w-2xl mx-auto flex items-center gap-2 glass rounded-full px-3 py-2 focus-within:ring-2 focus-within:ring-accent/30 transition-all"
        >
          {/* Goal dropdown */}
          <div className="relative shrink-0">
            <button
              type="button"
              onClick={() => setGoalOpen(v => !v)}
              className="flex items-center gap-1 text-accent font-bold text-sm px-3 py-1.5 rounded-full hover:bg-white/60 transition cursor-pointer"
            >
              <Icon name="gps_fixed" size={16} />
              <span className="hidden md:block">{t(activeIntentKey)}</span>
              <Icon name="expand_more" size={14} />
            </button>
            {goalOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setGoalOpen(false)} />
                <div className="absolute bottom-full mb-2 w-44 glass rounded-2xl shadow-glass z-50 start-0 overflow-hidden p-1 flex flex-col gap-0.5">
                  {INTENTS.map(i => (
                    <button
                      key={i.value}
                      type="button"
                      onClick={() => { setIntent(i.value); setGoalOpen(false) }}
                      className={`text-start px-3 py-2 text-sm rounded-xl transition-colors font-semibold cursor-pointer ${
                        intent === i.value ? 'bg-accent/10 text-accent' : 'text-text-main hover:bg-white/50'
                      }`}
                    >
                      {t(i.key)}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          <button
            type="button"
            className="p-2 rounded-full text-text-muted hover:text-accent hover:bg-white/50 transition cursor-pointer shrink-0"
            title={t('attach')}
          >
            <Icon name="attach_file" size={18} />
          </button>

          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder={t('inputPlaceholder')}
            dir="auto"
            disabled={loading}
            className="grow bg-transparent border-none focus:ring-0 focus:outline-none text-base py-1.5 px-1 text-text-main placeholder:text-text-muted/50 font-serif"
          />

          <button
            type="submit"
            disabled={loading || !input.trim()}
            title={t('send')}
            className="grad text-white h-10 w-10 rounded-full flex items-center justify-center hover:opacity-95 active:scale-[0.96] disabled:opacity-30 transition-all shrink-0 cursor-pointer shadow-glass"
          >
            <Icon name="send" size={16} className="rtl:rotate-180 text-white" />
          </button>
        </form>
        <p className="text-center text-[10px] text-text-muted mt-2.5">{t('disclaimer')}</p>
      </footer>
    </section>
  )
}
