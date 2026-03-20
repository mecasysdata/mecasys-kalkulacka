import streamlit as st
import pandas as pd
import numpy as np
import math
import pickle
import xgboost as xgb
import os
from datetime import date
from fpdf import FPDF

# --- 1. CESTY K SÚBOROM (OPRAVA TOČENIA SA DOOKOLA) ---
# Tento riadok zistí, v ktorom priečinku je tento skript app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@st.cache_resource
def load_ai_assets():
    try:
        # Definovanie ciest k súborom relatívne k app.py
        path_m1 = os.path.join(BASE_DIR, 'finalny_model.json')
        path_m1_cols = os.path.join(BASE_DIR, 'stlpce_modelu.pkl')
        path_m2 = os.path.join(BASE_DIR, 'xgb_model_cena.json')
        path_m2_cols = os.path.join(BASE_DIR, 'model_columns.pkl')

        # Kontrola, či súbory existujú, než ich skúsime otvoriť
        for p in [path_m1, path_m1_cols, path_m2, path_m2_cols]:
            if not os.path.exists(p):
                st.error(f"❌ Súbor nebol nájdený na ceste: {p}")
                return None, None, None, None

        # Načítanie Modelu M1 (Čas)
        m1 = xgb.Booster()
        m1.load_model(path_m1)
        with open(path_m1_cols, 'rb') as f:
            m1_cols = pickle.load(f)
            
        # Načítanie Modelu M2 (Cena)
        m2 = xgb.Booster()
        m2.load_model(path_m2)
        with open(path_m2_cols, 'rb') as f:
            m2_cols = pickle.load(f)
            
        return m1, m1_cols, m2, m2_cols
    except Exception as e:
        st.error(f"❌ Kritická chyba AI: {e}")
        return None, None, None, None

m1, m1_cols, m2, m2_cols = load_ai_assets()

# --- 2. DÁTA Z GOOGLE SHEETS ---
LINKS = {
    "materialy": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1281008948&single=true&output=csv",
    "zakaznici": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=324957857&single=true&output=csv",
    "mat_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=901617097&single=true&output=csv",
    "koop_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1180392224&single=true&output=csv"
}

@st.cache_data(ttl=300)
def load_db():
    loaded = {}
    for key, url in LINKS.items():
        try:
            df = pd.read_csv(url)
            df.columns = df.columns.str.strip().str.lower()
            # Oprava diakritiky a názvov stĺpcov
            rename_map = {'zákazník': 'zakaznik', 'akost': 'akost', 'akosť': 'akost', 
                          'materiál': 'material', 'j.cena/m': 'jc_m', 'cena/m': 'jc_m',
                          'minimalna_zakazka': 'min_zak', 'minimálna zákazka': 'min_zak'}
            df.rename(columns=rename_map, inplace=True, errors='ignore')
            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].astype(str).str.strip().str.upper()
            loaded[key] = df
        except: st.error(f"⚠️ Chyba načítania tabuľky: {key}")
    return loaded

db = load_db()

# --- 3. LOGIKA VÝPOČTU ---
if 'kosik' not in st.session_state:
    st.session_state.kosik = []

