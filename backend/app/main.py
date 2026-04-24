from flask import Flask, request, jsonify
from flask_cors import CORS
import joblib
import pandas as pd
import numpy as np
import os
import random
import json
from datetime import datetime, timezone
from nba_api.live.nba.endpoints import scoreboard

app = Flask(__name__)
# Enable CORS so your React/Node frontend can talk to this server
CORS(app)

# ==============================================================================
# 1. LOAD THE MODEL AND MEMORY
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, '../../backend/models/nba_model.pkl')
STATS_PATH = os.path.join(BASE_DIR, '../../backend/models/latest_team_stats.pkl')

LOG_PATH = os.path.join(BASE_DIR, '../../backend/data/prediction_log.jsonl')
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

try:
    model = joblib.load(MODEL_PATH)
    saved_stats = pd.read_pickle(STATS_PATH)
    print("✅ Flask API is live! Brain and Memory loaded successfully.")
except Exception as e:
    print(f"⚠️ Warning: Could not load models. Run your ML script first! Error: {e}")

def log_prediction(record: dict):
    try:
        with open(LOG_PATH, 'a') as f:
            f.write(json.dumps(record) + '\n')
    except Exception as e:
        print(f"⚠️ Could not write prediction log: {e}")

# ==============================================================================
# 2. THE PREDICTION ENDPOINT
# ==============================================================================
@app.route('/predict', methods=['POST'])
def get_prediction():
    try:
        data = request.get_json()
        team_a = data.get('team_a')
        team_b = data.get('team_b')
        home_team = data.get('home_team')

        print(f"\n🏀 Incoming Request: Team A: '{team_a}' | Team B: '{team_b}' | Home: '{home_team}'")

        try:
            t_a_id = saved_stats.loc[saved_stats['TEAM_NAME'] == team_a, 'TEAM_ID'].values[0]
            t_b_id = saved_stats.loc[saved_stats['TEAM_NAME'] == team_b, 'TEAM_ID'].values[0]
        except IndexError:
            print(f"❌ ERROR: The model database does not recognize one of these team names!")
            return jsonify({"error": "Team name mismatch"}), 400
        
        s_a = saved_stats[saved_stats['TEAM_ID'] == t_a_id].iloc[0]
        s_b = saved_stats[saved_stats['TEAM_ID'] == t_b_id].iloc[0]
        
        s_diff = s_a['Season_Win_Pct'] - s_b['Season_Win_Pct']
        dampened_diff = np.sign(s_diff) * np.sqrt(np.abs(s_diff))
        
        features = ['is_home', 'Off_Adv_SoS', 'Def_Adv_SoS', 'Rest_Adv', 'Season_Diff_Dampened']
        
        input_data = pd.DataFrame([[
            1 if team_a == home_team else 0,
            (s_a['ORtg_EWMA'] - s_b['DRtg_EWMA']) * (1 + s_b['Season_Win_Pct']),
            (s_b['ORtg_EWMA'] - s_a['DRtg_EWMA']) * (1 + s_a['Season_Win_Pct']),
            s_a['rest_days'] - s_b['rest_days'],
            dampened_diff
        ]], columns=features)
        
        prob_a = model.predict_proba(input_data)[0][1]
        
        return jsonify({
            "matchup": f"{team_a} vs {team_b}",
            "team_a": team_a,
            "team_b": team_b,
            "prob_a": round(prob_a, 4),
            "prob_b": round(1 - prob_a, 4)
        })

    except Exception as e:
        print(f"❌ SYSTEM ERROR: {str(e)}")
        return jsonify({"error": str(e)}), 400

