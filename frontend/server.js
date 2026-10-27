/**
 * COURTIQ — Node.js / Express Server
 * -----------------------------------
 * Routes:
 *   GET  /          → index page (live games from NBA API)
 *   GET  /predict   → custom prediction form
 *   GET  /records   → prediction history dashboard
 *   GET  /api/records → prediction history as JSON
 *   POST /api/predict → calls the Python Flask model API
 *   GET  /api/roster  → a team's expected rotation, from the Flask model API
 *
 * Environment variables (optional, set in .env — see .env.example):
 *   PORT            = 3000
 *   FLASK_API_URL   = http://localhost:5050   ← your Python model server
 */

require('dotenv').config();
const express    = require('express');
const ejsLayouts = require('express-ejs-layouts');
const axios      = require('axios');
const path       = require('path');
const records    = require('./records');

const app  = express();
const PORT = process.env.PORT || 3000;
const FLASK_API_URL = process.env.FLASK_API_URL || 'http://localhost:5050';

console.log('Serving static from:', path.join(__dirname, 'public'));

// ── VIEW ENGINE ──
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(ejsLayouts);
app.set('layout', 'layout');

// ── MIDDLEWARE ──
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

// ── NBA TEAM LIST (static — used for the dropdown) ──
const NBA_TEAMS = [
  { full_name: 'Atlanta Hawks',          abbr: 'ATL' },
  { full_name: 'Boston Celtics',         abbr: 'BOS' },
  { full_name: 'Brooklyn Nets',          abbr: 'BKN' },
  { full_name: 'Charlotte Hornets',      abbr: 'CHA' },
  { full_name: 'Chicago Bulls',          abbr: 'CHI' },
  { full_name: 'Cleveland Cavaliers',    abbr: 'CLE' },
  { full_name: 'Dallas Mavericks',       abbr: 'DAL' },
  { full_name: 'Denver Nuggets',         abbr: 'DEN' },
  { full_name: 'Detroit Pistons',        abbr: 'DET' },
  { full_name: 'Golden State Warriors',  abbr: 'GSW' },
  { full_name: 'Houston Rockets',        abbr: 'HOU' },
  { full_name: 'Indiana Pacers',         abbr: 'IND' },
  { full_name: 'Los Angeles Clippers',   abbr: 'LAC' },
  { full_name: 'Los Angeles Lakers',     abbr: 'LAL' },
  { full_name: 'Memphis Grizzlies',      abbr: 'MEM' },
  { full_name: 'Miami Heat',             abbr: 'MIA' },
  { full_name: 'Milwaukee Bucks',        abbr: 'MIL' },
  { full_name: 'Minnesota Timberwolves', abbr: 'MIN' },
  { full_name: 'New Orleans Pelicans',   abbr: 'NOP' },
  { full_name: 'New York Knicks',        abbr: 'NYK' },
  { full_name: 'Oklahoma City Thunder',  abbr: 'OKC' },
  { full_name: 'Orlando Magic',          abbr: 'ORL' },
  { full_name: 'Philadelphia 76ers',     abbr: 'PHI' },
  { full_name: 'Phoenix Suns',           abbr: 'PHX' },
  { full_name: 'Portland Trail Blazers', abbr: 'POR' },
  { full_name: 'Sacramento Kings',       abbr: 'SAC' },
  { full_name: 'San Antonio Spurs',      abbr: 'SAS' },
  { full_name: 'Toronto Raptors',        abbr: 'TOR' },
  { full_name: 'Utah Jazz',              abbr: 'UTA' },
  { full_name: 'Washington Wizards',     abbr: 'WAS' },
];

// ── HELPER: Fetch today's NBA games from nba_api via Flask ──
// The Flask server exposes a /games/today endpoint that returns
// game data from the nba_api scoreboard endpoint.
async function fetchTodaysGames() {
  try {
    const res = await axios.get(`${FLASK_API_URL}/games/today`, { timeout: 8000 });
    return res.data.games || [];
  } catch (err) {
    console.error('[fetchTodaysGames] Flask API unavailable:', err.message);
    // Empty list → index page shows its "no games" state instead of fake games
    return [];
  }
}

// ── ROUTES ──

// Home — Live Games
app.get('/', async (req, res) => {
  const games = await fetchTodaysGames();

  // Autonomous record keeping — fire-and-forget so the home page never blocks
  // resolveAllPending checks ALL past dates with pending predictions, not just today
  Promise.resolve()
    .then(() => records.resolveAllPending(games, FLASK_API_URL))
    .then(() => records.autoPredictGames(games, FLASK_API_URL))
    .catch(err => console.error('[Records] Auto-predict error:', err.message));

  res.render('index', {
    title: 'CourtIQ · Live Games',
    games
  });
});

// Records — Prediction History
app.get('/records', (req, res) => {
  const predictions = records.getAllPredictions();
  const stats       = records.getSummaryStats();
  res.render('records', {
    title: 'CourtIQ · Records',
    predictions,
    stats
  });
});

// API — Records JSON (for future live refresh)
app.get('/api/records', (req, res) => {
  res.json({
    predictions: records.getAllPredictions(),
    stats:       records.getSummaryStats(),
  });
});

// Custom Predict Page
app.get('/predict', (req, res) => {
  res.render('predict', {
    title: 'CourtIQ · Predict',
    nbaTeams: NBA_TEAMS
  });
});

// ── API: Prediction Endpoint ──
// Receives { teamA, teamB, homeTeam, outA?, outB? }, forwards to Flask model, returns probabilities.
// outA / outB are names of players sitting out.
app.post('/api/predict', async (req, res) => {
  const { teamA, teamB, homeTeam, outA = [], outB = [] } = req.body;

  if (!teamA || !teamB || !homeTeam) {
    return res.status(400).json({ error: 'teamA, teamB, and homeTeam are required.' });
  }

  try {
    const flaskRes = await axios.post(
      `${FLASK_API_URL}/predict`,
      { team_a: teamA, team_b: teamB, home_team: homeTeam, out_a: outA, out_b: outB },
      { timeout: 15000 }
    );

    const { prob_a, prob_b, factors } = flaskRes.data;
    return res.json({ probA: prob_a, probB: prob_b, factors });

  } catch (err) {
    console.error('[/api/predict] Flask error:', err.message);
    return res.status(502).json({ error: 'Model server unavailable. Is Flask running?' });
  }
});

// ── API: Roster Endpoint ──
app.get('/api/roster', async (req, res) => {
  try {
    const flaskRes = await axios.get(`${FLASK_API_URL}/roster`, {
      params: { team: req.query.team },
      timeout: 15000
    });
    return res.json(flaskRes.data);
  } catch (err) {
    console.error('[/api/roster] Flask error:', err.message);
    return res.status(502).json({ error: 'Model server unavailable. Is Flask running?', players: [] });
  }
});

// ── 404 ──
app.use((req, res) => {
  res.status(404).send('<p style="font-family:monospace;color:#ff4d1c;">404 — Page not found</p>');
});

// ── START ──
app.listen(PORT, () => {
  console.log(`[CourtIQ] Server running at http://localhost:${PORT}`);
  console.log(`[CourtIQ] Flask model API expected at ${FLASK_API_URL}`);
});
