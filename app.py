import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURATION & AUTH ---
st.set_page_config(page_title="Archery Tracker", page_icon="🏹", layout="wide")

@st.cache_resource
def get_worksheet():
    creds = Credentials.from_service_account_file("C:/Users/nicky/Desktop/ArcheryApp/google_creds.json", 
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    gc = gspread.authorize(creds)
    return gc.open_by_url("https://docs.google.com/spreadsheets/d/1Ui-oteX0ax8b4iYz3nYCf44PK2P4l0tgFp7zpgq9UVE/edit").worksheet("History")

worksheet = get_worksheet()
HEADERS = ["Archer_Name", "Group", "Month", "Round", "Raw_Score", "Bonus_Penalty", "Allowance_Used", "Final_Monthly_Total", "Handicap_Saved", "Hits", "Golds", "Bow_Type"]

# --- 2. DATA LOADING FUNCTIONS ---
@st.cache_data
def load_archery_references():
    excel_path = "C:/Users/nicky/Desktop/ArcheryApp/tidy_archery_reference.xlsx"
    xl = pd.ExcelFile(excel_path)
    master_df = xl.parse(xl.sheet_names[0])
    master_df.columns = master_df.columns.str.strip()
    return sorted(master_df["Round"].dropna().unique().tolist()), master_df

@st.cache_data(ttl=60)
def load_cloud_data():
    data = worksheet.get_all_records(default_blank=0)
    df = pd.DataFrame(data)
    if not df.empty:
        cols_to_fix = ["Month", "Raw_Score", "Bonus_Penalty", "Allowance_Used", "Final_Monthly_Total", "Handicap_Saved"]
        for col in cols_to_fix:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df

# --- 3. MAINTENANCE LOGIC ---
from datetime import datetime

def apply_active_penalties(df, current_season_month):
    # Get all months that have data, but filter to only include up to the CURRENT month
    # If it is May (Month 2), existing_months might be [1, 2].
    existing_months = sorted(df["Month"].unique())
    
    # We only look at months that are equal to or less than the current season month
    months_to_check = [int(m) for m in existing_months if int(m) <= int(current_season_month)]
    
    rows_to_add = []
    
    for month in months_to_check:
        active_this_month = df[df["Month"] == month]["Archer_Name"].unique()
        all_archers = df["Archer_Name"].unique()
        
        for name in all_archers:
            # Get the first month they ever appeared
            first_month_active = df[df["Archer_Name"] == name]["Month"].min()
            
            # EXEMPTION:
            # 1. If they didn't exist before this month (first_month_active >= month), they are new.
            # 2. If they are already in the active list for this month, skip.
            if first_month_active >= month or name in active_this_month:
                continue
            
            # Check for existing penalty
            condition = ((df["Archer_Name"] == name) & 
                         (df["Month"] == month) & 
                         (df["Round"] == "Penalty (Inactive)"))
            
            if not condition.any():
                # Get the last record to calculate penalty based on previous month's raw score
                last_record = df[df["Archer_Name"] == name].iloc[-1]
                penalty_value = float(last_record["Raw_Score"])
                new_total = float(last_record["Final_Monthly_Total"]) - penalty_value
                
                rows_to_add.append([
                    str(name), str(last_record["Group"]), int(month), "Penalty (Inactive)", 
                    0, -penalty_value, 0, new_total, float(last_record["Handicap_Saved"])
                ])
    
    if rows_to_add:
        worksheet.append_rows(rows_to_add)
        st.cache_data.clear()
        st.rerun()

# --- 4. EXECUTION ---
# Load data and setup variables FIRST
OFFICIAL_ROUNDS, reference_df = load_archery_references()
df = load_cloud_data()

# Calculate the season month dynamically based on the date
# (May 2026 = 2, June = 3, etc. as per your April=1 setup)
# --- 4. EXECUTION ---
today = datetime.now()
# Map April(4) to 1, May(5) to 2, etc.
month_map = {4: 1, 5: 2, 6: 3, 7: 4, 8: 5, 9: 6}
# If we are in June(6), current_season_month = 3. 
# If current month is not in the map, default to 6 (end of season)
current_season_month = month_map.get(today.month, 6) 

# Run current penalty
apply_active_penalties(df, current_season_month)

# --- 5. INTERFACE ---
st.title("🏹 Archery Tournament Ledger")

with st.sidebar:
    with st.expander("⚙️ Admin Maintenance Tools", expanded=False):
      st.subheader("Remove An Entry")
      if not df.empty:
          row_options = {i + 2: f"Row {i+2}: {row['Archer_Name']} ({row['Round']})" for i, row in df.iterrows()}
          selected_row = st.selectbox("Select row to delete:", options=list(row_options.keys()), format_func=lambda x: row_options[x])
          if st.button("🗑️ Delete Selected Row", use_container_width=True):
              worksheet.delete_rows(selected_row); st.rerun()
      st.write("---")
      st.subheader("Danger Zone")
      if st.checkbox("Verify league reset"):
          if st.button("🚨 Reset Entire Season", type="primary"):
              worksheet.clear(); worksheet.append_row(HEADERS); st.rerun()

col1, col2 = st.columns([1, 2])
with col1:
    with st.form(key="score_form"):
        name = st.text_input("Archer Name")
        group = st.radio("Archer Group", ["Group A", "Group B"], horizontal=True)
        month = st.selectbox("Season Month", [1, 2, 3, 4, 5, 6])
        round_shot = st.selectbox("Round Shot", options=OFFICIAL_ROUNDS)
        score = st.number_input("Total Score", min_value=0, max_value=1000)
        hits = st.number_input("Hits", min_value=0, max_value=300)
        golds = st.number_input("Golds", min_value=0, max_value=300)
        bow_type = st.selectbox("Bow Type", ["Recurve", "Barebow", "Longbow", "Compound"])
        submit_button = st.form_submit_button("Submit")

    if submit_button:
        if name.strip() == "":
            st.error("⚠️ Please fill out the Archer Name field.")
        else:
            p_name = name.strip()
            history = df[df["Archer_Name"] == p_name] if "Archer_Name" in df.columns else pd.DataFrame()
            last_row = history.iloc[-1] if not history.empty else None
            is_new_archer = last_row is None
            baseline_handicap = float(last_row["Handicap_Saved"]) if last_row is not None and "Handicap_Saved" in last_row else 0.0
            prev_raw = float(last_row["Raw_Score"]) if last_row is not None and "Raw_Score" in last_row else 0.0
            prev_total = float(last_row["Final_Monthly_Total"]) if last_row is not None and "Final_Monthly_Total" in last_row else 0.0
            target_round = str(round_shot).strip().lower()
            round_set = reference_df[reference_df["Round"].astype(str).str.strip().str.lower() == target_round]
            current_perf = float(round_set[round_set["Score"] <= score].sort_values("Score", ascending=False).iloc[0]["Handicap"]) if not round_set[round_set["Score"] <= score].empty else 50.0
            calculated_bonus = (float(score) - prev_raw) if not is_new_archer and int(month) > 1 else 0.0
            calculated_allowance = 0.0
            # Ensure we are looking for exact matches where possible
            # We round the handicap to 0 decimal places to find the correct reference row
            handicap_for_allowance = current_perf if is_new_archer else baseline_handicap
            rounded_handicap = round(handicap_for_allowance) 
            
            try:
                # Filter by exact round and the rounded handicap
                match = reference_df[
                    (reference_df["Round"].astype(str).str.strip().str.lower() == target_round) & 
                    (reference_df["Handicap"].astype(float).round() == rounded_handicap)
                ]
                
                if not match.empty:
                    calculated_allowance = float(match.iloc[0]["Allowance"])
            except Exception as e:
                st.error(f"Error matching allowance: {e}")
                calculated_allowance = 0.0
            total = prev_total + float(score) + calculated_bonus + calculated_allowance
            worksheet.append_row([p_name, group, int(month), round_shot, int(score), round(calculated_bonus, 1), round(calculated_allowance, 1), round(total, 1), round(current_perf, 1), int(hits), int(golds), bow_type])
            st.cache_data.clear()
            st.rerun()

with col2:
    if not df.empty and "Group" in df.columns:
        st.subheader("🏆 Season Leaderboards")
        display_cols = ["Archer_Name", "Final_Monthly_Total", "Month", "Round"]
        lb_col1, lb_col2 = st.columns(2)
        for g, col in zip(["Group A", "Group B"], [lb_col1, lb_col2]):
            with col:
                st.markdown(f"### {g}")
                group_data = df[df["Group"] == g].groupby("Archer_Name").last().reset_index()
                if not group_data.empty:
                    leaderboard_view = group_data[display_cols].rename(columns={"Archer_Name": "Archer", "Final_Monthly_Total": "Points", "Month": "Last Active", "Round": "Latest Round"}).sort_values(by="Points", ascending=False)
                    row_height = 35
                    header_height = 38
                    table_height = header_height + (row_height * len(leaderboard_view))
                    st.dataframe(leaderboard_view, use_container_width=True, hide_index=True, height=table_height)


st.write("---")
down_col, hist_col = st.columns([1, 2])

with down_col:
    st.subheader("📥 Download Monthly Scores")
    download_month = st.selectbox("Select month to download:", [1, 2, 3, 4, 5, 6], key="download_month")

    if not df.empty and "Hits" in df.columns:
        download_df = df[df["Month"] == download_month][["Archer_Name", "Round", "Raw_Score", "Hits", "Golds", "Bow_Type"]].copy()
        download_df = download_df[download_df["Round"] != "Penalty (Inactive)"]
        download_df.columns = ["Archer Name", "Round", "Score", "Hits", "Golds", "Bow Type"]

        if not download_df.empty:
            csv = download_df.to_csv(index=False)
            st.download_button(
                label=f"⬇️ Download Month {download_month} Scores as CSV",
                data=csv,
                file_name=f"archery_scores_month_{download_month}.csv",
                mime="text/csv"
            )
            row_height = 35
            header_height = 38
            download_height = header_height + (row_height * len(download_df))
            st.dataframe(download_df, use_container_width=True, hide_index=True, height=download_height)
        else:
            st.info(f"No scores recorded for Month {download_month} yet.")
    else:
        st.info("No data available to download.")

with hist_col:
    st.subheader("📊 Current Tournament History")
    history_cols = ["Archer_Name", "Group", "Month", "Round", "Raw_Score", "Final_Monthly_Total"]
    history_df = df[history_cols].sort_values(by="Month", ascending=False)
    row_height = 35
    header_height = 38
    table_height = header_height + (row_height * len(history_df))
    st.dataframe(history_df, use_container_width=True, hide_index=True, height=table_height)

st.write("---")
st.subheader("📈 Performance Progression")

for g in ["Group A", "Group B"]:
    st.markdown(f"### {g}")
    group_df = df[df["Group"] == g].sort_values(by="Month")
    
    if not group_df.empty:
        archer_options = sorted(group_df["Archer_Name"].unique().tolist())
        selected_archers = st.multiselect(
            f"Filter archers — {g}:",
            options=archer_options,
            default=archer_options,
            key=f"filter_{g}"
        )
        
        filtered_df = group_df[group_df["Archer_Name"].isin(selected_archers)]
        
        if not filtered_df.empty:
            fig = px.line(
                filtered_df,
                x="Month",
                y="Final_Monthly_Total",
                color="Archer_Name",
                markers=True,
                hover_data={"Round": True, "Raw_Score": True, "Month": True},
                title=f"Final Monthly Totals — {g}"
            )
            fig.update_layout(xaxis=dict(tickmode="linear", dtick=1))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No archers selected.")

    else:
        st.info("No tournament records logged in the database yet.")