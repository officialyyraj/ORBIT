import { useState } from 'react'
import { clearToken, getToken } from '../api/client'
export function useAuth() {
  const [authenticated, setAuthenticated] = useState(Boolean(getToken()))
  const logout = () => { clearToken(); setAuthenticated(false); window.location.href = '/login' }
  return { authenticated, logout }
}
