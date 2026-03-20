import streamlit as st
import pandas as pd
import numpy as np
import math
import pickle
import xgboost as xgb
from datetime import date
from fpdf import FPDF

# --- 1. KONFIGURÁCIA A NAČÍTANIE AI MODELOV ---
st.set_page_config(page_title="MECASYS AI Kalkulátor", layout="wide")

@st.cache_resource
def load_ai_assets():
    try:
        # MODEL M1: Čas (JSON + PKL stĺpce)
        m1 = xgb.Booster()
        m1.load_model('finalny_model.json')
        with open('stlpce_modelu.pkl', 'rb') as f:
            m1_cols = pickle.load(f)
            
        # MODEL M2: Cena (JSON + PKL stĺpce)
        m2 = xgb.Booster()
        m2.load_model('xgb_model_cena.json')
        with open('model_columns.pkl', 'rb') as f:
            m2_cols = pickle.load(f)
            
        return m1, m1_cols, m2, m2_cols
    except Exception as e:
        st.error(f"❌ Chyba pri načítaní AI modelov: {e}")
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
            # Unifikácia názvov (oprava chýb z tabuliek)
            rename_map = {'zákazník': 'zakaznik', 'akost': 'akost', 'akosť': 'akost', 'materiál': 'material', 'j.cena/m': 'jc_m'}
            df.rename(columns=rename_map, inplace=True, errors='ignore')
            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].astype(str).str.strip().str.upper()
            loaded[key] = df
        except: st.error(f"⚠️ Chyba pripojenia k tabuľke: {key}")
    return loaded

db = load_db()

# --- 3. POMOCNÉ FUNKCIE ---
def get_hustota(m, a, df_a):
    if m == "OCEĽ": return 7900
    if m == "NEREZ": return 8000
    if m == "PLAST":
        res = df_a[df_a['akost'] == a]['hustota']
        return float(pd.to_numeric(res.values[0], errors='coerce')) if not res.empty else 1200
    if m == "FAREBNÉ KOVY":
        if a.startswith("3.7"): return 4500
        if a.startswith("3."): return 2900
        if a.startswith("2."): return 9000
    return 7850

# --- 4. SESSION STATE (KOŠÍK) ---
if 'kosik' not in st.session_state:
    st.session_state.kosik = []

