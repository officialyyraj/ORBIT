import { useState } from 'react'
import type { Question } from '../api/client'
type AnswerResult = { correct: boolean; correct_choice_index: number; explanation?: string; distractor_explanations?: { choice: string; feedback: string }[] }
export default function QuizCard({ question, onAnswer }: { question: Question; onAnswer: (choice: number) => Promise<AnswerResult> }) {
  const [selected, setSelected] = useState<number | null>(null)
  const [result, setResult] = useState<AnswerResult | null>(null)
  const [loading, setLoading] = useState(false)
  const answer = async (choice: number) => { if (selected !== null) return; setSelected(choice); setLoading(true); try { setResult(await onAnswer(choice)) } finally { setLoading(false) } }
  const selectedChoice = selected === null ? '' : question.choices[selected]
  const distractor = result?.distractor_explanations?.find(item => item.choice === selectedChoice)
  return <div className="quiz-card"><div className="question-kicker">{question.question_type === 'application' ? 'APPLY THE CONCEPT' : 'CHECK YOUR UNDERSTANDING'}</div><h2>{question.prompt}</h2><div className="choices">{question.choices.map((choice, index) => { const state = result ? (index === result.correct_choice_index ? 'correct' : index === selected ? 'incorrect' : '') : selected === index ? 'selected' : ''; return <button key={choice} disabled={selected !== null || loading} className={`choice ${state}`} onClick={() => answer(index)}><span className="choice-index">{String.fromCharCode(65 + index)}</span>{choice}</button> })}</div>{result && <div className={`feedback ${result.correct ? 'feedback-correct' : 'feedback-wrong'}`}><strong>{result.correct ? 'Correct.' : 'Not quite.'}</strong> {result.explanation || (result.correct ? 'Your mastery estimate moved up.' : 'Review the concept and try the next question.')} {distractor && <p>{distractor.feedback}</p>}</div>}</div>
}
