import React, { useState } from 'react'
import { useAuthStore } from '../store/authStore'
import { gql, getAccessToken } from '../api/graphqlClient'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

export function SettingsPage(): React.ReactElement {
  const { user, logout } = useAuthStore()
  const [isDisconnected, setIsDisconnected] = useState(false)

  const handleDisconnectGitHub = async (): Promise<void> => {
    await gql.mutation({ deleteGithubToken: { __scalar: true } })
    setIsDisconnected(true)
  }

  const handleLogout = async (): Promise<void> => {
    const token = getAccessToken()
    try {
      await fetch('/api/auth/logout', {
        method: 'DELETE',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: 'same-origin',
      })
    } finally {
      logout()
      window.location.href = '/login'
    }
  }

  return (
    <div className="min-h-screen bg-muted/30 p-8">
      <div className="max-w-lg mx-auto space-y-4">
        <h1 className="text-xl font-bold mb-6">Settings</h1>

        {user && (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">GitHub Account</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3 mb-4">
                {user.avatarUrl && (
                  <img
                    src={user.avatarUrl}
                    alt={user.githubLogin}
                    className="w-10 h-10 rounded-full border"
                  />
                )}
                <div>
                  <p className="text-sm font-medium">{user.githubLogin}</p>
                  <p className="text-xs text-muted-foreground">GitHub ID: {user.githubId}</p>
                </div>
              </div>
              {isDisconnected ? (
                <span className="text-sm text-muted-foreground">GitHub token disconnected</span>
              ) : (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDisconnectGitHub}
                  className="text-red-600 border-red-200 hover:bg-red-50"
                  aria-label="Disconnect GitHub account"
                >
                  Disconnect GitHub
                </Button>
              )}
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Session</CardTitle>
          </CardHeader>
          <CardContent>
            <Button
              variant="outline"
              onClick={handleLogout}
              aria-label="Log out"
            >
              Log out
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
