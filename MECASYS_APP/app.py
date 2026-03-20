import streamlit as st
import pandas as pd
import numpy as np
import math
import pickle
import xgboost as xgb
import os
from datetime import date
from fpdf import FPDF

# --- 1. KONFIGURÁCIA A NAČÍTANIE AI MODELOV ---
st.set_page_config(page_title="MECASYS AI Kalkulátor", layout="wide")

# Definícia cesty k priečinku so súbormi
BASE_PATH = "MECASYS_APP"

@st.cache_resource
def load_ai_assets():
    try:
        # MODEL M1: Čas
        m1 = xgb.Booster()
        m1.load_model(os.path.join(BASE_PATH, 'finalny_model.json'))
        with open(os.path.join(BASE_PATH, 'stlpce_modelu.pkl'), 'rb') as f:
            m1_cols = pickle.load(f)
            
        # MODEL M2: Cena
        m2 = xgb.Booster()
        m2.load_model(os.path.join(BASE_PATH, 'xgb_model_cena.json'))
        with open(os.path.join(BASE_PATH, 'model_columns.pkl'), 'rb') as f:
            m2_cols = pickle.load(f)
            
        return m1, m1_cols, m2, m2_cols
    except Exception as e:
        st.error(f"❌ Chyba pri načítaní AI modelov z priečinka {BASE_PATH}: {e}")
        return None, None, None, None

m1, m1_cols, m2, m2_cols = load_ai_assets()

# --- 2. NAČÍTANIE DÁT Z GOOGLE SHEETS ---
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
            # Premenovanie pre ošetrenie chýb (KeyError) zo screenshotov
            rename_map = {
                'zákazník': 'zakaznik', 'akost': 'akost', 'akosť': 'akost', 
                'materiál': 'material', 'j.cena/m': 'jc_m', 'cena/m': 'jc_m',
                'minimalna_zakazka': 'min_zak', 'minimálna zákazka': 'min_zak'
            }
            df.rename(columns=rename_map, inplace=True, errors='ignore')
            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].astype(str).str.strip().str.upper()
            loaded[key] = df
        except: st.error(f"⚠️ Nepodarilo sa pripojiť k tabuľke: {key}")
    return loaded

db = load_db()

# --- 3. POMOCNÉ FUNKCIE ---
def get_hustota(m, a, df_a):
    if m == "OCEĽ": return 7900
    if m == "NEREZ": return 8000
    if m == "PLAST":
        res = df_a[df_a['akost'] == a]['hustota']
        return float(pd.to_numeric(res.values[0], errors='coerce')) if not res.empty else 1200
    return 7850

# --- 4. ROZHRANIE A VÝPOČTY ---
if 'kosik' not in st.session_state:
    st.session_state.kosik = []

if db and m1 and m2:
    st.title("⚙️ MECASYS AI - Komplexná Kalkulácia")
    
    with st.expander("📄 Základné údaje", expanded=True):
        c1, c2, c3 = st.columns(3)
        datum_cp = c1.date_input("Dátum", date.today())
        cp_num = c2.text_input("Číslo CP", "2026-001")
        zak_list = sorted(db['zakaznici']['zakaznik'].unique())
        vybrany_zak = c3.selectbox("Zákazník", zak_list)
        row_z = db['zakaznici'][db['zakaznici']['zakaznik'] == vybrany_zak].iloc[0]
        lojalita = float(pd.to_numeric(row_z.get('lojalita', 1.0), errors='coerce'))

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Špecifikácia dielu")
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
        res_mat['d'] = pd.to_numeric(res_mat['d'], errors='coerce')
        vyssie = res_mat[res_mat['d'] >= d].sort_values('d')
        if not vyssie.empty:
            jc_m = float(pd.to_numeric(vyssie.iloc[0]['jc_m'], errors='coerce'))
            calc_mat_unit = (l / 1000) * jc_m

    with col_r:
        st.subheader("Náklady a kooperácia")
        naklad_mat = st.number_input("Cena mat. / ks [€]", value=calc_mat_unit, format="%.3f")
        
        koop_ano = st.radio("Kooperácia?", ["NIE", "ÁNO"])
        naklad_koop = 0.0
        if koop_ano == "ÁNO":
            df_k = db['koop_cena']
            druhy = df_k[df_k['material'] == mat]['druh'].unique()
            if len(druhy) > 0:
                druh = st.selectbox("Služba", druhy)
                rk = df_k[(df_k['druh'] == druh) & (df_k['material'] == mat)].iloc[0]
                tarifa = float(pd.to_numeric(rk.get('tarifa', 0), errors='coerce'))
                min_zak_val = float(pd.to_numeric(rk.get('min_zak', 0), errors='coerce'))
                naklad_koop = st.number_input("Cena koop. / ks [€]", value=max(tarifa, min_zak_val/ks))
        
        narocnost = st.select_slider("Náročnosť", options=[1, 2, 3, 4, 5], value=3)

    # --- AI PREDIKCIA ---
    st.divider()
    # M1 Čas
    input_m1 = pd.DataFrame([[d, l, narocnost]], columns=m1_cols)
    cas_s = float(m1.predict(xgb.DMatrix(input_m1))[0])
    
    # M2 Cena
    input_m2 = pd.DataFrame([[naklad_mat, naklad_koop, cas_s, lojalita]], columns=m2_cols)
    cena_f = float(m2.predict(xgb.DMatrix(input_m2))[0])
    
    st.success(f"💰 Odhadovaná cena: **{cena_f:.2f} € / ks** (Predikovaný čas: {cas_s:.2f} s)")

    if st.button("➕ PRIDAŤ DO PONUKY"):
        st.session_state.kosik.append({"ITEM": item, "Ks": ks, "Cena/ks": round(cena_f, 2), "Spolu": round(cena_f * ks, 2)})
        st.rerun()

    if st.session_state.kosik:
        df_k = pd.DataFrame(st.session_state.kosik)
        st.table(df_k)
        if st.button("🏁 GENEROVAŤ PDF"):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt=f"CP: {cp_num} - {vybrany_zak}", ln=True)
            for r in st.session_state.kosik:
                pdf.cell(200, 10, txt=f"{r['ITEM']} | {r['Ks']}ks | {r['Cena/ks']}€/ks", ln=True)
            st.download_button("Siahnuť PDF", data=pdf.output(dest='S').encode('latin-1'), file_name="ponuka.pdf")

else:
    st.info("🔄 Inicializujem AI modely... Uisti sa, že súbory sú v priečinku MECASYS_APP.")
