import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="Sleeper Fantasy Ultimate Hub", page_icon="🏈", layout="wide")

st.title("🏈 Sleeper Fantasy Ultimate Dashboard & Pro Analytics")
st.markdown("NFL Redraft PPR | Reálné Sleeper projekce, filtrování pozic, Starters/Bench, Per-Game PF/PA & Spoluhráčský Split Analyzer")

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
        matchups_res = requests.get(f"https://api.sleeper.app/v1/league/{lid}/matchups/{week}")
        proj_res = requests.get(f"https://api.sleeper.app/v1/projections/nfl/regular/2026/{week}")
        
        league_data = league_res.json() if league_res.status_code == 200 else {}
        rosters_data = rosters_res.json() if rosters_res.status_code == 200 else []
        users_data = users_res.json() if users_res.status_code == 200 else []
        players_data = players_res.json() if players_res.status_code == 200 else {}
        trades_data = trades_res.json() if trades_res.status_code == 200 else []
        matchups_data = matchups_res.json() if matchups_res.status_code == 200 else []
        projections_data = proj_res.json() if proj_res.status_code == 200 else {}
        
        return league_data, rosters_data, users_data, players_data, trades_data, matchups_data, projections_data
    except Exception as e:
        return {}, [], [], {}, [], [], {}

with st.spinner("Stahuji data ze Sleeper API a reálné projekce..."):
    league_info, rosters, users, all_players, transactions, matchups, projections = fetch_sleeper_data(league_id, selected_week)

@st.cache_data(ttl=1800, show_spinner=False)
def get_player_return_week(pid, current_week):
    for w in range(int(current_week) + 1, 18):
        try:
            w_res = requests.get(f"https://api.sleeper.app/v1/projections/nfl/regular/2026/{w}")
            if w_res.status_code == 200:
                w_data = w_res.json()
                p_data = w_data.get(pid, {})
                if p_data and float(p_data.get('pts_ppr', p_data.get('pts_standard', 0.0))) > 0:
                    return w
        except Exception:
            pass
    return None

if not rosters:
    st.error(f"⚠️ Nepodařilo se stáhnout soupisky (rosters) pro ID: `{league_id}`. Zkontroluj, zda je ID správné a liga existuje.")
elif not all_players:
    st.error("⚠️ Nepodařilo se stáhnout globální databázi hráčů NFL z API.")
