import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

import { api, getTokens, setTokens, type Tokens } from './api/client'
import type { User } from './api/types'

type Auth = {
  user: User | undefined
  isLoggedIn: boolean
  login: (email: string, password: string) => Promise<void>
  register: (firstName: string, email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<Auth | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [isLoggedIn, setIsLoggedIn] = useState(() => getTokens() !== null)

  // Tokens live in localStorage; this keeps React in sync with them.
  useEffect(() => {
    const sync = () => setIsLoggedIn(getTokens() !== null)
    window.addEventListener('tokens-changed', sync)
    return () => window.removeEventListener('tokens-changed', sync)
  }, [])

  const { data: user } = useQuery({
    queryKey: ['me'],
    queryFn: () => api<User>('/api/v1/users/me'),
    enabled: isLoggedIn,
  })

  async function login(email: string, password: string) {
    const tokens = await api<Tokens>('/api/v1/auth/token', {
      method: 'POST',
      body: { email, password },
    })
    setTokens(tokens)
  }

  async function register(firstName: string, email: string, password: string) {
    await api('/api/v1/auth/register', {
      method: 'POST',
      body: { first_name: firstName, email, password },
    })
    await login(email, password)
  }

  function logout() {
    setTokens(null)
    queryClient.clear() // forget the previous user's data
  }

  return (
    <AuthContext value={{ user: isLoggedIn ? user : undefined, isLoggedIn, login, register, logout }}>
      {children}
    </AuthContext>
  )
}

export function useAuth(): Auth {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside AuthProvider')
  return auth
}