# --- 5. ROZHRANIE APLIKÁCIE ---
if db and m1 and m2:
    st.title("🚀 MECASYS AI - Komplexná Kalkulácia")
    
    with st.expander("📄 Základné údaje", expanded=True):
        c1, c2, c3 = st.columns(3)
        datum_cp = c1.date_input("Dátum CP", date.today())
        cp_num = c2.text_input("Číslo CP", "2026-001")
        zak_list = sorted(db['zakaznici']['zakaznik'].unique())
        vybrany_zak = c3.selectbox("Zákazník", zak_list)
        row_z = db['zakaznici'][db['zakaznici']['zakaznik'] == vybrany_zak].iloc[0]
        lojalita = float(pd.to_numeric(row_z.get('lojalita', 1.0), errors='coerce'))

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Technické parametre")
        item = st.text_input("ITEM (Názov/ID)").upper()
        mat = st.selectbox("Materiál", ["OCEĽ", "NEREZ", "PLAST", "FAREBNÉ KOVY"])
        akosti = sorted(db['materialy'][db['materialy']['material'] == mat]['akost'].unique())
        akost = st.selectbox("Akosť", akosti)
        d = st.number_input("Priemer d [mm]", value=20.0)
        l = st.number_input("Dĺžka l [mm]", value=50.0)
        ks = st.number_input("Množstvo [ks]", min_value=1, value=100)

    # Logika ceny materiálu (Bod 10)
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
        st.subheader("Vstupy pre technológa")
        naklad_mat = st.number_input("Cena materiálu na 1 ks [€]", value=calc_mat_unit, format="%.3f")
        
        koop_ano = st.radio("Kooperácia?", ["NIE", "ÁNO"])
        naklad_koop = 0.0
        if koop_ano == "ÁNO":
            df_k = db['koop_cena']
            druhy = df_k[df_k['material'] == mat]['druh'].unique()
            if len(druhy) > 0:
                druh = st.selectbox("Druh služby", druhy)
                rk = df_k[(df_k['druh'] == druh) & (df_k['material'] == mat)].iloc[0]
                h = get_hustota(mat, akost, db['materialy'])
                vaha = h * (math.pi/4) * (d/1000)**2 * (l/1000)
                plocha = (math.pi * d * l) / 10000
                tarifa = float(pd.to_numeric(rk.get('tarifa', 0), errors='coerce'))
                odhad_k = tarifa * (vaha if "KG" in str(rk.get('jednotka','')).upper() else plocha)
                min_zak_ks = float(pd.to_numeric(rk.get('min_zak', 0), errors='coerce')) / ks
                naklad_koop = st.number_input("Cena kooperácie na 1 ks [€]", value=max(odhad_k, min_zak_ks))
        
        narocnost = st.select_slider("Náročnosť (vstup pre M1)", options=[1, 2, 3, 4, 5], value=3)

    st.divider()

    # --- AI JADRO (M1 & M2) ---
    # 1. Model M1: Čas (Striktne)
    input_m1 = pd.DataFrame([[d, l, narocnost]], columns=m1_cols)
    dmatrix_m1 = xgb.DMatrix(input_m1)
    cas_sekundy = float(m1.predict(dmatrix_m1)[0])
    st.info(f"⏱️ **Model M1 (Čas):** {cas_sekundy:.2f} s / ks")

    # 2. Model M2: Cena (Striktne)
    input_m2 = pd.DataFrame([[naklad_mat, naklad_koop, cas_sekundy, lojalita]], columns=m2_cols)
    dmatrix_m2 = xgb.DMatrix(input_m2)
    cena_final = float(m2.predict(dmatrix_m2)[0])
    st.success(f"💰 **Model M2 (Predajná cena):** {cena_final:.2f} € / ks")

    # --- AKCIE ---
    c_add, c_reset = st.columns(2)
    if c_add.button("➕ PRIDAŤ POLOŽKU DO PONUKY"):
        st.session_state.kosik.append({
            "ITEM": item, "Ks": ks, "Mat/ks": round(naklad_mat, 3), 
            "Koop/ks": round(naklad_koop, 3), "Čas/ks [s]": round(cas_sekundy, 2),
            "Cena/ks": round(cena_final, 2), "Spolu": round(cena_final * ks, 2)
        })
        st.rerun()

    if st.session_state.kosik:
        st.subheader("🛒 Položky v aktuálnej ponuke")
        df_k = pd.DataFrame(st.session_state.kosik)
        st.dataframe(df_k, use_container_width=True)
        
        celkom = df_k['Spolu'].sum()
        st.metric("CELKOVÁ SUMA BEZ DPH", f"{celkom:.2f} €")

        if st.button("🏁 GENEROVAŤ PDF"):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(200, 10, txt=f"Cenová ponuka: {cp_num}", ln=True, align='C')
            pdf.set_font("Arial", size=10)
            pdf.cell(200, 10, txt=f"Zákazník: {vybrany_zak} | Dátum: {datum_cp}", ln=True)
            pdf.ln(10)
            
            # Tabuľka
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(60, 10, "ITEM", 1); pdf.cell(30, 10, "Množstvo", 1); pdf.cell(40, 10, "Cena/ks [€]", 1); pdf.cell(40, 10, "Spolu [€]", 1)
            pdf.ln()
            pdf.set_font("Arial", size=10)
            for _, r in df_k.iterrows():
                pdf.cell(60, 10, str(r['ITEM']), 1)
                pdf.cell(30, 10, str(r['Ks']), 1)
                pdf.cell(40, 10, f"{r['Cena/ks']:.2f}", 1)
                pdf.cell(40, 10, f"{r['Spolu']:.2f}", 1)
                pdf.ln()
            
            pdf.ln(5)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(170, 10, txt=f"CELKOM: {celkom:.2f} EUR", ln=True, align='R')
            
            st.download_button("📑 STIAHNUŤ PDF", data=pdf.output(dest='S').encode('latin-1'), file_name=f"{cp_num}.pdf")

        if c_reset.button("🗑️ VYMAZAŤ CELÚ PONUKU"):
            st.session_state.kosik = []
            st.rerun()
else:
    st.warning("🔄 Inicializujem aplikáciu... Uisti sa, že súbory .json a .pkl sú nahraté na GitHube.")
