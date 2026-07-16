import type { Artifact } from '../api/study'

export function OutlineReview({ artifact }: { artifact: Artifact }) {
  const outline = artifact.payload.outline
  if (!outline) return <p className="inline-guidance">提纲内容尚未生成。</p>
  return <article className="outline-review"><h2>{outline.title}</h2>{outline.sections.map((section) => <section key={`${section.heading}-${section.keypoint_ids.join('-')}`}><h3>{section.heading}</h3><p>{section.body}</p><small>关联重点 #{section.keypoint_ids.join('、#')}</small></section>)}</article>
}
