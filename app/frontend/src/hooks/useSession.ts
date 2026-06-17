import { useState, useCallback } from 'react'
import type { Session, Message, Intent, QueryResponse } from '../types'

const BASE = '/api'

async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${res.status}: ${body}`)
  }
  return res.json()
}

export function useSession() {
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadSessions = useCallback(async () => {
    const data = await apiFetch<Session[]>('/sessions')
    setSessions(data)
  }, [])

  const loadSession = useCallback(async (sid: string) => {
    setActiveId(sid)
    const data = await apiFetch<Message[]>(`/sessions/${sid}/messages`)
    setMessages(data)
  }, [])

  const newSession = useCallback(async (question: string, intent: Intent) => {
    setLoading(true)
    setError(null)
    try {
      const optimistic: Message = {
        role: 'user', text: question, citations: [], caveats: [],
      }
      setMessages([optimistic])
      setActiveId(null)

      // POST /sessions creates session + runs first query atomically
      const raw = await apiFetch<{ id: string; first_q: string; created_at: string; result: QueryResponse }>(
        '/sessions',
        {
          method: 'POST',
          body: JSON.stringify({ question, intent }),
        },
      )

      const newSid = raw.id
      setActiveId(newSid)
      setSessions(prev => [{ id: newSid, first_q: raw.first_q, created_at: raw.created_at }, ...prev])

      const assistantMsg: Message = {
        role: 'assistant',
        text: raw.result.answer,
        citations: raw.result.citations,
        caveats: raw.result.caveats,
        grounded: raw.result.grounded,
        intent: raw.result.intent,
      }
      setMessages([optimistic, assistantMsg])
      return newSid
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const sendMessage = useCallback(async (question: string, intent: Intent) => {
    if (!activeId) return newSession(question, intent)
    setLoading(true)
    setError(null)

    const optimistic: Message = { role: 'user', text: question, citations: [], caveats: [] }
    setMessages(prev => [...prev, optimistic])

    try {
      const res = await apiFetch<QueryResponse>(`/sessions/${activeId}/query`, {
        method: 'POST',
        body: JSON.stringify({ question, intent }),
      })
      const assistantMsg: Message = {
        role: 'assistant',
        text: res.answer,
        citations: res.citations,
        caveats: res.caveats,
        grounded: res.grounded,
        intent: res.intent,
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (e) {
      setError(String(e))
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setLoading(false)
    }
  }, [activeId, newSession])

  const deleteSession = useCallback(async (sid: string) => {
    await apiFetch(`/sessions/${sid}`, { method: 'DELETE' })
    setSessions(prev => prev.filter(s => s.id !== sid))
    if (activeId === sid) {
      setActiveId(null)
      setMessages([])
    }
  }, [activeId])

  const startNew = useCallback(() => {
    setActiveId(null)
    setMessages([])
    setError(null)
  }, [])

  return {
    sessions, activeId, messages, loading, error,
    loadSessions, loadSession, sendMessage, deleteSession, startNew,
  }
}
