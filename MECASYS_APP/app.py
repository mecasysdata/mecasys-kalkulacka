import streamlit as st
import pandas as pd
import numpy as np
import math
from datetime import date

# --- 1. ODKAZY NA GOOGLE SHEETS ---
LINKS = {
    "materialy": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1281008948&single=true&output=csv",
    "zakaznici": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=324957857&single=true&output=csv",
    "mat_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=901617097&single=true&output=csv",
    "koop_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1180392224&single=true&output=csv"
}

# --- 2. INTELIGENTNÉ NAČÍTANIE (OPRAVA NÁZVOV STĹPCOV) ---
@st.cache_data(ttl=300)
def load_all_data():
    loaded = {}
    for key, url in LINKS.items():
        try:
            df = pd.read_csv(url)
            # 1. Odstránime neviditeľné medzery z názvov stĺpcov
            df.columns = df.columns.str.strip()
            
            # 2. Manuálne premenovanie pre istotu (Mapovanie)
            rename_map = {
                'Zákazník': 'zakaznik', 'zakaznik': 'zakaznik',
                'minimalna_zakazka': 'minimalna_zakazka', 'min_zakazka': 'minimalna_zakazka',
                'minimalna zakazka': 'minimalna_zakazka',
                'akost': 'akost', 'Akosť': 'akost',
                'material': 'material', 'Materiál': 'material',
                'J.cena/m': 'J.cena/m', 'cena/m': 'J.cena/m'
            }
            df.rename(columns=rename_map, inplace=True)
            
            # 3. Všetky texty v bunkách na VEĽKÉ PÍSMENÁ pre ľahké porovnávanie
            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].astype(str).str.strip().str.upper()
            
            loaded[key] = df
        except Exception as e:
            st.error(f"Chyba v hárku {key}: {e}")
    return loaded

data = load_all_data()

# --- 3. POMOCNÉ FUNKCIE ---
def get_hustota(material, akost, df_akosti):
    m = str(material).upper()
    a = str(akost).upper()
    if m == "OCEĽ": return 7900
    if m == "NEREZ": return 8000
    if m == "PLAST":
        res = df_akosti[df_akosti['akost'] == a]['hustota']
        return float(res.values[0]) if not res.empty else 1200
    if m == "FAREBNÉ KOVY":
        if a.startswith("3.7"): return 4500
        if a.startswith("3."): return 2900
        if a.startswith("2."): return 9000
    return 7850

# --- 4. ROZHRANIE APLIKÁCIE ---
st.set_page_config(page_title="MECASYS Kalkulačka", layout="wide")
st.title("📊 MECASYS - Inteligentná predikcia ceny")

if 'kosik' not in st.session_state:
    st.session_state.kosik = []

if data:
    # --- HLAVIČKA ---
    with st.expander("📄 Základné údaje ponuky", expanded=True):
        c1, c2, c3 = st.columns(3)
        datum_cp = c1.date_input("Dátum", date.today())
        cislo_cp = c2.text_input("Číslo CP", "2026-001")
        
        df_z = data['zakaznici']
        # Použijeme zjednotený názov 'zakaznik'
        zak_col = 'zakaznik' if 'zakaznik' in df_z.columns else df_z.columns[0]
        zak_list = sorted(df_z[zak_col].unique())
        vybrany_zak = c3.selectbox("Zákazník", zak_list)
        
        row_z = df_z[df_z[zak_col] == vybrany_zak].iloc[0]
        # Ošetrenie chýbajúcich stĺpcov lojalita/krajina
        lojalita = row_z['lojalita'] if 'lojalita' in row_z else 0.5
        krajina = row_z['krajina'] if 'krajina' in row_z else "SR"

    # --- VSTUPY ---
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("Technické parametre")
        item_id = st.text_input("ITEM (Názov dielu)").upper()
        mat_kat = st.selectbox("Materiál", ["OCEĽ", "NEREZ", "PLAST", "FAREBNÉ KOVY"])
        
        df_a = data['materialy']
        akost_list = sorted(df_a[df_a['material'] == mat_kat]['akost'].unique())
        vybrana_akost = st.selectbox("Akosť", akost_list)
        
        d = st.number_input("Priemer d (mm)", value=20.0)
        l = st.number_input("Dĺžka l (mm)", value=50.0)
        pocet_ks = st.number_input("Počet kusov", min_value=1, value=100)

    with col_right:
        st.subheader("Výroba a Kooperácia")
        narocnost = st.select_slider("Náročnosť", options=["1", "2", "3", "4", "5"], value="3")
        koop_ano = st.radio("Kooperácia?", ["NIE", "ÁNO"])
        
        naklad_koop = 0.0
        if koop_ano == "ÁNO":
            df_k = data['koop_cena']
            druh_list = df_k[df_k['material'] == mat_kat]['druh'].unique()
            if len(druh_list) > 0:
                druh = st.selectbox("Druh služby", druh_list)
                row_k = df_k[(df_k['druh'] == druh) & (df_k['material'] == mat_kat)].iloc[0]
                
                h_val = get_hustota(mat_kat, vybrana_akost, df_a)
                vaha_ks = h_val * (math.pi/4) * (d/1000)**2 * (l/1000)
                plocha_dm2 = (math.pi * d * l) / 10000
                
                jednotka = str(row_k['jednotka']).upper()
                odhad = row_k['tarifa'] * (vaha_ks if "KG" in jednotka else plocha_dm2)
                
                # OŠETRENIE KEYERROR PRE MINIMÁLNU ZÁKAZKU
                min_z_val = row_k['minimalna_zakazka'] if 'minimalna_zakazka' in row_k else 0
                naklad_koop = max(odhad, min_z_val / pocet_ks)

    # --- VÝPOČET MATERIÁLU ---
    df_mc = data['mat_cena']
    mask = (df_mc['material'] == mat_kat) & (df_mc['akost'] == vybrana_akost)
    filtered_mc = df_mc[mask]
    
    naklad_mat = None
    if not filtered_mc.empty:
        vyssie = filtered_mc[filtered_mc['d'] >= d].sort_values('d')
        if not vyssie.empty:
            naklad_mat = (l / 1000) * vyssie.iloc[0]['J.cena/m']

    st.divider()
    if naklad_mat is None:
        st.warning("Cena materiálu nenájdená v cenníku.")
        naklad_mat = st.number_input("Zadaj cenu materiálu na 1 ks [€]", value=0.0)
    else:
        st.success(f"Cena materiálu určená: {naklad_mat:.3f} €/ks")

    # --- TLAČIDLO PRIDAŤ ---
    if st.button("➕ PRIDAŤ DO KOŠÍKA"):
        vaha = get_hustota(mat_kat, vybrana_akost, df_a) * (math.pi/4) * (d/1000)**2 * (l/1000)
        # Predikcia ceny (zjednodušená pre tento krok)
        cena_final = (naklad_mat + naklad_koop + (int(narocnost) * 2)) / lojalita
        
        st.session_state.kosik.append({
            "ITEM": item_id, "Ks": pocet_ks, "Váha": round(vaha, 3), 
            "Cena/ks": round(cena_final, 2), "Spolu": round(cena_final * pocet_ks, 2)
        })

    # --- VÝPIS KOŠÍKA ---
    if st.session_state.kosik:
        st.subheader("🛒 Rozpracovaná ponuka")
        st.table(pd.DataFrame(st.session_state.kosik))
        if st.button("🗑️ VYMAZAŤ KOŠÍK"):
            st.session_state.kosik = []
            st.rerun()
