/* ============================================================
   COURTIQ — Records Page Charts
   Reads window.RECORDS_DATA injected by records.ejs.
   Renders: pie chart (win/loss) + line chart (daily accuracy).
   ============================================================ */

(function () {
  const data = window.RECORDS_DATA;
  if (!data) return;

  // CourtIQ palette
  const WIN    = '#00e5a0';
  const LOSS   = '#ff4d1c';
  const DIM    = '#2a2a3a';
  const MUTED  = '#6b6b80';
  const TEXT   = '#e8e8f0';

  Chart.defaults.color          = MUTED;
  Chart.defaults.font.family    = "'DM Mono', monospace";
  Chart.defaults.font.size      = 11;

  // ── PIE CHART ────────────────────────────────────────────────
  const pieCanvas = document.getElementById('pie-chart');
  if (pieCanvas && (data.correct + data.incorrect) > 0) {
    new Chart(pieCanvas, {
      type: 'doughnut',
      data: {
        labels: ['Correct', 'Incorrect'],
        datasets: [{
          data: [data.correct, data.incorrect],
          backgroundColor: [WIN, LOSS],
          borderColor:     ['#0a0a0f'],
          borderWidth:     3,
          hoverOffset:     6,
        }]
      },
      options: {
        responsive:  true,
        cutout:      '62%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              padding:    16,
              color:      MUTED,
              font:       { size: 10, family: "'DM Mono', monospace" },
              usePointStyle: true,
              pointStyleWidth: 8,
            }
          },
          tooltip: {
            callbacks: {
              label: ctx => ` ${ctx.label}: ${ctx.parsed} (${((ctx.parsed / (data.correct + data.incorrect)) * 100).toFixed(1)}%)`
            }
          }
        }
      }
    });
  }

  // ── LINE CHART ───────────────────────────────────────────────
  const lineCanvas = document.getElementById('line-chart');
  if (!lineCanvas) return;

  // Filter to days that have at least one resolved game
  const daysWithData = data.byDate.filter(d => d.total > 0);

  if (daysWithData.length === 0) {
    lineCanvas.parentElement.innerHTML =
      '<p style="font-family:\'DM Mono\',monospace;font-size:0.65rem;letter-spacing:0.1em;color:var(--text-dim);text-align:center;padding:2rem 0">NO RESOLVED GAMES YET</p>';
    return;
  }

  // Build dataset — null for days with no games (line breaks instead of dropping to 0)
  const labels   = data.byDate.map(d => d.date.slice(5)); // "MM-DD"
  const accData  = data.byDate.map(d => d.total > 0 ? parseFloat((d.accuracy * 100).toFixed(1)) : null);

  // Overall average as a reference line
  const overallPct = data.accuracy !== null ? parseFloat((data.accuracy * 100).toFixed(1)) : null;

  new Chart(lineCanvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label:           'Daily Accuracy %',
          data:            accData,
          borderColor:     WIN,
          backgroundColor: 'rgba(0,229,160,0.08)',
          borderWidth:     2,
          pointRadius:     4,
          pointBackgroundColor: WIN,
          pointBorderColor:    '#0a0a0f',
          pointBorderWidth:    2,
          tension:         0.3,
          fill:            true,
          spanGaps:        false,   // gaps on days with no games
        },
        ...(overallPct !== null ? [{
          label:       'Overall Average',
          data:        labels.map(() => overallPct),
          borderColor: LOSS,
          borderWidth: 1,
          borderDash:  [4, 4],
          pointRadius: 0,
          fill:        false,
          tension:     0,
        }] : [])
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          grid:  { color: DIM },
          ticks: { color: MUTED, maxTicksLimit: 8, font: { size: 10 } },
        },
        y: {
          min:  0,
          max:  100,
          grid: { color: DIM },
          ticks: {
            color:    MUTED,
            font:     { size: 10 },
            callback: v => v + '%',
            stepSize: 25,
          },
        }
      },
      plugins: {
        legend: {
          labels: {
            color: MUTED,
            font:  { size: 10, family: "'DM Mono', monospace" },
            usePointStyle: true,
            pointStyleWidth: 8,
          }
        },
        tooltip: {
          callbacks: {
            label: ctx => ctx.parsed.y !== null ? ` ${ctx.dataset.label}: ${ctx.parsed.y}%` : ' No games'
          }
        }
      }
    }
  });
})();
