import { Navigate, Route, Routes } from 'react-router-dom'
import { BriefPage } from './pages/BriefPage'
import './App.css'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<BriefPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
