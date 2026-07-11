import { ArrowRight, BookOpen, Clock3, Gauge, Microscope, TriangleAlert } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import { WaferStages } from '../components/WaferStages'

export function DashboardPage() {
  const dashboard = useQuery({ queryKey: ['dashboard'], queryFn: api.getDashboard, retry: false })
  const data = dashboard.data
  const today = new Intl.DateTimeFormat('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  }).format(new Date())

  return (
    <div className="dashboard-page">
      <header className="dashboard-hero">
        <div>
          <p className="eyebrow">{today} · 本机复习台</p>
          <h1>今天，先把课堂留下来</h1>
          <p className="hero-copy">选定刚讲过的页面，十分钟后离开屏幕时，你会知道哪些真的记住了。</p>
        </div>
        <div className="hero-target" aria-label="今日复习目标十分钟">
          <span>目标</span>
          <strong>10</strong>
          <small>分钟</small>
        </div>
      </header>

      <section className="dashboard-grid" aria-label="今日概况">
        <article className="metric-card metric-card--accent">
          <div className="card-label"><Microscope aria-hidden="true" />今日新课</div>
          <strong>{data?.today_new_lessons ? `${data.today_new_lessons} 节` : '待录入'}</strong>
          <p>课后两分钟内选页，重点最鲜活。</p>
          <Link to="/lessons/new">记录本次课堂 <ArrowRight aria-hidden="true" /></Link>
        </article>
        <article className="metric-card">
          <div className="card-label"><Clock3 aria-hidden="true" />到期复习</div>
          <strong>{data?.due_count ?? 0} <small>题</small></strong>
          <p>{data?.due_count ? '优先回忆到期内容，再看来源页。' : '暂无积压；新课生成后会自动进入 R+0。'}</p>
          <Link to="/review">查看复习台 <ArrowRight aria-hidden="true" /></Link>
        </article>
        <article className="metric-card">
          <div className="card-label"><Gauge aria-hidden="true" />预计耗时</div>
          <strong>{data?.estimated_minutes ? `${data.estimated_minutes}` : '8–10'} <small>分钟</small></strong>
          <p>12 分钟后不再加题，15 分钟硬停止。</p>
        </article>
      </section>

      <section className="lab-section stage-overview">
        <div className="section-heading">
          <div>
            <p className="eyebrow">间隔轨迹</p>
            <h2>从当天回忆，到稳定掌握</h2>
          </div>
          <span className="status-chip status-chip--teal">本地排期</span>
        </div>
        <WaferStages active={0} />
        <p className="section-note">每次回答会结合 AI 评分与自评推进；断网时仍可凭自评完成排期。</p>
      </section>

      <section className="dashboard-lower">
        <article className="lab-section weak-summary">
          <div className="section-heading">
            <div>
              <p className="eyebrow">薄弱点</p>
              <h2>{data?.weak_points.length ? '优先补这几个缺口' : '还没有形成记录'}</h2>
            </div>
            <TriangleAlert aria-hidden="true" />
          </div>
          {data?.weak_points.length ? (
            <ul className="weak-point-list">
              {data.weak_points.map((point) => <li key={point.question_id}>{point.prompt}</li>)}
            </ul>
          ) : (
            <p>完成第一轮主动回忆后，这里会聚合“模糊”和“不会”的知识点。</p>
          )}
          <Link className="text-link" to="/progress">查看掌握进度</Link>
        </article>
        <article className="lab-section local-note">
          <BookOpen aria-hidden="true" />
          <div>
            <p className="eyebrow">数据边界</p>
            <h2>正式记录只留在这台电脑</h2>
            <p>只有你选中的页面、文本和课堂补充会发给当前 AI 后端。</p>
          </div>
        </article>
      </section>
    </div>
  )
}
