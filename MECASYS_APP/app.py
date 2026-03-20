import streamlit as st
import pandas as pd
import numpy as np
import math
import pickle
from datetime import date
from fpdf import FPDF

# --- 1. KONFIGURÁCIA A MODELY ---
st.set_page_config(page_title="MECASYS Kalkulátor", layout="wide")

@st.cache_resource
def load_models():
    try:
        with open('M1.pkl', 'rb') as f:
            m1 = pickle.load(f)
        with open('M2.pkl', 'rb') as f:
            m2 = pickle.load(f)
        return m1, m2
    except Exception as e:
        st.error(f"Kritická chyba: Nepodarilo sa načítať AI modely (.pkl). {e}")
        return None, None

model_m1, model_m2 = load_models()

# --- 2. NAČÍTANIE DÁT Z GOOGLE SHEETS ---
LINKS = {
    "materialy": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1281008948&single=true&output=csv",
    "zakaznici": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=324957857&single=true&output=csv",
    "mat_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=901617097&single=true&output=csv",
    "koop_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1180392224&single=true&output=csv"
}

@st.cache_data(ttl=300)
def load_and_clean_data():
    loaded = {}
    for key, url in LINKS.items():
        try:
            df = pd.read_csv(url)
            df.columns = df.columns.str.strip()
            # Unifikácia názvov (oprava KeyError z obrázkov)
            rename_map = {'Zákazník': 'zakaznik', 'Akosť': 'akost', 'Materiál': 'material', 'J.cena/m': 'jc_m'}
            df.rename(columns=rename_map, inplace=True, errors='ignore')
            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].astype(str).str.strip().str.upper()
            loaded[key] = df
        except: st.error(f"Chyba načítania: {key}")
    return loaded

data = load_and_clean_data()

# --- 3. POMOCNÉ FUNKCIE ---
def get_hustota(m, a, df_a):
    if m == "OCEĽ": return 7900
    if m == "NEREZ": return 8000
    if m == "PLAST":
        res = df_a[df_a['akost'] == a]['hustota']
        return float(res.values[0]) if not res.empty else 1200
    if m == "FAREBNÉ KOVY":
        if a.startswith("3.7"): return 4500
        if a.startswith("3."): return 2900
        if a.startswith("2."): return 9000
    return 7850

# --- 4. SESSION STATE (KOŠÍK) ---
if 'kosik' not in st.session_state:
    st.session_state.kosik = []

# --- 5. ROZHRANIE ---
st.title("📊 MECASYS AI - Technologická Kalkulácia")

