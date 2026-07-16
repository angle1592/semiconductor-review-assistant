import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import { EmptyState, ErrorState, LoadingState, PageHeading } from '../components/Ui'

export function ReviewPage() {
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.listProjects, retry: false })
  return (
    <section className="page">
      <PageHeading eyebrow="按需复习" title="选择一个项目开始复习" description="只使用你确认过的重点与保留的原题；不安排每日任务，也不会自动开始下一场。" />
      {projects.isPending && <LoadingState label="正在读取可复习项目" />}
      {projects.isError && <ErrorState title="项目暂时无法读取" description="请确认本机服务正在运行，然后重试。" onRetry={() => void projects.refetch()} />}
      {projects.data?.length === 0 && <EmptyState title="还没有复习项目" description="先创建项目、导入资料并确认重点，再从这里开始复习。" />}
      {projects.data && projects.data.length > 0 && <div className="project-index">{projects.data.map((project, index) => <Link key={project.id} className="project-row" to={`/projects/${project.id}`} onClick={() => sessionStorage.setItem(`shiyao:project:${project.id}:active-tab`, '复习')}><span className="project-order">{String(index + 1).padStart(2, '0')}</span><span><strong>{project.name}</strong><small>{project.description || '打开项目的复习内容库'}</small></span><time dateTime={project.updated_at}>{new Date(project.updated_at).toLocaleDateString('zh-CN')}</time><ArrowUpRight aria-hidden="true" /></Link>)}</div>}
    </section>
  )
}
