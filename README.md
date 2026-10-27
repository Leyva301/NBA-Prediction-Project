# CourtIQ — NBA Prediction Project

Predicts NBA game winners with a random forest trained on this season's (and last
season's) team game logs from the NBA stats API, and keeps a running record of how
the model's daily picks turned out.

```
backend/            Python — model + Flask API (port 5050)
  model.py          fetches game logs, trains the model; FEATURE_GROUPS switches live here
  features.py       team form, style matchups, player availability, head-to-head
  compare_features.py  backtests each factor group against the original model
  flask_api.py      /predict, /roster, /games/today, /games/date/YYYY-MM-DD
frontend/           Node.js — Express + EJS website (port 3000)
  server.js         pages: / (today's games), /predict, /records
  records.js        auto-predicts today's games and grades them once final
  predictions.json  saved prediction history
  views/  public/   templates, CSS, browser JS
start.sh            run both servers locally
start-flip.sh       run both servers in the background on an OSU flip server
setup-venv.sh       create venv/ and install Python dependencies
```

## Requirements

- Python 3.9+
- Node.js 18+

## Run it locally

```bash
bash start.sh
```

The first run creates `venv/` and installs the Python packages, then installs the
Node packages. Open http://localhost:3000.

The Flask API takes about 20 seconds to come up because it downloads the season's
game logs and trains the model on startup. Until then the home page shows no games.

To run the pieces by hand instead:

```bash
bash setup-venv.sh                       # once
source venv/bin/activate
cd backend && python flask_api.py        # terminal 1
cd frontend && npm install && npm start  # terminal 2
```

To just see the model's backtest and a sample prediction:

```bash
cd backend && python model.py
```

## Matchup factors and turning them off

On top of the original team-form features, the model can use four groups of
matchup factors (all in `backend/features.py`):

- **style_matchups**: 3-pt volume and accuracy, inside scoring, turnovers,
  offensive rebounding and free throws, each against what the other defense allows
- **roster_strength**: quality of the players actually available, from each
  player's recent box scores weighted by their usual minutes
- **perimeter**: how good the available shooters are, against the 3-pt % the
  other defense allows
- **head_to_head**: margin in earlier meetings, scaled down when there are few

To see whether each group helps, run the comparison (takes a couple of minutes):

```bash
cd backend && python compare_features.py
```

It backtests the original model, the original plus each group, everything, and
everything minus each group, then prints suggested switches. To turn a group
off, set it to `False` in `FEATURE_GROUPS` at the top of `backend/model.py`, or
without editing anything:

```bash
COURTIQ_DISABLE=head_to_head,perimeter python flask_api.py
```

On the Predict page you can uncheck players who are injured or resting; the
model rebuilds that team's strength without them. Players who have missed the
team's last 3 games are left out automatically.

## Configuration

Both servers work with no configuration. Flask uses port 5050 rather than 5000
because macOS AirPlay Receiver already listens on 5000. To use another port, run
`FLASK_PORT=5051 bash start.sh` (the scripts point Node at it for you). To change
the website port, copy `frontend/.env.example` to `frontend/.env` and edit `PORT`.

## Hosting on an OSU flip server

Node talks to Flask on the same machine, so no config changes are needed.

```bash
ssh <onid>@flip.engr.oregonstate.edu
hostname                     # note which flip (flip1–flip4) you landed on
git clone https://github.com/Leyva301/NBA-Prediction-Project.git   # first time only
cd NBA-Prediction-Project && git pull
bash start-flip.sh           # starts both servers in the background
```

The site is then at `http://<flip host>.engr.oregonstate.edu:3000`.

| Command | What it does |
|---|---|
| `bash start-flip.sh status` | show whether both servers are running |
| `bash start-flip.sh logs` | tail `flask.log` and `node.log` |
| `bash start-flip.sh stop` | stop both servers |

## How the records work

Every time someone loads the home page, the site predicts any of today's games that
haven't started yet, and grades earlier predictions whose games have gone final.
Results are saved in `frontend/predictions.json` and shown on `/records`.

## Troubleshooting

- **No games on the home page:** Flask is still starting, or it crashed. Check the
  terminal (or `flask.log` on flip). The NBA API sometimes rate-limits or times out;
  wait 30 seconds and restart.
- **Port already in use:** `bash start-flip.sh stop`, or
  `pkill -f flask_api.py && pkill -f server.js`. If something else owns the port,
  pick another one: `FLASK_PORT=5051 bash start.sh`.
