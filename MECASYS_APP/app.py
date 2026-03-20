import streamlit as st
import pandas as pd
import numpy as np
import math
import pickle
import xgboost as xgb
import os
from datetime import date
from fpdf import FPDF

# --- 1. INTELIGENTNÉ NAČÍTANIE MODELOV ---
st.set_page_config(page_title="MECASYS AI Kalkulátor", layout="wide")

def find_file(filename):
    """Skontroluje, či súbor existuje v root alebo v MECASYS_APP/"""
    paths = [filename, os.path.join("MECASYS_APP", filename)]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

@st.cache_resource
def load_ai_assets():
    try:
        # Hľadanie súborov
        m1_path = find_file('finalny_model.json')
        m1_cols_path = find_file('stlpce_modelu.pkl')
        m2_path = find_file('xgb_model_cena.json')
        m2_cols_path = find_file('model_columns.pkl')

        if not all([m1_path, m1_cols_path, m2_path, m2_cols_path]):
            st.error("❌ Chýbajú kritické súbory (.json alebo .pkl) v priečinkoch.")
            return None, None, None, None

        # Načítanie M1 (Čas)
        m1 = xgb.Booster()
        m1.load_model(m1_path)
        with open(m1_cols_path, 'rb') as f:
            m1_cols = pickle.load(f)
            
        # Načítanie M2 (Cena)
        m2 = xgb.Booster()
        m2.load_model(m2_path)
        with open(m2_cols_path, 'rb') as f:
            m2_cols = pickle.load(f)
            
        return m1, m1_cols, m2, m2_cols
    except Exception as e:
        st.error(f"❌ Chyba pri načítaní AI: {e}")
        return None, None, None, None

m1, m1_cols, m2, m2_cols = load_ai_assets()

# --- 2. NAČÍTANIE DÁT (GOOGLE SHEETS) ---
LINKS = {
    "materialy": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1281008948&single=true&output=csv",
    "zakaznici": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=324957857&single=true&output=csv",
    "mat_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=901617097&single=true&output=csv",
    "koop_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1180392224&single=true&output=csv"
}

@st.cache_data(ttl=300)
def load_db():
    data_out = {}
    for key, url in LINKS.items():
        try:
            df = pd.read_csv(url)
            df.columns = df.columns.str.strip().str.lower()
            # Mapa premenovania pre stabilitu (diakritika)
            rename_map = {
                'zákazník': 'zakaznik', 'akost': 'akost', 'akosť': 'akost', 
                'materiál': 'material', 'j.cena/m': 'jc_m', 'cena/m': 'jc_m',
                'minimalna_zakazka': 'min_zak', 'minimálna zákazka': 'min_zak'
            }
            df.rename(columns=rename_map, inplace=True, errors='ignore')
            # Vyčistenie textových hodnôt
            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].astype(str).str.strip().str.upper()
            data_out[key] = df
        except: st.error(f"Chyba tabuľky: {key}")
    return data_out

db = load_db()

# --- 3. ROZHRANIE ---
if 'kosik' not in st.session_state:
    st.session_state.kosik = []

