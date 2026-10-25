import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getEdgeReview, refineEdges } from '../api/client'
import { useState } from 'react'

export default function AdminReviewPage() {
  const client = useQueryClient()
  const [message, setMessage] = useState('')
  const review = useQuery({ queryKey: ['edge-review'], queryFn: getEdgeReview })
  const refine = async () => { setMessage('Refining edge confidence…'); const result = await refineEdges(); setMessage(`${result.updated_edges} edges evaluated from response evidence.`); await client.invalidateQueries({ queryKey: ['edge-review'] }); await client.invalidateQueries({ queryKey: ['kst'] }) }
  if (review.isLoading) return <div className="loading">Loading edge review…</div>
  if (review.error) return <div className="page"><div className="error-box">{(review.error as Error).message}</div></div>
  return <div className="page"><div className="page-intro"><div><span className="eyebrow">ADMIN / GRAPH QUALITY</span><h2>Review prerequisite confidence</h2><p>These edges have confidence below the review threshold. ORBIT surfaces evidence for human review and never mutates the graph structure automatically.</p></div><button className="primary-button" onClick={refine}>Run refinement</button></div>{message && <div className="success-box">{message}</div>}<section className="panel"><div className="panel-heading"><div><span className="eyebrow">LOW-CONFIDENCE EDGES</span><h3>{review.data?.edges.length || 0} edges need attention</h3></div><span className="pill">Threshold {Math.round((review.data?.threshold || 0) * 100)}%</span></div>{review.data?.edges.length ? <div className="edge-review-table">{review.data.edges.map(edge => <div className="edge-review-row" key={edge.edge_id}><div><strong>{edge.prerequisite_name}</strong><span>→ {edge.topic_name}</span></div><div className="edge-score"><b>{Math.round(edge.confidence_score * 100)}%</b><small>{edge.sample_count} paired learner responses · gap {Math.round(edge.positive_gap * 100)}%</small></div></div>)}</div> : <div className="empty-state">No edges are currently below the review threshold. Run refinement after more paired quiz evidence is available.</div>}</section></div>
}
