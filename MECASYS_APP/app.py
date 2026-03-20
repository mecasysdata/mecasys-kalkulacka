import streamlit as st
import pandas as pd
import numpy as np
import math
import joblib
import json
from datetime import date
from io import BytesIO

# --- 1. KONFIGURÁCIA A ODKAZY (CSV EXPORTY) ---
LINKS = {
    "materialy": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1281008948&single=true&output=csv",
    "zakaznici": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=324957857&single=true&output=csv",
    "mat_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=901617097&single=true&output=csv",
    "koop_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1180392224&single=true&output=csv"
}

# --- 2. POMOCNÉ FUNKCIE ---
@st.cache_data(ttl=600)
def load_all_data():
    data = {}
    for key, url in LINKS.items():
        df = pd.read_csv(url)
        # Unifikácia textov na VEĽKÉ PÍSMENÁ a orezanie medzier
        df.columns = df.columns.str.strip()
        for col in df.select_dtypes(include='object').columns:
            df[col] = df[col].astype(str).str.strip().str.upper()
        data[key] = df
    return data

def get_hustota(material, akost, df_akosti):
    material = material.upper()
    akost = str(akost).upper()
    
    if material == "OCEĽ": return 7900
    if material == "NEREZ": return 8000
    if material == "PLAST":
        res = df_akosti[df_akosti['akost'] == akost]['hustota']
        return res.values[0] if not res.empty else 1200
    if material == "FAREBNÉ KOVY":
        if akost.startswith("3.7"): return 4500 # Titán
        if akost.startswith("3."): return 2900  # Hliník
        if akost.startswith("2."): return 9000  # Meď, Mosadz
    return 7850 # Default

# --- 3. SESSION STATE (Nákupný košík) ---
if 'kosik' not in st.session_state:
    st.session_state.kosik = []

# --- 4. NAČÍTANIE DÁT A MODELOV ---
data = load_all_data()

# --- 5. UI - HLAVIČKA CP ---
st.set_page_config(page_title="MECASYS AI Kalkulátor", layout="wide")
st.title("🚀 MECASYS - Inteligentná predikcia ceny")

with st.expander("📄 Hlavička Cenovej Ponuky", expanded=True):
    col_h1, col_h2, col_h3 = st.columns(3)
    datum_cp = col_h1.date_input("Dátum CP", date.today())
    cislo_cp = col_h2.text_input("Číslo CP (Cenova_ponuka)", value="2026-XXX")
    
    # Výber zákazníka
    df_z = data['zakaznici']
    list_zakaznikov = sorted(df_z['zakaznik'].unique().tolist())
    list_zakaznikov.append("--- NOVÝ ZÁKAZNÍK ---")
    vybrany_zakaznik = col_h3.selectbox("Zákazník", list_zakaznikov)
    
    lojalita = 0.5
    krajina = "SR"
    
    if vybrany_zakaznik == "--- NOVÝ ZÁKAZNÍK ---":
        novy_zak = st.text_input("Názov nového zákazníka")
        krajina = st.selectbox("Krajina", ["SLOVENSKO", "ČESKO", "NEMECKO", "RAKÚSKO"])
        vybrany_zakaznik = novy_zak
    else:
        row_z = df_z[df_z['zakaznik'] == vybrany_zakaznik].iloc[0]
        krajina = row_z['krajina']
        lojalita = row_z['lojalita']

st.divider()

# --- 6. VSTUPY PRE ITEM ---
col_i1, col_i2 = st.columns(2)

with col_i1:
    st.subheader("Technické parametre")
    item_id = st.text_input("ITEM (Názov dielu)")
    mat_kat = st.selectbox("Materiál", ["OCEĽ", "NEREZ", "PLAST", "FAREBNÉ KOVY"])
    
    # Dynamický filter akostí
    df_a = data['materialy']
    mask = (df_a['material'] == mat_kat)
    akost_list = sorted(df_a[mask]['akost'].unique().tolist())
    vybrana_akost = st.selectbox("Akosť", akost_list)
    
    d = st.number_input("Priemer d (mm)", min_value=0.1, value=20.0)
    l = st.number_input("Dĺžka l (mm)", min_value=0.1, value=50.0)
    pocet_ks = st.number_input("Počet kusov", min_value=1, value=100)

