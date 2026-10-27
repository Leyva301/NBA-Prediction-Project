"""
features.py — Matchup factors for the NBA model
-----------------------------------------------
Turns raw game logs into the numbers the model learns from. model.py decides
which of them are switched on (see FEATURE_GROUPS there).

Every number used for training is "pre-game": it only uses games that happened
before the game being predicted, so the backtest can't peek at the answer.
Each table also keeps a "_cur" (current) copy that includes the latest game,
which is what live predictions use.

Factor groups:
  base             win %, offense/defense ratings, home court, rest
  style_matchups   how each team's style (3-pt volume/accuracy, paint scoring,
                   turnovers, offensive rebounding, free throws) lines up with
                   what the other team's defense usually allows
  roster_strength  the quality of the players actually available, from each
                   player's recent box scores, weighted by their usual minutes
  perimeter        how good the available shooters are, against the 3-pt %
                   the other defense allows
  head_to_head     average margin in earlier meetings between the two teams
"""
import numpy as np
import pandas as pd

# ── Tunable constants ──────────────────────────────────────────
TEAM_SPAN = 10             # EWMA span (games) for team stats
PLAYER_SPAN = 15           # EWMA span (games) for player stats
ROTATION_MINUTES = 10      # players expected to play fewer minutes are ignored
GAME_MINUTES = 240         # 5 players x 48 minutes
PLAYER_SHRINK_GAMES = 5    # new players are pulled toward replacement level
THREE_PCT_SHRINK = 75      # 3-pt attempts of league-average shooting added to each player
H2H_SHRINK = 3             # head-to-head margin is scaled by n / (n + H2H_SHRINK)
RECENT_TEAM_GAMES = 3      # live rotation = players who appeared in the team's last N games

# Style stats measured for each team's offense and for the offense it allows.
STYLE_STATS = ['TPAr', 'TP_PCT', 'TWO_PCT', 'TOV_RATE', 'OREB_PCT', 'FT_RATE']


def _ewm_pair(grouped, col, span):
    """(pre-game, current) EWMA of a column within each group."""
    cur = grouped[col].transform(lambda x: x.ewm(span=span).mean())
    return cur, cur.groupby(grouped.ngroup()).shift(1)


# ==============================================================================
# TEAM TABLE — one row per team per game
# ==============================================================================
def build_team_table(df_team: pd.DataFrame) -> pd.DataFrame:
    df = df_team.copy()
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])

    # Attach the opponent's box score from the same game
    box = ['TEAM_ID', 'FGM', 'FGA', 'FG3M', 'FG3A', 'FTA', 'OREB', 'DREB', 'TOV']
    opp = df[['GAME_ID'] + box].rename(columns={c: f'OPP_{c}' for c in box})
    df = df.merge(opp, on='GAME_ID')
    df = df[df['TEAM_ID'] != df['OPP_TEAM_ID']]
    df = df.sort_values(['TEAM_ID', 'GAME_DATE']).reset_index(drop=True)

    # Advanced ratings: points per 100 possessions (ignores pace)
    poss = df['FGA'] + 0.44 * df['FTA'] - df['OREB'] + df['TOV']
    opp_poss = df['OPP_FGA'] + 0.44 * df['OPP_FTA'] - df['OPP_OREB'] + df['OPP_TOV']
    df['ORtg'] = (df['PTS'] / poss) * 100
    df['DRtg'] = ((df['PTS'] - df['PLUS_MINUS']) / poss) * 100
    df['Win'] = (df['WL'] == 'W').astype(int)
    df['is_home'] = (~df['MATCHUP'].str.contains('@')).astype(int)

    # Style: what this offense does, and what this defense allows
    def style(p, o, possessions):
        return {
            'TPAr':     df[f'{p}FG3A'] / df[f'{p}FGA'],
            'TP_PCT':   df[f'{p}FG3M'] / df[f'{p}FG3A'],
            'TWO_PCT':  (df[f'{p}FGM'] - df[f'{p}FG3M']) / (df[f'{p}FGA'] - df[f'{p}FG3A']),
            'TOV_RATE': df[f'{p}TOV'] / possessions,
            'OREB_PCT': df[f'{p}OREB'] / (df[f'{p}OREB'] + df[f'{o}DREB']),
            'FT_RATE':  df[f'{p}FTA'] / df[f'{p}FGA'],
        }
    for s, v in style('', 'OPP_', poss).items():
        df[s] = v
    for s, v in style('OPP_', '', opp_poss).items():
        df[f'ALW_{s}'] = v

    # Rolling form, reset each season
    by_team = df.groupby(['SEASON_ID', 'TEAM_ID'])
    df['rest_days'] = by_team['GAME_DATE'].diff().dt.days.fillna(4)

    win_cur = by_team['Win'].transform(lambda x: x.expanding().mean())
    df['Season_Win_Pct_cur'] = win_cur
    df['Season_Win_Pct'] = win_cur.groupby(by_team.ngroup()).shift(1)

    rolling = {'ORtg': 'ORtg_EWMA', 'DRtg': 'DRtg_EWMA'}
    rolling.update({s: s for s in STYLE_STATS})
    rolling.update({f'ALW_{s}': f'ALW_{s}' for s in STYLE_STATS})
    for src, name in rolling.items():
        df[f'{name}_cur'], df[name] = _ewm_pair(by_team, src, TEAM_SPAN)

    # Head-to-head: average margin in earlier meetings (both seasons)
    by_pair = df.groupby(['TEAM_ID', 'OPP_TEAM_ID'])['PLUS_MINUS']
    df['H2H_Games'] = by_pair.cumcount()
    df['H2H_Mean'] = by_pair.transform(lambda x: x.shift(1).expanding().mean()).fillna(0)

    return df


