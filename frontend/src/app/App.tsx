import { useEffect } from 'react'
import { Route, Routes } from 'react-router-dom'
import { useConversationStore } from '../stores/conversationStore'
import { ChatRoomPage } from '../pages/ChatRoomPage'
import { DebatePage } from '../pages/DebatePage'

export default function App() {
  const load = useConversationStore((state) => state.load)
  useEffect(() => { void load() }, [load])
  return <Routes>
    <Route path="/debate" element={<DebatePage />} />
    <Route path="*" element={<ChatRoomPage />} />
  </Routes>
}
