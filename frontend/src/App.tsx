import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Archive, Brain, ListChecks, Settings } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'

import { DashboardPage } from './pages/DashboardPage'
import { MasteryPage } from './pages/MasteryPage'
import { ProjectDetailPage } from './pages/ProjectDetailPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { ReviewPage } from './pages/ReviewPage'
import { SettingsPage } from './pages/SettingsPage'
import { SetupPage } from './pages/SetupPage'

const navigation = [
  { to: '/projects', label: '项目', icon: Archive },
  { to: '/review', label: '开始复习', icon: ListChecks },
  { to: '/mastery', label: '掌握情况', icon: Brain },
  { to: '/settings', label: '设置', icon: Settings },
]

function AppShell() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/" className="brand" aria-label="拾要首页">
          <span className="brand-bookmark" aria-hidden="true"><b>拾</b><b>要</b></span>
          <span className="brand-copy">
            <strong>拾要</strong>
            <small>从资料中拾取真正重要的内容</small>
          </span>
        </NavLink>
        <nav className="primary-nav" aria-label="主导航">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => isActive ? 'is-active' : ''}>
              <Icon aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <p className="sidebar-note"><span>本机保存</span> · 第三方 AI</p>
      </aside>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/mastery" element={<MasteryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/setup" element={<SetupPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export function AppRoutes() {
  const [queryClient] = useState(() => new QueryClient({
    defaultOptions: {
      queries: { retry: 1, staleTime: 15_000 },
    },
  }))
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  )
}
