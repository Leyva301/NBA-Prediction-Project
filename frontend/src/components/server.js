/**
 * COURTIQ — Node.js / Express Server
 * -----------------------------------
 * Routes:
 *   GET  /          → index page (live games from NBA API)
 *   GET  /predict   → custom prediction form
 *   POST /api/predict → calls the Python Flask model API
 *
 * Environment variables (set in .env):
 *   PORT            = 3000
 *   FLASK_API_URL   = http://localhost:5000   ← your Python model server
 *   NBA_API_KEY     = (if you move to a paid NBA data provider)
 */

/**
 * COURTIQ — Node.js / Express Server
 */

require('dotenv').config();
const express    = require('express');
const ejsLayouts = require('express-ejs-layouts');
const axios      = require('axios');
const path       = require('path');
const fs         = require('fs');
const { readPredictions, logPrediction, resolveOutcomes, computeStats } = require('./public/predictions');

const app  = express();
const PORT = process.env.PORT || 3000;
const FLASK_API_URL = process.env.FLASK_API_URL || 'http://localhost:5000';

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));
app.use(ejsLayouts);
app.set('layout', 'layout');

app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

// Auto-resolve outcomes every 10 minutes
resolveOutcomes();
setInterval(resolveOutcomes, 10 * 60 * 1000);

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
  { full_name: 'Utah Jazz',             abbr: 'UTA' },
  { full_name: 'Washington Wizards',     abbr: 'WAS' },
];

async function fetchTodaysGames() {
  try {
    const res = await axios.get(`${FLASK_API_URL}/games/today`, { timeout: 8000 });
    return res.data.games || [];
  } catch (err) {
    console.error('[fetchTodaysGames] Flask API unavailable:', err.message);
    return [
      { gameId: 'mock-1', homeTeam: 'Milwaukee Bucks', homeAbbr: 'MIL', homeScore: null, awayTeam: 'Miami Heat', awayAbbr: 'MIA', awayScore: null, status: 'upcoming', statusText: '7:30 PM ET' },
      { gameId: 'mock-2', homeTeam: 'Golden State Warriors', homeAbbr: 'GSW', homeScore: 112, awayTeam: 'Los Angeles Lakers', awayAbbr: 'LAL', awayScore: 108, status: 'live', statusText: 'Q3 4:22' },
    ];
  }
}

// ── ROUTES ──
app.get('/', async (req, res) => {
  const games = await fetchTodaysGames();
  res.render('index', { title: 'CourtIQ · Live Games', games });
});

app.get('/predict', (req, res) => {
  res.render('predict', { title: 'CourtIQ · Predict', nbaTeams: NBA_TEAMS });
});

app.get('/record', (req, res) => {
  const predictions = readPredictions();
  const stats       = computeStats(predictions);
  res.render('record', { title: 'CourtIQ · Record', predictions, stats });
});

app.get('/api/games', async (req, res) => {
  const games = await fetchTodaysGames();
  res.json({ games });
});

app.post('/api/predict', async (req, res) => {
  const { teamA, teamB, homeTeam, gameId } = req.body;
  if (!teamA || !teamB || !homeTeam) {
    return res.status(400).json({ error: 'teamA, teamB, and homeTeam are required.' });
  }
  try {
    const flaskRes = await axios.post(
      `${FLASK_API_URL}/predict`,
      { team_a: teamA, team_b: teamB, home_team: homeTeam },
      { timeout: 15000 }
    );
    const { prob_a, prob_b } = flaskRes.data;
    const predictedWinner = prob_a >= prob_b ? teamA : teamB;
    const confidence      = Math.max(prob_a, prob_b);
    if (gameId) {
      logPrediction({ gameId, awayTeam: teamA, homeTeam, predictedWinner, confidence });
    }
    return res.json({ probA: prob_a, probB: prob_b, predictedWinner, confidence });
  } catch (err) {
    console.error('[/api/predict] Flask error:', err.message);
    return res.status(502).json({ error: 'Model server unavailable. Is Flask running?' });
  }
});

app.use((req, res) => {
  res.status(404).send('<p style="font-family:monospace;color:#ff4d1c;">404 — Page not found</p>');
});

app.listen(PORT, () => {
  console.log(`[CourtIQ] Server running at http://localhost:${PORT}`);
  console.log(`[CourtIQ] Flask model API expected at ${FLASK_API_URL}`);
});








// require('dotenv').config();
// const express    = require('express');
// const ejsLayouts = require('express-ejs-layouts');
// const axios      = require('axios');
// const path       = require('path');

// const app  = express();
// const PORT = process.env.PORT || 3003;
// const FLASK_API_URL = process.env.FLASK_API_URL || 'http://flip3.engr.oregonstate.edu:5000';

// console.log('Serving static from:', path.join(__dirname, 'public'));

// // ── VIEW ENGINE ──
// app.set('view engine', 'ejs');
// app.set('views', path.join(__dirname, 'views'));
// app.use(ejsLayouts);
// app.set('layout', 'layout');

// // ── MIDDLEWARE ──
// app.use(express.json());
// app.use(express.urlencoded({ extended: true }));
// app.use(express.static(path.join(__dirname, 'public')));

