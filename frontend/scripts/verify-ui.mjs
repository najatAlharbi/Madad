/** Drive the real UI in a headless browser and report what rendered.
 *
 * This is a verification harness, not a test suite: it walks the whole
 * warehouse journey plus the authority pages, screenshots each screen, and
 * fails loudly on any console error, failed request, or missing expected text.
 *
 * Usage (both servers must be running):
 *   node scripts/verify-ui.mjs
 */
import { mkdirSync } from 'node:fs'
import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'
const OUT = 'verify-shots'
const problems = []
let step = 0

async function shot(page, name) {
  step += 1
  const file = `${OUT}/${String(step).padStart(2, '0')}-${name}.png`
  await page.screenshot({ path: file, fullPage: true })
  return file
}

async function expectText(page, needle, where) {
  const body = await page.textContent('body')
  if (!body?.includes(needle)) {
    problems.push(`[${where}] expected to find "${needle}"`)
    return false
  }
  return true
}

const run = async () => {
  mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch()
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await context.newPage()

  page.on('console', (msg) => {
    const text = msg.text()
    // 409 and 410 are design signals ("no forecast yet", "session gone"),
    // not faults — the browser logs the failed fetch regardless.
    const byDesign = /status of (409|410)/.test(text)
    if (msg.type() === 'error' && !byDesign) problems.push(`console error: ${text.slice(0, 200)}`)
  })
  page.on('requestfailed', (req) => {
    problems.push(`request failed: ${req.method()} ${req.url()} — ${req.failure()?.errorText}`)
  })
  page.on('response', (res) => {
    if (res.url().includes('/api/') && res.status() >= 400 && res.status() !== 409 && res.status() !== 410) {
      problems.push(`api ${res.status()} on ${res.url()}`)
    }
  })

  // 1. Landing (skip the loading animation)
  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Skip' }).click().catch(() => {})
  await page.waitForTimeout(400)
  await expectText(page, 'Every connection', 'landing')
  await expectText(page, 'Hospital Warehouse Manager', 'landing')
  console.log('landing            ->', await shot(page, 'landing'))

  // 2. Pick the warehouse workspace
  await page.getByRole('button', { name: /Hospital Warehouse Manager/ }).click()
  await page.waitForURL('**/warehouse')
  await page.waitForTimeout(700)
  await expectText(page, 'My Warehouse', 'warehouse home (empty)')
  console.log('warehouse (empty)  ->', await shot(page, 'warehouse-empty'))

  // 3. Upload page -> load the demo facility
  await page.getByRole('link', { name: 'Upload Data' }).click()
  await page.waitForURL('**/warehouse/upload')
  await expectText(page, 'Add your month', 'upload step 1')
  console.log('upload step 1      ->', await shot(page, 'upload-step1'))

  await page.getByRole('button', { name: 'Load demo facility' }).click()
  await page.waitForSelector('text=Run the models', { timeout: 30000 })
  await expectText(page, 'Sample data', 'upload step 3 demo badge')
  console.log('upload step 3      ->', await shot(page, 'upload-step3'))

  // 4. Run the real models
  await page.getByRole('button', { name: 'Run forecast' }).click()
  await page.waitForSelector('text=Forecast ready', { timeout: 60000 })
  await expectText(page, 'Forecast ready', 'upload step 4')
  console.log('upload step 4      ->', await shot(page, 'upload-step4'))

  // 5. Forecasts page — the chart
  await page.getByRole('button', { name: 'See forecasts' }).click()
  await page.waitForURL('**/warehouse/forecasts')
  await page.waitForSelector('svg.recharts-surface', { timeout: 20000 })
  await expectText(page, 'Expected · P50', 'forecasts')
  await expectText(page, 'Range hit rate', 'forecasts')
  const paths = await page.locator('svg.recharts-surface path').count()
  if (paths < 4) problems.push(`chart drew only ${paths} paths — expected area + 2 lines + reference`)
  console.log(`forecasts (chart, ${paths} paths) ->`, await shot(page, 'forecasts'))

  // 6. Warehouse home now populated
  await page.getByRole('link', { name: 'My Warehouse' }).click()
  await page.waitForTimeout(600)
  await expectText(page, 'What to do this month', 'warehouse home (populated)')
  console.log('warehouse (full)   ->', await shot(page, 'warehouse-full'))

  // 7. Transfers — real LP
  await page.getByRole('link', { name: 'Get & Share Stock' }).click()
  await page.waitForURL('**/warehouse/transfers')
  await page.waitForSelector('text=/coverable|Nothing to request/', { timeout: 120000 })
  console.log('transfers          ->', await shot(page, 'transfers'))

  // 8. Emergency tab
  await page.getByRole('button', { name: /Emergency request/ }).click()
  await page.waitForTimeout(400)
  await expectText(page, 'Nearest warehouses', 'emergency')
  console.log('emergency          ->', await shot(page, 'emergency'))

  // 9. Chat — a real LLM call
  await page.getByRole('link', { name: 'Ask Madad' }).click()
  await page.waitForURL('**/warehouse/chat')
  // The suggestions only mount once /api/chat/history resolves.
  const firstSuggestion = page.locator('button.suggest').first()
  await firstSuggestion.waitFor({ state: 'visible', timeout: 15000 })
  await firstSuggestion.click()
  // The spinner lives in a .turn-bot too, so wait for the answer by
  // waiting for the spinner to go, not for the bubble to appear.
  await page.locator('.turn-bot').first().waitFor({ timeout: 60000 })
  await page.locator('.turn-bot .spinner').waitFor({ state: 'detached', timeout: 60000 })
  const bot = await page.locator('.turn-bot').last().textContent()
  if (!bot || bot.trim().length < 15) problems.push('chat returned an empty answer')
  else console.log('   chat answer:', bot.trim().slice(0, 110).replace(/\s+/g, ' '))
  await expectText(page, 'Based on:', 'chat context chips')
  console.log('chat               ->', await shot(page, 'chat'))

  // 10. Authority pages (no session needed)
  for (const [path, needle, name] of [
    ['/authority', 'Network Overview', 'authority-home'],
    ['/authority/shortages', 'Shortages & Procurement', 'authority-shortages'],
    ['/authority/transfers', 'Transfer Network', 'authority-transfers'],
  ]) {
    await page.goto(BASE + path, { waitUntil: 'networkidle' })
    await page.waitForTimeout(900)
    await expectText(page, needle, name)
    console.log(`${name.padEnd(18)} ->`, await shot(page, name))
  }

  // 11. Every breakpoint, on the densest screens. A layout that survives the
  //     forecast picker and the transfer tables survives the rest.
  for (const [width, height, label] of [
    [390, 844, 'phone'],
    [768, 1024, 'tablet'],
    [1024, 800, 'laptop-narrow'],
    [1440, 900, 'desktop'],
  ]) {
    await page.setViewportSize({ width, height })
    for (const [path, name] of [
      ['/warehouse', 'home'],
      ['/warehouse/forecasts', 'forecasts'],
      ['/warehouse/transfers', 'transfers'],
      ['/', 'landing'],
    ]) {
      await page.goto(BASE + path, { waitUntil: 'networkidle' })
      await page.waitForTimeout(path === '/' ? 1800 : 900)
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      if (overflow > 4) problems.push(`horizontal overflow on ${name} at ${width}px: ${overflow}px`)
      await shot(page, `rwd-${width}-${name}`)
    }
    console.log(`${label.padEnd(18)} -> ${width}px checked (4 screens)`)
  }

  await browser.close()

  console.log('\n' + '='.repeat(60))
  if (problems.length === 0) {
    console.log('UI VERIFICATION PASSED — no console errors, no failed requests')
  } else {
    console.log(`UI VERIFICATION FOUND ${problems.length} PROBLEM(S):`)
    for (const problem of problems) console.log('  -', problem)
  }
  process.exit(problems.length === 0 ? 0 : 1)
}

run().catch((error) => {
  console.error('harness crashed:', error.message)
  process.exit(2)
})
