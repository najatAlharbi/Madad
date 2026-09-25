# Madad design package

Drop this whole folder into the repo as `design/`.

- `design-tokens.md` — every colour, font size and shape. Use these exact values.
- `screens.md` — what each page shows, screen by screen, including the chart spec.
- `mockups/` — the approved markup for each screen. Reference for layout, spacing and
  copy. It uses a small templating syntax (`sc-for`, `sc-if`, `{{ }}`) from the design
  tool: ignore it and read the structure. Rebuild in React, do not port these files.
- `logo.png` — the Madad logo. Used in the sidebar, the landing page and the loading
  state.

Screen files map to routes like this:

| Mockup | Route |
| --- | --- |
| Main.html | / (landing + loading) |
| WarehouseHome.html | /warehouse |
| Forecasts.html | /warehouse/forecasts |
| Transfers.html | /warehouse/transfers |
| Upload.html | /warehouse/upload |
| Assistant.html | /warehouse/chat |
| AuthorityHome.html | /authority |
| Shortages.html | /authority/shortages |
| Redistribution.html | /authority/transfers |
| Reports.html | /authority/reports |
| Model.html | /how-it-works |
