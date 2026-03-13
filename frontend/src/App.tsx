import { BrowserRouter, Routes, Route } from "react-router-dom"
import Layout from "@/components/Layout"
import KnowledgeBasePage from "@/pages/KnowledgeBasePage"
import KBFilesPage from "@/pages/KBFilesPage"
import ChatPage from "@/pages/ChatPage"
import TasksPage from "@/pages/TasksPage"
import SettingsPage from "@/pages/SettingsPage"

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<KnowledgeBasePage />} />
          <Route path="kb/:kbId" element={<KBFilesPage />} />
          <Route path="kb/:kbId/chat" element={<ChatPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
