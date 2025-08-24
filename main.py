import streamlit as st
import pandas as pd
import requests
import numpy as np

# --- Configuration ---
st.set_page_config(layout="wide", page_title="Fantasy Football Draft Assistant")

# --- Helper Functions ---
def normalize_name(name):
    if not isinstance(name, str):
        return ""
    return name.lower().replace('.', '').replace(',', '').strip()

@st.cache_data(ttl=3600)
def load_data():
    try:
        adp_df = pd.read_csv("2025ADP.csv")
        ppr_df = pd.read_csv("2024PPR.csv")
    except FileNotFoundError as e:
        st.error(f"Error loading CSV: {e}")
        return None

    ppr_df = ppr_df[ppr_df['Player'].notna()]
    ppr_df['TTL'] = pd.to_numeric(ppr_df['TTL'], errors='coerce')
    ppr_df.dropna(subset=['TTL'], inplace=True)

    merged_df = pd.merge(adp_df, ppr_df, on="Player", how="inner")
    merged_df['Available'] = True
    merged_df['BasePOS'] = merged_df['POS'].str.extract(r'([A-Z]+)').fillna('UNK')
    merged_df['ValueScore'] = merged_df['TTL'] / merged_df['AVG_x']
    merged_df['AdjValueScore'] = merged_df['ValueScore']
    merged_df['NormalizedPlayer'] = merged_df['Player'].apply(normalize_name)

    # Compute weekly points
    weekly_cols = [str(i) for i in range(1, 19)]
    for col in weekly_cols:
        merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)

    # Consistency = std of weekly points
    merged_df['Consistency'] = merged_df[weekly_cols].std(axis=1)
    merged_df['Risk'] = merged_df['Consistency']

    # Boom% = % weeks >= 120% of avg, Bust% = % weeks <= 80% of avg
    avg_points = merged_df[weekly_cols].mean(axis=1)
    merged_df['Boom%'] = ((merged_df[weekly_cols].T >= avg_points*1.2).T.sum(axis=1) / 18) * 100
    merged_df['Bust%'] = ((merged_df[weekly_cols].T <= avg_points*0.8).T.sum(axis=1) / 18) * 100

    # Ensure Bye column exists
    if 'Bye' not in merged_df.columns:
        merged_df['Bye'] = 0

    return merged_df.sort_values('ValueScore', ascending=False).reset_index(drop=True)

@st.cache_data(ttl=3600)
def get_sleeper_players():
    try:
        response = requests.get("https://api.sleeper.app/v1/players/nfl")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None

def build_photo_map(sleeper_data):
    if not sleeper_data:
        return {}
    photo_map = {}
    for player_id, info in sleeper_data.items():
        name = normalize_name(info.get('full_name', ''))
        if name:
            photo_map[name] = player_id
    return photo_map

def get_player_photo_url(player_name, photo_map):
    player_id = photo_map.get(normalize_name(player_name))
    if player_id:
        url = f"https://sleepercdn.com/content/nfl/players/thumb/{player_id}.jpg"
        try:
            r = requests.head(url, timeout=3)
            if r.status_code == 200:
                return url
        except:
            pass
    # Gray placeholder
    return "https://via.placeholder.com/120x120/cccccc/333333?text=No+Photo"

# --- Initialize Session State ---
if 'draft_data' not in st.session_state:
    st.session_state.draft_data = load_data()
    sleeper_players = get_sleeper_players()
    st.session_state.photo_map = build_photo_map(sleeper_players)
    st.session_state.drafted_players = []

    # Top-tier pools for scarcity
    top_n_per_position = {'QB': 12, 'RB': 25, 'WR': 25, 'TE': 12}
    df = st.session_state.draft_data
    top_tier_players = {}
    total_counts = {}
    for pos, n in top_n_per_position.items():
        top_players_for_pos = df[df['BasePOS'] == pos].nlargest(n, 'ValueScore')['Player'].tolist()
        top_tier_players[pos] = top_players_for_pos
        total_counts[pos] = len(top_players_for_pos)
    st.session_state.top_tier_info = {'players': top_tier_players, 'totals': total_counts}

# --- Main App ---
st.title("🏆 Fantasy Football Draft Assistant")
st.markdown("Enhanced draft assistant with dynamic recommendations, risk analysis, and positional alerts.")

df = st.session_state.draft_data
available_df = df[df['Available']].copy()
top_tier_info = st.session_state.top_tier_info
remaining_counts = {}

# Scarcity calculation and adjusted value score
for pos, total_in_tier in top_tier_info['totals'].items():
    tier_list = top_tier_info['players'][pos]
    remaining_in_tier = available_df[available_df['Player'].isin(tier_list)].shape[0]
    remaining_counts[pos] = remaining_in_tier
    if remaining_in_tier > 0:
        scarcity_multiplier = pow(total_in_tier / remaining_in_tier, 2)
        pos_mask = available_df['BasePOS'] == pos
        available_df.loc[pos_mask, 'AdjValueScore'] = available_df.loc[pos_mask, 'ValueScore'] * scarcity_multiplier

ranked_df = available_df.sort_values('AdjValueScore', ascending=False)

# --- Sidebar ---
with st.sidebar:
    st.header("Draft Summary")
    st.subheader("Top Tier Scarcity")
    for pos, total in top_tier_info['totals'].items():
        remaining = remaining_counts.get(pos, 0)
        progress_val = min(max(remaining / total, 0), 1)  # Clamp between 0 and 1
        st.progress(progress_val, text=f"{pos}: {remaining}/{total}")

    st.subheader("Drafted Players")
    if st.session_state.drafted_players:
        for i, player in enumerate(st.session_state.drafted_players):
            st.markdown(f"{i+1}. {player}")
    else:
        st.write("No players drafted yet.")

# --- Filters ---
st.header("Available Players")
all_pos = sorted(ranked_df['BasePOS'].unique())
selected_pos = st.multiselect("Filter by Position:", options=all_pos, default=['RB','WR','TE'])
filtered_df = ranked_df[ranked_df['BasePOS'].isin(selected_pos)] if selected_pos else ranked_df

num_cols = 4
cols = st.columns(num_cols)

# --- Display Players ---
for i, row in enumerate(filtered_df.head(28).itertuples()):
    with cols[i % num_cols]:
        st.markdown(f"**{row.Player}** ({row.POS})")
        photo_url = get_player_photo_url(row.Player, st.session_state.photo_map)
        st.image(photo_url, width=100, use_container_width=False)
        st.metric(label="Adj. Value", value=f"{row.AdjValueScore:.2f}")
        st.metric(label="Consistency", value=f"{row.Consistency:.2f}")
        st.metric(label="Risk", value=f"{row.Risk:.2f}")
        boom_value = getattr(row, 'Boom%', None)  # safe access
        bust_value = getattr(row, 'Bust%', None)

        st.metric(label="Boom%", value=f"{boom_value:.0f}%" if boom_value is not None else "0%")
        st.metric(label="Bust%", value=f"{bust_value:.0f}%" if bust_value is not None else "0%")

        if st.button("Draft Player", key=f"draft_{row.Index}"):
            st.session_state.draft_data.loc[row.Index, 'Available'] = False
            st.session_state.drafted_players.append(row.Player)
            st.experimental_rerun()

# --- Positional Alerts ---
st.subheader("Positional Alerts")
for pos, remaining in remaining_counts.items():
    if remaining <= 3:
        st.warning(f"⚠️ Running low on top-tier {pos} players! Only {remaining} left.")