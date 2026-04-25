"""
flask_api.py — Python model server
------------------------------------
Run this alongside the Node.js server:
  python flask_api.py

Endpoints:
  POST /predict              → runs the NBA win probability model
  GET  /games/today          → returns today's NBA scoreboard
  GET  /games/date/YYYY-MM-DD → returns scoreboard for a specific past date
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
from datetime import date, datetime

from model import model, df_processed, features, predict_raw

from nba_api.stats.endpoints import scoreboardv2, leaguegamefinder
from nba_api.stats.static import teams as nba_teams_static

app = Flask(__name__)
CORS(app)


# ── shared scoreboard helper ───────────────────────────────────
def fetch_scoreboard(game_date=None):
    """
    Fetch and parse a scoreboard for a given date.
    game_date: MM/DD/YYYY string for nba_api, or None for today.
    """
    board = scoreboardv2.ScoreboardV2(game_date=game_date) if game_date else scoreboardv2.ScoreboardV2()

    game_header = board.game_header.get_data_frame()
    line_score  = board.line_score.get_data_frame()
    all_teams   = {t['id']: t for t in nba_teams_static.get_teams()}
    games_out   = []

    for _, row in game_header.iterrows():
        gid       = row['GAME_ID']
        status_id = row['GAME_STATUS_ID']  # 1=upcoming, 2=live, 3=final

        scores = line_score[line_score['GAME_ID'] == gid]
        if len(scores) < 2:
            continue

        away_row = scores.iloc[0]
        home_row = scores.iloc[1]

        status_map = {1: 'upcoming', 2: 'live', 3: 'final'}

        games_out.append({
            'gameId':     gid,
            'awayTeam':   away_row['TEAM_CITY_NAME'] + ' ' + away_row['TEAM_NAME'],
            'awayAbbr':   away_row['TEAM_ABBREVIATION'],
            'awayScore':  int(away_row['PTS']) if away_row['PTS'] else None,
            'homeTeam':   home_row['TEAM_CITY_NAME'] + ' ' + home_row['TEAM_NAME'],
            'homeAbbr':   home_row['TEAM_ABBREVIATION'],
            'homeScore':  int(home_row['PTS']) if home_row['PTS'] else None,
            'status':     status_map.get(status_id, 'upcoming'),
            'statusText': str(row.get('GAME_STATUS_TEXT', '')).strip(),
        })

    return games_out


# ── /predict ──────────────────────────────────────────────────
@app.route('/predict', methods=['POST'])
def predict():
    data      = request.get_json()
    team_a    = data.get('team_a')
    team_b    = data.get('team_b')
    home_team = data.get('home_team')

    if not all([team_a, team_b, home_team]):
        return jsonify({'error': 'team_a, team_b, home_team required'}), 400

    try:
        prob_a = predict_raw(team_a, team_b, home_team)
        return jsonify({'prob_a': round(prob_a, 4), 'prob_b': round(1 - prob_a, 4)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ── /games/today ──────────────────────────────────────────────
@app.route('/games/today', methods=['GET'])
def games_today():
    try:
        return jsonify({'games': fetch_scoreboard()})
    except Exception as e:
        return jsonify({'error': str(e), 'games': []}), 500


# ── /games/date/<YYYY-MM-DD> ──────────────────────────────────
# Uses LeagueGameFinder instead of ScoreboardV2 — ScoreboardV2 does not
# return final scores for past dates, only the pre-game scheduled state.
@app.route('/games/date/<string:date_str>', methods=['GET'])
def games_by_date(date_str):
    try:
        dt       = datetime.strptime(date_str, '%Y-%m-%d')
        nba_date = dt.strftime('%m/%d/%Y')

        finder = leaguegamefinder.LeagueGameFinder(
            date_from_nullable=nba_date,
            date_to_nullable=nba_date,
            league_id_nullable='00'
        )
        df = finder.get_data_frames()[0]

        if df.empty:
            return jsonify({'games': []})

        # LeagueGameFinder returns one row per team per game — pair them up by GAME_ID
        games_out = []
        seen = set()

        for game_id, group in df.groupby('GAME_ID'):
            if game_id in seen or len(group) < 2:
                continue
            seen.add(game_id)

            # Away team has '@' in MATCHUP (e.g. "BOS @ PHI"), home team has 'vs.'
            away_row = group[group['MATCHUP'].str.contains('@')].iloc[0]
            home_row = group[group['MATCHUP'].str.contains('vs.')].iloc[0]

            away_pts = int(away_row['PTS']) if away_row['PTS'] is not None else None
            home_pts = int(home_row['PTS']) if home_row['PTS'] is not None else None

            # WL column tells us if the game is final
            is_final = away_row['WL'] in ('W', 'L')

            games_out.append({
                'gameId':     game_id,
                'awayTeam':   away_row['TEAM_NAME'],
                'awayAbbr':   away_row['TEAM_ABBREVIATION'],
                'awayScore':  away_pts,
                'homeTeam':   home_row['TEAM_NAME'],
                'homeAbbr':   home_row['TEAM_ABBREVIATION'],
                'homeScore':  home_pts,
                'status':     'final' if is_final else 'upcoming',
                'statusText': 'Final' if is_final else '',
            })

        return jsonify({'games': games_out})

    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD.', 'games': []}), 400
    except Exception as e:
        return jsonify({'error': str(e), 'games': []}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