if data and model_m1:
    with st.expander("📄 Záhlavie Cenovej Ponuky", expanded=True):
        c1, c2, c3 = st.columns(3)
        datum = c1.date_input("Dátum", date.today())
        cp_cislo = c2.text_input("Číslo CP", "2026-XXX")
        zak_list = sorted(data['zakaznici']['zakaznik'].unique())
        vybrany_zak = c3.selectbox("Zákazník", zak_list)
        row_z = data['zakaznici'][data['zakaznici']['zakaznik'] == vybrany_zak].iloc[0]
        lojalita = float(row_z.get('lojalita', 1.0))

    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Technické parametre")
        item_id = st.text_input("ITEM (Názov komponentu)").upper()
        mat_kat = st.selectbox("Materiál", ["OCEĽ", "NEREZ", "PLAST", "FAREBNÉ KOVY"])
        akosti = sorted(data['materialy'][data['materialy']['material'] == mat_kat]['akost'].unique())
        akost = st.selectbox("Akosť", akosti)
        d = st.number_input("Priemer d [mm]", value=20.0)
        l = st.number_input("Dĺžka l [mm]", value=50.0)
        ks = st.number_input("Počet kusov", min_value=1, value=100)

    # VÝPOČET MATERIÁLU (Logika Bod 10)
    df_mc = data['mat_cena']
    mask = (df_mc['material'] == mat_kat) & (df_mc['akost'] == akost)
    res_mat = df_mc[mask]
    
    naklad_mat_vypocitany = 0.0
    if not res_mat.empty:
        vyssie = res_mat[res_mat['d'] >= d].sort_values('d')
        if not vyssie.empty:
            naklad_mat_vypocitany = (l / 1000) * float(vyssie.iloc[0]['jc_m'])

    with col_r:
        st.subheader("Vstupy technológa")
        # Ručná korekcia materiálu
        naklad_mat = st.number_input("Cena materiálu na 1 komponent [€]", value=naklad_mat_vypocitany, format="%.3f")
        
        # Kooperácia (Logika Bod 11)
        koop_ano = st.radio("Kooperácia?", ["NIE", "ÁNO"])
        naklad_koop = 0.0
        if koop_ano == "ÁNO":
            df_k = data['koop_cena']
            druhy = df_k[df_k['material'] == mat_kat]['druh'].unique()
            if len(druhy) > 0:
                druh = st.selectbox("Služba", druhy)
                rk = df_k[(df_k['druh'] == druh) & (df_k['material'] == mat_kat)].iloc[0]
                h_val = get_hustota(mat_kat, akost, data['materialy'])
                vaha = h_val * (math.pi/4) * (d/1000)**2 * (l/1000)
                plocha = (math.pi * d * l) / 10000
                odhad_k = float(rk['tarifa']) * (vaha if "KG" in str(rk['jednotka']).upper() else plocha)
                min_z = float(rk.get('min_zak', 0))
                vypocitana_k = max(odhad_k, min_z / ks)
                naklad_koop = st.number_input("Cena kooperácie na 1 komponent [€]", value=vypocitana_k)

        narocnost = st.select_slider("Náročnosť výroby", options=[1, 2, 3, 4, 5], value=3)

    # --- JADRO VÝPOČTU (MODELY M1 A M2) ---
    st.divider()
    
    # 1. Predikcia Času (M1) - STRIKTNÁ
    vstupy_m1 = np.array([[d, l, narocnost]]) # Príklad vstupu, uprav podľa tvojho modelu
    cas_sekundy = float(model_m1.predict(vstupy_m1)[0])
    st.info(f"⏱️ Model M1 predikoval čas: {cas_sekundy:.2f} sekúnd / ks")

    # 2. Predikcia Finálnej Ceny (M2) - STRIKTNÁ
    # Vstupy pre M2: Mat + Koop + Čas + Lojalita
    vstupy_m2 = np.array([[naklad_mat, naklad_koop, cas_sekundy, lojalita]])
    try:
        cena_final = float(model_m2.predict(vstupy_m2)[0])
        st.success(f"💰 Finálna cena určená modelom M2: {cena_final:.2f} € / ks")
    except:
        st.error("Chyba M2 modelu.")
        cena_final = 0.0

    # --- TLAČIDLÁ AKCIE ---
    c_add, c_done = st.columns(2)
    
    if c_add.button("➕ PRIDAŤ POLOŽKU A POKRAČOVAŤ"):
        st.session_state.kosik.append({
            "ITEM": item_id, "Ks": ks, "Materiál": naklad_mat, 
            "Koop": naklad_koop, "Čas [s]": round(cas_sekundy, 2),
            "Cena/ks": round(cena_final, 2), "Spolu": round(cena_final * ks, 2)
        })
        st.toast(f"Položka {item_id} pridaná!")

    # --- ZOBRAZENIE KOŠÍKA A FINÁLNE PDF ---
    if st.session_state.kosik:
        df_final = pd.DataFrame(st.session_state.kosik)
        st.write("### Aktuálny rozpis ponuky")
        st.dataframe(df_final, use_container_width=True)
        
        celkom_cp = df_final['Spolu'].sum()
        st.metric("CELKOVÁ HODNOTA PONUKY", f"{celkom_cp:.2f} €")

        if st.button("🏁 HOTOVO - GENEROVAŤ PDF"):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(200, 10, txt=f"Cenová ponuka: {cp_cislo}", ln=True, align='C')
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt=f"Zákazník: {vybrany_zak} | Dátum: {datum}", ln=True)
            pdf.ln(10)
            
            # Tabuľka do PDF
            pdf.set_font("Arial", 'B', 10)
            pdf.cell(50, 10, "ITEM", 1); pdf.cell(30, 10, "Množstvo", 1); pdf.cell(40, 10, "Cena/ks", 1); pdf.cell(40, 10, "Spolu", 1)
            pdf.ln()
            pdf.set_font("Arial", size=10)
            for _, row in df_final.iterrows():
                pdf.cell(50, 10, str(row['ITEM']), 1)
                pdf.cell(30, 10, str(row['Ks']), 1)
                pdf.cell(40, 10, f"{row['Cena/ks']:.2f} EUR", 1)
                pdf.cell(40, 10, f"{row['Spolu']:.2f} EUR", 1)
                pdf.ln()
            
            pdf.ln(10)
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(200, 10, txt=f"CELKOM BEZ DPH: {celkom_cp:.2f} EUR", ln=True, align='R')
            
            st.download_button("📩 Stiahnuť hotovú ponuku (PDF)", 
                             data=pdf.output(dest='S').encode('latin-1'), 
                             file_name=f"Ponuka_{cp_cislo}.pdf")
