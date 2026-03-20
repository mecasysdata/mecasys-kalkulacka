import streamlit as st
import pandas as pd
import numpy as np
import math
from datetime import date

# --- 1. ODKAZY NA GOOGLE SHEETS (CSV EXPORTY) ---
LINKS = {
    "materialy": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1281008948&single=true&output=csv",
    "zakaznici": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=324957857&single=true&output=csv",
    "mat_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=901617097&single=true&output=csv",
    "koop_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1180392224&single=true&output=csv"
}

# --- 2. NAČÍTANIE A ČISTENIE DÁT ---
@st.cache_data(ttl=300)
def load_all_data():
    loaded = {}
    for key, url in LINKS.items():
        try:
            df = pd.read_csv(url)
            df.columns = df.columns.str.strip() # Odstránenie medzier v názvoch
            # Prevod všetkých textových hodnôt na VEĽKÉ PÍSMENÁ
            for col in df.select_dtypes(include='object').columns:
                df[col] = df[col].astype(str).str.strip().str.upper()
            loaded[key] = df
        except Exception as e:
            st.error(f"Chyba pri načítaní hárka {key}: {e}")
    return loaded

data = load_all_data()

# --- 3. SESSION STATE (KOŠÍK) ---
if 'kosik' not in st.session_state:
    st.session_state.kosik = []

# --- 4. POMOCNÉ FUNKCIE (BIZNIS LOGIKA) ---

def get_hustota(material, akost, df_akosti):
    """Logika určenia hustoty podľa Bodu 4 zadania"""
    if material == "OCEĽ": return 7900
    if material == "NEREZ": return 8000
    if material == "PLAST":
        res = df_akosti[df_akosti['akost'] == akost]['hustota']
        return float(res.values[0]) if not res.empty else 1200
    if material == "FAREBNÉ KOVY":
        if akost.startswith("3.7"): return 4500 # Titán
        if akost.startswith("3."): return 2900  # Hliník
        if akost.startswith("2."): return 9000  # Cu, Ms, Bz
    return 7850

def najdi_cenu_materialu(df_mc, m_user, a_user, d_user, l_user):
    """Logika hľadania najbližšieho vyššieho priemeru (Bod 10)"""
    mask = (df_mc['material'] == m_user) & (df_mc['akost'] == a_user)
    filtered = df_mc[mask]
    if filtered.empty: return None
    
    # Hľadáme d >= užívateľské d a vezmeme najmenšie z nich
    vyssie = filtered[filtered['d'] >= d_user].sort_values('d')
    if not vyssie.empty:
        cena_m = vyssie.iloc[0]['J.cena/m']
        return (l_user / 1000) * cena_m
    return None

# --- 5. ROZHRANIE (UI) ---
st.set_page_config(page_title="MECASYS Kalkulačka", layout="wide")
st.title("📊 MECASYS - Inteligentná predikcia ceny")

if data:
    # HLAVIČKA CP
    with st.expander("📄 Základné údaje ponuky", expanded=True):
        c1, c2, c3 = st.columns(3)
        datum_cp = c1.date_input("Dátum", date.today())
        cislo_cp = c2.text_input("Číslo CP", "2026-001")
        zak_list = sorted(data['zakaznici']['zakaznik'].unique())
        vybrany_zak = c3.selectbox("Zákazník", zak_list)
        
        row_z = data['zakaznici'][data['zakaznici']['zakaznik'] == vybrany_zak].iloc[0]
        krajina = row_z['krajina']
        lojalita = row_z['lojalita']

    # VSTUPY PRE ITEM
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("Technické parametre")
        item_id = st.text_input("ITEM (Názov dielu)").upper()
        mat_kat = st.selectbox("Materiál", ["OCEĽ", "NEREZ", "PLAST", "FAREBNÉ KOVY"])
        
        df_a = data['materialy']
        akost_list = sorted(df_a[df_a['material'] == mat_kat]['akost'].unique())
        vybrana_akost = st.selectbox("Akosť", akost_list)
        
        d = st.number_input("Priemer d (mm)", value=20.0, step=0.1)
        l = st.number_input("Dĺžka l (mm)", value=50.0, step=0.1)
        pocet_ks = st.number_input("Počet kusov", min_value=1, value=100)

    with col_right:
        st.subheader("Výroba a Kooperácia")
        narocnost = st.select_slider("Náročnosť", options=["1", "2", "3", "4", "5"], value="3")
        koop_ano = st.radio("Vyžaduje kooperáciu?", ["NIE", "ÁNO"])
        
        # Výpočet kooperácie (Bod 11)
        naklad_koop = 0.0
        if koop_ano == "ÁNO":
            df_k = data['koop_cena']
            druh_list = df_k[df_k['material'] == mat_kat]['druh'].unique()
            if len(druh_list) > 0:
                druh = st.selectbox("Druh kooperácie", druh_list)
                row_k = df_k[(df_k['druh'] == druh) & (df_k['material'] == mat_kat)].iloc[0]
                
                h_val = get_hustota(mat_kat, vybrana_akost, df_a)
                vaha_ks = h_val * (math.pi/4) * (d/1000)**2 * (l/1000)
                plocha_dm2 = (math.pi * d * l) / 10000
                
                odhad = row_k['tarifa'] * (vaha_ks if "KG" in str(row_k['jednotka']).upper() else plocha_dm2)
                naklad_koop = max(odhad, row_k['minimalna_zakazka'] / pocet_ks)
            else:
                st.warning("Pre tento materiál nie sú definované kooperácie.")

    # VÝPOČET MATERIÁLU
    naklad_mat = najdi_cenu_materialu(data['mat_cena'], mat_kat, vybrana_akost, d, l)
    
    st.divider()
    
    # RUČNÉ ZADANIE CENY (Ak sa nenašla v Exceli)
    if naklad_mat is None:
        st.warning("Cena materiálu pre tento rozmer nie je v cenníku.")
        naklad_mat = st.number_input("Zadaj cenu materiálu na 1 komponent [€]", value=0.0)
    else:
        st.success(f"Cena materiálu z cenníka: {naklad_mat:.3f} €/ks")

    # TLAČIDLO PRIDAŤ
    if st.button("➕ PRIDAŤ POLOŽKU DO KOŠÍKA"):
        # Tu len simulujeme výsledok AI modelov, kým ich neprepojíme
        vaha = get_hustota(mat_kat, vybrana_akost, df_a) * (math.pi/4) * (d/1000)**2 * (l/1000)
        cena_ai = (naklad_mat + naklad_koop + (int(narocnost) * 2)) / lojalita
        
        st.session_state.kosik.append({
            "ITEM": item_id, "Ks": pocet_ks, "Váha/ks": round(vaha, 3), 
            "Mat/ks": round(naklad_mat, 2), "Koop/ks": round(naklad_koop, 2),
            "Cena/ks": round(cena_ai, 2), "Spolu": round(cena_ai * pocet_ks, 2)
        })

    # TABUĽKA KOŠÍKA
    if st.session_state.kosik:
        st.subheader("🛒 Aktuálna ponuka (Náhľad)")
        df_kosik = pd.DataFrame(st.session_state.kosik)
        st.dataframe(df_kosik, use_container_width=True)
        st.metric("CELKOVÁ CENA CP", f"{df_kosik['Spolu'].sum():.2f} €")
        
        if st.button("💾 ULOŽIŤ DO DATABÁZY A ARCHÍVU"):
            st.success("Dáta boli pripravené na export do databaza_ponuk.xlsx!")
            st.session_state.kosik = [] # Reset košíka
