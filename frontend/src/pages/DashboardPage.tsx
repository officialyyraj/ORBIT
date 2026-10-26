import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getLibrary, getMastery, getRoadmap, getSelectedTrackId, setSelectedTrackId, type WeightedRoadmap } from '../api/client'
import MasteryBar from '../components/MasteryBar'

export default function DashboardPage() {
  const [chosenTrackId, setChosenTrackId] = useState(() => getSelectedTrackId() || '')
  const library = useQuery({ queryKey: ['library'], queryFn: getLibrary })
  const trackId = library.data?.tracks.some(track => track.id === chosenTrackId)
    ? chosenTrackId
    : library.data?.tracks[0]?.id || ''
  const mastery = useQuery({ queryKey: ['mastery'], queryFn: getMastery })
  const roadmap = useQuery<WeightedRoadmap>({ queryKey: ['roadmap', 'weighted', trackId], queryFn: () => getRoadmap('weighted', trackId) as Promise<WeightedRoadmap>, enabled: Boolean(trackId) })
  useEffect(() => {
    if (trackId && chosenTrackId !== trackId) {
      setChosenTrackId(trackId)
      setSelectedTrackId(trackId)
    }
  }, [chosenTrackId, trackId])
  if (mastery.isLoading || roadmap.isLoading || library.isLoading) return <div className="loading">Loading your orbit…</div>
  if (mastery.error || roadmap.error || library.error) return <div className="page"><div className="error-box">Unable to load your learning profile. Please try again.</div></div>
  const estimates = mastery.data?.estimates || []
  const path = roadmap.data?.path || []
  const average = estimates.length ? estimates.reduce((total, item) => total + item.p_mastery, 0) / estimates.length : null
  const next = path[0]
  const trackCount = library.data?.tracks?.length || 0
  return <div className="page">
    <section className="hero-card"><div><span className="eyebrow">WELCOME BACK, LEARNER</span><h2>{next ? 'Your next move is clear.' : 'Build your learning orbit.'}</h2><p>{next ? `ORBIT recommends ${next.topic_name} next, based on your current mastery and prerequisite graph.` : 'Start with a track, complete a short assessment, and ORBIT will shape a path around what you know.'}</p><label className="track-picker">Learning track <select value={trackId} onChange={event => { setChosenTrackId(event.target.value); setSelectedTrackId(event.target.value) }}>{library.data?.tracks.map(track => <option key={track.id} value={track.id}>{track.title}</option>)}</select></label><div className="lesson-actions"><Link className="primary-button" to={next ? `/quiz/topic/${next.topic_id}` : '/library'}>{next ? 'Continue learning →' : 'Explore the library →'}</Link>{next && <Link className="secondary-button" to="/roadmap">Inspect the path</Link>}</div></div><div className="orb-stat"><span>AVERAGE MASTERY</span><strong>{average === null ? '—' : Math.round(average * 100)}{average !== null && <small>%</small>}</strong></div></section>
    <div className="section-grid"><section className="panel"><div className="panel-heading"><div><span className="eyebrow">RECOMMENDED NEXT</span><h3>{next ? next.topic_name : 'No route yet'}</h3></div><span className="track-index">01</span></div>{next ? <><p>{next.reason}</p><div className="contribution"><span>Gap {Math.round(next.objective_breakdown.mastery_deficit * 100)}%</span><span>Review {Math.round(next.objective_breakdown.retention_penalty * 100)}%</span><span>{Math.round(next.objective_breakdown.time_cost * 100)}% time weight</span></div></> : <p className="empty-state">Complete a diagnostic or topic quiz to generate a personalized route.</p>}</section><section className="panel"><div className="panel-heading"><div><span className="eyebrow">YOUR SPACE</span><h3>At a glance</h3></div></div><div className="stat-list"><div><span>Tracks available</span><strong>{trackCount}</strong></div><div><span>Observed topics</span><strong>{estimates.length}</strong></div><div><span>Roadmap steps</span><strong>{path.length}</strong></div></div><Link className="text-link" to="/ai-lab">Understand the engines →</Link></section></div>
    <div className="section-grid"><section className="panel"><div className="panel-heading"><div><span className="eyebrow">MASTERY PROFILE</span><h3>What you know</h3></div><Link className="text-link" to="/roadmap">Open progress →</Link></div>{estimates.length ? <div className="mastery-list">{estimates.slice(0, 6).map(item => <MasteryBar key={item.topic_id} name={item.topic_name} value={item.p_mastery} lastStudied={item.last_updated} />)}</div> : <p className="empty-state">No observed mastery yet. Your first answer will start the profile.</p>}</section><section className="panel"><div className="panel-heading"><div><span className="eyebrow">THREE ENGINES</span><h3>Why ORBIT adapts</h3></div></div><div className="engine-list"><Link to="/ai-lab"><b>01 / Knowledge graph</b><span>Prerequisites keep each next step grounded.</span></Link><Link to="/ai-lab"><b>02 / BKT</b><span>Answers become a changing estimate of mastery.</span></Link><Link to="/ai-lab"><b>03 / A* roadmap</b><span>Search balances gap, retention, and time.</span></Link></div></section></div>
  </div>
}