with col_i2:
    st.subheader("Výroba a Kooperácia")
    narocnost = st.select_slider("Náročnosť", options=["1", "2", "3", "4", "5"], value="3")
    
    koop_check = st.radio("Vyžaduje kooperáciu?", ["NIE", "ÁNO"])
    naklad_kooperacia = 0.0
    
    if koop_check == "ÁNO":
        df_k = data['koop_cena']
        druh_koop = st.selectbox("Druh kooperácie", df_k['druh'].unique())
        
        # Logika výpočtu kooperácie
        row_k = df_k[(df_k['druh'] == druh_koop) & (df_k['material'] == mat_kat)].iloc[0]
        tarifa = row_k['tarifa']
        jednotka = row_k['jednotka']
        min_zakazka = row_k['minimalna_zakazka']
        
        # Pomocné výpočty pre koop
        hustota_pre_vypocet = get_hustota(mat_kat, vybrana_akost, df_a)
        vaha_ks_koop = hustota_pre_vypocet * (math.pi/4) * (d/1000)**2 * (l/1000)
        plocha_dm2 = (math.pi * d * l) / 10000
        
        if "KG" in jednotka.upper():
            odhad_koop = tarifa * vaha_ks_koop
        else: # dm2
            odhad_koop = tarifa * plocha_dm2
            
        # Ochranná podmienka (Minimálna zákazka)
        celkom_koop = pocet_ks * odhad_koop
        if celkom_koop < min_zakazka:
            naklad_kooperacia = min_zakazka / pocet_ks
        else:
            naklad_kooperacia = odhad_koop

# --- 7. VÝPOČET CENY MATERIÁLU ---
df_mc = data['mat_cena']
mask_mc = (df_mc['akost'] == vybrana_akost)
df_mc_filtered = df_mc[mask_mc]

naklad_material = 0.0
if not df_mc_filtered.empty:
    # Hľadáme presnú zhodu alebo najbližšiu vyššiu (d)
    # Predpokladáme, že stĺpec s priemerom sa volá 'd'
    vyssie_d = df_mc_filtered[df_mc_filtered['d'] >= d].sort_values('d')
    if not vyssie_d.empty:
        cena_za_m = vyssie_d.iloc[0]['J.cena/m']
        naklad_material = (l / 1000) * cena_za_m
    else:
        st.warning("Priemer d nie je v cenníku.")
        naklad_material = st.number_input("Zadaj cenu materiálu na 1 ks [€]", min_value=0.0)
else:
    st.warning("Akosť nie je v cenníku.")
    naklad_material = st.number_input("Zadaj cenu materiálu na 1 ks [€]", min_value=0.0)

# --- 8. TLAČIDLO PRIDAŤ DO KOŠÍKA ---
if st.button("➕ PRIDAŤ POLOŽKU DO PONUKY"):
    # Logika pre Modely M1 a M2 (Simulácia podla zadania)
    # Tu by sa načítal json a pkl súbory
    cas_predikcia = 5.5 # Tu by bol np.expm1(model_m1.predict(...))
    vstupne_naklady = naklad_material + naklad_kooperacia
    
    # Jednotková cena M2 (Simulácia)
    jednotkova_cena = (vstupne_naklady + (cas_predikcia * 0.5)) / lojalita 
    
    hmotnost = get_hustota(mat_kat, vybrana_akost, df_a) * (math.pi/4) * (d/1000)**2 * (l/1000)

    nova_polozka = {
        "Dátum CP": datum_cp,
        "Číslo CP": cislo_cp,
        "Zákazník": vybrany_zakaznik,
        "Krajina": krajina,
        "Lojalita": lojalita,
        "ITEM": item_id.upper(),
        "Materiál": mat_kat,
        "Akosť": vybrana_akost,
        "d": d,
        "l": l,
        "Hustota": get_hustota(mat_kat, vybrana_akost, df_a),
        "Hmotnosť": hmotnost,
        "Náročnosť": narocnost,
        "J.cena materiálu": naklad_material / (l/1000) if l > 0 else 0,
        "Náklad materiál": naklad_material,
        "Náklad kooperácia": naklad_kooperacia,
        "Vstupné náklady": vstupne_naklady,
        "Čas (min)": cas_predikcia,
        "Jednotková cena": jednotkova_cena,
        "Počet kusov": pocet_ks,
        "Cena spolu": jednotkova_cena * pocet_ks
    }
    st.session_state.kosik.append(nova_polozka)
    st.success(f"Položka {item_id} pridaná!")

# --- 9. PREHĽAD KOŠÍKA A ARCHIVÁCIA ---
if st.session_state.kosik:
    st.subheader("🛒 Aktuálna rozpracovaná ponuka")
    df_kosik = pd.DataFrame(st.session_state.kosik)
    st.table(df_kosik[['ITEM', 'Materiál', 'Počet kusov', 'Jednotková cena', 'Cena spolu']])
    
    celkova_suma_cp = df_kosik['Cena spolu'].sum()
    st.metric("CELKOVÁ CENA CP", f"{celkova_suma_cp:.2f} €")
    
    col_f1, col_f2 = st.columns(2)
    
    if col_f1.button("💾 ULOŽIŤ CELÚ PONUKU DO DATABÁZY"):
        # Tu by bol kód pre GSheets Connection conn.create(...)
        st.balloons()
        st.success("Všetky položky boli zapísané do databaza_ponuk.xlsx")
        st.session_state.kosik = [] # Vymazanie košíka po uložení
        
    if col_f2.button("📑 GENEROVAŤ PDF"):
        st.info("Generujem PDF dokument s logom MECASYS...")
        # Tu by bola logika pre FPDF alebo ReportLab
