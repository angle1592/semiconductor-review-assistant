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
