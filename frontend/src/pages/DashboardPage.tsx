import { useQuery } from '@tanstack/react-query'
import { ArrowRight, FileStack, ScanSearch } from 'lucide-react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import { ErrorState, LoadingState, PageHeading } from '../components/Ui'

export function DashboardPage() {
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.listProjects })

  return (
    <section className="page page--home">
      <PageHeading
        eyebrow="总复习工作台"
        title="把散落的资料，整理成可复习的重点"
        description="先建立项目；资料提取、重点确认与复习流程会在接下来的阶段逐步接通。"
        actions={<Link className="button button--primary" to="/projects">进入项目 <ArrowRight /></Link>}
      />

      <div className="home-ledger" aria-label="当前工作概览">
        <article>
          <FileStack aria-hidden="true" />
          <span>复习项目</span>
          {projects.isPending ? <LoadingState label="正在统计项目" /> : projects.isError ? <ErrorState title="暂时无法统计" description="项目服务未响应。" /> : <strong>{projects.data.length}</strong>}
        </article>
        <article>
          <ScanSearch aria-hidden="true" />
          <span>当前阶段</span>
          <strong className="text-value">建立资料索引</strong>
          <small>导入与提取能力正在接入</small>
        </article>
      </div>

      <div className="workflow-strip" aria-label="拾要工作流程">
        {['建立项目', '导入资料', '确认重点', '开始复习', '回看掌握'].map((step, index) => (
          <div key={step} className={index === 0 ? 'is-current' : ''}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <strong>{step}</strong>
          </div>
        ))}
      </div>
    </section>
  )
}
