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
