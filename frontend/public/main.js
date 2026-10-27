/* ============================================================
   COURTIQ — Client-Side JS
   Handles: modal, predictions, live date, custom predict page
   ============================================================ */

// ── LIVE DATE ──
const dateEl = document.getElementById('live-date');
if (dateEl) {
  const now = new Date();
  dateEl.textContent = now.toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric'
  }).toUpperCase();
}

// ── MODAL LOGIC ──
const modal = document.getElementById('pred-modal');

function closeModal() {
  modal.classList.remove('active');
  modal.setAttribute('aria-hidden', 'true');
}

modal?.addEventListener('click', (e) => {
  if (e.target === modal) closeModal();
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeModal();
});

// ── RUN PREDICTION (index page) ──
async function runPrediction(teamA, teamB, homeTeam) {
  // Open modal immediately with loading state
  modal.classList.add('active');
  modal.setAttribute('aria-hidden', 'false');

  const matchupEl    = document.getElementById('modal-matchup');
  const barsEl       = document.getElementById('modal-bars');
  const confidenceEl = document.getElementById('modal-confidence');
  const labelA       = document.getElementById('label-a');
  const labelB       = document.getElementById('label-b');
  const barA         = document.getElementById('bar-a');
  const barB         = document.getElementById('bar-b');
  const numA         = document.getElementById('num-a');
  const numB         = document.getElementById('num-b');

  matchupEl.textContent = `${teamA} vs ${teamB}`;
  barsEl.style.opacity = '0.3';
  confidenceEl.textContent = 'RUNNING MODEL...';
  confidenceEl.className = 'confidence-badge mono';

  try {
    const res = await fetch('/api/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teamA, teamB, homeTeam })
    });

    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();

    // Animate bars in
    barsEl.style.opacity = '1';
    labelA.textContent = abbrev(teamA);
    labelB.textContent = abbrev(teamB);
    numA.textContent   = `${(data.probA * 100).toFixed(1)}%`;
    numB.textContent   = `${(data.probB * 100).toFixed(1)}%`;

    setTimeout(() => {
      barA.style.width = `${data.probA * 100}%`;
      barB.style.width = `${data.probB * 100}%`;
    }, 80);

    const isBet = data.probA > 0.62 || data.probA < 0.38;
    confidenceEl.textContent = isBet
      ? `✓ HIGH CONFIDENCE — MODEL EDGE DETECTED`
      : `⚠ LOW EDGE — CAUTION ADVISED`;
    confidenceEl.classList.add(isBet ? 'bet' : 'caution');

  } catch (err) {
    confidenceEl.textContent = `ERROR: ${err.message}`;
    confidenceEl.style.color = 'var(--loss)';
  }
}

// ── CUSTOM PREDICT PAGE ──
async function submitCustomPrediction() {
  const teamA    = document.getElementById('team-a')?.value;
  const teamB    = document.getElementById('team-b')?.value;
  const homeRadio = document.querySelector('input[name="home"]:checked')?.value;
  const homeTeam = homeRadio === 'a' ? teamA : teamB;

  const placeholder = document.getElementById('result-placeholder');
  const content     = document.getElementById('result-content');
  const errorEl     = document.getElementById('result-error');
  const loadingEl   = document.getElementById('result-loading');

  if (!teamA || !teamB) {
    showError('Please select both teams.', placeholder, content, errorEl, loadingEl);
    return;
  }
  if (teamA === teamB) {
    showError('Please select two different teams.', placeholder, content, errorEl, loadingEl);
    return;
  }

  // Show loading
  placeholder?.classList.add('hidden');
  content?.classList.add('hidden');
  errorEl?.classList.add('hidden');
  loadingEl?.classList.remove('hidden');

  try {
    const res = await fetch('/api/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teamA, teamB, homeTeam, outA: playersOut('a'), outB: playersOut('b') })
    });

    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();

    loadingEl.classList.add('hidden');
    content.classList.remove('hidden');

    document.getElementById('result-matchup').textContent = `${abbrev(teamA)} vs ${abbrev(teamB)}`;
    document.getElementById('res-label-a').textContent = abbrev(teamA);
    document.getElementById('res-label-b').textContent = abbrev(teamB);
    document.getElementById('res-pct-a').textContent   = `${(data.probA * 100).toFixed(1)}%`;
    document.getElementById('res-pct-b').textContent   = `${(data.probB * 100).toFixed(1)}%`;

    setTimeout(() => {
      document.getElementById('res-bar-a').style.width = `${data.probA * 100}%`;
      document.getElementById('res-bar-b').style.width = `${data.probB * 100}%`;
    }, 80);

    const verdict   = document.getElementById('result-verdict');
    const isBet     = data.probA > 0.62 || data.probA < 0.38;
    verdict.textContent  = isBet
      ? `✓ HIGH CONFIDENCE — MODEL EDGE DETECTED`
      : `⚠ LOW EDGE — CAUTION ADVISED`;
    verdict.className = `result-verdict mono ${isBet ? 'bet' : 'caution'}`;

    renderFactors(data.factors || {}, abbrev(teamA), abbrev(teamB));

  } catch (err) {
    showError(err.message, placeholder, content, errorEl, loadingEl);
  }
}

