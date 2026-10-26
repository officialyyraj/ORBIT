import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getKst, getLibrary, getMastery, getRoadmap, getSelectedTrackId, setSelectedTrackId, type ParetoPath, type RoadmapNode } from '../api/client'
import RoadmapGraph from '../components/RoadmapGraph'

export default function RoadmapPage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'weighted' | 'pareto'>('weighted')
  const [selectedLabel, setSelectedLabel] = useState('Balanced')
  const [chosenTrackId, setChosenTrackId] = useState(() => getSelectedTrackId() || '')
  const library = useQuery({ queryKey: ['library'], queryFn: getLibrary })
  const trackId = library.data?.tracks.some(track => track.id === chosenTrackId)
    ? chosenTrackId
    : library.data?.tracks[0]?.id || ''
  const kst = useQuery({ queryKey: ['kst'], queryFn: getKst })
  const mastery = useQuery({ queryKey: ['mastery'], queryFn: getMastery })
  const roadmap = useQuery({ queryKey: ['roadmap', mode, trackId], queryFn: () => getRoadmap(mode, trackId), enabled: Boolean(trackId) })
  useEffect(() => { setSelectedLabel('Balanced') }, [mode])
  useEffect(() => {
    if (trackId && chosenTrackId !== trackId) {
      setChosenTrackId(trackId)
      setSelectedTrackId(trackId)
    }
  }, [chosenTrackId, trackId])
  if (kst.isLoading || mastery.isLoading || roadmap.isLoading || library.isLoading) return <div className="loading">Plotting your roadmap…</div>
  if (kst.error || mastery.error || roadmap.error || library.error) return <div className="error-box">Unable to load your roadmap.</div>

  const paretoPaths = roadmap.data?.mode === 'pareto' ? roadmap.data.paths : []
  const selectedPareto: ParetoPath | undefined = paretoPaths.find(path => path.label === selectedLabel) || paretoPaths[0]
  const path: RoadmapNode[] = roadmap.data?.mode === 'pareto' ? (selectedPareto?.path || []) : (roadmap.data?.path || [])

  return <div className="page"><div className="page-intro"><div><span className="eyebrow">THE KNOWLEDGE SPACE</span><h2>Your learning orbit</h2><p>Prerequisites stay in order. The emphasis shifts toward the topics where you can make the most progress.</p></div><Link to="/dashboard" className="secondary-button">← Dashboard</Link></div><div className="mode-toolbar"><label className="track-picker">Roadmap track <select value={trackId} onChange={event => { setChosenTrackId(event.target.value); setSelectedTrackId(event.target.value) }}>{library.data?.tracks.map(track => <option key={track.id} value={track.id}>{track.title}</option>)}</select></label><div className="mode-switch"><button className={mode === 'weighted' ? 'active' : ''} onClick={() => setMode('weighted')}>Balanced score</button><button className={mode === 'pareto' ? 'active' : ''} onClick={() => setMode('pareto')}>Pareto options</button></div>{mode === 'pareto' && <div className="pareto-options">{paretoPaths.map(option => <button key={option.label} className={selectedLabel === option.label ? 'selected' : ''} onClick={() => setSelectedLabel(option.label)}>{option.label}</button>)}</div>}</div><RoadmapGraph topics={kst.data?.topics || []} edges={kst.data?.edges || []} mastery={mastery.data?.estimates || []} path={path} /><section className="roadmap-list panel"><div className="panel-heading"><div><span className="eyebrow">{mode === 'pareto' ? `${selectedPareto?.label || 'PARETO'} PATH` : 'RECOMMENDED SEQUENCE'}</span><h3>Your next steps</h3></div><span className="pill">{path.length} topics in path</span></div>{path.map(node => <div className="roadmap-row" key={node.topic_id}><div className="step-number">{node.order}</div><div className="roadmap-main"><div className="roadmap-title"><h4>{node.topic_name}</h4><span className="mastery-chip">{Math.round(node.mastery_estimate * 100)}% mastery</span></div><p>{node.reason}</p><div className="contribution"><span>Gap {Math.round(node.objective_breakdown.mastery_deficit * 100)}%</span><span>Review {Math.round(node.objective_breakdown.retention_penalty * 100)}%</span><span>Time {Math.round(node.objective_breakdown.time_cost * 100)}%</span></div></div><button className="study-button" onClick={() => navigate(`/quiz/topic/${node.topic_id}`)}>Study this topic →</button></div>)}</section></div>
}
