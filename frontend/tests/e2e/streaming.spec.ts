import { test, expect } from '@playwright/test'

test.describe('Job streaming', () => {
  test('login page loads', async ({ page }) => {
    await page.goto('/login')
    await expect(page.locator('h1')).toContainText('AgentOps Dashboard')
  })

  test('login page has github button', async ({ page }) => {
    await page.goto('/login')
    const button = page.getByRole('button', { name: /sign in with github/i })
    await expect(button).toBeVisible()
  })
})
