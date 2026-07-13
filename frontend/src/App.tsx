import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BarChart3, BookOpen, CircuitBoard, Home, PlayCircle, Settings2, type LucideIcon } from 'lucide-react'
import { NavLink, Route, Routes } from 'react-router-dom'

import { CourseDetailPage } from './pages/CourseDetailPage'
import { CoursesPage } from './pages/CoursesPage'
import { DashboardPage } from './pages/DashboardPage'
import { LessonPage } from './pages/LessonPage'
import { ProgressPage } from './pages/ProgressPage'
import { ReviewPage } from './pages/ReviewPage'
import { SettingsPage } from './pages/SettingsPage'
import { SetupPage } from './pages/SetupPage'

const navigation: ReadonlyArray<{ to: string; label: string; icon: LucideIcon; end?: boolean }> = [
  { to: '/', label: '首页', icon: Home, end: true },
  { to: '/courses', label: '课程', icon: BookOpen },
  { to: '/review', label: '开始复习', icon: PlayCircle },
  { to: '/progress', label: '掌握进度', icon: BarChart3 },
  { to: '/settings', label: '设置', icon: Settings2 },
]

function AppShell() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink className="brand" to="/" aria-label="半导体复习台首页">
          <span className="brand-mark"><CircuitBoard aria-hidden="true" /></span>
          <span><strong>回片</strong><small>半导体复习台</small></span>
        </NavLink>
        <nav className="primary-nav" aria-label="主导航">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink className={({ isActive }) => isActive ? 'is-active' : ''} to={to} end={end} key={to}>
              <Icon aria-hidden="true" /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="local-dot" aria-hidden="true" />
          <div><strong>本机数据</strong><small>唯一权威来源</small></div>
        </div>
      </aside>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/courses" element={<CoursesPage />} />
          <Route path="/courses/:id" element={<CourseDetailPage />} />
          <Route path="/lessons/new" element={<LessonPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/progress" element={<ProgressPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route path="*" element={<DashboardPage />} />
        </Routes>
      </main>
      <nav className="bottom-nav" aria-label="移动端主导航">
        {navigation.map(({ to, label, icon: Icon, end }) => (
          <NavLink aria-label={`移动端：${label}`} className={({ isActive }) => isActive ? 'is-active' : ''} to={to} end={end} key={to}>
            <Icon aria-hidden="true" /><span>{label === '开始复习' ? '复习' : label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

export function AppRoutes() {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, staleTime: 15_000 },
          mutations: { retry: false },
        },
      }),
  )
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  )
}
