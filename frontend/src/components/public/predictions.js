/**
 * predictions.js — Prediction Record Tracker
 * --------------------------------------------
 * Handles reading/writing predictions.json and
 * resolving outcomes by checking final scores via Flask.
 */

const fs   = require('fs');
const path = require('path');
const axios = require('axios');

const PREDICTIONS_FILE = path.join(__dirname, 'predictions.json');
const FLASK_API_URL = process.env.FLASK_API_URL || 'http://localhost:5000';

// ── READ ────────────────────────────────────────────────────────
function readPredictions() {
  try {
    if (!fs.existsSync(PREDICTIONS_FILE)) {
      fs.writeFileSync(PREDICTIONS_FILE, JSON.stringify({ predictions: [] }, null, 2));
    }
    const raw = fs.readFileSync(PREDICTIONS_FILE, 'utf8');
    return JSON.parse(raw).predictions || [];
  } catch (err) {
    console.error('[predictions] Read error:', err.message);
    return [];
  }
}

// ── WRITE ───────────────────────────────────────────────────────
function writePredictions(predictions) {
  try {
    fs.writeFileSync(PREDICTIONS_FILE, JSON.stringify({ predictions }, null, 2));
  } catch (err) {
    console.error('[predictions] Write error:', err.message);
  }
}

// ── LOG A NEW PREDICTION ─────────────────────────────────────────
function logPrediction({ gameId, awayTeam, homeTeam, predictedWinner, confidence }) {
  const predictions = readPredictions();

  // Avoid duplicate entries for the same game
  const exists = predictions.find(p => p.gameId === gameId);
  if (exists) return exists;

  const entry = {
    id:              `${gameId}-${Date.now()}`,
    gameId,
    date:            new Date().toISOString(),
    awayTeam,
    homeTeam,
    predictedWinner,
    confidence,      // probability of predictedWinner winning (0-1)
    actualWinner:    null,
    result:          'pending'  // 'correct' | 'wrong' | 'pending'
  };

  predictions.push(entry);
  writePredictions(predictions);
  console.log(`[predictions] Logged: ${awayTeam} @ ${homeTeam} → ${predictedWinner} (${(confidence*100).toFixed(1)}%)`);
  return entry;
}

// ── RESOLVE OUTCOMES ─────────────────────────────────────────────
// Called periodically — checks Flask for final scores and updates pending predictions
async function resolveOutcomes() {
  const predictions = readPredictions();
  const pending = predictions.filter(p => p.result === 'pending');
  if (pending.length === 0) return;

  console.log(`[predictions] Checking ${pending.length} pending prediction(s)...`);

  try {
    const res   = await axios.get(`${FLASK_API_URL}/games/today`, { timeout: 8000 });
    const games = res.data.games || [];

    let updated = false;

    for (const pred of pending) {
      // Find the matching finished game
      const game = games.find(g =>
        g.gameId === pred.gameId && g.status === 'final'
      );
      if (!game) continue;

      // Determine actual winner by score
      const actualWinner = game.homeScore > game.awayScore
        ? game.homeTeam
        : game.awayTeam;

      pred.actualWinner = actualWinner;
      pred.result       = actualWinner === pred.predictedWinner ? 'correct' : 'wrong';
      pred.finalScore   = `${game.awayAbbr} ${game.awayScore} - ${game.homeScore} ${game.homeAbbr}`;
      updated = true;

      console.log(`[predictions] Resolved: ${pred.awayTeam} @ ${pred.homeTeam} → ${pred.result.toUpperCase()} (actual: ${actualWinner})`);
    }

    if (updated) writePredictions(predictions);

  } catch (err) {
    console.error('[predictions] Could not resolve outcomes:', err.message);
  }
}

// ── COMPUTE STATS ────────────────────────────────────────────────
function computeStats(predictions) {
  const total   = predictions.length;
  const correct = predictions.filter(p => p.result === 'correct').length;
  const wrong   = predictions.filter(p => p.result === 'wrong').length;
  const pending = predictions.filter(p => p.result === 'pending').length;
  const resolved = correct + wrong;

  const accuracy      = resolved > 0 ? correct / resolved : 0;
  const avgConfidence = total > 0
    ? predictions.reduce((sum, p) => sum + p.confidence, 0) / total
    : 0;

  return { total, correct, wrong, pending, accuracy, avgConfidence };
}

module.exports = { readPredictions, logPrediction, resolveOutcomes, computeStats };
