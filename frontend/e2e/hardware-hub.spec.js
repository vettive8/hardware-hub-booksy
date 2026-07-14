import { expect, test } from '@playwright/test'

const admin = { email: 'admin@booksy.com', password: 'Admin123!' }
const qaUser = { name: 'Browser QA User', email: 'browser.qa@booksy.com', password: 'Browser123!' }

async function login(page, credentials) {
  await page.getByLabel('Work email').fill(credentials.email)
  await page.getByLabel('Password').fill(credentials.password)
  await page.getByRole('button', { name: /Sign in/ }).click()
  await expect(page.getByText('Hardware inventory')).toBeVisible()
}

test.describe.serial('Hardware Hub visible feature audit', () => {
  test.beforeEach(async ({ page }) => {
    page.browserErrors = []
    page.on('console', message => {
      if (message.type() === 'error') page.browserErrors.push(`console: ${message.text()}`)
    })
    page.on('pageerror', error => page.browserErrors.push(`page: ${error.message}`))
  })

  test.afterEach(async ({ page }) => {
    expect(page.browserErrors, 'browser console/page errors').toEqual([])
  })

  test('admin can inspect, rent, return, audit, and manage the fleet', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Sign in to your account' })).toBeVisible()
    await login(page, admin)

    const search = page.getByPlaceholder(/Search hardware or brand/)
    await search.fill('Apple iPhone 13 Pro Max')
    let iphone = page.locator('tbody tr').filter({ hasText: 'Apple iPhone 13 Pro Max' })
    await expect(iphone).toHaveCount(1)
    await iphone.getByRole('button', { name: 'Rent' }).click()
    await expect(page.getByText('Apple iPhone 13 Pro Max rented')).toBeVisible()
    await expect(iphone.getByText('In Use')).toBeVisible()
    await iphone.getByRole('button', { name: 'Return' }).click()
    await expect(page.getByText('Apple iPhone 13 Pro Max returned')).toBeVisible()
    await expect(iphone.getByText('Available')).toBeVisible()

    await search.fill('')
    await page.getByLabel('Filter by status').selectOption('Repair')
    await expect(page.getByText('Razer Basilisk V2')).toBeVisible()
    await expect(page.getByText('Apple iPhone 13 Pro Max')).toBeHidden()
    await page.getByLabel('Filter by status').selectOption('All')
    await page.getByLabel('Sort hardware').selectOption('brand')

    await page.getByRole('button', { name: /AI inventory audit/ }).click()
    await expect(page.getByText('Deterministic safety floor')).toBeVisible()
    await expect(page.locator('.audit-summary').getByText('9', { exact: true })).toBeVisible()

    await page.getByRole('button', { name: /Admin panel/ }).click()
    const hardwareForm = page.locator('form').filter({ hasText: 'Add hardware' })
    await hardwareForm.getByLabel('Device name').fill('Browser QA Laptop')
    await hardwareForm.getByLabel('Brand').fill('Framework')
    await hardwareForm.getByLabel('Purchase date').fill('2026-01-15')
    await hardwareForm.getByLabel('Notes').fill('Created by isolated Playwright test')
    await hardwareForm.getByRole('button', { name: /Add hardware/ }).click()
    await expect(page.getByText('Hardware added')).toBeVisible()

    let qaRow = page.locator('.manage-row').filter({ hasText: 'Browser QA Laptop' })
    await expect(qaRow).toHaveCount(1)
    await qaRow.getByRole('button', { name: 'Send to repair' }).click()
    await expect(page.getByText('Marked for repair')).toBeVisible()
    qaRow = page.locator('.manage-row').filter({ hasText: 'Browser QA Laptop' })
    await qaRow.getByRole('button', { name: 'Complete repair' }).click()
    await expect(page.getByText('Repair completed')).toBeVisible()

    const accountForm = page.locator('form').filter({ hasText: 'Create account' })
    await accountForm.getByLabel('Full name').fill(qaUser.name)
    await accountForm.getByLabel('Work email').fill(qaUser.email)
    await accountForm.getByLabel('Password').fill(qaUser.password)
    await accountForm.getByRole('button', { name: /Create account/ }).click()
    await expect(page.getByText('Account created')).toBeVisible()
    await expect(page.getByText(qaUser.email)).toBeVisible()

    qaRow = page.locator('.manage-row').filter({ hasText: 'Browser QA Laptop' })
    await expect(qaRow.getByRole('button', { name: 'Delete' })).toBeEnabled()
  })

  test('a newly admin-created member can rent and return but cannot see admin controls', async ({ page }) => {
    await page.goto('/')
    await login(page, qaUser)
    await expect(page.getByRole('button', { name: /Admin panel/ })).toHaveCount(0)

    const search = page.getByPlaceholder(/Search hardware or brand/)
    await search.fill('Apple iPhone 13 Pro Max')
    const iphone = page.locator('tbody tr').filter({ hasText: 'Apple iPhone 13 Pro Max' })
    await iphone.getByRole('button', { name: 'Rent' }).click()
    await expect(page.getByText('Apple iPhone 13 Pro Max rented')).toBeVisible()
    await page.getByRole('button', { name: /My rentals/ }).click()
    await expect(page.getByText('Rented to browser.qa@booksy.com')).toBeVisible()
    await page.getByRole('button', { name: 'Return hardware' }).click()
    await expect(page.getByText('Apple iPhone 13 Pro Max returned')).toBeVisible()
    await expect(page.getByText('No active rentals')).toBeVisible()
  })

  test('mobile login and navigation remain usable', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')
    await expect(page.locator('.login-story')).toBeHidden()
    await expect(page.locator('.mobile-brand')).toBeVisible()
    await login(page, admin)
    await expect(page.locator('.sidebar')).toBeVisible()
    await expect(page.getByRole('button', { name: /My rentals/ })).toBeVisible()
  })

  test('interactive reports render and their controls work', async ({ page }) => {
    const reportBase = process.env.REPORT_BASE_URL || 'http://127.0.0.1:8765'
    await page.goto(reportBase + '/build-report.html')
    await expect(page.getByRole('heading', { name: /How the build/ })).toBeVisible()
    await page.getByRole('button', { name: 'Gaps' }).click()
    await expect(page.getByText('Live demo URL')).toBeVisible()
    await expect(page.getByText('Admin command center')).toBeHidden()
    await page.getByPlaceholder(/Search method/).fill('/api/audit')
    await expect(page.locator('#endpoint-body tr')).toHaveCount(1)
    await page.getByRole('button', { name: 'Differences' }).click()
    await expect(page.getByText('Gemini semantic search + sqlite-vec')).toBeVisible()
    await page.locator('#readiness-list input').first().check()
    await expect(page.getByText('1 of 6 follow-ups marked complete')).toBeVisible()

    await page.goto(reportBase + '/code-review-report.html')
    await expect(page.getByRole('heading', { name: /Review the evidence/ })).toBeVisible()
    await page.getByRole('button', { name: 'P0' }).click()
    await expect(page.getByText('Quarantine LLM findings per record')).toBeVisible()
    await expect(page.getByText('Define the SQLite operating envelope')).toBeHidden()
    await page.getByLabel('Decision for Per-finding LLM quarantine + counter + UI + mixed-response test').selectOption('approve')
    await expect(page.getByText('1 of 11 decisions recorded')).toBeVisible()
    await page.getByLabel('Claude Fable review').fill('Independent review draft')
    await expect(page.getByText('Saved locally')).toBeVisible()
    await page.reload()
    await expect(page.getByLabel('Claude Fable review')).toHaveValue('Independent review draft')
    await page.getByRole('button', { name: 'Copy prompt' }).click()
    await expect(page.locator('#prompt-status')).toHaveText('Copied')

    await page.goto(reportBase + '/technology-report.html')
    await expect(page.getByRole('heading', { name: /One API/ })).toBeVisible()
    await expect(page.locator('#catalog-message')).toContainText('Live catalog loaded')
    await page.getByPlaceholder(/Search name or model ID/).fill('claude-haiku-4.5')
    await expect(page.locator('#models tr')).toHaveCount(1)
  })

  test('admin can delete a disposable hardware record', async ({ page }) => {
    test.skip(process.env.E2E_ALLOW_DELETE !== '1', 'Requires explicit approval for browser-driven deletion')

    await page.goto('/')
    await login(page, admin)
    await page.getByRole('button', { name: /Admin panel/ }).click()

    const hardwareForm = page.locator('form').filter({ hasText: 'Add hardware' })
    await hardwareForm.getByLabel('Device name').fill('Browser QA Delete Target')
    await hardwareForm.getByLabel('Brand').fill('Framework')
    await hardwareForm.getByRole('button', { name: /Add hardware/ }).click()
    await expect(page.getByText('Hardware added')).toBeVisible()

    const targetRow = page.locator('.manage-row').filter({ hasText: 'Browser QA Delete Target' })
    await expect(targetRow).toHaveCount(1)
    page.once('dialog', dialog => dialog.accept())
    await targetRow.getByRole('button', { name: 'Delete' }).click()

    await expect(page.getByText('Hardware deleted')).toBeVisible()
    await expect(page.getByText('Browser QA Delete Target')).toBeHidden()
  })
})
