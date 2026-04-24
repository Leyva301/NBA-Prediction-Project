/**
 * records.js — Prediction Record Keeping (Data Layer)
 * -----------------------------------------------------
 * Handles all read/write/resolve logic for predictions.json.
 * Imported by server.js — no UI concerns here.
 *
 * Exports:
 *   autoPredictGames(games, flaskApiUrl)  → auto-predict any new games
 *   resolveFinishedGames(games)           → mark correct/incorrect for final games
 *   getAllPredictions()                   → full list, newest-first
 *   getSummaryStats()                     → KPIs + per-day accuracy for charts
 */

const fs   = require('fs');
const path = require('path');
const axios = require('axios');

const STORE_PATH = path.join(__dirname, 'predictions.json');

// ── Internal helpers ──────────────────────────────────────────────────────────

function readStore() {
  if (!fs.existsSync(STORE_PATH)) {
    fs.writeFileSync(STORE_PATH, JSON.stringify({ predictions: [] }, null, 2));
  }
  try {
    return JSON.parse(fs.readFileSync(STORE_PATH, 'utf8'));
  } catch {
    return { predictions: [] };
  }
}

function writeStore(store) {
  fs.writeFileSync(STORE_PATH, JSON.stringify(store, null, 2));
}

function todayISO() {
  return new Date().toISOString().slice(0, 10); // "YYYY-MM-DD"
}

// ── Exports ───────────────────────────────────────────────────────────────────

/**
 * For each game not yet in the store, call Flask /predict and save the result.
 * Silently skips games where Flask returns an error (home page must never break).
 */
async function autoPredictGames(games, flaskApiUrl) {
  const store = readStore();
  const existingIds = new Set(store.predictions.map(p => p.gameId));
  let changed = false;

  for (const game of games) {
    if (!game.gameId || existingIds.has(game.gameId)) continue;

    try {
      const res = await axios.post(
        `${flaskApiUrl}/predict`,
        { team_a: game.awayTeam, team_b: game.homeTeam, home_team: game.homeTeam },
        { timeout: 15000 }
      );

      const { prob_a, prob_b } = res.data;
      const predictedWinner = prob_a >= 0.5 ? game.awayTeam : game.homeTeam;
      const predictedAbbr   = prob_a >= 0.5 ? game.awayAbbr : game.homeAbbr;
      const probWinner       = prob_a >= 0.5 ? prob_a : prob_b;
      const probLoser        = prob_a >= 0.5 ? prob_b : prob_a;

      store.predictions.push({
        gameId:          game.gameId,
        date:            todayISO(),
        awayTeam:        game.awayTeam,
        awayAbbr:        game.awayAbbr,
        homeTeam:        game.homeTeam,
        homeAbbr:        game.homeAbbr,
        predictedWinner,
        predictedAbbr,
        probWinner:      parseFloat(probWinner.toFixed(4)),
        probLoser:       parseFloat(probLoser.toFixed(4)),
        actualWinner:    null,
        actualAbbr:      null,
        correct:         null,
        status:          game.status,
        predictedAt:     new Date().toISOString(),
        resolvedAt:      null,
      });

      existingIds.add(game.gameId);
      changed = true;
      console.log(`[Records] Predicted: ${game.awayAbbr} @ ${game.homeAbbr} → ${predictedAbbr} (${(probWinner * 100).toFixed(1)}%)`);
    } catch (err) {
      console.error(`[Records] Failed to predict ${game.awayAbbr} @ ${game.homeAbbr}:`, err.message);
    }
  }

  if (changed) writeStore(store);
}

/**
 * For each final game that has an unresolved prediction, determine the actual
 * winner from the scores and mark correct/incorrect.
 */
function resolveFinishedGames(games) {
  const store = readStore();
  let changed = false;

  for (const game of games) {
    if (game.status !== 'final') continue;
    if (game.homeScore === null || game.awayScore === null) continue;

    const pred = store.predictions.find(
      p => p.gameId === game.gameId && p.correct === null
    );
    if (!pred) continue;

    const actualWinner = game.homeScore > game.awayScore ? game.homeTeam : game.awayTeam;
    const actualAbbr   = game.homeScore > game.awayScore ? game.homeAbbr : game.awayAbbr;

    pred.actualWinner = actualWinner;
    pred.actualAbbr   = actualAbbr;
    pred.correct      = pred.predictedWinner === actualWinner;
    pred.status       = 'final';
    pred.resolvedAt   = new Date().toISOString();
    changed = true;

    console.log(`[Records] Resolved: ${game.awayAbbr} @ ${game.homeAbbr} → actual: ${actualAbbr} | correct: ${pred.correct}`);
  }

  if (changed) writeStore(store);
}

/**
 * Returns all predictions sorted newest-first.
 */
function getAllPredictions() {
  const { predictions } = readStore();
  return predictions.slice().sort((a, b) => new Date(b.predictedAt) - new Date(a.predictedAt));
}

/**
 * Returns KPI summary + per-day accuracy array for the last 30 days (charts).
 */
function getSummaryStats() {
  const { predictions } = readStore();
  const resolved  = predictions.filter(p => p.correct !== null);
  const correct   = resolved.filter(p => p.correct === true).length;
  const incorrect = resolved.filter(p => p.correct === false).length;
  const pending   = predictions.filter(p => p.correct === null).length;
  const total     = predictions.length;
  const accuracy  = resolved.length > 0 ? (correct / resolved.length) : null;

  // Build per-day buckets for the last 30 days
  const byDate = {};
  for (let i = 29; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    byDate[d.toISOString().slice(0, 10)] = { correct: 0, total: 0 };
  }

  for (const p of resolved) {
    if (byDate[p.date]) {
      byDate[p.date].total   += 1;
      byDate[p.date].correct += p.correct ? 1 : 0;
    }
  }

  const byDateArray = Object.entries(byDate).map(([date, val]) => ({
    date,
    correct: val.correct,
    total:   val.total,
    accuracy: val.total > 0 ? parseFloat((val.correct / val.total).toFixed(4)) : null,
  }));

  return { total, correct, incorrect, pending, accuracy, byDate: byDateArray };
}

module.exports = { autoPredictGames, resolveFinishedGames, getAllPredictions, getSummaryStats };