if db and m1 and m2:
    st.title("⚙️ MECASYS AI - Produkčná Kalkulácia")
    
    with st.expander("📄 Základné údaje", expanded=True):
        c1, c2, c3 = st.columns(3)
        datum_cp = c1.date_input("Dátum", date.today())
        cp_num = c2.text_input("Číslo CP", "2026-001")
        # Ošetrenie stĺpca zákazník
        z_col = 'zakaznik' if 'zakaznik' in db['zakaznici'].columns else db['zakaznici'].columns[0]
        vybrany_zak = c3.selectbox("Zákazník", sorted(db['zakaznici'][z_col].unique()))
        row_z = db['zakaznici'][db['zakaznici'][z_col] == vybrany_zak].iloc[0]
        lojalita = float(pd.to_numeric(row_z.get('lojalita', 1.0), errors='coerce'))

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Technické vstupy")
        item = st.text_input("ITEM (Názov)").upper()
        mat = st.selectbox("Materiál", ["OCEĽ", "NEREZ", "PLAST", "FAREBNÉ KOVY"])
        akosti = sorted(db['materialy'][db['materialy']['material'] == mat]['akost'].unique())
        akost = st.selectbox("Akosť", akosti)
        d = st.number_input("Priemer d [mm]", value=20.0)
        l = st.number_input("Dĺžka l [mm]", value=50.0)
        ks = st.number_input("Množstvo [ks]", min_value=1, value=100)

    # Cena materiálu z tabuľky (ošetrenie TypeError)
    df_mc = db['mat_cena']
    mask = (df_mc['material'] == mat) & (df_mc['akost'] == akost)
    res_mat = df_mc[mask]
    calc_mat_unit = 0.0
    if not res_mat.empty:
        # Prevod na čísla pre výpočet
        d_vals = pd.to_numeric(res_mat['d'], errors='coerce')
        jc_vals = pd.to_numeric(res_mat['jc_m'], errors='coerce')
        vyssie = res_mat[d_vals >= d].copy()
        vyssie['jc_num'] = pd.to_numeric(vyssie['jc_m'], errors='coerce')
        vyssie = vyssie.sort_values('d')
        if not vyssie.empty:
            calc_mat_unit = (l / 1000) * float(vyssie.iloc[0]['jc_num'])

    with col_r:
        st.subheader("Vstupy pre technológa")
        naklad_mat = st.number_input("Materiál / ks [€]", value=calc_mat_unit, format="%.3f")
        
        koop_ano = st.radio("Kooperácia?", ["NIE", "ÁNO"])
        naklad_koop = 0.0
        if koop_ano == "ÁNO":
            df_k = db['koop_cena']
            druhy = df_k[df_k['material'] == mat]['druh'].unique()
            if len(druhy) > 0:
                druh = st.selectbox("Služba", druhy)
                rk = df_k[(df_k['druh'] == druh) & (df_k['material'] == mat)].iloc[0]
                tarifa = float(pd.to_numeric(rk.get('tarifa', 0), errors='coerce'))
                min_zak = float(pd.to_numeric(rk.get('min_zak', 0), errors='coerce'))
                naklad_koop = st.number_input("Kooperácia / ks [€]", value=max(tarifa, min_zak/ks))
        
        narocnost = st.select_slider("Náročnosť výroby", options=[1, 2, 3, 4, 5], value=3)

    # --- AI PREDIKCIA (M1 a M2) ---
    st.divider()
    # M1 Čas
    input_m1 = pd.DataFrame([[d, l, narocnost]], columns=m1_cols)
    cas_s = float(m1.predict(xgb.DMatrix(input_m1))[0])
    
    # M2 Cena
    input_m2 = pd.DataFrame([[naklad_mat, naklad_koop, cas_s, lojalita]], columns=m2_cols)
    cena_f = float(m2.predict(xgb.DMatrix(input_m2))[0])
    
    st.success(f"💰 Odhadovaná cena: **{cena_f:.2f} € / ks** | ⏱️ Predikovaný čas: **{cas_s:.2f} s**")

    if st.button("➕ PRIDAŤ DO PONUKY"):
        st.session_state.kosik.append({
            "ITEM": item, "Ks": ks, "Cena/ks": round(cena_f, 2), "Spolu": round(cena_f * ks, 2)
        })
        st.rerun()

    if st.session_state.kosik:
        st.subheader("🛒 Rozpracovaná ponuka")
        st.table(pd.DataFrame(st.session_state.kosik))
        if st.button("🏁 GENEROVAŤ PDF"):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(200, 10, txt=f"CP: {cp_num} - {vybrany_zak}", ln=True, align='C')
            pdf.set_font("Arial", size=10)
            for r in st.session_state.kosik:
                pdf.cell(200, 10, txt=f"{r['ITEM']} | {r['Ks']}ks | {r['Cena/ks']}€/ks | Spolu: {r['Spolu']}€", ln=True)
            st.download_button("Siahnuť PDF", data=pdf.output(dest='S').encode('latin-1'), file_name=f"{cp_num}.pdf")
else:
    st.warning("🔄 Čakám na nahranie súborov .json a .pkl na GitHub. Skontroluj priečinok MECASYS_APP.")
