import pandas as pd
import numpy as np
from nba_api.stats.endpoints import leaguegamelog
from nba_api.stats.static import teams
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, brier_score_loss

# ==============================================================================
# STEP 1: DATA ACQUISITION
# We pull the official NBA game logs for every team in the current season.
# ==============================================================================
print("Fetching 2025-26 Season Data...")
log = leaguegamelog.LeagueGameLog(player_or_team_abbreviation='T', season='2025-26')
df_raw = log.get_data_frames()[0]

# ==============================================================================
# STEP 2: FEATURE ENGINEERING (Team Level)
# This function calculates advanced stats and rolling averages for each team.
# ==============================================================================
def process_data_pro(df):
    df = df.copy()
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df = df.sort_values(['TEAM_ID', 'GAME_DATE'])
    
    # CALCULATE ADVANCED RATINGS
    # We estimate possessions (poss) to find points per 100 possessions (ORtg/DRtg).
    # This is more accurate than raw PPG because it ignores game pace.
    poss = df['FGA'] + 0.44 * df['FTA'] - df['OREB'] + df['TOV']
    df['ORtg'] = (df['PTS'] / poss) * 100
    df['DRtg'] = ((df['PTS'] - df['PLUS_MINUS']) / poss) * 100
    df['Win'] = df['WL'].apply(lambda x: 1 if x == 'W' else 0)
    
    # CALCULATE SITUATIONAL FACTORS
    # 'is_home' identifies home-court advantage.
    # 'rest_days' calculates time since the last game to account for fatigue.
    df['is_home'] = df['MATCHUP'].apply(lambda x: 0 if '@' in x else 1)
    df['rest_days'] = df.groupby('TEAM_ID')['GAME_DATE'].diff().dt.days.fillna(4)
    
    # CALCULATE SEASON PERFORMANCE (BASELINE)
    # The team's overall win percentage up until that game.
    df['Season_Win_Pct'] = df.groupby('TEAM_ID')['Win'].transform(lambda x: x.shift(1).expanding().mean())

    # CALCULATE RECENT FORM (EWMA)
    # Exponentially Weighted Moving Average gives more "weight" to the most recent 10 games.
    # This captures if a team is currently on a hot or cold streak.
    df["ORtg_EWMA"] = df.groupby("TEAM_ID")["ORtg"].transform(lambda x: x.shift(1).ewm(span=10).mean())
    df["DRtg_EWMA"] = df.groupby("TEAM_ID")["DRtg"].transform(lambda x: x.shift(1).ewm(span=10).mean())
    
    return df.dropna()

df_processed = process_data_pro(df_raw)

# ==============================================================================
# STEP 3: MATCHUP CONSTRUCTION
# We take the team stats and merge them with their opponent's stats for every game.
# ==============================================================================
match_cols = ['GAME_ID', 'GAME_DATE', 'TEAM_ID', 'TEAM_NAME', 'Win', 'is_home', 'rest_days', 'Season_Win_Pct', 'ORtg_EWMA', 'DRtg_EWMA']
matchups = df_processed[match_cols]

# Create a second dataframe for opponents and rename columns to avoid confusion
opponents = matchups.copy().rename(columns={
    'TEAM_ID': 'OPP_ID', 'TEAM_NAME': 'OPP_NAME', 'Win': 'OPP_Win', 
    'is_home': 'OPP_is_home', 'rest_days': 'OPP_rest', 
    'Season_Win_Pct': 'OPP_Win_Pct', 'ORtg_EWMA': 'OPP_ORtg', 'DRtg_EWMA': 'OPP_DRtg'
})

# Merge so each row contains Team A vs Team B data
df_final = pd.merge(matchups, opponents, on=['GAME_ID', 'GAME_DATE'])
df_final = df_final[df_final['TEAM_ID'] != df_final['OPP_ID']]

# CALCULATE MATCHUP ADVANTAGES
# Off_Adv_SoS: How well Team A scores vs Team B's defense, adjusted for Team B's strength.
df_final['Off_Adv_SoS'] = (df_final['ORtg_EWMA'] - df_final['OPP_DRtg']) * (1 + df_final['OPP_Win_Pct'])
df_final['Def_Adv_SoS'] = (df_final['OPP_ORtg'] - df_final['DRtg_EWMA']) * (1 + df_final['OPP_Win_Pct'])
df_final['Rest_Adv'] = df_final['rest_days'] - df_final['OPP_rest']

