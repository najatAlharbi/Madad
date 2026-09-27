# Madad screens — what each page shows

Reference for building the frontend. The `mockups/` folder holds the approved markup for
each screen; read it for layout and spacing. The mockups use a small templating syntax
(`sc-for`, `sc-if`, `{{ }}`) from the design tool — ignore it and read the HTML structure,
colours and copy. Rebuild in React.

Two workspaces, no login. The landing page picks one.

---

## Landing — `/`

Loading state first: the logo inside a spinning ring, wordmark, progress bar, then fade
into the chooser after ~2s.

Chooser: brand block, headline "Every connection makes a difference.", and two cards.

| Card | Label | Goes to |
| --- | --- | --- |
| Hospital Warehouse Manager | 01 / Operations, "Can upload data" | `/warehouse` |
| Regulatory Authority | 02 / Oversight, "View only" | `/authority` |

Right side: a green panel with the network illustration and three figures — 1,091
warehouses, 36 supplies, 81.5% range hit rate.

---

## Warehouse workspace

Sidebar: My Warehouse, Forecasted Needs, Get & Share Stock, Upload Data, Ask Madad.
Footer card: "Connected supplies. Better care.", the facility name, and links to switch
workspace and to How it works.

### My Warehouse — `/warehouse`

- Hero: the month's headline (e.g. "3 supplies may run out in April"), one supporting
  line, buttons to review forecasts and upload the next month.
- Emergency banner: "Need a critical medical supply now?" with a red button to the
  emergency tab.
- Four KPI cards: supplies tracked, critical, at risk, surplus.
- "What to do this month": a row per action — status pill, title with the quantity,
  a short detail line, a button.
- AI card: a two-sentence summary plus suggested questions.

### Forecasted Needs — `/warehouse/forecasts`

The most important screen. Left column (370px) is a picker: one row per supply with the
action line, a coverage bar and a status pill, and a toggle between "Need action" and
"All".

Right side is the forecast for the selected supply:

1. **Chart** — Recharts ComposedChart over 13 months:
   - `<Line dataKey="actual">` solid, ink colour — past consumption
   - `<Line dataKey="forecast" strokeDasharray="7 5">` green — forecast (P50)
   - `<Area dataKey="range">` sage — P10–P90, a cone opening from the last actual month
   - `<ReferenceLine y={stock}>` dashed gold — stock on hand
   - shaded band and a "FORECAST" label over the final month
   - legend: Actual consumption · Forecasted consumption (P50) · Forecast range (P10–P90)
     · Stock on hand · Actual (when the real value is known)
   - data shape: `[{ month, actual, forecast, range: [p10, p90] }]`, with `actual` null on
     the forecast row and `forecast` set on the last actual row so the lines join
2. Four cards: Forecast low (P10), Forecast (P50), Forecast high (P90), and the gap.
3. Model quality strip: range hit rate, P50 error, rows tested on, link to How it works.
4. One AI sentence and the action buttons.

### Get & Share Stock — `/warehouse/transfers`

Three tabs.

- **What you need**: a card per short supply, listing donor warehouses with their spare
  quantity, distance and suggested amount, each with a Request button.
- **Emergency request**: supply, quantity, urgency, then a ranked list of nearest
  warehouses that can cover it.
- **Requests to you**: incoming requests for your surplus, with accept and decline.

Right panel: the AI-drafted request message (with copy, edit, Arabic) and a count of
requests sent.

### Upload Data — `/warehouse/upload`

Four steps in a stepper: add your month → check and match → run models → results.

- Step 1: drop zone, "Load demo facility" button, manual entry form, and a table of the
  required format.
- Step 2: suggested column mapping with confidence pills, plus the validation checks as
  pass / warning / block rows.
- Step 3: the pipeline stages with a Run button.
- Step 4: counts of short, surplus and covered, an AI summary, and links onward.

### Ask Madad — `/warehouse/chat`

Chat column with suggested questions, and a right panel listing what the assistant can
look up plus the guardrails. Every answer shows the lookup used and its source.

---

## Authority workspace

Sidebar: Network Overview, Shortages & Procurement, Transfer Network, Reports. No upload
anywhere.

### Network Overview — `/authority`

Hero "One network. A clearer picture.", four KPIs (predicted shortage, covered by
transfers, needs buying, suggested transfers), a "Supplies that need buying" list, an AI
network brief, and a monitoring scope card.

### Shortages & Procurement — `/authority/shortages`

Per-supply table: coverage bar, shortage, still short, coverage percentage. Filters: All,
Needs buying, Partly covered, Fixed by transfers. Detail panel with the four quantities,
a recommendation and an AI note.

### Transfer Network — `/authority/transfers`

Summary strip, the largest transfers with distance and a "Far" flag over 50km, a donor
map, and a detail panel with an AI explanation and a "Flag for review" action.

### Reports — `/authority/reports`

Settings on the left (report type, period, audience, language), preview on the right.
English and Arabic, Arabic rendered RTL with Noto Kufi Arabic.

---

## How it works — `/how-it-works`

Reachable from both workspaces. The four pipeline steps, forecast quality metrics, how to
read a range, and the data limits.

---

## Rules that apply everywhere

- Any sample or demo value carries a visible badge saying so.
- Status words always accompany status colours.
- Numbers come from the API, never hard-coded in a component.
- Empty states say what to do next, never just a dash.
- Keep copy short: the mockups are the reference for length, not a starting point to
  expand on.
