import pandas as pd

# --- Data Loading and Preparation ---
# Load the CSV files
try:
    adp_df = pd.read_csv("2025ADP.csv")
    # Using the correct filename from your attachment for PPR data
    ppr_df = pd.read_csv("2024PPR.csv")
except FileNotFoundError as e:
    print(f"Error loading CSV file: {e}")
    print("Please make sure '2025ADP.csv' and 'FantasyPros_Fantasy_Football_Points_PPR.csv' are in the correct folder.")
    exit()


# Clean up PPR data - remove '#' rows and handle non-numeric 'TTL'
ppr_df = ppr_df[ppr_df['Player'].notna()]
ppr_df['TTL'] = pd.to_numeric(ppr_df['TTL'], errors='coerce')
ppr_df.dropna(subset=['TTL'], inplace=True)


# Merge the DataFrames on the 'Player' column
merged_df = pd.merge(adp_df, ppr_df, on="Player", how="inner")

# Add an 'Available' column, True by default
merged_df['Available'] = True

# Extract base position (e.g., 'RB' from 'RB1')
merged_df['BasePOS'] = merged_df['POS'].str.extract(r'([A-Z]+)').fillna('UNK')

# --- Core Functions ---

def calculate_value_score(df):
    """Calculates a baseline ValueScore for each player."""
    # Use the 'AVG' from ADP data as the denominator
    df['ValueScore'] = df['TTL'] / df['AVG_x']
    # Initialize AdjValueScore to be the same as ValueScore initially
    df['AdjValueScore'] = df['ValueScore']
    return df

def player_unavailable(df, player_name):
    """Marks a drafted player as unavailable."""
    # Use .str.contains for partial name matching, case-insensitive
    mask = df['Player'].str.contains(player_name, case=False, na=False)
    if mask.sum() == 0:
        print(f"--- Player '{player_name}' not found. Please try again. ---")
    elif mask.sum() > 1:
        print(f"--- Multiple players match '{player_name}'. Please be more specific. ---")
    else:
        player_found = df.loc[mask, 'Player'].iloc[0]
        df.loc[mask, 'Available'] = False
        print(f"\n>>> {player_found} has been drafted. <<<")
    return df


merged_df = calculate_value_score(merged_df)


top_n_per_position = {'QB': 12, 'RB': 25, 'WR': 25, 'TE': 12}

# Create a list of players who are in the initial top tier for each position
top_tier_players = {}
total_counts = {}
for pos, n in top_n_per_position.items():
    # Find the top N players for the position based on their initial ValueScore
    top_players_for_pos = merged_df[merged_df['BasePOS'] == pos].nlargest(n, 'ValueScore')['Player'].tolist()
    top_tier_players[pos] = top_players_for_pos
    total_counts[pos] = len(top_players_for_pos)

print("--- Fantasy Draft Picker ---")
print("Scarcity is calculated based on the top players at QB, RB, WR, and TE.")


while True:
    # Get a fresh copy of available players for this round's ranking
    available_df = merged_df[merged_df['Available']].copy()

    # --- Scarcity Calculation ---
    # This is the logic that makes the values change.
    for pos, total_in_tier in total_counts.items():
        # How many of the original top-tier players for this position are still available?
        tier_list = top_tier_players[pos]
        remaining_in_tier = available_df[available_df['Player'].isin(tier_list)].shape[0]

        # Avoid division by zero if all top players are gone
        if remaining_in_tier == 0:
            continue

        # Calculate the scarcity multiplier (the power of 2 makes the effect significant)
        scarcity_multiplier = pow(total_in_tier / remaining_in_tier, 2)

        # Apply this multiplier to ALL available players at this position
        pos_mask = available_df['BasePOS'] == pos
        available_df.loc[pos_mask, 'AdjValueScore'] = available_df.loc[pos_mask, 'ValueScore'] * scarcity_multiplier

    # Rank the available players by their newly adjusted score
    ranked_df = available_df.sort_values(by='AdjValueScore', ascending=False)

    print("\n--- Top 15 Available Players (Adjusted for Scarcity) ---")
    display_cols = ['Player', 'POS', 'AdjValueScore']
    print(ranked_df[display_cols].head(15).to_string(index=False))

    # Display the current scarcity state
    print("\n--- Remaining Players in Top Tier ---")
    for pos, total in total_counts.items():
        remaining = available_df[available_df['Player'].isin(top_tier_players[pos])].shape[0]
        print(f"{pos}: {remaining}/{total}")

    # --- User Input ---
    player_choice = input("\nEnter the player you want to draft (or type 'exit'): ")
    if player_choice.lower() in ['exit', 'done', 'quit']:
        print("\nDraft finished!")
        break

    # Update the main DataFrame to mark the player as drafted
    merged_df = player_unavailable(merged_df, player_choice)