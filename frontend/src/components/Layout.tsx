import { NavLink, Outlet } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useAuth } from '../hooks/useAuth'

const items = [
  { to: '/dashboard', label: 'Home', icon: '⌂' },
  { to: '/library', label: 'Learn', icon: '↗' },
  { to: '/roadmap', label: 'Progress', icon: '◒' },
  { to: '/ai-lab', label: 'AI Lab', icon: '✦' },
  { to: '/settings', label: 'Settings', icon: '⊙' },
]

export default function Layout() {
  const { logout } = useAuth()
  const [dark, setDark] = useState(() => localStorage.getItem('orbit-theme') === 'dark')
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; localStorage.setItem('orbit-theme', dark ? 'dark' : 'light') }, [dark])
  return <div className="app-shell">
    <main className="main-content">
      <header className="topbar">
        <NavLink className="wordmark" to="/dashboard"><span className="wordmark-mark">O</span><span>ORBIT</span></NavLink>
        <div className="topbar-meta"><span className="topbar-kicker">ADAPTIVE LEARNING SYSTEM</span><span className="avatar">D</span></div>
      </header>
      <Outlet />
    </main>
    <aside className="right-rail" aria-label="Primary navigation">
      <div className="rail-top"><span className="rail-label">NAVIGATE</span><nav>{items.map(item => <NavLink key={item.to} to={item.to} className={({ isActive }) => isActive ? 'rail-link active' : 'rail-link'}><span className="rail-icon" aria-hidden="true">{item.icon}</span><span>{item.label}</span></NavLink>)}</nav></div>
      <div className="rail-bottom"><button className="theme-toggle" onClick={() => setDark(value => !value)} aria-label="Toggle color theme"><span>{dark ? '☼' : '◐'}</span><small>{dark ? 'Light' : 'Dark'}</small></button><button className="rail-signout" onClick={logout}>Sign out</button></div>
    </aside>
  </div>
}
