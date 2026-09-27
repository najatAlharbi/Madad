/** Drive the real file-upload path in a browser: choose file -> map ->
 *  confirm -> run forecast -> see the chart.
 *
 * verify-ui.mjs covers the "Load demo facility" shortcut; this covers the
 * path an actual warehouse manager takes with their own spreadsheet.
 *
 * Usage (both servers running), from frontend/:
 *   node scripts/verify-upload.mjs [../data/test_uploads/clean_facility_1047_2023-11.csv]
 */
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'
const FILE = resolve(process.argv[2] ?? '../data/test_uploads/clean_facility_1047_2023-11.csv')
const OUT = 'verify-shots/upload'
const problems = []
let step = 0

const shot = async (page, name) => {
  step += 1
  const file = `${OUT}/${String(step).padStart(2, '0')}-${name}.png`
  await page.screenshot({ path: file, fullPage: true })
  return file
}

const run = async () => {
  mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch()
  const page = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage()

  page.on('console', (m) => {
    if (m.type() === 'error' && !/status of (409|410)/.test(m.text())) {
      problems.push(`console error: ${m.text().slice(0, 180)}`)
    }
  })
  page.on('response', (r) => {
    if (r.url().includes('/api/') && r.status() >= 400 && ![409, 410].includes(r.status())) {
      problems.push(`api ${r.status()} ${r.url()}`)
    }
  })

  console.log('uploading:', FILE)

  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Skip' }).click().catch(() => {})
  await page.getByRole('button', { name: /Hospital Warehouse Manager/ }).click()
  await page.waitForURL('**/warehouse')

  await page.getByRole('link', { name: 'Upload Data' }).click()
  await page.waitForURL('**/warehouse/upload')

  // Step 1 -> pick the file through the real <input type=file>
  await page.locator('input[type=file]').setInputFiles(FILE)

  // Step 2: mapping + checks
  await page.waitForSelector('text=Match your columns', { timeout: 30000 })
  const mapped = await page.locator('select.select').count()
  const values = await page.locator('select.select').evaluateAll((els) => els.map((e) => e.value))
  const unmapped = values.filter((v) => !v).length
  console.log(`step 2: ${mapped} fields, ${unmapped} unmapped`)
  if (unmapped > 0) problems.push(`${unmapped} field(s) left unmapped by the suggestion`)
  const checks = await page.locator('.check-row').count()
  console.log(`step 2: ${checks} validation checks shown`)
  if (checks === 0) problems.push('no validation checks rendered')
  console.log('step 2 ->', await shot(page, 'mapping'))

  await page.getByRole('button', { name: 'Confirm and continue' }).click()

  // Step 3: run
  await page.waitForSelector('text=Run the models', { timeout: 30000 })
  console.log('step 3 ->', await shot(page, 'run'))
  await page.getByRole('button', { name: 'Run forecast' }).click()

  // Step 4: results
  await page.waitForSelector('text=Forecast ready', { timeout: 90000 })
  const body = await page.textContent('body')
  if (!body?.includes('Forecast ready')) problems.push('no results panel')
  console.log('step 4 ->', await shot(page, 'results'))

  // The forecast itself
  await page.getByRole('button', { name: 'See forecasts' }).click()
  await page.waitForURL('**/warehouse/forecasts')
  await page.waitForSelector('svg.recharts-surface', { timeout: 30000 })

  const heading = await page.locator('#fcTitle').textContent()
  const p50 = await page.locator('.q-cell.q-mid').first().textContent()
  console.log(`chart rendered for: ${heading?.trim()}`)
  console.log(`P50 card: ${p50?.replace(/\s+/g, ' ').trim()}`)

  // A demo badge must NOT appear — this is the user's own data.
  if (body?.includes('Sample data')) problems.push('user upload wrongly badged as sample data')

  console.log('forecast ->', await shot(page, 'forecast'))

  await browser.close()
  console.log('\n' + '='.repeat(56))
  if (problems.length === 0) console.log('UPLOAD PATH PASSED')
  else {
    console.log(`UPLOAD PATH FOUND ${problems.length} PROBLEM(S):`)
    problems.forEach((p) => console.log('  -', p))
  }
  process.exit(problems.length ? 1 : 0)
}

run().catch((e) => {
  console.error('harness crashed:', e.message)
  process.exit(2)
})
