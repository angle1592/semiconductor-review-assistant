import { expect, test } from '@playwright/test'

test('creates and opens an empty review project', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '把散落的资料，整理成可复习的重点' })).toBeVisible()

  await page.getByRole('link', { name: '项目', exact: true }).click()
  await page.getByRole('button', { name: '新建复习项目' }).click()
  await page.getByLabel('项目名称').fill('资格考试总复习')
  await page.getByLabel('项目说明').fill('Playwright 本地生产链路验证')
  await page.getByLabel('什么内容最重要').fill('优先定义、公式与易错点')
  await page.getByRole('button', { name: '创建项目' }).click()

  await expect(page.getByRole('heading', { name: '资格考试总复习' })).toBeVisible()
  await expect(page.getByRole('tab', { name: '概览' })).toBeVisible()
  await expect(page.getByRole('tab', { name: '资料' })).toBeVisible()
})

test('completes first-run provider setup with manual model fallback', async ({ page }) => {
  const provider = {
    id: 'p1', name: '主力服务', protocol: 'openai_compatible', base_url: 'https://relay.test/v1',
    enabled: false, is_default: false, credential_generation: 1, api_key_configured: true,
    models_fetched_at: null, created_at: '2026-07-16T12:00:00Z', updated_at: '2026-07-16T12:00:00Z',
  }
  const model = {
    id: 'm1', provider_id: 'p1', model_id: 'manual-review-model', display_name: 'manual-review-model',
    text_status: 'untested', structured_status: 'untested', vision_status: 'untested',
    prompt_cache_status: 'unsupported', safe_error_code: null, validated_at: null,
  }

  await page.route(/\/api\/providers(?:\/.*)?(?:\?.*)?$/, async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/providers' && request.method() === 'POST') {
      await route.fulfill({ status: 201, json: provider })
    } else if (path === '/api/providers/p1/models:refresh') {
      await route.fulfill({ status: 404, json: { code: 'upstream_endpoint_not_found', message: '服务商没有提供模型列表接口。' } })
    } else if (path === '/api/providers/p1/models' && request.method() === 'POST') {
      await route.fulfill({ status: 201, json: model })
    } else if (path === '/api/providers/p1/models/m1:probe') {
      await route.fulfill({ status: 200, json: { ...model, text_status: 'passed', structured_status: 'passed', vision_status: 'passed' } })
    } else if (path === '/api/providers/p1:enable') {
      await route.fulfill({ status: 200, json: { ...provider, enabled: true, is_default: true } })
    } else {
      await route.abort('failed')
    }
  })
  await page.route('**/api/system/setup-complete', (route) => route.fulfill({ status: 204 }))

  await page.goto('/setup')
  await page.getByLabel('API 地址').fill('relay.test')
  await expect(page.getByText('请输入不含查询参数和账号信息的 HTTP(S) 地址。')).toBeVisible()
  await expect(page.getByRole('button', { name: '获取模型' })).toBeDisabled()

  await page.getByLabel('API 地址').fill('https://relay.test')
  await page.getByLabel('API Key').fill('private-test-key')
  await page.getByRole('button', { name: '获取模型' }).click()
  await expect(page.getByText('核对 API 地址，或在下方手动填写模型。')).toBeVisible()

  await page.getByLabel('手动模型 ID').fill('manual-review-model')
  await page.getByRole('button', { name: '添加模型' }).click()
  await expect(page.getByRole('button', { name: '启用此服务' })).toBeDisabled()
  await expect(page.getByText('文本、结构化输出和视觉三项能力通过后，才可启用此服务。')).toBeVisible()

  await page.getByRole('button', { name: '校验模型能力' }).click()
  await expect(page.getByText('视觉：通过')).toBeVisible()
  await expect(page.getByRole('button', { name: '启用此服务' })).toBeEnabled()
  await page.getByRole('button', { name: '启用此服务' }).click()

  await expect(page.getByRole('heading', { name: '复习项目' })).toBeVisible()
  await expect(page.getByLabel('API Key')).toHaveCount(0)
})
