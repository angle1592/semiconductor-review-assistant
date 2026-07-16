import { expect, test } from '@playwright/test'


test('reviews source questions and generated modes, then records mastery', async ({ page }) => {
  const attempts: Array<Record<string, unknown>> = []
  const point = {
    id: 9, project_id: 'dynamic', title: '能量守恒', explanation: '总能量保持不变。',
    importance: 'core', source_block_ids: ['block-1'], evidence_quotes: ['总能量保持不变'],
    origin: 'ai', run_id: 4, user_edited: false, position: 0, created_at: '', updated_at: '',
  }
  const sourceQuestion = {
    id: 11, project_id: 'dynamic', document_id: 2, question_text: '什么是能量守恒？',
    answer_text: '封闭系统总能量保持不变。', source_block_ids: ['block-1'],
    evidence_quotes: ['总能量保持不变'], user_edited: true, archived: false,
    run_id: 4, created_at: '', updated_at: '',
  }
  const artifacts = [
    {
      id: 12, project_id: 'dynamic', kind: 'outline', status: 'succeeded',
      payload: { outline: { title: '章节提纲', sections: [{ heading: '核心定律', body: '定义与边界', keypoint_ids: [9] }] } },
      keypoint_ids: [9], source_question_ids: [], cache_status: 'miss', public_error_code: null,
      error_detail: null, created_at: '', updated_at: '',
    },
    {
      id: 13, project_id: 'dynamic', kind: 'flashcard', status: 'succeeded',
      payload: { flashcards: [{ front: '能量会消失吗？', back: '不会，只会转换形式。', keypoint_ids: [9] }] },
      keypoint_ids: [9], source_question_ids: [], cache_status: 'hit', public_error_code: null,
      error_detail: null, created_at: '', updated_at: '',
    },
    {
      id: 14, project_id: 'dynamic', kind: 'ai_new', status: 'succeeded',
      payload: { questions: [{ question: '判断机械能转换。', answer: '总能量守恒。', explanation: '形式改变。', origin: 'ai_new', source_question_ids: [11], keypoint_ids: [9] }] },
      keypoint_ids: [9], source_question_ids: [11], cache_status: 'miss', public_error_code: null,
      error_detail: null, created_at: '', updated_at: '',
    },
  ]

  await page.route(/\/api\/projects\/[^/]+\/keypoints$/, (route) => route.fulfill({ json: [point] }))
  await page.route(/\/api\/projects\/[^/]+\/source-questions$/, (route) => route.fulfill({ json: [sourceQuestion] }))
  await page.route(/\/api\/projects\/[^/]+\/artifacts$/, (route) => route.fulfill({ json: artifacts }))
  await page.route(/\/api\/projects\/[^/]+\/study-attempts$/, async (route) => {
    attempts.push(route.request().postDataJSON())
    await route.fulfill({ status: 201, json: { id: attempts.length } })
  })
  await page.route(/\/api\/projects\/[^/]+\/mastery\/summary$/, (route) => route.fulfill({
    json: { total: 3, by_level: { unrated: 0, learning: 0, familiar: 2, mastered: 1 }, by_type: { source_question: 1, artifact: 2 } },
  }))
  await page.route(/\/api\/projects\/[^/]+\/mastery(?:\?.*)?$/, (route) => route.fulfill({
    json: [
      { id: 1, project_id: 'dynamic', target_type: 'source_question', target_id: 11, level: 'familiar', last_attempt_at: '2026-07-17T00:00:00Z', updated_at: '' },
      { id: 2, project_id: 'dynamic', target_type: 'artifact', target_id: 13, level: 'mastered', last_attempt_at: '2026-07-17T00:00:00Z', updated_at: '' },
    ],
  }))

  await page.goto('/')
  await page.getByRole('link', { name: '项目', exact: true }).click()
  await page.getByRole('button', { name: '新建复习项目' }).click()
  await page.getByLabel('项目名称').fill('发布故事验证')
  await page.getByLabel('什么内容最重要').fill('优先定义与易错原因')
  await page.getByRole('button', { name: '创建项目' }).click()
  await page.getByRole('tab', { name: '复习' }).click()

  await expect(page.getByText('什么是能量守恒？')).toBeVisible()
  const originalRow = page.locator('article.review-library-row').filter({ hasText: '什么是能量守恒？' })
  await originalRow.getByRole('button', { name: '开始作答' }).click()
  await page.getByLabel('我的答案').fill('我先在本机作答')
  await page.getByRole('button', { name: '核对答案' }).click()
  await expect(page.getByText('封闭系统总能量保持不变。')).toBeVisible()
  await page.getByRole('button', { name: '我答对了' }).click()
  await expect(page.getByRole('status')).toContainText('本次复习记录已保存')
  await page.getByRole('button', { name: '返回复习内容' }).click()

  const outlineRow = page.locator('article.review-library-row').filter({ hasText: '章节提纲' })
  await outlineRow.getByRole('button', { name: '开始复习' }).click()
  await expect(page.getByRole('heading', { name: '章节提纲' })).toBeVisible()
  await page.getByRole('button', { name: '已熟悉' }).click()
  await page.getByRole('button', { name: '返回复习内容' }).click()

  const cardRow = page.locator('article.review-library-row').filter({ hasText: '生成内容 #13' })
  await cardRow.getByRole('button', { name: '开始复习' }).click()
  await expect(page.getByText('能量会消失吗？')).toBeVisible()
  await page.getByRole('button', { name: '显示答案' }).click()
  await expect(page.getByText('不会，只会转换形式。')).toBeVisible()
  await page.getByRole('button', { name: '已掌握' }).click()
  await page.getByRole('button', { name: '返回复习内容' }).click()

  const aiRow = page.locator('article.review-library-row').filter({ hasText: '生成内容 #14' })
  await aiRow.getByRole('button', { name: '开始复习' }).click()
  await expect(page.getByText('判断机械能转换。')).toBeVisible()
  await page.getByRole('button', { name: '核对答案' }).click()
  await page.getByRole('button', { name: '还需复习' }).click()
  await expect(page.getByRole('status')).toContainText('本次复习记录已保存')
  expect(attempts).toHaveLength(4)
  expect(JSON.stringify(attempts)).not.toContain('我先在本机作答')

  await page.getByRole('button', { name: '返回复习内容' }).click()
  await page.getByRole('tab', { name: '掌握情况' }).click()
  await expect(page.getByText('只记录你明确给出的判断')).toBeVisible()
  await expect(page.locator('.mastery-summary article').filter({ hasText: '已熟悉' }).getByText('2', { exact: true })).toBeVisible()
  await expect(page.locator('.mastery-summary article').filter({ hasText: '已掌握' }).getByText('1', { exact: true })).toBeVisible()
})
