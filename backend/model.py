"""
model.py — NBA Prediction Model
--------------------------------
Fetches team and player game logs, builds the matchup features (features.py),
and trains the win-probability model.
flask_api.py imports: model, features, predict_raw, predict_detail, team_rotation

Run directly to print a backtest and a sample prediction:
  python model.py

To see which factor groups actually help, run:
  python compare_features.py
"""
import os
from datetime import date

import pandas as pd
import numpy as np
from nba_api.stats.endpoints import leaguegamelog
from nba_api.stats.static import teams
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss

import features as fx

# ==============================================================================
# FEATURE SWITCHES
# Turn a factor group off (False) if compare_features.py shows it hurts.
# 'base' is the original model and always stays on.
# To drop a single feature instead of a whole group, add its name to
# DISABLED_FEATURES (names are listed in features.FEATURE_GROUP_COLUMNS).
#
# You can also switch groups off without editing this file:
#   COURTIQ_DISABLE=head_to_head,perimeter python flask_api.py
# ==============================================================================
FEATURE_GROUPS = {
    'style_matchups':  True,   # 3-pt / paint / turnovers / rebounds / FTs vs what the defense allows
    'roster_strength': True,   # quality of the players actually available
    'perimeter':       True,   # available shooters' skill vs the opponent's 3-pt defense
    'head_to_head':    True,   # margin in earlier meetings this season and last
}
DISABLED_FEATURES = set()

for _name in filter(None, os.environ.get('COURTIQ_DISABLE', '').split(',')):
    if _name.strip() in FEATURE_GROUPS:
        FEATURE_GROUPS[_name.strip()] = False
    else:
        DISABLED_FEATURES.add(_name.strip())


def feature_list(groups=None, disabled=()):
    """Model columns for the given groups (default: the switches above)."""
    groups = FEATURE_GROUPS if groups is None else groups
    on = ['base'] + [g for g, enabled in groups.items() if enabled]
    return [c for g in on for c in fx.FEATURE_GROUP_COLUMNS[g] if c not in disabled]


features = feature_list(disabled=DISABLED_FEATURES)

# ==============================================================================
# STEP 1: DATA ACQUISITION
# Official NBA game logs for the current and previous season: one row per team
# per game, and one row per player per game (who played and how well).
# ==============================================================================
def season_string(start_year: int) -> str:
    """2025 -> '2025-26'"""
    return f"{start_year}-{(start_year + 1) % 100:02d}"

def current_season_start(today: date = None) -> int:
    """NBA seasons tip off in October, so Jan-Sep belong to the season that started last year."""
    today = today or date.today()
    return today.year if today.month >= 10 else today.year - 1

CURRENT_SEASON = season_string(current_season_start())
PREVIOUS_SEASON = season_string(current_season_start() - 1)

def fetch_season(season: str, kind: str = 'T') -> pd.DataFrame:
    """kind 'T' = team game logs, 'P' = player game logs."""
    log = leaguegamelog.LeagueGameLog(player_or_team_abbreviation=kind, season=season, timeout=60)
    return log.get_data_frames()[0]

print(f"Fetching {PREVIOUS_SEASON} and {CURRENT_SEASON} Season Data...")
df_raw = pd.concat([fetch_season(PREVIOUS_SEASON), fetch_season(CURRENT_SEASON)], ignore_index=True)
df_players_raw = pd.concat([fetch_season(PREVIOUS_SEASON, 'P'), fetch_season(CURRENT_SEASON, 'P')],
                           ignore_index=True)

# ==============================================================================
# STEP 2-3: FEATURE ENGINEERING + MATCHUP CONSTRUCTION (see features.py)
# ==============================================================================
LEAGUE_3P = df_raw['FG3M'].sum() / df_raw['FG3A'].sum()

team_table = fx.build_team_table(df_raw)
player_table = fx.build_player_table(df_players_raw, LEAGUE_3P)
df_final = fx.build_training_set(team_table, player_table, LEAGUE_3P)
team_state = fx.team_current_state(team_table)

# ==============================================================================
# STEP 4: MODEL TRAINING
# A Random Forest (an ensemble of 200 decision trees) learns patterns.
# ==============================================================================
def new_model(n_estimators=200):
    return RandomForestClassifier(n_estimators=n_estimators, max_depth=7, min_samples_leaf=5,
                                  random_state=42, n_jobs=-1)

model = new_model()
model.fit(df_final[features], df_final['Win'])

