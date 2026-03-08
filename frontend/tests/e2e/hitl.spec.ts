import { test, expect } from '@playwright/test'

test.describe('HITL flows', () => {
  test('login page accessible', async ({ page }) => {
    await page.goto('/login')
    await expect(page).toHaveTitle(/AgentOps Dashboard/)
  })
})