// ── WHO'S PLAYING: roster checkboxes on the predict page ──
async function loadRoster(side) {
  const team = document.getElementById(`team-${side}`)?.value;
  const box  = document.getElementById(`roster-${side}`);
  if (!box) return;
  if (!team) {
    box.innerHTML = `<span class="roster-empty mono">Select Team ${side.toUpperCase()}</span>`;
    return;
  }
  box.innerHTML = '<span class="roster-empty mono">Loading roster...</span>';
  try {
    const res  = await fetch(`/api/roster?team=${encodeURIComponent(team)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `Server error ${res.status}`);
    box.innerHTML = `<div class="roster-team mono">${abbrev(team)}</div>`;
    data.players.forEach(p => {
      const label = document.createElement('label');
      label.className = 'radio-opt';
      label.title = `${p.minutes} min/game · rating ${p.rating}`;
      const input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = true;
      input.value = p.name;
      const name = document.createElement('span');
      name.textContent = `${p.name} · ${Math.round(p.minutes)}m`;
      label.append(input, name);
      box.append(label);
    });
  } catch (err) {
    box.innerHTML = `<span class="roster-empty mono">Roster unavailable: ${err.message}</span>`;
  }
}

function playersOut(side) {
  return [...document.querySelectorAll(`#roster-${side} input[type=checkbox]:not(:checked)`)].map(i => i.value);
}

['a', 'b'].forEach(side => {
  document.getElementById(`team-${side}`)?.addEventListener('change', () => loadRoster(side));
});

// Plain-English labels for the factors the model returns (Team A's point of view)
const FACTOR_LABELS = {
  Roster_Strength_Diff: 'Available player quality',
  Perimeter_Edge:       'Shooters vs perimeter D',
  Three_Matchup:        '3-pt matchup',
  Two_Matchup:          'Inside scoring matchup',
  TOV_Matchup:          'Turnover matchup',
  OREB_Matchup:         'Offensive rebounding',
  FT_Matchup:           'Free throw matchup',
  H2H_Margin:           'Head-to-head margin',
  Season_Diff_Dampened: 'Season record',
};

function renderFactors(factors, labelA, labelB) {
  const el = document.getElementById('result-factors');
  if (!el) return;
  el.innerHTML = '';
  Object.entries(FACTOR_LABELS).forEach(([key, label]) => {
    if (!(key in factors)) return;
    const v   = factors[key];
    const row = document.createElement('div');
    row.className = 'factor-row';
    const name = document.createElement('span');
    name.textContent = label;
    const edge = document.createElement('span');
    edge.className = v > 0 ? 'edge-a' : v < 0 ? 'edge-b' : '';
    edge.textContent = v === 0 ? 'EVEN' : `${v > 0 ? labelA : labelB} +${Math.abs(v).toFixed(Math.abs(v) < 1 ? 3 : 1)}`;
    row.append(name, edge);
    el.append(row);
  });
}

function showError(msg, placeholder, content, errorEl, loadingEl) {
  placeholder?.classList.add('hidden');
  content?.classList.add('hidden');
  loadingEl?.classList.add('hidden');
  if (errorEl) {
    errorEl.classList.remove('hidden');
    errorEl.textContent = `ERROR: ${msg}`;
  }
}

// ── HELPER: shorten team name to first word (e.g. "Milwaukee Bucks" → "MIL") ──
function abbrev(name) {
  // Return last word (usually the team nickname)
  const parts = name.trim().split(' ');
  return parts[parts.length - 1].toUpperCase();
}