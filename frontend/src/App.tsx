import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { DashboardPage } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { SettingsPage } from './pages/SettingsPage'
import { useAuthStore } from './store/authStore'

function ProtectedRoute({ children }: { children: React.ReactElement }): React.ReactElement {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return children
}

function AuthCallbackPage(): React.ReactElement {
  const setToken = useAuthStore((s) => s.setToken)
  const setUser = useAuthStore((s) => s.setUser)

  React.useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    if (!code) {
      window.location.href = '/login'
      return
    }

    const exchangeCode = async (): Promise<void> => {
      const response = await fetch('/api/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ code }),
      })
      const data = await response.json() as { access_token: string }
      setToken(data.access_token)

      const userResponse = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${data.access_token}` },
      })
      const userData = await userResponse.json() as { github_id: string; github_login: string; avatar_url?: string }
      setUser({ github_id: userData.github_id, github_login: userData.github_login, avatar_url: userData.avatar_url })

      window.location.href = '/dashboard'
    }

    exchangeCode().catch(console.error)
  }, [setToken, setUser])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950">
      <p className="text-gray-400">Signing in...</p>
    </div>
  )
}

export default function App(): React.ReactElement {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <DashboardPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <SettingsPage />
            </ProtectedRoute>
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
      </Routes>
    </BrowserRouter>
  )
}
