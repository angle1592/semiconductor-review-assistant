import { CircleCheckBig, ScanSearch, TrendingUp } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'
import { PageHeading } from '../components/Ui'
import { WaferStages } from '../components/WaferStages'

export function ProgressPage() {
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: api.getDashboard, retry: false })
  const data = dashboard.data
  return (
    <div>
      <PageHeading eyebrow="掌握进度" title="看清哪里还不稳" description="阶段来自真实回答，不用连续天数制造压力。" />
      <section className="progress-metrics">
        <article><span><CircleCheckBig />稳定掌握</span><strong>{data?.stable_count ?? 0}</strong><p>通过 R+60 的知识点</p></article>
        <article><span><TrendingUp />待巩固</span><strong>{data?.reinforce_count ?? 0}</strong><p>次日会再次出现</p></article>
        <article><span><ScanSearch />薄弱点</span><strong>{data?.not_mastered_count ?? 0}</strong><p>需要回看来源页</p></article>
      </section>
      <section className="lab-section progress-map">
        <div className="section-heading">
          <div><p className="eyebrow">复习晶圆图</p><h2>五个固定阶段</h2></div>
          <span className="status-chip status-chip--teal">规则已启用</span>
        </div>
        <WaferStages active={0} />
        <div className="rule-grid">
          <div><strong>掌握</strong><p>前进一阶段；通过 R+60 后进入稳定掌握。</p></div>
          <div><strong>待巩固</strong><p>次日再现，当前阶段不变。</p></div>
          <div><strong>未掌握</strong><p>次日再现，并回退一阶段。</p></div>
        </div>
      </section>
      <section className="state-panel state-panel--empty">
        <ScanSearch aria-hidden="true" />
        <h2>{data?.weak_points.length ? '当前需要优先巩固' : '薄弱点会在第一次复习后出现'}</h2>
        {data?.weak_points.length ? (
          <ul className="weak-point-list">{data.weak_points.map((point) => <li key={point.question_id}>{point.prompt}</li>)}</ul>
        ) : <p>每个知识点都会保留课程、课件和页码来源。</p>}
      </section>
    </div>
  )
}
