import { RotateCcw } from 'lucide-react'
import { useState } from 'react'

import type { Artifact } from '../api/study'

export function FlashcardReview({ artifact }: { artifact: Artifact }) {
  const cards = artifact.payload.flashcards ?? []
  const [index, setIndex] = useState(0)
  const [revealed, setRevealed] = useState(false)
  const card = cards[index]
  if (!card) return <p className="inline-guidance">记忆卡尚未生成。</p>
  function next() { setIndex((value) => (value + 1) % cards.length); setRevealed(false) }
  function advance() { if (revealed) next(); else setRevealed(true) }
  return <article className="flashcard" tabIndex={0} onKeyDown={(event) => { if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); advance() } }}><small>{index + 1} / {cards.length}</small><h2>{revealed ? card.back : card.front}</h2><button className="button button--primary" type="button" onClick={advance}>{revealed ? '下一张' : '显示答案'}</button>{revealed && <button className="button button--ghost" type="button" onClick={() => setRevealed(false)}><RotateCcw /> 再想一次</button>}</article>
}