TEAM_STATE_COLS = ['Season_Win_Pct', 'ORtg_EWMA', 'DRtg_EWMA'] + STYLE_STATS + [f'ALW_{s}' for s in STYLE_STATS]


def team_current_state(team_table: pd.DataFrame) -> pd.DataFrame:
    """Each team's latest numbers (including its most recent game), indexed by TEAM_ID."""
    latest = team_table.sort_values('GAME_DATE').groupby('TEAM_ID').tail(1).set_index('TEAM_ID')
    state = latest[[f'{c}_cur' for c in TEAM_STATE_COLS]]
    state.columns = TEAM_STATE_COLS
    return state.assign(LAST_GAME=latest['GAME_DATE'])


def head_to_head(team_table: pd.DataFrame, team_id: int, opp_id: int):
    """(mean margin, games) for team_id in every meeting with opp_id so far."""
    games = team_table[(team_table['TEAM_ID'] == team_id) & (team_table['OPP_TEAM_ID'] == opp_id)]
    return (float(games['PLUS_MINUS'].mean()) if len(games) else 0.0), len(games)


# ==============================================================================
# PLAYER TABLE — one row per player per game played
# ==============================================================================
def _minutes(series: pd.Series) -> pd.Series:
    """Minutes arrive as numbers or 'MM:SS' strings depending on the endpoint."""
    if series.dtype == object:
        series = series.astype(str).map(
            lambda m: int(m.split(':')[0]) + int(m.split(':')[1]) / 60 if ':' in m else m)
    return pd.to_numeric(series, errors='coerce').fillna(0)


def build_player_table(df_player: pd.DataFrame, league_3p: float) -> pd.DataFrame:
    df = df_player.copy()
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df['MIN'] = _minutes(df['MIN'])
    df = df[df['MIN'] > 0].sort_values(['PLAYER_ID', 'GAME_DATE']).reset_index(drop=True)

    # Game Score (Hollinger): a one-number box-score rating of a player's game
    df['GmSc'] = (df['PTS'] + 0.4 * df['FGM'] - 0.7 * df['FGA'] - 0.4 * (df['FTA'] - df['FTM'])
                  + 0.7 * df['OREB'] + 0.3 * df['DREB'] + df['STL'] + 0.7 * df['AST']
                  + 0.7 * df['BLK'] - 0.4 * df['PF'] - df['TOV'])

    # Player rows follow the player across teams and seasons
    by_player = df.groupby('PLAYER_ID')
    games = by_player.cumcount() + 1

    gmsc_cur, gmsc_pre = _ewm_pair(by_player, 'GmSc', PLAYER_SPAN)
    min_cur, min_pre = _ewm_pair(by_player, 'MIN', PLAYER_SPAN)
    fg3a_cur, fg3a_pre = _ewm_pair(by_player, 'FG3A', PLAYER_SPAN)

    # Replacement level: what a fringe player produces per minute
    replacement = 0.6 * df['GmSc'].sum() / df['MIN'].sum()

    def shrink_rate(gmsc, mins, n):
        rate = gmsc / mins.replace(0, np.nan)
        return (n * rate + PLAYER_SHRINK_GAMES * replacement) / (n + PLAYER_SHRINK_GAMES)

    made, tried = by_player['FG3M'].cumsum(), by_player['FG3A'].cumsum()
    pct_cur = (made + THREE_PCT_SHRINK * league_3p) / (tried + THREE_PCT_SHRINK)

    ngroup = by_player.ngroup()
    df['rate_cur'], df['rate'] = shrink_rate(gmsc_cur, min_cur, games), shrink_rate(gmsc_pre, min_pre, games - 1)
    df['mins_cur'], df['mins'] = min_cur, min_pre
    df['fg3a_cur'], df['fg3a'] = fg3a_cur, fg3a_pre
    df['fg3pct_cur'], df['fg3pct'] = pct_cur, pct_cur.groupby(ngroup).shift(1)
    df.attrs['replacement'] = replacement
    df.attrs['league_3p'] = league_3p
    return df


