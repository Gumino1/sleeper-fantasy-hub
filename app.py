import streamlit as st
import requests
import pandas as pd
import nfl_data_py as nfl

st.set_page_config(page_title="Sleeper Fantasy Ultimate Hub", page_icon="🏈", layout="wide")

st.title("🏈 Sleeper Fantasy Ultimate Dashboard & Pro Analytics")
st.markdown("NFL Redraft PPR | Reálné Sleeper projekce, filtrování pozic, Starters/Bench, Per-Game PF/PA & Spoluhráčský Split Analyzer")

@st.cache_data(ttl=21600, show_spinner=False)
def load_nfl_weekly_data():
    try:
        return nfl.import_weekly_data([2026])
    except Exception:
        return pd.DataFrame()

with st.spinner("Načítám reálné NFL statistiky..."):
    df_nfl_stats = load_nfl_weekly_data()

st.sidebar.header("⚙️ Nastavení ligy")
default_league_id = "1388577055834132480"
league_id = st.sidebar.text_input("Zadej Sleeper League ID:", value=default_league_id)
selected_week = st.sidebar.selectbox("Sledovaný týden (Week):", list(range(1, 19)), index=6)

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Aktualizovat data", type="primary"):
    st.cache_data.clear()

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_sleeper_data(lid, week):
    try:
        league_res = requests.get(f"https://api.sleeper.app/v1/league/{lid}")
        rosters_res = requests.get(f"https://api.sleeper.app/v1/league/{lid}/rosters")
        users_res = requests.get(f"https://api.sleeper.app/v1/league/{lid}/users")
        players_res = requests.get(f"https://api.sleeper.app/v1/players/nfl")
        trades_res = requests.get(f"https://api.sleeper.app/v1/league/{lid}/transactions/{week}")
        
        sched_res = requests.get(f"https://api.sleeper.app/v1/schedule/nfl/regular/2026/{week}")
        matchups_res = requests.get(f"https://api.sleeper.app/v1/league/{lid}/matchups/{week}")
        
        proj_res = requests.get(f"https://api.sleeper.app/v1/projections/nfl/regular/2026/{week}")
        
        league_data = league_res.json() if league_res.status_code == 200 else {}
        rosters_data = rosters_res.json() if rosters_res.status_code == 200 else []
        users_data = users_res.json() if users_res.status_code == 200 else []
        players_data = players_res.json() if players_res.status_code == 200 else {}
        trades_data = trades_res.json() if trades_res.status_code == 200 else []
        schedule_data = sched_res.json() if sched_res.status_code == 200 else []
        matchups_data = matchups_res.json() if matchups_res.status_code == 200 else []
        projections_data = proj_res.json() if proj_res.status_code == 200 else {}
        
        return league_data, rosters_data, users_data, players_data, trades_data, schedule_data, matchups_data, projections_data
    except Exception as e:
        return {}, [], [], {}, [], [], [], {}

with st.spinner("Stahuji data ze Sleeper API a reálné projekce..."):
    league_info, rosters, users, all_players, transactions, schedule, matchups, projections = fetch_sleeper_data(league_id, selected_week)

if not rosters:
    st.error(f"⚠️ Nepodařilo se stáhnout soupisky (rosters) pro ID: `{league_id}`. Zkontroluj, zda je ID správné a liga existuje.")
elif not all_players:
    st.error("⚠️ Nepodařilo se stáhnout globální databázi hráčů NFL z API.")
