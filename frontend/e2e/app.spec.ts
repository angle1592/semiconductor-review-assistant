import { expect, test } from '@playwright/test'

test('production app opens, creates a course, and reaches settings', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: '今天，先把课堂留下来' })).toBeVisible()
  await expect(page.getByLabel('今日复习目标十分钟')).toContainText('10')

  await page.getByRole('link', { name: '课程', exact: true }).click()
  await expect(page).toHaveURL(/\/courses$/)
  await expect(page.getByRole('heading', { name: '课程与课件' })).toBeVisible()

  await page.getByRole('button', { name: '新建课程', exact: true }).click()
  const courseTitle = `E2E 半导体制造 ${Date.now()}`
  await page.getByLabel('课程名称').fill(courseTitle)
  await page.getByLabel('简短说明').fill('Playwright 本地生产链路验证')
  await page.getByRole('button', { name: '保存课程' }).click()

  await expect(page.getByRole('heading', { name: courseTitle })).toBeVisible()
  await expect(page.getByText('Playwright 本地生产链路验证')).toBeVisible()

  await page.getByRole('link', { name: '设置', exact: true }).click()
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByRole('heading', { name: '连接与数据边界' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '当前生成与评分服务' })).toBeVisible()
})

test('deletes an imported document from the course page', async ({ page, request }) => {
  const courseResponse = await request.post('/api/courses', {
    data: { title: `删除测试 ${Date.now()}`, description: '' },
  })
  expect(courseResponse.ok()).toBe(true)
  const course = await courseResponse.json()
  const pdf = Buffer.from(
    'JVBERi0xLjcKJcK1wrYKJSBXcml0dGVuIGJ5IE11UERGIDEuMjkuMAoKMSAwIG9iago8PC9UeXBlL0NhdGFsb2cvUGFnZXMgMiAwIFIvSW5mbzw8L1Byb2R1Y2VyKE11UERGIDEuMjkuMCk+Pj4+CmVuZG9iagoKMiAwIG9iago8PC9UeXBlL1BhZ2VzL0NvdW50IDEvS2lkc1s0IDAgUl0+PgplbmRvYmoKCjMgMCBvYmoKPDwvRm9udDw8L2hlbHYgNSAwIFI+Pj4+CmVuZG9iagoKNCAwIG9iago8PC9UeXBlL1BhZ2UvTWVkaWFCb3hbMCAwIDIwMCAxMjBdL1JvdGF0ZSAwL1Jlc291cmNlcyAzIDAgUi9QYXJlbnQgMiAwIFIvQ29udGVudHNbNiAwIFJdPj4KZW5kb2JqCgo1IDAgb2JqCjw8L1R5cGUvRm9udC9TdWJ0eXBlL1R5cGUxL0Jhc2VGb250L0hlbHZldGljYS9FbmNvZGluZy9XaW5BbnNpRW5jb2Rpbmc+PgplbmRvYmoKCjYgMCBvYmoKPDwvTGVuZ3RoIDY1Pj4Kc3RyZWFtCgpxCkJUCjEgMCAwIDEgMjAgNzAgVG0KL2hlbHYgMTEgVGYgWzw2NDY1NmM2NTc0NjUyMDZkNjU+XVRKCkVUClEKCmVuZHN0cmVhbQplbmRvYmoKCnhyZWYKMCA3CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDA0MiAwMDAwMCBuIAowMDAwMDAwMTIwIDAwMDAwIG4gCjAwMDAwMDAxNzIgMDAwMDAgbiAKMDAwMDAwMDIxMyAwMDAwMCBuIAowMDAwMDAwMzIwIDAwMDAwIG4gCjAwMDAwMDA0MDkgMDAwMDAgbiAKCnRyYWlsZXIKPDwvU2l6ZSA3L1Jvb3QgMSAwIFIvSURbPEMzQTU2QkMzOTlDMkI0QzJCNzREMjgwMTExQzJCRkMzPjxCQUVDNTdGOEY5RDRBODkwNTE0OEM5MTdFQUE0RUE5MT5dPj4Kc3RhcnR4cmVmCjUyMwolJUVPRgo=',
    'base64',
  )
  const uploadResponse = await request.post(`/api/courses/${course.id}/documents`, {
    multipart: {
      file: { name: '待删除课件.pdf', mimeType: 'application/pdf', buffer: pdf },
    },
  })
  expect(uploadResponse.ok()).toBe(true)
  const document = await uploadResponse.json()

  await page.goto(`/courses/${course.id}`)
  await expect(page.getByText('待删除课件.pdf')).toBeVisible()
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('相关课次、题目、答案和复习记录也会一并删除')
    await dialog.accept()
  })
  await page.getByRole('button', { name: '删除课件 待删除课件.pdf' }).click()

  await expect(page.getByText('已删除 待删除课件.pdf。')).toBeVisible()
  await expect(page.locator('.document-card').getByText('待删除课件.pdf')).toHaveCount(0)
  expect((await request.get(`/api/documents/${document.id}`)).status()).toBe(404)
})

test('deletes a course from the course list', async ({ page, request }) => {
  const courseTitle = `待删除课程 ${Date.now()}`
  const courseResponse = await request.post('/api/courses', {
    data: { title: courseTitle, description: '课程删除链路验证' },
  })
  expect(courseResponse.ok()).toBe(true)
  const course = await courseResponse.json()

  await page.goto('/courses')
  await expect(page.getByRole('heading', { name: courseTitle })).toBeVisible()
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('课件、课次、题目、答案和复习记录都会一并删除')
    await dialog.accept()
  })
  await page.getByRole('button', { name: `删除课程 ${courseTitle}` }).click()

  await expect(page.getByText(`已删除课程“${courseTitle}”。`)).toBeVisible()
  await expect(page.getByRole('heading', { name: courseTitle })).toHaveCount(0)
  expect((await request.get(`/api/courses/${course.id}`)).status()).toBe(404)
})

test.describe('mobile layout', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('uses the mobile navigation without horizontal overflow', async ({ page }) => {
    await page.goto('/')

    const navigation = page.getByRole('navigation', { name: '移动端主导航' })
    await expect(navigation).toBeVisible()
    await expect(page.getByRole('link', { name: '移动端：首页' })).toBeVisible()

    await page.getByRole('link', { name: '移动端：课程' }).click()
    await expect(page).toHaveURL(/\/courses$/)
    await expect(page.getByRole('heading', { name: '课程与课件' })).toBeVisible()

    const hasHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    )
    expect(hasHorizontalOverflow).toBe(false)
  })
})