// // ── NBA TEAM LIST (static — used for the dropdown) ──
// const NBA_TEAMS = [
//   { full_name: 'Atlanta Hawks',          abbr: 'ATL' },
//   { full_name: 'Boston Celtics',         abbr: 'BOS' },
//   { full_name: 'Brooklyn Nets',          abbr: 'BKN' },
//   { full_name: 'Charlotte Hornets',      abbr: 'CHA' },
//   { full_name: 'Chicago Bulls',          abbr: 'CHI' },
//   { full_name: 'Cleveland Cavaliers',    abbr: 'CLE' },
//   { full_name: 'Dallas Mavericks',       abbr: 'DAL' },
//   { full_name: 'Denver Nuggets',         abbr: 'DEN' },
//   { full_name: 'Detroit Pistons',        abbr: 'DET' },
//   { full_name: 'Golden State Warriors',  abbr: 'GSW' },
//   { full_name: 'Houston Rockets',        abbr: 'HOU' },
//   { full_name: 'Indiana Pacers',         abbr: 'IND' },
//   { full_name: 'Los Angeles Clippers',   abbr: 'LAC' },
//   { full_name: 'Los Angeles Lakers',     abbr: 'LAL' },
//   { full_name: 'Memphis Grizzlies',      abbr: 'MEM' },
//   { full_name: 'Miami Heat',             abbr: 'MIA' },
//   { full_name: 'Milwaukee Bucks',        abbr: 'MIL' },
//   { full_name: 'Minnesota Timberwolves', abbr: 'MIN' },
//   { full_name: 'New Orleans Pelicans',   abbr: 'NOP' },
//   { full_name: 'New York Knicks',        abbr: 'NYK' },
//   { full_name: 'Oklahoma City Thunder',  abbr: 'OKC' },
//   { full_name: 'Orlando Magic',          abbr: 'ORL' },
//   { full_name: 'Philadelphia 76ers',     abbr: 'PHI' },
//   { full_name: 'Phoenix Suns',           abbr: 'PHX' },
//   { full_name: 'Portland Trail Blazers', abbr: 'POR' },
//   { full_name: 'Sacramento Kings',       abbr: 'SAC' },
//   { full_name: 'San Antonio Spurs',      abbr: 'SAS' },
//   { full_name: 'Toronto Raptors',        abbr: 'TOR' },
//   { full_name: 'Utah Jazz',              abbr: 'UTA' },
//   { full_name: 'Washington Wizards',     abbr: 'WAS' },
// ];

// // ── HELPER: Fetch today's NBA games from nba_api via Flask ──
// // The Flask server exposes a /games/today endpoint that returns
// // game data from the nba_api scoreboard endpoint.
// async function fetchTodaysGames() {
//   try {
//     const res = await axios.get(`${FLASK_API_URL}/games/today`, { timeout: 8000 });
//     return res.data.games || [];
//   } catch (err) {
//     console.error('[fetchTodaysGames] Flask API unavailable:', err.message);
//     // Return mock data so the UI still loads during development
//     return [
//       {
//         homeTeam: 'Milwaukee Bucks', homeAbbr: 'MIL', homeScore: null,
//         awayTeam: 'Miami Heat',      awayAbbr: 'MIA', awayScore: null,
//         status: 'upcoming', statusText: '7:30 PM ET'
//       },
//       {
//         homeTeam: 'Golden State Warriors', homeAbbr: 'GSW', homeScore: 112,
//         awayTeam: 'Los Angeles Lakers',    awayAbbr: 'LAL', awayScore: 108,
//         status: 'live', statusText: 'Q3 4:22'
//       },
//     ];
//   }
// }

// // ── ROUTES ──

// // Home — Live Games
// app.get('/', async (req, res) => {
//   const games = await fetchTodaysGames();
//   res.render('index', {
//     title: 'CourtIQ · Live Games',
//     games
//   });
// });

// // Custom Predict Page
// app.get('/predict', (req, res) => {
//   res.render('predict', {
//     title: 'CourtIQ · Predict',
//     nbaTeams: NBA_TEAMS
//   });
// });

// // ── API: Prediction Endpoint ──
// // Receives { teamA, teamB, homeTeam }, forwards to Flask model, returns probabilities.
// app.post('/api/predict', async (req, res) => {
//   const { teamA, teamB, homeTeam } = req.body;

//   if (!teamA || !teamB || !homeTeam) {
//     return res.status(400).json({ error: 'teamA, teamB, and homeTeam are required.' });
//   }

//   try {
//     const flaskRes = await axios.post(
//       `${FLASK_API_URL}/predict`,
//       { team_a: teamA, team_b: teamB, home_team: homeTeam },
//       { timeout: 15000 }
//     );

//     const { prob_a, prob_b } = flaskRes.data;
//     return res.json({ probA: prob_a, probB: prob_b });

//   } catch (err) {
//     console.error('[/api/predict] Flask error:', err.message);
//     return res.status(502).json({ error: 'Model server unavailable. Is Flask running?' });
//   }
// });

// // ── 404 ──
// app.use((req, res) => {
//   res.status(404).send('<p style="font-family:monospace;color:#ff4d1c;">404 — Page not found</p>');
// });

// // ── START ──
// app.listen(PORT, () => {
//   console.log(`[CourtIQ] Server running at http://localhost:${PORT}`);
//   console.log(`[CourtIQ] Flask model API expected at ${FLASK_API_URL}`);
// });