import streamlit as st
import pandas as pd
import math
import xgboost as xgb
import joblib
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# --- 1. KONFIGURÁCIA ---
st.set_page_config(page_title="MECASYS Kalkulátor", layout="wide")
st.title("📊 MECASYS - Inteligentná kalkulácia cien")

# --- 2. NAČÍTANIE MODELOV (Strikné načítanie z GitHubu) ---
@st.cache_resource
def load_models():
    m1 = xgb.Booster(); m1.load_model('finalny_model.json')
    c1 = joblib.load('stlpce_modelu.pkl')
    m2 = xgb.Booster(); m2.load_model('xgb_model_cena.json')
    c2 = joblib.load('model_columns.pkl')
    return m1, c1, m2, c2

try:
    model_cas, cols_cas, model_cena, cols_cena = load_models()
except Exception as e:
    st.error(f"Chyba pri načítaní modelov: {e}. Skontrolujte, či sú súbory .json a .pkl v rovnakom priečinku.")
    st.stop()

# --- 3. PRIPOJENIE K GOOGLE SHEET ---
conn = st.connection("gsheets", type=GSheetsConnection)

# Načítanie hárkov (Názvy podľa tvojho linku)
df_materialy = conn.read(worksheet="material_cena")
df_kooperacie = conn.read(worksheet="kooperacia_cennik")
df_lojalita = conn.read(worksheet="zakaznik_lojalita")
df_databaza = conn.read(worksheet="databaza_ponuk")

# --- 4. VSTUPNÉ PARAMETRE ---
st.header("1. Zadanie rozmerov a materiálu")
col1, col2, col3 = st.columns(3)

with col1:
    zakaznik = st.selectbox("Vyber zákazníka", df_lojalita["Meno"].unique())
    cislo_cp = st.text_input("Číslo CP")
    item_nazov = st.text_input("ITEM / Názov dielu")

with col2:
    d = st.number_input("Priemer d [mm]", min_value=0.0, format="%.2f", value=10.0)
    l = st.number_input("Dĺžka l [mm]", min_value=0.0, format="%.2f", value=50.0)
    pocet_kusov = st.number_input("Počet kusov [ks]", min_value=1, step=1, value=1)

with col3:
    vybrany_mat = st.selectbox("Vyber materiál", df_materialy["Materiál"].unique())

# --- 5. VÝPOČET GEOMETRIE A HMOTNOSTI ---
plocha_plasta_mm2 = math.pi * d * l
objem_mm3 = math.pi * ((d / 2) ** 2) * l

# Dáta o materiáli
row_mat = df_materialy[df_materialy["Materiál"] == vybrany_mat].iloc[0]
hustota = row_mat["Hustota"]
cena_mat_kg = row_mat["Cena_za_kg"]

hmotnost_kg = objem_mm3 * hustota
naklad_material_O = hmotnost_kg * cena_mat_kg

# --- 6. KOOPERÁCIA (Prepočet na dm2) ---
st.header("2. Externé spracovanie")
kooperacia_ano = st.checkbox("Vyžaduje komponent kooperáciu?")
naklad_kooperacia_P = 0.0

if kooperacia_ano:
    # Tu používame malé písmená 'druh', 'jednotka' atď. podľa tvojho Sheetu
    druh_koop = st.selectbox("Druh kooperácie", df_kooperacie["druh"].unique())
    row_koop = df_kooperacie[df_kooperacie["druh"] == druh_koop].iloc[0]
    
    if row_koop["jednotka"] == "dm2":
        odhad = row_koop["tarifa"] * (plocha_plasta_mm2 / 10000)
    else:
        odhad = row_koop["tarifa"] * hmotnost_kg
        
    # Kontrola minimálnej zákazky
    if (odhad * pocet_kusov) < row_koop["minimalna zakazka"]:
        naklad_kooperacia_P = row_koop["minimalna zakazka"] / pocet_kusov
    else:
        naklad_kooperacia_P = odhad

vstupne_naklady_Q = naklad_material_O + naklad_kooperacia_P

# --- 7. PREDIKCIA AI MODELMI (M1 a M2) ---
# Príprava dát pre M1 (Čas)
in_cas = pd.DataFrame([[d, l, hmotnost_kg]], columns=['d', 'l', 'hmotnost'])
pred_cas_R = model_cas.predict(xgb.DMatrix(in_cas))[0]

# Príprava dát pre M2 (Cena)
in_cena = pd.DataFrame([[vstupne_naklady_Q, pred_cas_R]], columns=['vstupne_naklady', 'vypocitany_cas'])
pred_cena_S = model_cena.predict(xgb.DMatrix(in_cena))[0]

# --- 8. FINÁLNE CENY A VALIDÁCIA ---
st.header("3. Výsledná kalkulácia")
c_v1, c_v2 = st.columns(2)

with c_v1:
    st.metric("Predikovaný strojný čas [R]", f"{pred_cas_R:.2f} min")
    st.metric("Navrhnutá jednotková cena [S]", f"{pred_cena_S:.2f} €")

with c_v2:
    override = st.checkbox("Manuálna korekcia technológom")
    finalna_cena_S = st.number_input("Konečná jednotková cena [€/ks]", value=float(pred_cena_S)) if override else pred_cena_S

cena_spolu_U = finalna_cena_S * pocet_kusov
st.subheader(f"Celková hodnota položky [U]: {cena_spolu_U:.2f} €")

# --- 9. ZÁPIS DO DATABÁZY ---
if st.button("💾 ULOŽIŤ DO EXCELU"):
    novy_riadok = pd.DataFrame([{
        "Dátum CP": datetime.now().strftime("%d.%m.%Y"),
        "Číslo CP": cislo_cp,
        "Zákazník": zakaznik,
        "ITEM": item_nazov,
        "d": d,
        "l": l,
        "Hmotnosť": hmotnost_kg,
        "Náklad materiál": naklad_material_O,
        "Náklad kooperácia": naklad_kooperacia_P,
        "Vstupné náklady": vstupne_naklady_Q,
        "Predikovaný čas": pred_cas_R,
        "Jednotková cena": finalna_cena_S,
        "Počet kusov": pocet_kusov,
        "Cena spolu": cena_spolu_U
    }])
    
    updated_df = pd.concat([df_databaza, novy_riadok], ignore_index=True)
    conn.update(worksheet="databaza_ponuk", data=updated_df)
    st.success("Hotovo! Ponuka bola zapísaná do hárka databaza_ponuk.")