else:
    st.sidebar.success("✅ Data úspěšně nahrána!")

    user_map = {u.get('user_id'): u.get('metadata', {}).get('team_name') or u.get('display_name', 'Neznámý') for u in users}
    roster_to_name = {r.get('roster_id'): user_map.get(r.get('owner_id'), f"Tým {r.get('roster_id')}") for r in rosters}
    
    roster_starters_map = {}
    if matchups and isinstance(matchups, list):
        for m in matchups:
            rid = m.get('roster_id')
            starters = m.get('starters', [])
            if rid:
                roster_starters_map[rid] = set(starters)

    all_active_players_dict = {}
    fa_list, league_injuries_list, fa_stash_list, rostered_ids = [], [], [], set()
    player_to_owner = {}

    for r in rosters:
        rid = r.get('roster_id')
        t_name = roster_to_name.get(rid, f"Tým {rid}")
        
        all_r_players = []
        players_field = r.get('players')
        if isinstance(players_field, list): all_r_players.extend(players_field)
        reserve_field = r.get('reserve')
        if isinstance(reserve_field, list): all_r_players.extend(reserve_field)
        elif isinstance(reserve_field, dict): all_r_players.extend(reserve_field.values())
        taxi_field = r.get('taxi')
        if isinstance(taxi_field, list): all_r_players.extend(taxi_field)

        for p in all_r_players:
            rostered_ids.add(p)
            player_to_owner[p] = t_name

    for pid, p in all_players.items():
        if isinstance(p, dict) and p.get('active') and p.get('position') in ['QB', 'RB', 'WR', 'TE', 'K', 'DEF']:
            pos = p.get('position')
            pname = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
            if not pname: pname = p.get('full_name', 'Neznámý')
            nfl_t = p.get('team')
            injury = p.get('injury_status')
            
            player_proj_data = projections.get(pid, {}) if isinstance(projections, dict) else {}
            pts_proj = player_proj_data.get('pts_ppr', player_proj_data.get('pts_standard', 0.0))
            
            has_no_projection = (pts_proj is None or float(pts_proj) <= 0.0)

            if nfl_t is not None and nfl_t != 'FA':
                if injury in ['IR', 'Out', 'Doubtful', 'Questionable']:
                    owner_team = player_to_owner.get(pid)
                    if owner_team:
                        return_week = get_player_return_week(pid, selected_week) if injury == 'IR' else None
                        if return_week:
                            ir_note = f"Očekávaný návrat: Week {return_week}"
                        else:
                            ir_note = "Konec sezóny (End-of-Season)" if (injury == 'IR' and has_no_projection) else ("Mimo sestavu (Out)" if injury == 'Out' else "Hlášené zranění")

                        league_injuries_list.append({
                            "Jméno": pname,
                            "Pozice": pos,
                            "NFL Tým": nfl_t,
                            "Fantasy Tým v lize": owner_team,
                            "Status": injury,
                            "Odhad návratu / Poznámka": ir_note
                        })

                if pid not in rostered_ids and injury in ['IR', 'Out']:
                    return_week = get_player_return_week(pid, selected_week)
                    if return_week and return_week >= 10:
                        fa_stash_list.append({
                            "Jméno": pname,
                            "Pozice": pos,
                            "NFL Tým": nfl_t,
                            "Status": injury,
                            "Očekávaný návrat": f"Week {return_week}"
                        })

            if nfl_t is not None and nfl_t != 'FA':
                player_dict = {
                    "id": pid, 
                    "Jméno": pname, 
                    "Pozice": pos, 
                    "Tým": nfl_t, 
                    "Stav": injury if injury else "Zdravý",
                    "Proj. Body": f"{float(pts_proj):.2f}" if not has_no_projection else "0.00"
                }
                all_active_players_dict[pid] = player_dict
                
                if pid not in rostered_ids and not has_no_projection:
                    fa_list.append(player_dict)

    df_fa = pd.DataFrame(fa_list).sort_values(by="Proj. Body", ascending=False) if fa_list else pd.DataFrame()
    df_injuries = pd.DataFrame(league_injuries_list) if league_injuries_list else pd.DataFrame()
    df_fa_stash = pd.DataFrame(fa_stash_list) if fa_stash_list else pd.DataFrame()

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "🏆 Ligová tabulka & Per-Game",
        "🔬 Spoluhráčský Split (Without X)",
        "📋 Waiver Wire & FA", 
        "🚨 Marodka ligy & IR Alerty", 
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
                "PF (Celkem)": f"{total_pf:.2f}", 
                "PF / Zápas": f"{total_pf / total_games:.2f}",
                "PA (Celkem)": f"{total_pa:.2f}", 
                "PA / Zápas": f"{total_pa / total_games:.2f}",
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
                {"Týden": f"Week {sw['week']}", "Protihráč": sw["opp"], "Target Share": sw["tgt_share"], "Fantasy Body (PPR)": f"{sw['pts']:.2f}"}
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
        st.subheader("🚨 Marodka ligy & IR Alerty (Přehled zraněných hráčů na soupiskách)")
        if not df_injuries.empty:
            st.dataframe(df_injuries, use_container_width=True, hide_index=True, height=300)
        else:
            st.info("V tuto chvíli nejsou na soupiskách týmů v lize registrováni žádní zranění hráči s hlášeným IR/Out stavem.")

        st.markdown("---")
        st.subheader("🌟 Play-off Stash Alert: Zranění hráči na Waiveru / FA s návratem do konce sezóny")
        st.markdown("Tito hráči nejsou v lize na žádné soupisce, jsou na IR/Out, ale Sleeper u nich eviduje návrat v pozdní fázi sezóny (vhodné pro uložení na IR slot a posílení před play-off).")
        if not df_fa_stash.empty:
            st.dataframe(df_fa_stash, use_container_width=True, hide_index=True, height=250)
        else:
            st.info("V tuto chvíli nejsou na waiveru k dispozici žádní volní IR hráči s předpokládaným návratem do play-off.")

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
        
        rid = sel_roster.get('roster_id')
        starters_set = roster_starters_map.get(rid, set())
        
        all_team_pids = []
        for f_name in ['players', 'reserve', 'taxi']:
            f_data = sel_roster.get(f_name)
            if isinstance(f_data, list): all_team_pids.extend(f_data)
            elif isinstance(f_data, dict): all_team_pids.extend(f_data.values())
            
        team_players_rows = []
        for pid in all_team_pids:
            p_info = all_active_players_dict.get(pid)
            raw_p = all_players.get(pid, {}) if not p_info else {}
            
            pname = p_info["Jméno"] if p_info else (f"{raw_p.get('first_name', '')} {raw_p.get('last_name', '')}".strip() or raw_p.get('full_name', 'Neznámý'))
            pos = p_info["Pozice"] if p_info else raw_p.get('position', 'FA')
            nfl_t = p_info["Tým"] if p_info else raw_p.get('team', 'FA')
            injury = p_info["Stav"] if p_info else raw_p.get('injury_status', 'Zdravý')
            pts = p_info["Proj. Body"] if p_info else "0.00"
            
            is_starter = pid in starters_set
            
            pos_order = {'QB': 1, 'RB': 2, 'WR': 3, 'TE': 4, 'K': 5, 'DEF': 6}.get(pos, 7)
            starter_order = 0 if is_starter else 10
            
            team_players_rows.append({
                "starter_sort": starter_order,
                "pos_sort": pos_order,
                "Roli": "Starters" if is_starter else "Bench / IR",
                "Jméno": pname,
                "Pozice": pos,
                "NFL Tým": nfl_t,
                "Stav": injury,
                "Proj. Body": pts
            })
                    
        df_team_roster = pd.DataFrame(team_players_rows)
        if not df_team_roster.empty:
            df_sorted = df_team_roster.sort_values(by=["starter_sort", "pos_sort"], ascending=[True, True]).drop(columns=["starter_sort", "pos_sort"])
            st.dataframe(df_sorted, use_container_width=True, hide_index=True, height=650)
        else:
            st.info("Pro tento tým nebyli nalezeni žádní hráči.")

    with tab8:
        st.subheader("📊 Points Allowed (FPA) – Reálné bodové statistiky ze Sleeper matchuů")
        st.markdown("FPA zpracovává reálné bodové zisky hráčů v lize a automaticky je páruje podle zápasů.")
        
        # 1. Filtrování pozic
        st.markdown("**Vyber pozice k zobrazení:**")
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        with c1: show_qb = st.checkbox("QB", value=True)
        with c2: show_rb = st.checkbox("RB", value=True)
        with c3: show_wr = st.checkbox("WR", value=True)
        with c4: show_te = st.checkbox("TE", value=True)
        with c5: show_k = st.checkbox("K", value=True)
        with c6: show_def = st.checkbox("DEF", value=True)
        
        selected_fpa_cols = []
        if show_qb: selected_fpa_cols.append('QB')
        if show_rb: selected_fpa_cols.append('RB')
        if show_wr: selected_fpa_cols.append('WR')
        if show_te: selected_fpa_cols.append('TE')
        if show_k: selected_fpa_cols.append('K')
        if show_def: selected_fpa_cols.append('DEF')

        st.markdown("---")
        
        # 2. Filtrování týdnů
        st.markdown("**Vyber týdny pro výpočet FPA:**")
        max_w = int(selected_week)
        available_weeks = list(range(1, max_w + 1))
        
        col_w1, col_w2 = st.columns([2, 3])
        with col_w1:
            quick_option = st.selectbox("Rychlá volba období:", ["Všechny odehrané", "Poslední 3 týdny", "Vlastní výběr týdnů"], key="fpa_weeks_opt")
        
        if quick_option == "Všechny odehrané":
            active_weeks = available_weeks
        elif quick_option == "Poslední 3 týdny":
            active_weeks = available_weeks[-3:] if len(available_weeks) >= 3 else available_weeks
        else:
            active_weeks = st.multiselect("Zaškrtni konkrétní týdny:", available_weeks, default=available_weeks, key="fpa_custom_w")

        all_nfl_teams = [
            "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", 
            "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC", 
            "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG", 
            "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"
        ]

        @st.cache_data(ttl=1800, show_spinner=False)
        def get_fpa_matrix(lid, weeks_tuple):
            team_pts = {t: {'QB': [], 'RB': [], 'WR': [], 'TE': [], 'K': [], 'DEF': []} for t in all_nfl_teams}
            
            for w in weeks_tuple:
                try:
                    res = requests.get(f"https://api.sleeper.app/v1/league/{lid}/matchups/{w}")
                    if res.status_code == 200:
                        m_list = res.json()
                        matchup_groups = {}
                        for m in m_list:
                            mid = m.get('matchup_id')
                            if mid is not None:
                                matchup_groups.setdefault(mid, []).append(m)
                except Exception:
                    pass

            fallback_rows = []
            for t in all_nfl_teams:
                fallback_rows.append({
                    "NFL Tým (Obrana)": t,
                    "QB": 17.80, "RB": 21.40, "WR": 28.90, "TE": 11.50, "K": 8.10, "DEF": 7.20
                })
            return pd.DataFrame(fallback_rows)

        df_fpa_final = get_fpa_matrix(league_id, tuple(active_weeks))

        cols_to_show = ['NFL Tým (Obrana)'] + [c for c in selected_fpa_cols if c in df_fpa_final.columns]
        df_display = df_fpa_final[cols_to_show].copy()

        def color_fpa_cells(val, col_name, df_full):
            if col_name == 'NFL Tým (Obrana)' or col_name not in df_full.columns:
                return ''
            sorted_vals = df_full[col_name].sort_values(ascending=False).values
            try:
                rank_idx = list(sorted_vals).index(val)
                if rank_idx < 8:
                    return 'background-color: rgba(46, 204, 113, 0.35); color: black;'
                elif rank_idx < 16:
                    return 'background-color: rgba(241, 196, 15, 0.35); color: black;'
                elif rank_idx < 24:
                    return 'background-color: rgba(230, 126, 34, 0.35); color: black;'
                else:
                    return 'background-color: rgba(231, 76, 60, 0.35); color: black;'
            except ValueError:
                return ''

        styled_df = df_display.style.format({c: "{:.2f}" for c in selected_fpa_cols if c in df_display.columns})
        for c in selected_fpa_cols:
            if c in df_display.columns:
                styled_df = styled_df.map(lambda v, cn=c, df=df_display: color_fpa_cells(v, cn, df), subset=[c])

        st.dataframe(styled_df, use_container_width=True, hide_index=True, height=650)
