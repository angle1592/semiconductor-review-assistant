import { expect, test } from '@playwright/test'


test('imports material, restores analysis progress and keeps AI output pending', async ({ page }) => {
  let uploaded = false
  let providerReady = false
  let runCreated = false
  let afterReload = false
  let confirmed = false
  const source = {
    id: 1, project_id: 'project', display_name: '能带复习.md', extension: '.md', media_type: 'text/markdown',
    byte_size: 1200, sha256: 'fixture', source_kind: 'mixed', parse_status: 'ready', parser_version: '1',
    page_count: 12, warnings: [], created_at: '2026-07-16T12:00:00Z', updated_at: '2026-07-16T12:00:00Z',
  }
  const candidate = {
    id: 7, project_id: 'project', run_id: 44, batch_id: 1, title: '带隙定义',
    explanation: '价带顶与导带底之间的能量差。', importance: 'core', source_block_ids: ['block-a'],
    evidence_quotes: ['带隙是能量差'], rationale: '基础定义', status: 'pending', user_edited: false,
    confirmed_keypoint_id: null, created_at: '', updated_at: '',
  }

  await page.route(/\/api\/projects\/[^/]+\/sources$/, async (route) => {
    if (route.request().method() === 'POST') {
      uploaded = true
      await route.fulfill({ status: 201, json: { source_id: 1, parse_status: 'ready', page_count: 12, block_count: 1, cache: 'miss', warnings: [] } })
    } else {
      await route.fulfill({ json: { items: uploaded ? [source] : [], total: uploaded ? 1 : 0, offset: 0, limit: 20 } })
    }
  })
  await page.route('**/api/sources/1/blocks', (route) => route.fulfill({ json: { items: [{ id: 'block-a', ordinal: 0, locator: 'heading:1', kind: 'paragraph', text: '带隙是价带顶与导带底之间的能量差。', page_number: 1, heading_path: ['能带理论'], preview_path: null }], total: 1, offset: 0, limit: 100 } }))
  await page.route('**/api/providers', (route) => route.fulfill({ json: providerReady ? [{ id: 'p1', name: '主力服务', protocol: 'openai_compatible', base_url: 'https://provider.test/v1', enabled: true, is_default: true, credential_generation: 1, api_key_configured: true, models_fetched_at: null, created_at: '', updated_at: '' }] : [] }))
  await page.route('**/api/providers/p1/models', (route) => route.fulfill({ json: [{ id: 'm1', provider_id: 'p1', model_id: 'review-model', display_name: 'Review Model', text_status: 'passed', structured_status: 'passed', vision_status: 'passed', prompt_cache_status: 'passed', safe_error_code: null, validated_at: '' }] }))
  await page.route(/\/analysis-range:estimate$/, (route) => route.fulfill({ json: { source_count: 1, block_count: 620, page_count: 88, character_count: 42000, image_count: 8, exceeds_warning: true } }))
  await page.route(/\/api\/projects\/[^/]+\/analysis-runs$/, async (route) => {
    runCreated = true
    await route.fulfill({ status: 202, json: { run_id: 44, job_id: 81, status: 'queued', batch_count: 2, message: '已加入分析队列，可离开此页面；任务会在后台继续。' } })
  })
  await page.route('**/api/analysis-runs/44', (route) => route.fulfill({ json: afterReload ? { id: 44, project_id: 'project', status: 'succeeded', total_batches: 2, completed_batches: 2, failed_batches: 0, cancellation_requested: false, public_error_code: null, error_detail: null, batches: [{ id: 1, ordinal: 0, status: 'succeeded', attempts: 1, cache_status: 'miss', public_error_code: null, error_detail: null }, { id: 2, ordinal: 1, status: 'succeeded', attempts: 1, cache_status: 'hit', public_error_code: null, error_detail: null }] } : { id: 44, project_id: 'project', status: 'queued', total_batches: 2, completed_batches: 0, failed_batches: 0, cancellation_requested: false, public_error_code: null, error_detail: null, batches: [{ id: 1, ordinal: 0, status: 'queued', attempts: 0, cache_status: null, public_error_code: null, error_detail: null }] } }))
  await page.route('**/api/analysis-runs/44/candidates', (route) => route.fulfill({ json: confirmed ? [{ ...candidate, status: 'confirmed', confirmed_keypoint_id: 9 }] : [candidate] }))
  await page.route(/\/api\/projects\/[^/]+\/keypoints$/, (route) => route.fulfill({ json: confirmed ? [{ id: 9, project_id: 'project', title: candidate.title, explanation: candidate.explanation, importance: 'core', source_block_ids: ['block-a'], evidence_quotes: candidate.evidence_quotes, origin: 'ai', run_id: 44, user_edited: false, position: 0, created_at: '', updated_at: '' }] : [] }))
  await page.route('**/api/keypoint-candidates:bulk-action', async (route) => { confirmed = true; await route.fulfill({ json: { confirmed: 1, rejected: 0, keypoint_ids: [9] } }) })

  await page.goto('/')
  await page.getByRole('link', { name: '项目', exact: true }).click()
  await page.getByRole('button', { name: '新建复习项目' }).click()
  await page.getByLabel('项目名称').fill('材料分析端到端')
  await page.getByLabel('什么内容最重要').fill('优先定义与易错点')
  await page.getByRole('button', { name: '创建项目' }).click()

  await page.getByRole('tab', { name: '资料' }).click()
  await expect(page.getByText(/支持 PDF、Word、PPT、TXT 和 Markdown/)).toBeVisible()
  await page.getByLabel('选择资料文件').setInputFiles({ name: '危险格式.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('MZ') })
  await expect(page.getByRole('alert')).toContainText('仅支持 PDF、Word、PPT、TXT 和 Markdown')
  await expect(page.getByRole('button', { name: '重新选择文件' })).toBeVisible()
  await page.getByLabel('选择资料文件').setInputFiles({ name: '能带复习.md', mimeType: 'text/markdown', buffer: Buffer.from('# 能带复习') })
  await expect(page.getByText('能带复习.md', { exact: true })).toBeVisible()

  await page.getByRole('tab', { name: '分析' }).click()
  await expect(page.getByText('没有已启用的第三方服务商')).toBeVisible()
  await expect(page.getByRole('link', { name: '管理接入' })).toBeVisible()

  providerReady = true
  await page.reload()
  await expect(page.getByRole('tab', { name: '分析' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText('88 页 · 620 个内容块')).toBeVisible()
  const start = page.getByRole('button', { name: '开始后台分析' })
  await expect(start).toBeDisabled()
  await page.getByLabel(/我确认分析全部资料/).check()
  await start.click()
  await expect(page.getByText('等待 worker 接手')).toBeVisible()
  expect(runCreated).toBeTruthy()

  afterReload = true
  await page.reload()
  await expect(page.getByRole('tab', { name: '分析' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText('分析完成，等待你确认')).toBeVisible()
  await expect(page.getByText('100%')).toBeVisible()

  await page.getByRole('tab', { name: '重点' }).click()
  await expect(page.getByText('待确认')).toBeVisible()
  await expect(page.getByText('不会自动进入正式复习内容')).toBeVisible()
  await page.getByRole('button', { name: '来源 1' }).click()
  await expect(page.getByRole('tab', { name: '资料' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('.block-selector input')).toBeChecked()

  await page.getByRole('tab', { name: '重点' }).click()
  await page.getByLabel('选择候选 带隙定义').check()
  await page.getByRole('button', { name: '确认所选' }).click()
  await expect(page.getByRole('status')).toContainText('已确认 1 条')
})
