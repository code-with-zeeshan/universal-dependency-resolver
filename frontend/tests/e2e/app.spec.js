// @ts-check
const { test, expect } = require('@playwright/test')

test.describe('Universal Dependency Resolver E2E', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('renders the app title', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('Universal Dependency Resolver')
  })

  test('shows package input form', async ({ page }) => {
    await expect(page.locator('input[placeholder*="Package name"]')).toBeVisible()
    await expect(page.locator('select')).toBeVisible()
    await expect(page.locator('button:has-text("Add Package")')).toBeVisible()
  })

  test('shows resolve dependencies button', async ({ page }) => {
    const resolveBtn = page.locator('button:has-text("Resolve Dependencies")')
    await expect(resolveBtn).toBeVisible()
    await expect(resolveBtn).toBeDisabled()
  })

  test('adds a package to the list', async ({ page }) => {
    await page.fill('input[placeholder*="Package name"]', 'flask')
    await page.click('button:has-text("Add Package")')

    await expect(page.locator('text=flask')).toBeVisible()
  })

  test('removes a package from the list', async ({ page }) => {
    await page.fill('input[placeholder*="Package name"]', 'flask')
    await page.click('button:has-text("Add Package")')
    await expect(page.locator('text=flask')).toBeVisible()

    await page.click('button:has-text("Remove")')
    await expect(page.locator('text=flask')).not.toBeVisible()
  })

  test('adds multiple packages and resolves', async ({ page }) => {
    await page.fill('input[placeholder*="Package name"]', 'flask')
    await page.click('button:has-text("Add Package")')

    await page.fill('input[placeholder*="Package name"]', 'requests')
    await page.click('button:has-text("Add Package")')

    const resolveBtn = page.locator('button:has-text("Resolve Dependencies")')
    await expect(resolveBtn).not.toBeDisabled()
  })

  test('selects ecosystem before adding', async ({ page }) => {
    await page.selectOption('select', 'pypi')

    await page.fill('input[placeholder*="Package name"]', 'flask')
    await page.click('button:has-text("Add Package")')

    await expect(page.locator('text=pypi')).toBeVisible()
  })

  test('clears input after adding a package', async ({ page }) => {
    await page.fill('input[placeholder*="Package name"]', 'flask')
    await page.click('button:has-text("Add Package")')

    await expect(page.locator('input[placeholder*="Package name"]')).toHaveValue('')
  })

  test('shows error when adding empty package', async ({ page }) => {
    await page.click('button:has-text("Add Package")')
    await expect(page.locator('text=Package name is required')).toBeVisible()
  })

  test('loading state while resolving', async ({ page, context }) => {
    // Mock the API to delay resolution
    await page.route('**/api/v1/packages/resolve', async (route) => {
      await new Promise(r => setTimeout(r, 500))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          resolved_packages: { flask: { version: '2.3.3', ecosystem: 'pypi' } },
        }),
      })
    })

    await page.fill('input[placeholder*="Package name"]', 'flask')
    await page.click('button:has-text("Add Package")')

    const resolveBtn = page.locator('button:has-text("Resolve Dependencies")')
    await resolveBtn.click()

    await expect(page.locator('button:has-text("Resolving...")')).toBeVisible()
  })

  test('shows resolved dependencies', async ({ page }) => {
    await page.route('**/api/v1/packages/resolve', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          resolved_packages: {
            flask: { version: '2.3.3', ecosystem: 'pypi', dependencies: {} },
          },
          warnings: [],
        }),
      })
    })

    await page.route('**/api/v1/packages/export-formats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          formats: ['requirements.txt', 'package.json'],
        }),
      })
    })

    await page.route('**/api/v1/packages/export', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ content: 'flask==2.3.3' }),
      })
    })

    await page.fill('input[placeholder*="Package name"]', 'flask')
    await page.click('button:has-text("Add Package")')

    await page.click('button:has-text("Resolve Dependencies")')

    await expect(page.locator('text=Resolved Dependencies')).toBeVisible()
    await expect(page.locator('text=flask')).toBeVisible()
    await expect(page.locator('text=requirements.txt')).toBeVisible()
  })

  test('opens export preview modal', async ({ page }) => {
    await page.route('**/api/v1/packages/resolve', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          resolved_packages: { flask: { version: '2.3.3', ecosystem: 'pypi' } },
        }),
      })
    })
    await page.route('**/api/v1/packages/export-formats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ formats: ['requirements.txt'] }),
      })
    })
    await page.route('**/api/v1/packages/export', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ content: 'flask==2.3.3' }),
      })
    })

    await page.fill('input[placeholder*="Package name"]', 'flask')
    await page.click('button:has-text("Add Package")')
    await page.click('button:has-text("Resolve Dependencies")')

    await page.waitForSelector('text=requirements.txt')
    await page.click('text=requirements.txt')

    await expect(page.locator('text=Copy to Clipboard')).toBeVisible()
    await expect(page.locator('text=Download')).toBeVisible()
    await expect(page.locator('text=flask==2.3.3')).toBeVisible()
  })

  test('handles API errors gracefully', async ({ page }) => {
    await page.route('**/api/v1/packages/resolve', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: { message: 'Resolution failed', type: 'internal_error' },
        }),
      })
    })

    await page.fill('input[placeholder*="Package name"]', 'flask')
    await page.click('button:has-text("Add Package")')
    await page.click('button:has-text("Resolve Dependencies")')

    await expect(page.locator('text=Failed to resolve dependencies')).toBeVisible()
  })

  test('shows health check status via API', async ({ page, context }) => {
    const response = await page.request.get('/api/v1/health')
    expect(response.status()).toBe(200)
    const data = await response.json()
    expect(data).toHaveProperty('status')
    expect(data).toHaveProperty('checks')
  })

  test('supports keyboard shortcut to add package', async ({ page }) => {
    await page.fill('input[placeholder*="Package name"]', 'flask')
    await page.press('input[placeholder*="Package name"]', 'Enter')

    await expect(page.locator('text=flask')).toBeVisible()
  })

  test('package list shows ecosystem tag', async ({ page }) => {
    await page.selectOption('select', 'npm')
    await page.fill('input[placeholder*="Package name"]', 'express')
    await page.click('button:has-text("Add Package")')

    await expect(page.locator('text=express')).toBeVisible()
    await expect(page.locator('text=npm')).toBeVisible()
  })

  test('resolve button is disabled when no packages', async ({ page }) => {
    const resolveBtn = page.locator('button:has-text("Resolve Dependencies")')
    await expect(resolveBtn).toBeDisabled()
  })

  test('clears error after successful retry', async ({ page }) => {
    let callCount = 0
    await page.route('**/api/v1/packages/resolve', async (route) => {
      callCount++
      if (callCount === 1) {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            error: { message: 'Resolution failed', type: 'internal_error' },
          }),
        })
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'success',
            resolved_packages: { flask: { version: '2.3.3', ecosystem: 'pypi' } },
          }),
        })
      }
    })

    await page.fill('input[placeholder*="Package name"]', 'flask')
    await page.click('button:has-text("Add Package")')

    // First attempt fails
    await page.click('button:has-text("Resolve Dependencies")')
    await expect(page.locator('text=Failed to resolve dependencies')).toBeVisible()

    // Second attempt succeeds
    await page.click('button:has-text("Resolve Dependencies")')
    await expect(page.locator('text=Resolved Dependencies')).toBeVisible()
  })
})
