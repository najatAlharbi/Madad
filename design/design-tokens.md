# Madad design tokens

Every colour, font size and shape used in the approved mockups. Claude Code must use
these exact values as CSS variables. Do not introduce new colours.

## Colours

```css
:root {
  /* brand */
  --green-900: #03392E;   /* hover on primary */
  --green-700: #055444;   /* primary: buttons, active nav text, P50 line, hero background */
  --green-100: #E6EFE8;   /* active nav background, highlight card */
  --sage-200:  #CFE0D6;   /* forecast range band */
  --sage-100:  #D7E5DB;   /* secondary bar fill */
  --gold-600:  #9E8251;   /* accent, stock line, active nav bar, eyebrow text */
  --gold-100:  #E9DFD4;   /* icon tiles */
  --sand-50:   #FBF7F2;   /* emergency banner background */
  --sand-200:  #EFE4D6;   /* emergency banner border */

  /* surfaces */
  --bg:        #F4F6F1;   /* page background */
  --surface:   #FFFFFF;   /* cards, sidebar */
  --surface-2: #F9FAF8;   /* inputs */
  --border:    #E3E7DF;
  --border-2:  #D3DAD0;   /* input and button borders */
  --row-line:  #EEF1EC;   /* table row separators */

  /* text */
  --ink:   #16362B;       /* headings */
  --body:  #3E4F48;
  --muted: #5F6F68;

  /* status */
  --critical:    #9B2F2A;  --critical-bg: #F7E4E1;  --critical-fg: #8A2A25;
  --at-risk:     #9E8251;  --at-risk-bg:  #F5ECDD;  --at-risk-fg:  #74501A;
  --surplus:     #2C6A7F;  --surplus-bg:  #E1EEF0;  --surplus-fg:  #1F5A66;
  --ok:          #1F5B3F;  --ok-bg:       #E4EFE6;
  --neutral-bg:  #EEF0EC;  --neutral-fg:  #46554F;
}
```

Status colour meaning, used everywhere without exception:

| Status | Rule | Colour |
| --- | --- | --- |
| Critical | stock < P50 | critical (red) |
| At risk | P50 <= stock < P90 | at-risk (gold) |
| Surplus | stock >= P90 | surplus (blue) |
| Covered / done | — | ok (green) |

## Type

```css
font-family: 'Segoe UI', 'Noto Sans', system-ui, -apple-system, sans-serif;
/* Arabic: 'Noto Kufi Arabic', 'Segoe UI', sans-serif */
```

| Role | Size | Weight | Notes |
| --- | --- | --- | --- |
| Page title (h1) | 30px | 700 | letter-spacing -0.01em |
| Hero title | 34px | 700 | white on green |
| Card title (h2) | 16px | 700 | |
| Section eyebrow | 11px | 600 | uppercase, letter-spacing 0.16em, colour gold-600 |
| Breadcrumb | 11px | 600 | uppercase, letter-spacing 0.14em, colour muted |
| Body | 14px | 400 | |
| Small | 12px | 400 | colour muted |
| Big number (KPI) | 30px | 700 | tabular-nums |
| Wordmark MADAD | 22px | 700 | letter-spacing 0.2em |

All numbers use `font-variant-numeric: tabular-nums`.

## Shape and spacing

| Element | Spec |
| --- | --- |
| Card | 16px radius, 1px --border, 20px 22px padding, --surface |
| Hero banner | 18px radius, --green-700 background, 26px 34px padding |
| Button | 10px radius, 44px tall, 600 weight, 0 18px padding |
| Small button | 36px tall, 13px |
| Primary button | --green-700 background, white text |
| Danger button | --critical background, white text (emergency request only) |
| Input / select | 10px radius, 44px tall, --surface-2 background, --border-2 border |
| Pill / status chip | 999px radius, 26px tall, 12px, 600 weight |
| Segmented control | 12px radius, --neutral-bg track, white active segment |
| Sidebar | 256px wide, --surface, active item: --green-100 background + 3px --gold-600 left border |
| Page padding | 26px 36px |
| Gap between sections | 16–18px |

## Layout

- Sidebar (256px) + main content, full height.
- Page header: breadcrumb, h1, then the portal pill and avatar on the right.
- Content grids are two columns: a list or main panel on the left, a detail panel of
  390–430px on the right.
- Everything above the fold; no page-level horizontal scrolling.

## Accessibility

- Text contrast at least 4.5:1. Never use colour alone to carry a status; always pair it
  with the status word.
- Interactive targets at least 44px tall.
- Real `<button>` and `<a>` elements, labelled inputs, `aria-pressed` on toggles.
- Every chart needs a text alternative describing what it shows.

## Voice

Short. One status word, one action line, then the numbers. No marketing sentences, no
explanatory paragraphs inside cards. "Get 46 units", not "You may wish to consider
requesting additional units".