def lineup_strength(players: pd.DataFrame, keys, replacement: float, league_3p: float) -> pd.DataFrame:
    """
    Sum up the players available to each team (one group per `keys`).
    players needs columns: rate, mins, fg3a, fg3pct.

    Roster_Strength  expected Game Score of the lineup over 240 minutes; minutes
                     the rotation can't cover are filled at replacement level
    Shooter_Volume   expected 3-pt attempts from the available players
    Shooter_Excess   extra points those attempts produce vs a league-average shooter
    """
    p = players[(players['mins'] >= ROTATION_MINUTES) & players['rate'].notna()].copy()
    p['prod'] = p['rate'] * p['mins']
    p['excess'] = p['fg3a'] * (p['fg3pct'].fillna(league_3p) - league_3p) * 3
    g = p.groupby(keys)[['mins', 'prod', 'fg3a', 'excess']].sum()

    # A deep rotation can't play more than 240 minutes: scale everyone down
    scale = np.minimum(1, GAME_MINUTES / g['mins'])
    return pd.DataFrame({
        'Roster_Strength': scale * g['prod'] + np.maximum(0, GAME_MINUTES - g['mins']) * replacement,
        'Shooter_Volume': scale * g['fg3a'],
        'Shooter_Excess': scale * g['excess'],
    })


def empty_lineup(replacement: float) -> dict:
    return {'Roster_Strength': GAME_MINUTES * replacement, 'Shooter_Volume': 0.0, 'Shooter_Excess': 0.0}


def current_rotation(player_table: pd.DataFrame, team_table: pd.DataFrame, team_id: int) -> pd.DataFrame:
    """
    The team's players right now: anyone whose latest game was for this team and
    came in one of the team's last RECENT_TEAM_GAMES games. Players sitting out
    longer than that drop off on their own; shorter absences go in the `out` list.
    """
    team_dates = team_table.loc[team_table['TEAM_ID'] == team_id, 'GAME_DATE'].sort_values()
    if team_dates.empty:
        return player_table.iloc[0:0]
    cutoff = team_dates.iloc[-min(RECENT_TEAM_GAMES, len(team_dates))]

    latest = player_table.groupby('PLAYER_ID').tail(1)
    roster = latest[(latest['TEAM_ID'] == team_id) & (latest['GAME_DATE'] >= cutoff)]
    roster = roster.assign(rate=roster['rate_cur'], mins=roster['mins_cur'],
                           fg3a=roster['fg3a_cur'], fg3pct=roster['fg3pct_cur'])
    return roster.sort_values('mins', ascending=False)


