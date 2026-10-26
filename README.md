# CourtIQ — NBA Prediction Project

Predicts NBA game winners with a random forest trained on this season's (and last
season's) team game logs from the NBA stats API, and keeps a running record of how
the model's daily picks turned out.

```
backend/            Python — model + Flask API (port 5000)
  model.py          fetches game logs, builds features, trains the model
  flask_api.py      /predict, /games/today, /games/date/YYYY-MM-DD
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

## Configuration

Both servers work with no configuration. To change ports or where Node finds
Flask, copy `frontend/.env.example` to `frontend/.env` and edit it.

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

Every time someone loads the home page, the site predicts any of today's games it
hasn't predicted yet, and grades earlier predictions whose games have gone final.
Results are saved in `frontend/predictions.json` and shown on `/records`.

## Troubleshooting

- **No games on the home page:** Flask is still starting, or it crashed. Check the
  terminal (or `flask.log` on flip). The NBA API sometimes rate-limits or times out;
  wait 30 seconds and restart.
- **Port already in use:** `bash start-flip.sh stop`, or
  `pkill -f flask_api.py && pkill -f server.js`.
