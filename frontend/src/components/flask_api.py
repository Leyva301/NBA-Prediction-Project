"""
flask_api.py — Python model server
------------------------------------
Run this alongside the Node.js server:
  python flask_api.py

Endpoints:
  POST /predict       → runs the NBA win probability model
  GET  /games/today   → returns today's NBA scoreboard
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
from datetime import date

# Import your existing model code
# Assumes model.py exports: model, df_processed, predict_pro_raw, features
# (see notes below on how to refactor your original script)
from model import model, df_processed, features, predict_raw

# nba_api for live scoreboard
from nba_api.stats.endpoints import scoreboardv2
from nba_api.stats.static import teams as nba_teams_static

app = Flask(__name__)
CORS(app)  # Allow Node.js server to call this

# ── /predict ──────────────────────────────────────────────────
@app.route('/predict', methods=['POST'])
def predict():
    data     = request.get_json()
    team_a   = data.get('team_a')
    team_b   = data.get('team_b')
    home_team= data.get('home_team')

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
        board       = scoreboardv2.ScoreboardV2()
        game_header = board.game_header.get_data_frame()
        line_score  = board.line_score.get_data_frame()

        all_teams  = {t['id']: t for t in nba_teams_static.get_teams()}
        games_out  = []

        for _, row in game_header.iterrows():
            gid       = row['GAME_ID']
            status_id = row['GAME_STATUS_ID']  # 1=upcoming, 2=live, 3=final

            scores = line_score[line_score['GAME_ID'] == gid]
            if len(scores) < 2:
                continue

            away_row = scores.iloc[0]
            home_row = scores.iloc[1]

            def abbr(team_id):
                t = all_teams.get(team_id)
                return t['abbreviation'] if t else '???'

            status_map = {1: 'upcoming', 2: 'live', 3: 'final'}
            status_txt = row.get('GAME_STATUS_TEXT', '')

            games_out.append({
                'gameId':      gid,
                'awayTeam':    away_row['TEAM_CITY_NAME'] + ' ' + away_row['TEAM_NAME'],
                'awayAbbr':    away_row['TEAM_ABBREVIATION'],
                'awayScore':   int(away_row['PTS']) if away_row['PTS'] else None,
                'homeTeam':    home_row['TEAM_CITY_NAME'] + ' ' + home_row['TEAM_NAME'],
                'homeAbbr':    home_row['TEAM_ABBREVIATION'],
                'homeScore':   int(home_row['PTS']) if home_row['PTS'] else None,
                'status':      status_map.get(status_id, 'upcoming'),
                'statusText':  status_txt.strip(),
            })

        return jsonify({'games': games_out})

    except Exception as e:
        return jsonify({'error': str(e), 'games': []}), 500


if __name__ == '__main__':
    # Port 5000 — keep Node.js on 3000
    app.run(host='0.0.0.0', port=5000, debug=False)