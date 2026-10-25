import { useEffect, useState } from 'react'

export default function SettingsPage() {
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === 'dark')
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; localStorage.setItem('orbit-theme', dark ? 'dark' : 'light') }, [dark])
  return <div className="page narrow"><div className="page-intro"><div><span className="eyebrow">SETTINGS</span><h2>Make ORBIT yours.</h2><p>Small preferences for a focused learning environment. Your learning data stays in the existing ORBIT profile.</p></div></div><section className="panel settings-list"><div className="settings-row"><div><h4>Color theme</h4><p>Switch between the pure white and pure black interfaces.</p></div><button className="secondary-button" onClick={() => setDark(value => !value)}>{dark ? 'Use light theme' : 'Use dark theme'}</button></div><div className="settings-row"><div><h4>Learning profile</h4><p>Mastery estimates are updated by the same BKT pipeline after every scored answer.</p></div><span className="pill">ACTIVE</span></div><div className="settings-row"><div><h4>Data boundary</h4><p>AI Lab demonstrations are synthetic and do not write learner responses or mastery records.</p></div><span className="pill">PROTECTED</span></div></section></div>
}