# ==============================================================================
# 3. THE LIVE SCOREBOARD ENDPOINT (WITH TEST MODE)
# ==============================================================================
@app.route('/live-scores', methods=['GET'])
def get_live_scores():
    try:
        board = scoreboard.ScoreBoard()
        games = board.games.get_dict()
        
        live_games = []
        for game in games:
            live_games.append({
                "id": game['gameId'],
                "status": game['gameStatusText'], 
                "awayTeam": game['awayTeam']['teamName'],
                "awayScore": game['awayTeam']['score'],
                "homeTeam": game['homeTeam']['teamName'],
                "homeScore": game['homeTeam']['score']
            })

        # 🛑 DEV MODE: If the NBA has no games right now, send fake ones to test the UI!
        if len(live_games) == 0:
            print("⚠️ No real games found. Sending mock data for UI testing.")
            return jsonify([
                {
                    "id": "mock_1", "status": "Q3 04:12", 
                    "awayTeam": "Warriors", "awayScore": 112, 
                    "homeTeam": "Lakers", "homeScore": 108
                },
                {
                    "id": "mock_2", "status": "Final", 
                    "awayTeam": "Heat", "awayScore": 98, 
                    "homeTeam": "Celtics", "homeScore": 105
                },
                {
                    "id": "mock_3", "status": "8:30 PM ET", 
                    "awayTeam": "Suns", "awayScore": 0, 
                    "homeTeam": "Nuggets", "homeScore": 0
                }
            ])
            
        return jsonify(live_games)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==============================================================================
# 4. MODEL EXPLANATION ENDPOINT
# ==============================================================================
def _nick(name):
    return name.strip().split()[-1]

def generate_narrative(team_a, team_b, home_team, is_home, off_adv, def_adv,
                       rest_adv, season_diff, s_a, s_b, prob_a):
    lines = []
    favored = team_a if prob_a > 0.5 else team_b
    conf = abs(prob_a - 0.5) * 2

    if conf > 0.35:
        lines.append(f"The model strongly favors the {_nick(favored)} in this matchup.")
    elif conf > 0.15:
        lines.append(f"The model leans toward the {_nick(favored)}, though this figures to be competitive.")
    else:
        lines.append(f"This is a near toss-up — the model gives the {_nick(favored)} a razor-thin edge.")

    lines.append(f"The {_nick(home_team)} hold home-court advantage, one of the most consistent edges in the league.")

    a_ortg = float(s_a['ORtg_EWMA']); b_drtg = float(s_b['DRtg_EWMA'])
    a_drtg = float(s_a['DRtg_EWMA']); b_ortg = float(s_b['ORtg_EWMA'])

    if off_adv > 3:
        lines.append(f"Offensively, the {_nick(team_a)} (ORtg {a_ortg:.1f}) are exposing {_nick(team_b)}'s defense (DRtg {b_drtg:.1f}) — a clear scoring advantage.")
    elif off_adv < -3:
        lines.append(f"The {_nick(team_b)} defense (DRtg {b_drtg:.1f}) is built to slow {_nick(team_a)}'s offense (ORtg {a_ortg:.1f}) down.")
    else:
        lines.append(f"The offensive matchup is close — {_nick(team_a)}'s ORtg ({a_ortg:.1f}) vs {_nick(team_b)}'s DRtg ({b_drtg:.1f}) nearly cancel out.")

    if def_adv > 3:
        lines.append(f"However, {_nick(team_b)}'s offense (ORtg {b_ortg:.1f}) can stress {_nick(team_a)}'s defense (DRtg {a_drtg:.1f}), keeping this game within reach.")
    elif def_adv < -3:
        lines.append(f"On the other end, {_nick(team_a)}'s defense (DRtg {a_drtg:.1f}) can suffocate {_nick(team_b)}'s offense (ORtg {b_ortg:.1f}).")

    a_rest = int(s_a['rest_days']); b_rest = int(s_b['rest_days'])
    if rest_adv >= 2:
        lines.append(f"The {_nick(team_a)} arrive fresher — {a_rest} days of rest vs {b_rest} for {_nick(team_b)} — a fatigue edge that compounds over 48 minutes.")
    elif rest_adv <= -2:
        lines.append(f"The {_nick(team_b)} have the rest edge ({b_rest} days vs {a_rest}), which quietly shifts outcomes in the fourth quarter.")

    a_pct = float(s_a['Season_Win_Pct']); b_pct = float(s_b['Season_Win_Pct'])
    diff = abs(a_pct - b_pct)
    if diff > 0.15:
        better = team_a if a_pct > b_pct else team_b
        worse  = team_b if a_pct > b_pct else team_a
        lines.append(f"Season records favor the {_nick(better)} ({max(a_pct,b_pct):.0%} vs {min(a_pct,b_pct):.0%} for {_nick(worse)}), reflecting a real gap in consistency this year.")
    elif diff < 0.05:
        lines.append("Both teams carry nearly identical season records — on paper this is a genuine 50/50.")

    lines.append("Note: This model relies on rolling seasonal averages and does not adjust for real-time injuries or lineup changes — always factor in the latest news before acting on this projection.")
    return " ".join(lines)


