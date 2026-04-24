# CourtIQ — Hosting Guide

CourtIQ runs two servers that must both be active:

| Server | Port | Role |
|--------|------|------|
| Python / Flask (`flask_api.py`) | 5000 | NBA data + ML model |
| Node.js / Express (`server.js`) | 3000 | UI (what you visit in the browser) |

The `.env` file inside `frontend/src/components/` controls where Node looks for Flask.
Switching environments is just a matter of pointing that variable to the right host.

---

## Option A — Run Locally

Both servers run on your own machine. Only you (and others on your LAN) can access it.

### 1. Switch the environment

```bash
bash switch-env.sh local
```

This writes `localhost:5000` into the `.env` file.

### 2. Start both servers

```bash
bash start.sh
```

### 3. Open in browser

```
http://localhost:3000
```

---

## Option B — Run on OSU Flip Server

The app runs on an OSU flip server and is accessible to anyone with the URL.

### Step 1 — Find your flip server

Every time you SSH into `flip.engr.oregonstate.edu`, the load balancer may assign you
to a different machine (flip1–flip4). Always check which one you landed on:

```bash
ssh <onid>@flip.engr.oregonstate.edu
hostname   # e.g. "flip3.engr.oregonstate.edu"
```

Use that specific hostname for all subsequent steps (e.g. `flip3`).

### Step 2 — Switch the environment (on your local machine)

```bash
bash switch-env.sh flip flip3   # replace flip3 with your actual flip host
```

This rewrites the `.env` file so Node points to Flask on the flip server.

### Step 3 — Push to GitHub

```bash
git add frontend/src/components/.env
git commit -m "switch to flip3 environment"
git push
```

### Step 4 — Pull on the flip server

SSH in and navigate to the project:

```bash
ssh <onid>@flip3.engr.oregonstate.edu
cd ~/path/to/NBA-Prediction-Project
git pull
```

> **First time only:** clone the repo on the flip server:
> ```bash
> git clone https://github.com/<your-repo>.git
> cd NBA-Prediction-Project
> ```

### Step 5 — Start the servers on flip

```bash
bash start-flip.sh
```

Both servers launch in the background via `nohup`. They will keep running after you
log out. The startup message will print the full URL when ready:

```
================================================
 [CourtIQ] Both servers are running!
 Frontend : http://flip3.engr.oregonstate.edu:3000
 Flask API: http://flip3.engr.oregonstate.edu:5000
================================================
```

> **Note:** The first startup takes ~20 seconds — `model.py` fetches the full NBA
> season game log from the NBA API on import before training the model.

### Step 6 — Share the link

```
http://flip3.engr.oregonstate.edu:3000
```

Any computer (on or off campus) can open this URL while the servers are running.

---

## Managing the Flip Servers

### Check if servers are running

```bash
bash start-flip.sh status
```

### View live logs

```bash
bash start-flip.sh logs
# Ctrl+C to stop tailing
```

Logs are also saved at:
- `frontend/src/components/flask.log`
- `frontend/src/components/node.log`

### Stop both servers

```bash
bash start-flip.sh stop
```

### Restart (stop + start)

```bash
bash start-flip.sh stop && bash start-flip.sh
```

---

## Switching Back to Local

```bash
bash switch-env.sh local
bash start.sh
```

> If you previously committed the flip `.env` to git, commit the local one too:
> ```bash
> git add frontend/src/components/.env
> git commit -m "switch back to local environment"
> ```

---

## Environment File Reference

| File | Purpose |
|------|---------|
| `env.local` | Template for local hosting — do not edit |
| `env.flip` | Template for flip hosting — do not edit |
| `frontend/src/components/.env` | **Active config** — managed by `switch-env.sh` |

### What the `.env` looks like

**Local:**
```
PORT=3000
FLASK_API_URL=http://localhost:5000
```

**Flip:**
```
PORT=3000
FLASK_API_URL=http://flip3.engr.oregonstate.edu:5000
```

---

## Troubleshooting

**`flask_api.py` crashes on startup**
- Check `flask.log` for the error
- Most common cause: `nba_api` rate-limited. Wait 30s and retry.
- Make sure Python dependencies are installed: `pip3 install -r requirements.txt`

**Port already in use**
- Run `bash start-flip.sh stop` to kill existing processes, then restart.
- Or manually: `pkill -f flask_api.py && pkill -f server.js`

**Landed on a different flip server**
- Re-run `bash switch-env.sh flip flipX` with the correct host, push, pull, and restart.
- The flip load balancer is not sticky — always confirm with `hostname` after SSH.

**Predictions not auto-resolving**
- The home page load triggers resolution. Visit `/` on the live server.
- Check `node.log` for `[Records]` lines to confirm the logic ran.
