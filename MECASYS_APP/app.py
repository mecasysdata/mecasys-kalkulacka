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

# --- 2. INTELIGENTNÉ NAČÍTANIE ---
@st.cache_data(ttl=300)
def load_and_clean_data():
    loaded = {}
    for key, url in LINKS.items():
        try:
            df = pd.read_csv(url)
            df.columns = df.columns.str.strip() # Odstráni medzery
            
            # UNIFIKÁCIA NÁZVOV (Mapovanie tvojich stĺpcov na názvy v kóde)
            rename_map = {
                'Zákazník': 'zakaznik', 'zakaznik': 'zakaznik',
                'minimalna_zakazka': 'minimalna_zakazka', 'min_zakazka': 'minimalna_zakazka',
                'Akosť': 'akost', 'akost': 'akost',
                'Materiál': 'material', 'material': 'material',
                'J.cena/m': 'J.cena/m', 'Cena/m': 'J.cena/m'
            }
            df.rename(columns=rename_map, inplace=True)
            
            # Prevod textov na VEĽKÉ PÍSMENÁ
            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].astype(str).str.strip().str.upper()
            
            loaded[key] = df
        except Exception as e:
            st.error(f"Chyba v hárku {key}: {e}")
    return loaded

data = load_and_clean_data()

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

# --- 4. ROZHRANIE ---
st.set_page_config(page_title="MECASYS Kalkulačka", layout="wide")
st.title("📊 MECASYS - Inteligentná kalkulácia")

if 'kosik' not in st.session_state:
    st.session_state.kosik = []

if data:
    # --- HLAVIČKA ---
    with st.expander("📄 Základné údaje ponuky", expanded=True):
        c1, c2, c3 = st.columns(3)
        datum_cp = c1.date_input("Dátum", date.today())
        cislo_cp = c2.text_input("Číslo CP", "2026-XXX")
        
        df_z = data['zakaznici']
        zak_list = sorted(df_z['zakaznik'].unique()) if 'zakaznik' in df_z.columns else ["Chyba stĺpca"]
        vybrany_zak = c3.selectbox("Zákazník", zak_list)
        
        row_z = df_z[df_z['zakaznik'] == vybrany_zak].iloc[0] if vybrany_zak in df_z['zakaznik'].values else None
        lojalita = row_z['lojalita'] if row_z is not None and 'lojalita' in row_z else 1.0
        krajina = row_z['krajina'] if row_z is not None and 'krajina' in row_z else "SR"

    # --- VSTUPY ---
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Technické parametre")
        item_id = st.text_input("ITEM (Názov dielu)").upper()
        mat_kat = st.selectbox("Materiál", ["OCEĽ", "NEREZ", "PLAST", "FAREBNÉ KOVY"])
        
        df_a = data['materialy']
        akost_list = sorted(df_a[df_a['material'] == mat_kat]['akost'].unique())
        vybrana_akost = st.selectbox("Akosť", akost_list)
        d = st.number_input("Priemer d (mm)", value=20.0, step=0.1)
        l = st.number_input("Dĺžka l (mm)", value=50.0, step=0.1)
        pocet_ks = st.number_input("Počet kusov", min_value=1, value=100)

    with col_r:
        st.subheader("Výroba a Kooperácia")
        narocnost = st.select_slider("Náročnosť", options=["1", "2", "3", "4", "5"], value="3")
        koop_ano = st.radio("Kooperácia?", ["NIE", "ÁNO"])
        
        naklad_koop = 0.0
        if koop_ano == "ÁNO":
            df_k = data['koop_cena']
            # Filtrujeme služby podľa materiálu
            druh_list = df_k[df_k['material'] == mat_kat]['druh'].unique()
            if len(druh_list) > 0:
                druh = st.selectbox("Druh služby", druh_list)
                row_k = df_k[(df_k['druh'] == druh) & (df_k['material'] == mat_kat)].iloc[0]
                
                h_val = get_hustota(mat_kat, vybrana_akost, df_a)
                vaha_ks = h_val * (math.pi/4) * (d/1000)**2 * (l/1000)
                plocha_dm2 = (math.pi * d * l) / 10000
                
                jednotka = str(row_k['jednotka']).upper()
                odhad = row_k['tarifa'] * (vaha_ks if "KG" in jednotka else plocha_dm2)
                
                min_z = row_k['minimalna_zakazka'] if 'minimalna_zakazka' in row_k else 0
                naklad_koop = max(odhad, min_z / pocet_ks)

    # --- VÝPOČET MATERIÁLU (BOD 10) ---
    df_mc = data['mat_cena']
    mask = (df_mc['material'] == mat_kat) & (df_mc['akost'] == vybrana_akost)
    filtered_mc = df_mc[mask]
    
    naklad_mat = None
    if not filtered_mc.empty:
        # Hľadáme najbližší vyšší priemer
        vyssie = filtered_mc[filtered_mc['d'] >= d].sort_values('d')
        if not vyssie.empty:
            try:
                cena_m = float(vyssie.iloc[0]['J.cena/m'])
                naklad_mat = (l / 1000) * cena_m
            except:
                naklad_mat = None

    st.divider()
    if naklad_mat is None:
        st.warning("⚠️ Cena materiálu nebola v cenníku nájdená pre tieto rozmery.")
        naklad_mat = st.number_input("Zadaj cenu materiálu na 1 komponent [€]", value=0.0, step=0.1)
    else:
        st.success(f"✅ Cena materiálu určená z cenníka: {naklad_mat:.3f} €/ks")

    # --- TLAČIDLO PRIDAŤ ---
    if st.button("➕ PRIDAŤ DO KOŠÍKA"):
        h_val = get_hustota(mat_kat, vybrana_akost, data['materialy'])
        vaha = h_val * (math.pi/4) * (d/1000)**2 * (l/1000)
        # Simulácia finálnej ceny (kým nebudeme mať model M2)
        cena_ks = (naklad_mat + naklad_koop + (int(narocnost) * 1.5)) / lojalita
        
        st.session_state.kosik.append({
            "ITEM": item_id, "Materiál": mat_kat, "Ks": pocet_ks, 
            "Váha/ks": round(vaha, 3), "Cena/ks": round(cena_ks, 2), "Spolu": round(cena_ks * pocet_ks, 2)
        })

    # --- KOŠÍK ---
    if st.session_state.kosik:
        st.subheader("🛒 Rozpracovaná ponuka")
        st.dataframe(pd.DataFrame(st.session_state.kosik), use_container_width=True)
        if st.button("🗑️ VYMAZAŤ KOŠÍK"):
            st.session_state.kosik = []
            st.rerun()
