import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AppRoutes } from './App'


describe('拾要 application shell', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows the general-review identity and primary navigation', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }))

    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRoutes />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: '拾要首页' })).toBeInTheDocument()
    expect(screen.getByText('从资料中拾取真正重要的内容')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '项目' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '开始复习' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '掌握情况' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '设置' })).toBeInTheDocument()
  })

  it('renders the on-demand project review entry', () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => [] }))
    render(
      <MemoryRouter initialEntries={['/review']}>
        <AppRoutes />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: '选择一个项目开始复习' })).toBeInTheDocument()
    expect(screen.queryByText('复习队列尚未开放')).not.toBeInTheDocument()
  })
})
