# CourtIQ — Prediction Record Keeping Feature Plan

## Overview

Add a **Records** tab to CourtIQ that automatically logs model predictions for every day's
NBA games, resolves them once games go final, and displays the results in a graphical
dashboard (pie chart, line chart, table).

---

## How Autonomous Recording Works

1. **On every `GET /` request (home page load)**, the server:
   - Fetches today's games from Flask (`/games/today`)
   - For each game not yet in the store → calls Flask `/predict` → saves the prediction
   - For each `final` game that has a prediction not yet resolved → reads the score,
     determines the actual winner, marks `correct: true/false`

2. This means **no user action is needed** — visiting the home page is enough to trigger
   both prediction creation and resolution.

3. Predictions are persisted in a flat JSON file (`predictions.json`) so they survive
   server restarts.

---

## Data Schema (`predictions.json`)

```json
{
  "predictions": [
    {
      "gameId":          "0022401234",
      "date":            "2026-04-24",
      "awayTeam":        "Los Angeles Lakers",
      "awayAbbr":        "LAL",
      "homeTeam":        "Golden State Warriors",
      "homeAbbr":        "GSW",
      "predictedWinner": "Golden State Warriors",
      "probWinner":      0.61,
      "probLoser":       0.39,
      "actualWinner":    null,
      "correct":         null,
      "status":          "upcoming",
      "predictedAt":     "2026-04-24T18:00:00.000Z",
      "resolvedAt":      null
    }
  ]
}
```

**Field notes:**
- `correct` is `null` while unresolved, `true`/`false` once the game goes final
- `status` mirrors the NBA API status: `upcoming`, `live`, `final`
- `predictedWinner` is whichever team the model gave `> 50%` probability

---

## Files to Create

### 1. `frontend/src/components/records.js` (Node.js module)
Server-side helper imported by `server.js`.

**Exports:**
- `autoPredictGames(games, flaskApiUrl)` — loops through today's games, skips any
  already in the store, calls Flask `/predict` for new ones, saves to JSON
- `resolveFinishedGames(games)` — loops through `final` games, finds their prediction,
  compares `predictedWinner` to the team with the higher score, sets `correct`
- `getAllPredictions()` — returns the full predictions array sorted newest-first
- `getSummaryStats()` — returns `{ total, correct, incorrect, pending, accuracy,
  byDate: [{date, correct, total}] }` used to build charts

### 2. `frontend/src/components/views/records.ejs` (EJS page)
Rendered at `GET /records`. Layout: three sections stacked vertically.

**Section A — Hero / Stats Bar**
```
[ RECORDS ] · MODEL ACCURACY: 63.4% · 89 PREDICTIONS · 56 CORRECT · 25 INCORRECT · 8 PENDING
```

**Section B — Charts Row (two side-by-side)**
- Left: **Pie chart** — Correct vs Incorrect (resolved games only), using Chart.js
- Right: **Line chart** — Rolling 7-day accuracy over the last 30 days, using Chart.js

**Section C — Prediction Table**
Columns: `DATE | MATCHUP | PREDICTED WINNER | PROB | ACTUAL WINNER | RESULT`

Rows are color-coded:
- Green left-border → correct
- Red left-border → incorrect
- Dim / no border → pending (game not yet final)

### 3. `frontend/src/components/public/records.css`
Page-specific styles added alongside `style.css` (not replacing it).

Key elements:
- `.records-stats-bar` — horizontal KPI strip at the top
- `.charts-row` — CSS grid, two columns, collapses to one on mobile
- `.chart-card` — dark card wrapping each canvas
- `.records-table` — full-width table with sticky header
- `.row-correct` / `.row-incorrect` / `.row-pending` — row color states
- Reuses CSS variables already defined in `style.css` (no new font imports)

### 4. `frontend/src/components/public/records-charts.js`
Client-side JS loaded only on the Records page.

**Responsibilities:**
- Reads prediction data injected by EJS into `window.RECORDS_DATA`
- Renders **pie chart** on `<canvas id="pie-chart">` via Chart.js (loaded from CDN)
- Renders **line chart** on `<canvas id="line-chart">` via Chart.js
- Line chart shows one data point per day (accuracy %) for the last 30 days with data
- Applies CourtIQ color palette (`#ff4d1c` for incorrect, `#00e5a0` for correct)

---

## Files to Modify

### 5. `frontend/src/components/server.js`
Three additions:

**a)** `require('./records')` at the top to import the records module

**b)** Modify the existing `GET /` handler to call `autoPredictGames` and
`resolveFinishedGames` after fetching today's games (fire-and-forget with `catch` so
home page never breaks if Flask is down)

**c)** Add two new routes:
```
GET  /records        → render records.ejs with { predictions, stats }
GET  /api/records    → return JSON { predictions, stats } (for future live refresh)
```

### 6. `frontend/src/components/views/layout.ejs`
Add a third nav link:
```html
<a href="/records" class="nav-link">Records</a>
```

---

## Implementation Order

1. `records.js` — data layer first, no UI dependency
2. Modify `server.js` — wire routes and auto-predict hook
3. `records.css` — styles before template so the page renders correctly on first load
4. `records.ejs` — template (depends on data shape from records.js)
5. `records-charts.js` — chart rendering (depends on canvas elements in records.ejs)
6. `layout.ejs` — add nav link last (trivial change)

---

## Chart.js Integration

- Loaded via CDN `<script>` tag inside `records.ejs` only (not in layout so other pages
  are unaffected)
- No build step required — plain `<canvas>` elements
- Chart colors pulled from CourtIQ CSS variables

---

## Edge Cases Handled

| Scenario | Behavior |
|---|---|
| Flask is down when home page loads | `autoPredictGames` catches the error silently; existing predictions are unaffected |
| Game already predicted for the day | Duplicate check on `gameId` prevents double-entries |
| No games today | Records page still loads, charts show historical data |
| Tie score (theoretically impossible in NBA) | `actualWinner` set to `null`, `correct` stays `null` |
| Records page visited before any predictions | Shows empty state: "NO PREDICTIONS YET" |

---

## What Is NOT in Scope

- Database — flat JSON is sufficient for local use
- Authentication
- Manual override of results
- Predictions for the custom `/predict` page (only auto-predictions for scheduled games)
