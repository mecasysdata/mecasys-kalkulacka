import streamlit as st
import pandas as pd
import numpy as np
from datetime import date

# --- 1. TVOJE ODKAZY NA GOOGLE SHEETS ---
L_MAT_CENA = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=901617097&single=true&output=csv"
L_AKOSTI = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1281008948&single=true&output=csv"
L_KOOP = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1180392224&single=true&output=csv"
L_LOJALITA = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=324957857&single=true&output=csv"

# --- 2. NAČÍTANIE DÁT ---
@st.cache_data(ttl=300)
def load_data():
    try:
        df_m = pd.read_csv(L_MAT_CENA)
        df_a = pd.read_csv(L_AKOSTI)
        df_k = pd.read_csv(L_KOOP)
        df_l = pd.read_csv(L_LOJALITA)
        # Očistenie prípadných medzier v názvoch stĺpcov pre istotu
        df_l.columns = df_l.columns.str.strip()
        df_a.columns = df_a.columns.str.strip()
        return df_m, df_a, df_k, df_l
    except Exception as e:
        st.error(f"Chyba pri načítaní: {e}")
        return None, None, None, None

df_materialy, df_akosti, df_kooperacia, df_lojalita = load_data()

# --- 3. ROZHRANIE APLIKÁCIE ---
st.set_page_config(page_title="MECASYS Kalkulačka", layout="wide")
st.title("📊 MECASYS - Inteligentná kalkulácia")

if df_lojalita is not None and df_akosti is not None:
    with st.sidebar:
        st.header("Základné nastavenia")
        # TU JE ZMENA: namiesto 'Zákazník' je 'zakaznik'
        zakaznik = st.selectbox("Zákazník", df_lojalita['zakaznik'].unique())
        krajina = st.selectbox("Krajina", ["Slovensko", "Česko", "Nemecko", "Rakúsko", "Iné"])
        cislo_cp = st.text_input("Číslo CP", value="2024-001")

    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Parametre dielu")
        item_name = st.text_input("Názov dielu (ITEM)")
        # Ak máš v hárku akosti stĺpec s názvom 'akost', použijeme ho
        akost = st.selectbox("Akosť materiálu", df_akosti['akost'].unique())
        d = st.number_input("Priemer d (mm)", min_value=0.1, value=20.0)
        l = st.number_input("Dĺžka l (mm)", min_value=0.1, value=50.0)
        pocet_ks = st.number_input("Počet kusov", min_value=1, value=100)

    with col2:
        st.subheader("Výroba a Kooperácia")
        narocnost = st.slider("Náročnosť výroby (1-5)", 1, 5, 3)
        koop_ano = st.checkbox("Vyžaduje kooperáciu?")
        typ_koop = "Nie"
        if koop_ano:
            typ_koop = st.selectbox("Typ kooperácie", df_kooperacia['sluzba'].unique())

    # --- VÝPOČTY ---
    hustota = df_akosti[df_akosti['akost'] == akost]['hustota'].values[0]
    vaha_ks = (np.pi * (d/2)**2 * l * hustota) / 1_000_000
    
    # --- VÝSLEDOK ---
    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.metric("Váha (kg/ks)", f"{vaha_ks:.3f}")
    c2.metric("Zvolený zákazník", zakaznik)
    c3.metric("Zvolená akosť", akost)

    st.success("Dáta úspešne prepojené!")
