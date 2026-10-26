import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getLibrary, getMastery, getQuestions, getSelectedTrackId, setSelectedTrackId, submitResponse } from '../api/client'
import QuizCard from '../components/QuizCard'

export default function QuizPage() {
  const { topicId } = useParams()
  const diagnostic = !topicId
  const navigate = useNavigate()
  const client = useQueryClient()
  const library = useQuery({ queryKey: ['library'], queryFn: getLibrary, enabled: diagnostic })
  const [chosenTrackId, setChosenTrackId] = useState(() => getSelectedTrackId() || '')
  const trackId = library.data?.tracks.some(track => track.id === chosenTrackId)
    ? chosenTrackId
    : library.data?.tracks[0]?.id || ''
  const query = useQuery({
    queryKey: ['questions', topicId || 'diagnostic', diagnostic ? trackId : null],
    queryFn: () => getQuestions(topicId, diagnostic ? trackId : undefined),
    enabled: !diagnostic || Boolean(trackId),
  })
  const mastery = useQuery({ queryKey: ['mastery'], queryFn: getMastery, enabled: !diagnostic })
  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState<{ before: number; after: number }[]>([])
  const [finished, setFinished] = useState(false)

  useEffect(() => {
    setIndex(0)
    setFinished(false)
    setAnswers([])
  }, [topicId, trackId])

  useEffect(() => {
    if (diagnostic && trackId && chosenTrackId !== trackId) {
      setChosenTrackId(trackId)
      setSelectedTrackId(trackId)
    }
  }, [chosenTrackId, diagnostic, trackId])

  if ((diagnostic && library.isLoading) || query.isLoading || (!diagnostic && mastery.isLoading)) return <div className="loading">Preparing your questions…</div>
  if (diagnostic && library.error) return <div className="error-box">{(library.error as Error).message}</div>
  if (query.error) return <div className="error-box">{(query.error as Error).message}</div>

  const questions = query.data?.questions || []
  const question = questions[index]
  if (finished) {
    const before = answers[0]?.before
    const after = answers[answers.length - 1]?.after
    return <div className="page narrow"><div className="completion-card"><span className="eyebrow">{diagnostic ? 'DIAGNOSTIC COMPLETE' : 'TOPIC QUIZ COMPLETE'}</span><h2>{diagnostic ? 'Your orbit is calibrated.' : 'Nice work — your profile moved.'}</h2>{!diagnostic && before !== undefined && after !== undefined && <div className="before-after"><div><span>BEFORE</span><strong>{Math.round(before * 100)}%</strong></div><div className="arrow">→</div><div><span>AFTER</span><strong className="accent-text">{Math.round(after * 100)}%</strong></div></div>}<p>ORBIT has refreshed your mastery profile and roadmap using your latest answers.</p><Link to="/dashboard" className="primary-button">View updated dashboard</Link></div></div>
  }
  if (!question) return <div className="empty-state">No questions available yet.</div>

  const answer = async (choice: number) => {
    const previous = mastery.data?.estimates.find(item => item.topic_id === question.topic_id)?.p_mastery ?? 0.3
    const result = await submitResponse(question.id, choice)
    setAnswers(values => [...values, { before: previous, after: result.updated_mastery.p_mastery }])
    return result
  }
  const next = () => {
    if (index + 1 < questions.length) setIndex(index + 1)
    else {
      client.invalidateQueries({ queryKey: ['mastery'] })
      client.invalidateQueries({ queryKey: ['roadmap'] })
      setFinished(true)
    }
  }

  return <div className="page narrow">{diagnostic && <label className="track-picker">Choose a track for your diagnostic <select value={trackId} onChange={event => { setChosenTrackId(event.target.value); setSelectedTrackId(event.target.value) }}>{library.data?.tracks.map(track => <option key={track.id} value={track.id}>{track.title}</option>)}</select></label>}<div className="quiz-header"><Link to={diagnostic ? '/dashboard' : '/roadmap'} className="back-link">← Exit quiz</Link><div><span className="eyebrow">{diagnostic ? 'DIAGNOSTIC' : 'TOPIC CHECK'}</span><span className="progress-count">{index + 1} / {questions.length}</span></div></div><div className="quiz-progress"><div style={{ width: `${((index + 1) / questions.length) * 100}%` }} /></div><QuizCard key={question.id} question={question} onAnswer={answer} /><button className="primary-button next-button" onClick={next}>{index + 1 === questions.length ? 'Finish quiz' : 'Next question'} →</button></div>
}
