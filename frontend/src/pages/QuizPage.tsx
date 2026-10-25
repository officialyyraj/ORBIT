import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getMastery, getQuestions, submitResponse } from '../api/client'
import QuizCard from '../components/QuizCard'

export default function QuizPage() {
  const { topicId } = useParams()
  const diagnostic = !topicId
  const navigate = useNavigate()
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['questions', topicId || 'diagnostic'], queryFn: () => getQuestions(topicId) })
  const mastery = useQuery({ queryKey: ['mastery'], queryFn: getMastery, enabled: !diagnostic })
  const [index, setIndex] = useState(0)
  const [answers, setAnswers] = useState<{ before: number; after: number }[]>([])
  const [finished, setFinished] = useState(false)

  useEffect(() => {
    setIndex(0)
    setFinished(false)
    setAnswers([])
  }, [topicId])

  if (query.isLoading || (!diagnostic && mastery.isLoading)) return <div className="loading">Preparing your questions…</div>
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

  return <div className="page narrow"><div className="quiz-header"><Link to={diagnostic ? '/dashboard' : '/roadmap'} className="back-link">← Exit quiz</Link><div><span className="eyebrow">{diagnostic ? 'DIAGNOSTIC' : 'TOPIC CHECK'}</span><span className="progress-count">{index + 1} / {questions.length}</span></div></div><div className="quiz-progress"><div style={{ width: `${((index + 1) / questions.length) * 100}%` }} /></div><QuizCard key={question.id} question={question} onAnswer={answer} /><button className="primary-button next-button" onClick={next}>{index + 1 === questions.length ? 'Finish quiz' : 'Next question'} →</button></div>
}
