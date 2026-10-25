import { Navigate, Route, Routes } from 'react-router-dom'
import { getToken } from './api/client'
import Layout from './components/Layout'
import AdminReviewPage from './pages/AdminReviewPage'
import AuthPage from './pages/AuthPage'
import AiLabPage from './pages/AiLabPage'
import DashboardPage from './pages/DashboardPage'
import LearningLibraryPage from './pages/LearningLibraryPage'
import QuizPage from './pages/QuizPage'
import RoadmapPage from './pages/RoadmapPage'
import SettingsPage from './pages/SettingsPage'

function Protected() { return getToken() ? <Layout /> : <Navigate to="/login" replace /> }

export default function App() {
  return <Routes><Route path="/login" element={<AuthPage />} /><Route path="/signup" element={<AuthPage />} /><Route element={<Protected />}><Route path="/dashboard" element={<DashboardPage />} /><Route path="/library" element={<LearningLibraryPage />} /><Route path="/learn/:slug" element={<LearningLibraryPage />} /><Route path="/ai-lab" element={<AiLabPage />} /><Route path="/roadmap" element={<RoadmapPage />} /><Route path="/settings" element={<SettingsPage />} /><Route path="/quiz/diagnostic" element={<QuizPage />} /><Route path="/quiz/topic/:topicId" element={<QuizPage />} /><Route path="/admin/edges" element={<AdminReviewPage />} /></Route><Route path="*" element={<Navigate to={getToken() ? '/dashboard' : '/login'} replace />} /></Routes>
}