# ==============================================================================
# STEP 5: BACKTESTING (Validation)
# Walk forward through the last `days` game dates: retrain on every game before
# a block of dates, predict that block, move on. Each game is scored once (from
# the home team's side) so mirrored rows don't count twice.
# ==============================================================================
def walk_forward(df_back, cols, days=100, retrain_every=7, n_estimators=100):
    dates = sorted(df_back['GAME_DATE'].unique())[-days:]
    probs, wins = [], []

    for i in range(0, len(dates), retrain_every):
        block = dates[i:i + retrain_every]
        train = df_back[df_back['GAME_DATE'] < block[0]]
        test = df_back[df_back['GAME_DATE'].isin(block) & (df_back['is_home'] == 1)]
        if len(train) < 200 or len(test) == 0:
            continue
        m = new_model(n_estimators)
        m.fit(train[cols], train['Win'])
        probs.extend(m.predict_proba(test[cols])[:, 1])
        wins.extend(test['Win'])

    probs, wins = np.array(probs), np.array(wins)
    return {
        'games': len(wins),
        'accuracy': accuracy_score(wins, probs > 0.5),
        # Brier / log loss check whether "70%" really wins 70% of the time (lower is better)
        'brier': brier_score_loss(wins, probs),
        'log_loss': log_loss(wins, np.clip(probs, 1e-6, 1 - 1e-6), labels=[0, 1]),
    }

def run_final_backtest(df_back, days=100):
    r = walk_forward(df_back, features, days=days)
    print(f"\n--- {days}-DAY WALK-FORWARD BACKTEST ({r['games']} games) ---")
    print(f"Features: {', '.join(features)}")
    print(f"Historical Accuracy: {r['accuracy']:.2%}")
    print(f"Brier Score (Calibration): {r['brier']:.4f}")

# ==============================================================================
# STEP 6: LIVE PREDICTION INTERFACE
# ==============================================================================
def team_id(name: str) -> int:
    name = name.replace("TrailBlazers", "Trail Blazers")
    match = [t for t in teams.get_teams() if t['full_name'] == name]
    if not match:
        raise ValueError(f"Unknown team: {name}")
    return match[0]['id']

def team_rotation(name: str) -> list:
    """The players the model currently expects to play for a team."""
    roster = fx.current_rotation(player_table, team_table, team_id(name))
    roster = roster[roster['mins'] >= fx.ROTATION_MINUTES]
    return [{'name': r.PLAYER_NAME, 'minutes': round(float(r.mins), 1),
             'rating': round(float(r.rate * 36), 1)} for r in roster.itertuples()]

def _side(tid, opp_tid, is_home, game_day, out):
    """One team's pre-game state for a matchup happening on game_day."""
    s = team_state.loc[tid]
    roster = fx.current_rotation(player_table, team_table, tid)
    out = {o.strip().lower() for o in out or []}
    roster = roster[~roster['PLAYER_NAME'].str.lower().isin(out)]

    lineup = fx.lineup_strength(roster.assign(key=0), 'key', player_table.attrs['replacement'], LEAGUE_3P)
    lineup = lineup.iloc[0].to_dict() if len(lineup) else fx.empty_lineup(player_table.attrs['replacement'])

    h2h_mean, h2h_games = fx.head_to_head(team_table, tid, opp_tid)
    row = {c: s[c] for c in fx.TEAM_STATE_COLS}
    row.update(lineup, is_home=is_home, H2H_Mean=h2h_mean, H2H_Games=h2h_games,
               rest_days=float((game_day - s['LAST_GAME']).days))
    return pd.DataFrame([row])

def predict_detail(team_a: str, team_b: str, home_team: str, out_a=None, out_b=None, game_day=None) -> dict:
    """
    Win probability for team_a plus the matchup factors behind it.
    out_a / out_b: player names who won't play (injuries, rest).
    """
    a, b, home = team_id(team_a), team_id(team_b), team_id(home_team)
    game_day = pd.Timestamp(game_day or date.today())

    A = _side(a, b, int(home == a), game_day, out_a)
    B = _side(b, a, int(home == b), game_day, out_b)
    f_ab = fx.matchup_features(A, B, LEAGUE_3P)
    f_ba = fx.matchup_features(B, A, LEAGUE_3P)

    # Ask the model from both sides and average, so P(A) + P(B) = 1 exactly
    p_ab = model.predict_proba(f_ab[features])[0][1]
    p_ba = model.predict_proba(f_ba[features])[0][1]
    prob_a = float((p_ab + (1 - p_ba)) / 2)

    return {'prob_a': prob_a,
            'factors': {c: round(float(f_ab[c].iloc[0]), 4) for c in features}}

def predict_raw(team_a: str, team_b: str, home_team: str, out_a=None, out_b=None) -> float:
    """Returns win probability for team_a. Raises on bad team names."""
    return predict_detail(team_a, team_b, home_team, out_a, out_b)['prob_a']

if __name__ == '__main__':
    run_final_backtest(df_final)
    prob = predict_raw("New Orleans Pelicans", "Sacramento Kings", "Sacramento Kings")
    print(f"\nPROJECTION: New Orleans Pelicans ({prob:.1%}) vs Sacramento Kings ({1 - prob:.1%})")