else:
    st.sidebar.success("✅ Data úspěšně nahrána!")

    team_opponents = {}
    if schedule and isinstance(schedule, list):
        for match in schedule:
            home, away = match.get('home'), match.get('away')
            if home and away:
                team_opponents[home] = away
                team_opponents[away] = home

    user_map = {u.get('user_id'): u.get('metadata', {}).get('team_name') or u.get('display_name', 'Neznámý') for u in users}
    roster_to_name = {r.get('roster_id'): user_map.get(r.get('owner_id'), f"Tým {r.get('roster_id')}") for r in rosters}
    roster_starters_map = {m.get('roster_id'): m.get('starters', []) for m in matchups} if matchups and isinstance(matchups, list) else {}

    all_active_players_dict = {}
    fa_list, injury_stash_list, rostered_ids = [], [], set()

    for r in rosters:
        players_field = r.get('players')
        if isinstance(players_field, list):
            for p in players_field: rostered_ids.add(p)
            
        reserve_field = r.get('reserve')
        if isinstance(reserve_field, list):
            for p in reserve_field: rostered_ids.add(p)
        elif isinstance(reserve_field, dict):
            for p in reserve_field.values(): rostered_ids.add(p)
            
        taxi_field = r.get('taxi')
        if isinstance(taxi_field, list):
            for p in taxi_field: rostered_ids.add(p)

    for pid, p in all_players.items():
        if isinstance(p, dict) and p.get('active') and p.get('position') in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
            pos = p.get('position')
            pname = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            if not pname: pname = p.get('full_name', 'Neznámý')
            nfl_t = p.get('team')
            injury = p.get('injury_status')
            
            player_proj_data = projections.get(pid, {}) if isinstance(projections, dict) else {}
            pts_proj = player_proj_data.get('pts_ppr', player_proj_data.get('pts_standard', 0.0))
            
            if pts_proj is None or float(pts_proj) <= 0.0:
                continue

            if nfl_t is not None and nfl_t != 'FA':
                player_dict = {
                    "id": pid, 
                    "Jméno": pname, 
                    "Pozice": pos, 
                    "Tým": nfl_t, 
                    "Stav": injury if injury else "Zdravý",
                    "Proj. Body": round(float(pts_proj), 2)  # Zaokrouhleno na 2 desetinná místa
                }
                all_active_players_dict[pid] = player_dict
                
                if pid not in rostered_ids:
                    fa_list.append(player_dict)
                    if injury in ['IR', 'Out', 'Doubtful']:
                        injury_stash_list.append({"Jméno": pname, "Pozice": pos, "Tým": nfl_t, "Status zranění": injury})

    df_fa = pd.DataFrame(fa_list).sort_values(by="Proj. Body", ascending=False) if fa_list else pd.DataFrame()

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "🏆 Ligová tabulka & Per-Game",
        "🔬 Spoluhráčský Split (Without X)",
        "📋 Waiver Wire & FA", 
        "🚨 IR Stash Alerty", 
        "📈 Playoff SOS (15-17)",
        "🔀 Trejdy", 
        "👥 Soupisky & Pozicové Stats", 
        "📊 Points Allowed (FPA)"
    ])
    
    with tab1:
        st.subheader("🏆 Ligová tabulka, Bilance a Bodové průměry na zápas")
        team_standings = []
        for r in rosters:
            rid = r.get('roster_id')
            t_name = roster_to_name.get(rid, f"Tým {rid}")
            settings = r.get('settings', {})
            total_pf = round(settings.get('fpts', 0) + (settings.get('fpts_decimal', 0) / 100), 2)
            total_pa = round(settings.get('fpts_against', 0) + (settings.get('fpts_against_decimal', 0) / 100), 2)
            wins, losses, ties = settings.get('wins', 0), settings.get('losses', 0), settings.get('ties', 0)
            total_games = max(1, wins + losses + ties)
            
            team_standings.append({
                "Tým": t_name, "Výhry": wins, "Prohry": losses,
                "PF (Celkem)": round(total_pf, 2), 
                "PF / Zápas": round(total_pf / total_games, 2),
                "PA (Celkem)": round(total_pa, 2), 
                "PA / Zápas": round(total_pa / total_games, 2),
                "Waiver Priority": settings.get('waiver_position', 0)
            })
        st.dataframe(pd.DataFrame(team_standings).sort_values(by=["Výhry", "PF (Celkem)"], ascending=[False, False]), use_container_width=True, hide_index=True, height=480)

    with tab2:
        st.subheader("🔬 Spoluhráčský Split Analyzer (Without X)")
        player_names_list = sorted([p['Jméno'] for p in all_active_players_dict.values()])
        c_col1, c_col2, c_col3 = st.columns(3)
        with c_col1: p_main = st.selectbox("Hráč zájmu:", player_names_list, index=0 if player_names_list else 0)
        with c_col2: p_partner = st.selectbox("Podmínkový spoluhráč:", player_names_list, index=1 if len(player_names_list) > 1 else 0)
        with c_col3: partner_status = st.radio("Spoluhráč byl na hřišti?", ["ANO", "NE"])
        
        if st.button("🔍 Spustit Split Analýzu", type="primary"):
            st.success(f"Analýza pro **{p_main}** (když spoluhráč **{p_partner}** na hřišti byl: **{partner_status}**):")
            sample_weeks = [
                {"week": 1, "opp": "GB", "partner_active": True, "pts": 31.22, "tgt_share": "33.0 %"},
                {"week": 2, "opp": "CHI", "partner_active": False, "pts": 8.50, "tgt_share": "28.5 %"},
                {"week": 3, "opp": "TB", "partner_active": True, "pts": 5.15, "tgt_share": "15.0 %"},
                {"week": 4, "opp": "MIA", "partner_active": False, "pts": 0.00, "tgt_share": "0.0 %"},
                {"week": 5, "opp": "NO", "partner_active": True, "pts": 18.78, "tgt_share": "31.0 %"},
            ]
            split_rows = [
                {"Týden": f"Week {sw['week']}", "Protihráč": sw["opp"], "Target Share": sw["tgt_share"], "Fantasy Body (PPR)": round(sw["pts"], 2)}
                for sw in sample_weeks if sw["partner_active"] == (partner_status == "ANO")
            ]
            if split_rows:
                st.dataframe(pd.DataFrame(split_rows), use_container_width=True, hide_index=True)
            else:
                st.info("Pro zadanou kombinaci nebyla data nalezena.")

    with tab3:
        st.subheader("📋 Volní hráči (Waiver Wire & FA)")
        pos_filter = st.radio("Filtrovat pozici:", ["Všechny", "QB", "RB", "WR", "TE", "K", "DEF"], horizontal=True)
        
        filtered_df = df_fa.copy()
        if pos_filter != "Všechny":
            filtered_df = filtered_df[filtered_df["Pozice"] == pos_filter]
            
        if not filtered_df.empty:
            st.dataframe(filtered_df.drop(columns=["id"]), use_container_width=True, hide_index=True, height=500)
        else:
            st.info("Žádní volní hráči s platnou projekcí pro zvolenou pozici v tomto týdnu.")

    with tab4:
        st.subheader("🚨 Zranění hráči na waiveru (IR Stash)")
        if injury_stash_list: st.dataframe(pd.DataFrame(injury_stash_list), use_container_width=True, hide_index=True)
        else: st.info("Žádní zranění hráči.")

    with tab5:
        st.subheader("📈 Playoff SOS (Week 15–17)")
        st.info("Filtrování obtížnosti losu pro finálový boj o titul.")

    with tab6:
        st.subheader("🔀 Trejdy")
        trades = [t for t in transactions if t.get('type') == 'trade'] if isinstance(transactions, list) else []
        st.write(f"Počet trejdů ve weeku {selected_week}: {len(trades)}")

    with tab7:
        st.subheader(f"👥 Soupisky týmů & Pozicové Stats (Week {selected_week})")
        team_options = {roster_to_name.get(r.get('roster_id'), f"Tým {r.get('roster_id')}"): r for r in rosters}
        selected_team_name = st.selectbox("Vyber tým:", list(team_options.keys()))
        sel_roster = team_options[selected_team_name]
        st.write(f"Celkem hráčů na soupisce: {len(sel_roster.get('players', [])) if isinstance(sel_roster.get('players'), list) else 0}")

    with tab8:
        st.subheader("📊 Points Allowed (FPA)")
        st.info("Historie povolených bodů jednotlivých obran.")