# NON-LINEAR DAMPENING
# We "squish" the Season Win Pct difference using a square root. 
# This prevents the model from being overconfident when a #1 seed plays a #10 seed.
diff = df_final['Season_Win_Pct'] - df_final['OPP_Win_Pct']
df_final['Season_Diff_Dampened'] = np.sign(diff) * np.sqrt(np.abs(diff))

# ==============================================================================
# STEP 4: MODEL TRAINING
# We use a Random Forest (an ensemble of 200 decision trees) to learn patterns.
# ==============================================================================
features = ['is_home', 'Off_Adv_SoS', 'Def_Adv_SoS', 'Rest_Adv', 'Season_Diff_Dampened']
X = df_final[features]
y = df_final['Win']

model = RandomForestClassifier(n_estimators=200, max_depth=7, min_samples_leaf=5, random_state=42)
model.fit(X, y)

# ==============================================================================
# STEP 5: BACKTESTING (Validation)
# We test the model by simulating it day-by-day over the last 20 days.
# ==============================================================================
def run_final_backtest(df_back, days=20):
    unique_dates = sorted(df_back['GAME_DATE'].unique())[-days:]
    daily_acc, daily_brier = [], []
    
    for d in unique_dates:
        # Only "train" on games before the day we are predicting
        train = df_back[df_back['GAME_DATE'] < d]
        test = df_back[df_back['GAME_DATE'] == d]
        if len(train) < 200 or len(test) == 0: continue
        
        m = RandomForestClassifier(n_estimators=100, max_depth=7, random_state=42)
        m.fit(train[features], train['Win'])
        
        # Brier Score checks if our 70% probability is actually accurate in reality
        probs = m.predict_proba(test[features])[:, 1]
        daily_acc.append(accuracy_score(test['Win'], (probs > 0.5).astype(int)))
        daily_brier.append(brier_score_loss(test['Win'], probs))
        
    print(f"\n--- 20-DAY BACKTEST RESULTS ---")
    print(f"Historical Accuracy: {np.mean(daily_acc):.2%}")
    print(f"Brier Score (Calibration): {np.mean(daily_brier):.4f}")

# ==============================================================================
# STEP 6: LIVE PREDICTION INTERFACE
# Input two teams to get the win probability for tonight's matchup.
# ==============================================================================
def predict_pro(team_a, team_b, home_team):
    try:
        # Sanitize names (Handle common space/typo issues)
        def clean(name): return name.replace("TrailBlazers", "Trail Blazers")
        team_a, team_b, home_team = clean(team_a), clean(team_b), clean(home_team)

        t_a_id = [t for t in teams.get_teams() if t['full_name'] == team_a][0]['id']
        t_b_id = [t for t in teams.get_teams() if t['full_name'] == team_b][0]['id']
        
        # Pull the absolute latest stats available for both teams
        s_a = df_processed[df_processed['TEAM_ID'] == t_a_id].iloc[-1]
        s_b = df_processed[df_processed['TEAM_ID'] == t_b_id].iloc[-1]
        
        s_diff = s_a['Season_Win_Pct'] - s_b['Season_Win_Pct']
        dampened_diff = np.sign(s_diff) * np.sqrt(np.abs(s_diff))
        
        # Build the feature vector for the prediction
        input_data = pd.DataFrame([[
            1 if team_a == home_team else 0,
            (s_a['ORtg_EWMA'] - s_b['DRtg_EWMA']) * (1 + s_b['Season_Win_Pct']),
            (s_b['ORtg_EWMA'] - s_a['DRtg_EWMA']) * (1 + s_a['Season_Win_Pct']),
            s_a['rest_days'] - s_b['rest_days'],
            dampened_diff
        ]], columns=features)
        
        prob = model.predict_proba(input_data)[0][1]
        print(f"\nPROJECTION: {team_a} ({prob:.1%}) vs {team_b} ({1-prob:.1%})")
        print(f"ADVICE: {'BET' if prob > 0.62 or prob < 0.38 else 'CAUTION'} - Confidence threshold check.")
    except Exception as e:
        print(f"Prediction Error: {e}")

# ==============================================================================
# EXECUTION LOGIC
# ==============================================================================
run_final_backtest(df_final)
predict_pro("Charlotte Hornets", "Brooklyn Nets", "Brooklyn Nets")