# ==============================================================================
# MATCHUP FEATURES — Team A vs Team B
# ==============================================================================
def matchup_features(A: pd.DataFrame, B: pd.DataFrame, league_3p: float) -> pd.DataFrame:
    """
    A and B hold one row per game with the same columns (each team's pre-game
    state). Returns every candidate feature from Team A's point of view.
    """
    f = pd.DataFrame(index=A.index)

    # --- base ---
    f['is_home'] = A['is_home']
    f['Off_Adv_SoS'] = (A['ORtg_EWMA'] - B['DRtg_EWMA']) * (1 + B['Season_Win_Pct'])
    f['Def_Adv_SoS'] = (B['ORtg_EWMA'] - A['DRtg_EWMA']) * (1 + B['Season_Win_Pct'])
    f['Rest_Adv'] = A['rest_days'] - B['rest_days']
    # Square root "squishes" the gap so a #1 seed vs a #10 seed isn't overconfident
    diff = A['Season_Win_Pct'] - B['Season_Win_Pct']
    f['Season_Diff_Dampened'] = np.sign(diff) * np.sqrt(np.abs(diff))

    # --- style_matchups ---
    # Expected value of a stat when A's offense meets B's defense: the average of
    # what A usually does and what B usually allows.
    def meet(off, dfn, s):
        return (off[s] + dfn[f'ALW_{s}']) / 2

    def three_pts(off, dfn):   # 3-pt points per shot attempt
        return 3 * meet(off, dfn, 'TPAr') * meet(off, dfn, 'TP_PCT')

    def two_pts(off, dfn):     # 2-pt points per shot attempt
        return 2 * (1 - meet(off, dfn, 'TPAr')) * meet(off, dfn, 'TWO_PCT')

    f['Three_Matchup'] = three_pts(A, B) - three_pts(B, A)
    f['Two_Matchup'] = two_pts(A, B) - two_pts(B, A)
    f['TOV_Matchup'] = meet(B, A, 'TOV_RATE') - meet(A, B, 'TOV_RATE')   # positive = B turns it over more
    f['OREB_Matchup'] = meet(A, B, 'OREB_PCT') - meet(B, A, 'OREB_PCT')
    f['FT_Matchup'] = meet(A, B, 'FT_RATE') - meet(B, A, 'FT_RATE')

    # --- roster_strength ---
    f['Roster_Strength_Diff'] = A['Roster_Strength'] - B['Roster_Strength']

    # --- perimeter ---
    # Extra 3-pt points = the available shooters' own skill, plus how leaky the
    # other team's perimeter defense is on that many attempts.
    def perimeter(off, dfn):
        return off['Shooter_Excess'] + off['Shooter_Volume'] * (dfn['ALW_TP_PCT'] - league_3p) * 3
    f['Perimeter_Edge'] = perimeter(A, B) - perimeter(B, A)

    # --- head_to_head ---
    f['H2H_Margin'] = A['H2H_Mean'] * A['H2H_Games'] / (A['H2H_Games'] + H2H_SHRINK)

    return f


FEATURE_GROUP_COLUMNS = {
    'base':            ['is_home', 'Off_Adv_SoS', 'Def_Adv_SoS', 'Rest_Adv', 'Season_Diff_Dampened'],
    'style_matchups':  ['Three_Matchup', 'Two_Matchup', 'TOV_Matchup', 'OREB_Matchup', 'FT_Matchup'],
    'roster_strength': ['Roster_Strength_Diff'],
    'perimeter':       ['Perimeter_Edge'],
    'head_to_head':    ['H2H_Margin'],
}


def build_training_set(team_table: pd.DataFrame, player_table: pd.DataFrame, league_3p: float) -> pd.DataFrame:
    """One row per team per game: every candidate feature, plus Win and GAME_DATE."""
    replacement = player_table.attrs['replacement']

    # Who actually played each game, rated on their games before it
    strength = lineup_strength(player_table, ['GAME_ID', 'TEAM_ID'], replacement, league_3p).reset_index()
    t = team_table.merge(strength, on=['GAME_ID', 'TEAM_ID'], how='left')
    for col, default in empty_lineup(replacement).items():
        t[col] = t[col].fillna(default)

    needed = TEAM_STATE_COLS + ['rest_days']
    t = t.dropna(subset=needed)   # drops each team's first game of a season

    side_cols = ['GAME_ID', 'TEAM_ID', 'is_home', 'rest_days', 'H2H_Mean', 'H2H_Games',
                 'Roster_Strength', 'Shooter_Volume', 'Shooter_Excess'] + TEAM_STATE_COLS
    pairs = t[['GAME_ID', 'GAME_DATE', 'TEAM_ID', 'TEAM_NAME', 'Win'] + side_cols[2:]].merge(
        t[side_cols], on='GAME_ID', suffixes=('', '_B'))
    pairs = pairs[pairs['TEAM_ID'] != pairs['TEAM_ID_B']].reset_index(drop=True)

    A = pairs[side_cols[2:]]
    B = pairs[[f'{c}_B' for c in side_cols[2:]]].set_axis(side_cols[2:], axis=1)
    feats = matchup_features(A, B, league_3p)
    return pd.concat([pairs[['GAME_ID', 'GAME_DATE', 'TEAM_ID', 'TEAM_NAME', 'TEAM_ID_B', 'Win']], feats], axis=1)
