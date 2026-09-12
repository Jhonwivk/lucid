import { Navigate, Route, Routes } from 'react-router-dom'
import { AnalysesPage } from './pages/AnalysesPage'
import { WorkbenchPage } from './pages/WorkbenchPage'
import './App.css'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/analyses" replace />} />
      <Route path="/analyses" element={<AnalysesPage />} />
      <Route
        path="/analyses/:projectId"
        element={<ProjectWorkspaceRedirect />}
      />
      <Route
        path="/analyses/:projectId/:workspaceId"
        element={<WorkbenchPage />}
      />
      <Route path="/workbench" element={<Navigate to="/analyses" replace />} />
      <Route
        path="/workbench/:workspaceId"
        element={<Navigate to="/analyses" replace />}
      />
      <Route path="*" element={<Navigate to="/analyses" replace />} />
    </Routes>
  )
}

function ProjectWorkspaceRedirect() {
  return <Navigate to="materials" replace />
}
