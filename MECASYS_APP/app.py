import streamlit as st
import pandas as pd
import numpy as np
from datetime import date

# --- 1. TVOJE ODKAZY NA GOOGLE SHEETS ---
L_MAT_CENA = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=901617097&single=true&output=csv"
L_AKOSTI = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1281008948&single=true&output=csv"
L_KOOP = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1180392224&single=true&output=csv"
L_LOJALITA = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=324957857&single=true&output=csv"
L_DB = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=0&single=true&output=csv"

# --- 2. NAČÍTANIE DÁT ---
@st.cache_data(ttl=300)
def load_data():
    try:
        df_m = pd.read_csv(L_MAT_CENA)
        df_a = pd.read_csv(L_AKOSTI)
        df_k = pd.read_csv(L_KOOP)
        df_l = pd.read_csv(L_LOJALITA)
        return df_m, df_a, df_k, df_l
    except Exception as e:
        st.error(f"Chyba pri načítaní tabuliek z Google Sheets: {e}")
        return None, None, None, None

df_materialy, df_akosti, df_kooperacia, df_lojalita = load_data()

# --- 3. ROZHRANIE APLIKÁCIE ---
st.set_page_config(page_title="MECASYS Kalkulačka", layout="wide")
st.title("📊 MECASYS - Inteligentná kalkulácia cien")

if df_akosti is not None:
    with st.sidebar:
        st.header("Základné nastavenia")
        zakaznik = st.selectbox("Zákazník", df_lojalita['Zákazník'].unique())
        krajina = st.selectbox("Krajina", ["Slovensko", "Česko", "Nemecko", "Rakúsko", "Iné"])
        cislo_cp = st.text_input("Číslo CP", value="2024-001")

    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Parametre dielu")
        item_name = st.text_input("Názov dielu (ITEM)")
        akost = st.selectbox("Akosť materiálu", df_akosti['akost'].unique())
        d = st.number_input("Priemer d (mm)", min_value=0.1, value=20.0, step=0.1)
        l = st.number_input("Dĺžka l (mm)", min_value=0.1, value=50.0, step=0.1)
        pocet_ks = st.number_input("Počet kusov", min_value=1, value=100)

    with col2:
        st.subheader("Výroba a Kooperácia")
        narocnost = st.slider("Náročnosť výroby (1-5)", 1, 5, 3)
        koop_ano = st.checkbox("Vyžaduje kooperáciu?")
        typ_koop = "Nie"
        if koop_ano:
            typ_koop = st.selectbox("Typ kooperácie", df_kooperacia['sluzba'].unique())

    # --- VÝPOČTY ---
    # 1. Hustota a Váha
    hustota = df_akosti[df_akosti['akost'] == akost]['hustota'].values[0]
    vaha_ks = (np.pi * (d/2)**2 * l * hustota) / 1_000_000  # kg/ks
    
    # 2. Cena materiálu (zjednodušená logika podľa tvojich tabuliek)
    # Vyberieme cenu za kg podľa typu materiálu (napr. OCEĽ, NEREZ...)
    # V tvojom Exceli je logika IF(LEFT...), tu to dotiahneme z df_materialy
    cena_kg = 2.5 # Základná hodnota ak by zlyhalo hľadanie
    try:
        # Tu hľadáme cenu za kg z tabuľky material_cena (predpokladáme stĺpec 'cena_za_kg')
        cena_kg = df_materialy.iloc[0]['cena_za_kg'] 
    except:
        pass
    
    naklad_mat = vaha_ks * cena_kg
    
    # 3. Kooperácia
    naklad_koop = 0
    if koop_ano:
        row_k = df_kooperacia[df_kooperacia['sluzba'] == typ_koop].iloc[0]
        if row_k['jednotka'] == 'dm2':
            plocha_dm2 = (np.pi * d * l) / 10000
            naklad_koop = max(row_k['tarifa'] * plocha_dm2, row_k['min_zakazka'] / pocet_ks)
        else:
            naklad_koop = max(row_k['tarifa'] * vaha_ks, row_k['min_zakazka'] / pocet_ks)

    # --- ZOBRAZENIE VÝSLEDKOV ---
    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Váha (kg/ks)", f"{vaha_ks:.3f}")
    c2.metric("Materiál (€/ks)", f"{naklad_mat:.2L}")
    c3.metric("Kooperácia (€/ks)", f"{naklad_koop:.2L}")
    
    # Celková predikovaná cena (zatiaľ jednoduchý vzorec, kým sa zapojí AI)
    lojalita_koef = df_lojalita[df_lojalita['Zákazník'] == zakaznik]['koeficient'].values[0]
    celkova_cena = (naklad_mat + naklad_koop + (narocnost * 2)) * lojalita_koef
    c4.metric("Odhadovaná cena (€/ks)", f"{celkova_cena:.2L}", delta=f"{lojalita_koef} koef.")

    # --- TLAČIDLO ULOŽIŤ ---
    if st.button("💾 ULOŽIŤ PONUKU DO EXCELU"):
        st.warning("Ukladanie sa aktivuje po prepojení cez Secrets (GSheetsConnection).")

else:
    st.info("Načítavam dáta z Google Sheets... Prosím čakaj.")
