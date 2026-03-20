import streamlit as st
import pandas as pd
import math
import xgboost as xgb
import joblib
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# --- 1. NASTAVENIA ---
st.set_page_config(page_title="MECASYS Kalkulátor", layout="wide")
st.title("📊 MECASYS - Inteligentná kalkulácia cien")

# --- 2. NAČÍTANIE MODELOV (Strikné podľa GitHubu) ---
@st.cache_resource
def load_models():
    m1 = xgb.Booster(); m1.load_model('finalny_model.json')
    c1 = joblib.load('stlpce_modelu.pkl')
    m2 = xgb.Booster(); m2.load_model('xgb_model_cena.json')
    c2 = joblib.load('model_columns.pkl')
    return m1, c1, m2, c2

model_cas, cols_cas, model_cena, cols_cena = load_models()

# --- 3. PRIPOJENIE TABULIEK (Bod 35) ---
conn = st.connection("gsheets", type=GSheetsConnection)

df_materialy = conn.read(worksheet="material_cena")
df_kooperacie = conn.read(worksheet="kooperacie_cennik")
df_lojalita = conn.read(worksheet="zakaznik_lojalita")
df_databaza = conn.read(worksheet="databaza_ponuk")

# --- 4. VSTUPY (Bod 1-10) ---
st.header("1. Parametre komponentu")
col1, col2, col3 = st.columns(3)

with col1:
    zakaznik = st.selectbox("Zákazník", df_lojalita["Meno"].unique())
    cislo_cp = st.text_input("Číslo CP")
    item_nazov = st.text_input("ITEM / Názov dielu")

with col2:
    d = st.number_input("Priemer d [mm]", min_value=0.0, format="%.2f")
    l = st.number_input("Dĺžka l [mm]", min_value=0.0, format="%.2f")
    pocet_kusov = st.number_input("Počet kusov [ks]", min_value=1, step=1)

with col3:
    vybrany_mat = st.selectbox("Materiál", df_materialy["Materiál"].unique())

# --- 5. GEOMETRIA A MATERIÁL (Stĺpce G, H, O) ---
plocha_plasta_mm2 = math.pi * d * l
objem_mm3 = math.pi * ((d / 2) ** 2) * l

row_mat = df_materialy[df_materialy["Materiál"] == vybrany_mat].iloc[0]
hustota = row_mat["Hustota"]
cena_kg = row_mat["Cena_za_kg"]

hmotnost_kg = objem_mm3 * hustota # Stĺpec G
naklad_material_O = hmotnost_kg * cena_kg # Stĺpec O

# --- 6. KOOPERÁCIA (Stĺpec P + Prevod na dm2) ---
st.header("2. Kooperácia")
kooperacia_ano = st.checkbox("Vyžaduje komponent kooperáciu?")
naklad_kooperacia_P = 0.0

if kooperacia_ano:
    druh_koop = st.selectbox("Druh kooperácie", df_kooperacie["Druh"].unique())
    row_koop = df_kooperacie[df_kooperacie["Druh"] == druh_koop].iloc[0]
    
    if row_koop["Jednotka"] == "dm2":
        odhad = row_koop["Tarifa"] * (plocha_plasta_mm2 / 10000)
    else:
        odhad = row_koop["Tarifa"] * hmotnost_kg
        
    # Kontrola min. zákazky
    if (odhad * pocet_kusov) < row_koop["Min_zakazka"]:
        naklad_kooperacia_P = row_koop["Min_zakazka"] / pocet_kusov
    else:
        naklad_kooperacia_P = odhad

vstupne_naklady_Q = naklad_material_O + naklad_kooperacia_P # Stĺpec Q

# --- 7. PREDIKCIA (M1, M2) ---
# M1: Čas (R)
in_cas = pd.DataFrame([[d, l, hmotnost_kg]], columns=['d', 'l', 'hmotnost'])
pred_cas_R = model_cas.predict(xgb.DMatrix(in_cas))[0]

# M2: Cena (S)
in_cena = pd.DataFrame([[vstupne_naklady_Q, pred_cas_R]], columns=['vstupne_naklady', 'vypocitany_cas'])
pred_cena_S = model_cena.predict(xgb.DMatrix(in_cena))[0]

# --- 8. VALIDÁCIA TECHNOLÓGOM ---
st.header("3. Výsledok a uloženie")
c_v1, c_v2 = st.columns(2)
with c_v1:
    st.write(f"Odhadovaný čas: **{pred_cas_R:.2f} min**")
    st.write(f"Modelom navrhnutá cena: **{pred_cena_S:.2f} €/ks**")
with c_v2:
    override = st.checkbox("Upraviť cenu manuálne")
    jednotkova_cena_final = st.number_input("Finálna jednotková cena [€/ks]", value=float(pred_cena_S)) if override else pred_cena_S

cena_spolu_U = jednotkova_cena_final * pocet_kusov

# --- 9. ZÁPIS DO GOOGLE SHEETS (Stĺpce A-U) ---
if st.button("💾 ULOŽIŤ PONUKU"):
    novy_riadok = pd.DataFrame([{
        "A-Dátum": datetime.now().strftime("%d.%m.%Y"),
        "B-Číslo CP": cislo_cp,
        "C-Zákazník": zakaznik,
        "D-ITEM": item_nazov,
        "G-Hmotnosť": hmotnost_kg,
        "O-Náklad materiál": naklad_material_O,
        "P-Náklad kooperácia": naklad_kooperacia_P,
        "Q-Vstupné náklady": vstupne_naklady_Q,
        "R-Predikovaný čas": pred_cas_R,
        "S-Jednotková cena": jednotkova_cena_final,
        "T-Počet kusov": pocet_kusov,
        "U-Cena spolu": cena_spolu_U
    }])
    
    updated_df = pd.concat([df_databaza, novy_riadok], ignore_index=True)
    conn.update(worksheet="databaza_ponuk", data=updated_df)
    st.success("Dáta boli zapísané do tabuľky.")
