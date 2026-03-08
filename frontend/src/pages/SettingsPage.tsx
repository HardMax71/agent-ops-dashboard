import React from 'react'
import { useAuthStore } from '../store/authStore'
import { authApi } from '../api/endpoints'

export function SettingsPage(): React.ReactElement {
  const { user, logout } = useAuthStore()

  const handleDisconnectGitHub = async (): Promise<void> => {
    await authApi.deleteGithubToken()
  }

  const handleLogout = async (): Promise<void> => {
    await authApi.logout()
    logout()
    window.location.href = '/login'
  }

  return (
    <div className="min-h-screen bg-gray-950 p-8">
      <div className="max-w-lg mx-auto">
        <h1 className="text-xl font-bold text-gray-100 mb-6">Settings</h1>

        {user && (
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 mb-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-4">GitHub Account</h2>
            <div className="flex items-center gap-3 mb-4">
              {user.avatar_url && (
                <img
                  src={user.avatar_url}
                  alt={user.github_login}
                  className="w-10 h-10 rounded-full border border-gray-600"
                />
              )}
              <div>
                <p className="text-sm font-medium text-gray-200">{user.github_login}</p>
                <p className="text-xs text-gray-500">GitHub ID: {user.github_id}</p>
              </div>
            </div>
            <button
              onClick={handleDisconnectGitHub}
              className="text-sm text-red-400 hover:text-red-300 border border-red-800 hover:border-red-700 px-3 py-1.5 rounded transition-colors"
              aria-label="Disconnect GitHub account"
            >
              Disconnect GitHub
            </button>
          </div>
        )}

        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">Session</h2>
          <button
            onClick={handleLogout}
            className="text-sm text-gray-300 hover:text-gray-100 border border-gray-600 hover:border-gray-500 px-4 py-2 rounded transition-colors"
            aria-label="Log out"
          >
            Log out
          </button>
        </div>
      </div>
    </div>
  )
}