@app.route('/explain', methods=['POST'])
def explain_prediction():
    try:
        data      = request.get_json()
        team_a    = data.get('team_a')
        team_b    = data.get('team_b')
        home_team = data.get('home_team')

        try:
            t_a_id = saved_stats.loc[saved_stats['TEAM_NAME'] == team_a, 'TEAM_ID'].values[0]
            t_b_id = saved_stats.loc[saved_stats['TEAM_NAME'] == team_b, 'TEAM_ID'].values[0]
        except IndexError:
            return jsonify({"error": "Team name not recognized"}), 400

        s_a = saved_stats[saved_stats['TEAM_ID'] == t_a_id].iloc[0]
        s_b = saved_stats[saved_stats['TEAM_ID'] == t_b_id].iloc[0]

        s_diff      = s_a['Season_Win_Pct'] - s_b['Season_Win_Pct']
        dampened    = float(np.sign(s_diff) * np.sqrt(np.abs(s_diff)))
        is_home_val = 1 if team_a == home_team else 0
        off_adv     = float((s_a['ORtg_EWMA'] - s_b['DRtg_EWMA']) * (1 + s_b['Season_Win_Pct']))
        def_adv     = float((s_b['ORtg_EWMA'] - s_a['DRtg_EWMA']) * (1 + s_a['Season_Win_Pct']))
        rest_adv    = float(s_a['rest_days']) - float(s_b['rest_days'])

        features   = ['is_home', 'Off_Adv_SoS', 'Def_Adv_SoS', 'Rest_Adv', 'Season_Diff_Dampened']
        raw_vals   = [is_home_val, off_adv, def_adv, rest_adv, dampened]
        input_data = pd.DataFrame([raw_vals], columns=features)

        prob_a      = float(model.predict_proba(input_data)[0][1])
        importances = model.feature_importances_

        home_nick = _nick(home_team)
        away_team = team_b if team_a == home_team else team_a
        away_nick = _nick(away_team)

        factor_labels = ['Home Court', 'Offensive Matchup', 'Defensive Pressure', 'Rest Advantage', 'Season Record']
        factor_descs  = [
            f"The {home_nick} are at home — crowd energy, no travel, familiar floor. {away_nick} must overcome this on the road.",
            f"{_nick(team_a)} ORtg {float(s_a['ORtg_EWMA']):.1f} vs {_nick(team_b)} DRtg {float(s_b['DRtg_EWMA']):.1f}. How well does {_nick(team_a)}'s offense exploit {_nick(team_b)}'s defense, scaled by opponent quality?",
            f"{_nick(team_b)} ORtg {float(s_b['ORtg_EWMA']):.1f} vs {_nick(team_a)} DRtg {float(s_a['DRtg_EWMA']):.1f}. How much scoring pressure does {_nick(team_b)}'s offense put on {_nick(team_a)}'s defense?",
            f"{_nick(team_a)}: {int(s_a['rest_days'])}d rest · {_nick(team_b)}: {int(s_b['rest_days'])}d rest. A rested team executes better late in games — fatigue is a silent factor.",
            f"Win%: {_nick(team_a)} {float(s_a['Season_Win_Pct']):.0%} vs {_nick(team_b)} {float(s_b['Season_Win_Pct']):.0%}. Dampened with √ to prevent overconfidence in lopsided records.",
        ]

        factors = []
        for i, (label, raw, imp, desc) in enumerate(zip(factor_labels, raw_vals, importances, factor_descs)):
            if i == 0:
                # is_home is binary: 1 = Team A home, 0 = Team B home.
                # Always carry the full importance as impact so home court shows on the chart
                # regardless of which team is home.
                favors_a = (is_home_val == 1)
                impact   = float(imp)
            elif i == 2:
                # Def_Adv: positive means Team B's offense beats Team A's defense → favors Team B
                favors_a = raw < 0
                impact   = abs(raw) * float(imp)
            else:
                favors_a = raw > 0
                impact   = abs(raw) * float(imp)

            factors.append({
                'name':        label,
                'description': desc,
                'raw':         round(raw, 3),
                'importance':  round(float(imp), 4),
                'impact':      round(impact, 4),
                'favors':      team_a if favors_a else team_b,
                'favors_a':    favors_a,
            })

        stats = {
            'a': { 'ortg': round(float(s_a['ORtg_EWMA']), 1), 'drtg': round(float(s_a['DRtg_EWMA']), 1),
                   'win_pct': round(float(s_a['Season_Win_Pct']) * 100, 1), 'rest': int(s_a['rest_days']) },
            'b': { 'ortg': round(float(s_b['ORtg_EWMA']), 1), 'drtg': round(float(s_b['DRtg_EWMA']), 1),
                   'win_pct': round(float(s_b['Season_Win_Pct']) * 100, 1), 'rest': int(s_b['rest_days']) },
        }
        narrative = generate_narrative(team_a, team_b, home_team, is_home_val,
                                       off_adv, def_adv, rest_adv, dampened, s_a, s_b, prob_a)

        response = {
            'team_a':    team_a,
            'team_b':    team_b,
            'home_team': home_team,
            'prob_a':    round(prob_a, 4),
            'prob_b':    round(1 - prob_a, 4),
            'factors':   factors,
            'stats':     stats,
            'narrative': narrative,
        }

        log_prediction({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'team_a':    team_a,
            'team_b':    team_b,
            'home_team': home_team,
            'prob_a':    round(prob_a, 4),
            'prob_b':    round(1 - prob_a, 4),
            'feature_values': {
                'is_home':               is_home_val,
                'off_adv_sos':           round(off_adv, 4),
                'def_adv_sos':           round(def_adv, 4),
                'rest_adv':              round(rest_adv, 4),
                'season_diff_dampened':  round(dampened, 4),
            },
            'feature_importances': {f['name']: f['importance'] for f in factors},
            'stats': stats,
        })

        return jsonify(response)
    except Exception as e:
        print(f"❌ EXPLAIN ERROR: {e}")
        return jsonify({"error": str(e)}), 500

