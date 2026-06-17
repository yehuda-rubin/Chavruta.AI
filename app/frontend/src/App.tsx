import { useEffect } from 'react'
import { ChatPane } from './components/ChatPane'
import { SessionSidebar } from './components/SessionSidebar'
import { useSession } from './hooks/useSession'
import type { Intent } from './types'

export default function App() {
  const {
    sessions, activeId, messages, loading, error,
    loadSessions, loadSession, sendMessage, deleteSession, startNew,
  } = useSession()

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  return (
    <div className="flex h-full w-full">
      <SessionSidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={sid => loadSession(sid)}
        onNew={startNew}
        onDelete={sid => deleteSession(sid)}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
        <ChatPane
          messages={messages}
          loading={loading}
          error={error}
          onSend={(text: string, intent: Intent) => sendMessage(text, intent)}
        />
      </main>
    </div>
  )
}
