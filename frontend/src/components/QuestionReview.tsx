import { useState } from 'react'

import type { Artifact, SourceQuestion } from '../api/study'

export function QuestionReview({ artifact, sourceQuestion, onResult }: { artifact?: Artifact; sourceQuestion?: SourceQuestion; onResult: (correct: boolean) => void }) {
  const generated = artifact?.payload.questions?.[0]
  const question = sourceQuestion?.question_text ?? generated?.question
  const answer = sourceQuestion?.answer_text ?? generated?.answer
  const [revealed, setRevealed] = useState(false)
  const [draft, setDraft] = useState('')
  if (!question) return <p className="inline-guidance">没有可复习的题目。</p>
  return <article className="question-review"><p className="eyebrow">先在本机作答</p><h2>{question}</h2><label>我的答案<textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="答案只保存在本次记录中，不会自动发送给 AI。" /></label>{!revealed ? <button className="button button--primary" type="button" onClick={() => setRevealed(true)}>核对答案</button> : <div className="answer-sheet"><strong>参考答案</strong><p>{answer || '原资料没有提供答案。'}</p>{generated?.explanation && <p>{generated.explanation}</p>}<div className="candidate-toolbar"><button className="button button--secondary" type="button" onClick={() => onResult(true)}>我答对了</button><button className="button button--secondary" type="button" onClick={() => onResult(false)}>还需复习</button></div></div>}</article>
}
