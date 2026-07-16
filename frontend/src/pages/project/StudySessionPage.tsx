import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'

import { masteryApi, masteryKeys, type MasteryLevel } from '../../api/mastery'
import type { Artifact, SourceQuestion } from '../../api/study'
import { FlashcardReview } from '../../components/FlashcardReview'
import { MasteryControl } from '../../components/MasteryControl'
import { OutlineReview } from '../../components/OutlineReview'
import { QuestionReview } from '../../components/QuestionReview'

export function StudySessionPage({ projectId, artifact, sourceQuestion, onClose }: { projectId: string; artifact?: Artifact; sourceQuestion?: SourceQuestion; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [level, setLevel] = useState<MasteryLevel>('unrated')
  const targetType = artifact ? 'artifact' : 'source_question'
  const targetId = artifact?.id ?? sourceQuestion!.id
  const mode = artifact?.kind === 'outline' ? 'outline' : artifact?.kind === 'flashcard' ? 'flashcards' : artifact ? 'ai_questions' : 'source_questions'
  const attempt = useMutation({ mutationFn: (value: { correct?: boolean; rating?: MasteryLevel }) => masteryApi.attempt(projectId, { mode, item_type: targetType, item_id: targetId, correct: value.correct, self_rating: value.rating }), onSuccess: () => { void queryClient.invalidateQueries({ queryKey: masteryKeys.summary(projectId) }); void queryClient.invalidateQueries({ queryKey: masteryKeys.records(projectId) }) } })
  function rate(value: MasteryLevel) { setLevel(value); attempt.mutate({ rating: value }) }
  return <section className="study-session"><button className="back-link" type="button" onClick={onClose}><ArrowLeft /> 返回复习内容</button><div className="study-focus">{artifact?.kind === 'outline' && <OutlineReview artifact={artifact} />}{artifact?.kind === 'flashcard' && <FlashcardReview artifact={artifact} />}{artifact && !['outline', 'flashcard'].includes(artifact.kind) && <QuestionReview artifact={artifact} onResult={(correct) => attempt.mutate({ correct })} />}{sourceQuestion && <QuestionReview sourceQuestion={sourceQuestion} onResult={(correct) => attempt.mutate({ correct })} />}</div><MasteryControl value={level} disabled={attempt.isPending} onChange={rate} />{attempt.isSuccess && <p className="form-success" role="status">本次复习记录已保存。</p>}</section>
}
