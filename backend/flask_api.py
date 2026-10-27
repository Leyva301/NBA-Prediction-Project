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

import os

from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
from zoneinfo import ZoneInfo

from model import predict_raw

from nba_api.stats.endpoints import scoreboardv3, leaguegamefinder
from nba_api.stats.static import teams as nba_teams_static

app = Flask(__name__)
CORS(app)

# Map TEAM_ID → official full name. The live endpoints call the Clippers
# "LA Clippers", which doesn't match the "Los Angeles Clippers" the model expects.
TEAM_NAMES = {t['id']: t['full_name'] for t in nba_teams_static.get_teams()}


def to_score(value):
    """int score, or None when the API hasn't filled one in yet."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def nba_today():
    """Today's date in US Eastern time — the NBA schedule's calendar."""
    return datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d')


# ── shared scoreboard helper ───────────────────────────────────
def fetch_scoreboard(game_date=None):
    """
    Fetch and parse a scoreboard for a given date.
    game_date: YYYY-MM-DD string, or None for today.
    ScoreboardV2 is deprecated in nba_api and returns empty line scores for
    early-season games, so this uses ScoreboardV3.
    """
    board = scoreboardv3.ScoreboardV3(game_date=game_date or nba_today(), timeout=30)

    game_header = board.game_header.get_data_frame()
    line_score  = board.line_score.get_data_frame()
    status_map  = {1: 'upcoming', 2: 'live', 3: 'final'}
    games_out   = []

    for _, row in game_header.iterrows():
        gid       = row['gameId']
        status_id = int(row['gameStatus'])  # 1=upcoming, 2=live, 3=final

        scores = line_score[line_score['gameId'] == gid]
        if len(scores) < 2:
            continue

        # ScoreboardV3 lists the home team first, then the away team
        home_row = scores.iloc[0]
        away_row = scores.iloc[1]
        started  = status_id in (2, 3)

        games_out.append({
            'gameId':     gid,
            'awayTeam':   TEAM_NAMES.get(away_row['teamId'], f"{away_row['teamCity']} {away_row['teamName']}"),
            'awayAbbr':   away_row['teamTricode'],
            'awayScore':  to_score(away_row['score']) if started else None,
            'homeTeam':   TEAM_NAMES.get(home_row['teamId'], f"{home_row['teamCity']} {home_row['teamName']}"),
            'homeAbbr':   home_row['teamTricode'],
            'homeScore':  to_score(home_row['score']) if started else None,
            'status':     status_map.get(status_id, 'upcoming'),
            'statusText': str(row.get('gameStatusText', '')).strip(),
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
                'awayTeam':   TEAM_NAMES.get(away_row['TEAM_ID'], away_row['TEAM_NAME']),
                'awayAbbr':   away_row['TEAM_ABBREVIATION'],
                'awayScore':  away_pts,
                'homeTeam':   TEAM_NAMES.get(home_row['TEAM_ID'], home_row['TEAM_NAME']),
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
    # 5050, not Flask's usual 5000: macOS AirPlay Receiver listens on 5000
    app.run(host='0.0.0.0', port=int(os.environ.get('FLASK_PORT', 5050)), debug=False)
