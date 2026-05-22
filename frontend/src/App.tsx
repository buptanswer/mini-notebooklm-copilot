import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import Layout from "@/components/Layout"
import KBLayout from "@/components/KBLayout"
import KnowledgeBasePage from "@/pages/KnowledgeBasePage"
import KBFilesPage from "@/pages/KBFilesPage"
import ChatPage from "@/pages/ChatPage"
import ReviewPage from "@/pages/ReviewPage"
import CourseInfoPage from "@/pages/CourseInfoPage"
import TasksPage from "@/pages/TasksPage"
import SettingsPage from "@/pages/SettingsPage"

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<KnowledgeBasePage />} />
          <Route path="kb/:kbId" element={<KBLayout />}>
            <Route index element={<Navigate to="files" replace />} />
            <Route path="files" element={<KBFilesPage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="review" element={<ReviewPage />} />
            <Route path="review/:conversationId" element={<ReviewPage />} />
            <Route path="info" element={<CourseInfoPage />} />
          </Route>
          <Route path="tasks" element={<TasksPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