# ==============================================================================
# 5. DEV-ONLY: SIMULATED LIVE GAME ENDPOINT
# Scores tick up randomly on every request so you can test UI updates locally.
# Hit /dev/live-scores instead of /live-scores while testing.
# ==============================================================================
_mock_state = {
    "away1": 98, "home1": 95,
    "away2": 54, "home2": 61,
    "quarter1": 3, "clock1": 240,
    "quarter2": 2, "clock2": 480,
}

@app.route('/dev/live-scores', methods=['GET'])
def dev_live_scores():
    s = _mock_state
    s["away1"] += random.randint(0, 3)
    s["home1"] += random.randint(0, 3)
    s["away2"] += random.randint(0, 2)
    s["home2"] += random.randint(0, 2)
    s["clock1"] = max(0, s["clock1"] - 5)
    s["clock2"] = max(0, s["clock2"] - 5)

    mins1, secs1 = divmod(s["clock1"], 60)
    mins2, secs2 = divmod(s["clock2"], 60)

    return jsonify([
        {
            "id": "dev_1",
            "status": f"Q{s['quarter1']} {mins1:02d}:{secs1:02d}",
            "awayTeam": "Warriors", "awayScore": s["away1"],
            "homeTeam": "Lakers",   "homeScore": s["home1"],
        },
        {
            "id": "dev_2",
            "status": f"Q{s['quarter2']} {mins2:02d}:{secs2:02d}",
            "awayTeam": "Heat",    "awayScore": s["away2"],
            "homeTeam": "Celtics", "homeScore": s["home2"],
        },
        {
            "id": "dev_3",
            "status": "7:30 PM ET",
            "awayTeam": "Suns", "awayScore": 0,
            "homeTeam": "Nuggets", "homeScore": 0,
        }
    ])

# ==============================================================================
# 5. START THE SERVER
# ==============================================================================
if __name__ == '__main__':
    app.run(debug=True, port=5001)