if db and m1 and m2:
    st.title("⚙️ MECASYS AI - Produkčný Kalkulátor")
    
    with st.expander("📄 Základné informácie", expanded=True):
        c1, c2, c3 = st.columns(3)
        datum_cp = c1.date_input("Dátum", date.today())
        cp_cislo = c2.text_input("Číslo CP", "2026-001")
        vybrany_zak = c3.selectbox("Zákazník", sorted(db['zakaznici']['zakaznik'].unique()))
        row_z = db['zakaznici'][db['zakaznici']['zakaznik'] == vybrany_zak].iloc[0]
        lojalita = float(pd.to_numeric(row_z.get('lojalita', 1.0), errors='coerce'))

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Technické parametre")
        item = st.text_input("ITEM (ID dielu)").upper()
        mat = st.selectbox("Materiál", ["OCEĽ", "NEREZ", "PLAST", "FAREBNÉ KOVY"])
        akosti = sorted(db['materialy'][db['materialy']['material'] == mat]['akost'].unique())
        akost = st.selectbox("Akosť", akosti)
        d = st.number_input("Priemer d [mm]", value=20.0)
        l = st.number_input("Dĺžka l [mm]", value=50.0)
        ks = st.number_input("Množstvo [ks]", min_value=1, value=100)

    # Nájdenie ceny materiálu (oprava TypeError zo screenshotu)
    df_mc = db['mat_cena']
    mask = (df_mc['material'] == mat) & (df_mc['akost'] == akost)
    res_mat = df_mc[mask]
    calc_mat_unit = 0.0
    if not res_mat.empty:
        # Prevod d a jc_m na čísla pre výpočet
        res_mat['d_num'] = pd.to_numeric(res_mat['d'], errors='coerce')
        res_mat['jc_num'] = pd.to_numeric(res_mat['jc_m'], errors='coerce')
        vyssie = res_mat[res_mat['d_num'] >= d].sort_values('d_num')
        if not vyssie.empty:
            calc_mat_unit = (l / 1000) * float(vyssie.iloc[0]['jc_num'])

    with col_r:
        st.subheader("Vstupy technológa")
        naklad_mat = st.number_input("Materiál / ks [€]", value=calc_mat_unit, format="%.3f")
        
        koop_ano = st.radio("Kooperácia?", ["NIE", "ÁNO"])
        naklad_koop = 0.0
        if koop_ano == "ÁNO":
            df_k = db['koop_cena']
            druhy = df_k[df_k['material'] == mat]['druh'].unique()
            if len(druhy) > 0:
                druh = st.selectbox("Typ kooperácie", druhy)
                rk = df_k[(df_k['druh'] == druh) & (df_k['material'] == mat)].iloc[0]
                tarifa = float(pd.to_numeric(rk.get('tarifa', 0), errors='coerce'))
                min_zak = float(pd.to_numeric(rk.get('min_zak', 0), errors='coerce'))
                naklad_koop = st.number_input("Kooperácia / ks [€]", value=max(tarifa, min_zak/ks))
        
        narocnost = st.select_slider("Náročnosť výroby", options=[1, 2, 3, 4, 5], value=3)

    # --- AI JADRO ---
    st.divider()
    # Predikcia Času (M1)
    input_m1 = pd.DataFrame([[d, l, narocnost]], columns=m1_cols)
    cas_s = float(m1.predict(xgb.DMatrix(input_m1))[0])
    
    # Predikcia Ceny (M2)
    input_m2 = pd.DataFrame([[naklad_mat, naklad_koop, cas_s, lojalita]], columns=m2_cols)
    cena_f = float(m2.predict(xgb.DMatrix(input_m2))[0])
    
    st.success(f"💰 Odhadovaná cena: **{cena_f:.2f} € / ks** (Predpokladaný čas: {cas_s:.2f} s)")

    if st.button("➕ Pridať do košíka"):
        st.session_state.kosik.append({"ITEM": item, "Ks": ks, "Cena/ks": round(cena_f, 2), "Spolu": round(cena_f * ks, 2)})
        st.rerun()

    if st.session_state.kosik:
        st.table(pd.DataFrame(st.session_state.kosik))
        if st.button("🏁 Exportovať do PDF"):
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt=f"CP {cp_cislo} - {vybrany_zak}", ln=True, align='C')
            for r in st.session_state.kosik:
                pdf.cell(200, 10, txt=f"{r['ITEM']} | {r['Ks']} ks | {r['Cena/ks']} €/ks", ln=True)
            st.download_button("Siahnuť ponuku", data=pdf.output(dest='S').encode('latin-1'), file_name=f"CP_{cp_cislo}.pdf")
else:
    st.info("🔄 Inicializujem AI modely. Ak vidíš chybu, skontroluj, či sú súbory .json a .pkl v rovnakom priečinku ako app.py.")
