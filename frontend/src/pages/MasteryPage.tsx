import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { api } from '../api/client'
import { EmptyState, ErrorState, LoadingState, PageHeading } from '../components/Ui'

export function MasteryPage() {
  const projects = useQuery({ queryKey: ['projects'], queryFn: api.listProjects, retry: false })
  return (
    <section className="page">
      <PageHeading eyebrow="掌握情况" title="选择项目查看真实记录" description="掌握程度只来自你的主动复习与手动评级，不推算考试日、到期日或连续学习。" />
      {projects.isPending && <LoadingState label="正在读取项目" />}
      {projects.isError && <ErrorState title="项目暂时无法读取" description="请确认本机服务正在运行，然后重试。" onRetry={() => void projects.refetch()} />}
      {projects.data?.length === 0 && <EmptyState title="还没有掌握记录" description="创建项目并完成一次复习后，这里才会出现真实数据。" />}
      {projects.data && projects.data.length > 0 && <div className="project-index">{projects.data.map((project, index) => <Link key={project.id} className="project-row" to={`/projects/${project.id}`} onClick={() => sessionStorage.setItem(`shiyao:project:${project.id}:active-tab`, '掌握情况')}><span className="project-order">{String(index + 1).padStart(2, '0')}</span><span><strong>{project.name}</strong><small>查看掌握程度与复习记录</small></span><time dateTime={project.updated_at}>{new Date(project.updated_at).toLocaleDateString('zh-CN')}</time><ArrowUpRight aria-hidden="true" /></Link>)}</div>}
    </section>
  )
}
