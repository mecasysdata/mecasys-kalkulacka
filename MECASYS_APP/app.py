import streamlit as st
import pandas as pd
import math
import xgboost as xgb
import joblib
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# --- 1. KONFIGURÁCIA STRÁNKY ---
st.set_page_config(page_title="MECASYS Kalkulátor", layout="wide")
st.title("📊 MECASYS - Inteligentná kalkulácia cien")

# --- 2. NAČÍTANIE AI MODELOV ---
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
    st.error(f"Chyba pri načítaní modelov: {e}")
    st.stop()

# --- 3. PRIPOJENIE KU GOOGLE SHEETS ---
conn = st.connection("gsheets", type=GSheetsConnection)

# Načítanie všetkých potrebných hárkov
df_materialy = conn.read(worksheet="material_cena")
df_kooperacie = conn.read(worksheet="kooperacia_cennik")
df_lojalita = conn.read(worksheet="zakaznik_lojalita")
df_databaza = conn.read(worksheet="databaza_ponuk")

# --- 4. VSTUPNÉ POLIA (Interaktívna časť) ---
st.header("1. Zadanie parametrov")
col1, col2, col3 = st.columns(3)

with col1:
    zakaznik = st.selectbox("Zákazník", df_lojalita["Meno"].unique())
    cislo_cp = st.text_input("Číslo CP")
    item_nazov = st.text_input("ITEM / Názov dielu")
    krajina = st.text_input("Krajina", value="SK")

with col2:
    d = st.number_input("Priemer d [mm]", min_value=0.0, format="%.2f", value=10.0)
    l = st.number_input("Dĺžka l [mm]", min_value=0.0, format="%.2f", value=50.0)
    pocet_kusov = st.number_input("Počet kusov [ks]", min_value=1, step=1, value=1)
    # Získanie koeficientu lojality pre neskorší výpočet (ak ho máš v tabuľke)
    lojalita_val = df_lojalita[df_lojalita["Meno"] == zakaznik]["Koeficient"].values[0] if "Koeficient" in df_lojalita.columns else 1.0

with col3:
    vybrany_mat = st.selectbox("Materiál", df_materialy["Materiál"].unique())
    akost = st.text_input("Akosť materiálu")
    narocnost = st.slider("Náročnosť výroby (1-5)", 1, 5, 1)

# --- 5. VÝPOČTY (Geometria a Materiál) ---
plocha_plasta_mm2 = math.pi * d * l
objem_mm3 = math.pi * ((d / 2) ** 2) * l

row_mat = df_materialy[df_materialy["Materiál"] == vybrany_mat].iloc[0]
hustota = row_mat["Hustota"]
cena_mat_kg = row_mat["Cena_za_kg"]

hmotnost_kg = objem_mm3 * hustota
naklad_material_O = hmotnost_kg * cena_mat_kg

# --- 6. KOOPERÁCIA ---
st.header("2. Kooperácia")
kooperacia_ano = st.checkbox("Vyžaduje komponent kooperáciu?")
naklad_kooperacia_P = 0.0

if kooperacia_ano:
    druh_koop = st.selectbox("Druh kooperácie", df_kooperacie["druh"].unique())
    row_koop = df_kooperacie[df_kooperacie["druh"] == druh_koop].iloc[0]
    
    if row_koop["jednotka"] == "dm2":
        odhad = row_koop["tarifa"] * (plocha_plasta_mm2 / 10000)
    else:
        odhad = row_koop["tarifa"] * hmotnost_kg
        
    if (odhad * pocet_kusov) < row_koop["minimalna zakazka"]:
        naklad_kooperacia_P = row_koop["minimalna zakazka"] / pocet_kusov
    else:
        naklad_kooperacia_P = odhad

vstupne_naklady_Q = naklad_material_O + naklad_kooperacia_P

# --- 7. PREDIKCIA AI (Čas a Cena) ---
in_cas = pd.DataFrame([[d, l, hmotnost_kg]], columns=['d', 'l', 'hmotnost'])
pred_cas_R = model_cas.predict(xgb.DMatrix(in_cas))[0]

in_cena = pd.DataFrame([[vstupne_naklady_Q, pred_cas_R]], columns=['vstupne_naklady', 'vypocitany_cas'])
pred_cena_S = model_cena.predict(xgb.DMatrix(in_cena))[0]

# --- 8. FINÁLNA VALIDÁCIA ---
st.header("3. Výsledok")
c1, c2 = st.columns(2)
with c1:
    st.metric("Predikovaný čas [min]", f"{pred_cas_R:.2f}")
    st.metric("Odporúčaná cena [€/ks]", f"{pred_cena_S:.2f}")

with c2:
    override = st.checkbox("Upraviť cenu ručne")
    finalna_cena_S = st.number_input("Finálna jednotková cena [€]", value=float(pred_cena_S)) if override else pred_cena_S

cena_spolu_U = finalna_cena_S * pocet_kusov

# --- 9. ZÁPIS DO TABUĽKY (Presne podľa tvojho screenshotu) ---
if st.button("💾 ULOŽIŤ PONUKU"):
    novy_riadok = pd.DataFrame([{
        "Dátum CP": datetime.now().strftime("%d.%m.%Y"),
        "Číslo CP": cislo_cp,
        "Zákazník": zakaznik,
        "Krajina": krajina,
        "Lojalita": lojalita_val,
        "ITEM": item_nazov,
        "Materiál": vybrany_mat,
        "Akosť": akost,
        "d": d,
        "l": l,
        "Hustota": hustota,
        "Hmotnosť": hmotnost_kg,
        "Náročnosť": narocnost,
        "J.cena materiálu": cena_mat_kg,
        "Náklad materiál": naklad_material_O,
        "Náklad kooperácia": naklad_kooperacia_P,
        "Vstupné náklady": vstupne_naklady_Q,
        "Čas (min)": pred_cas_R,
        "Jednotková cena": finalna_cena_S,
        "Počet kusov": pocet_kusov,
        "Cena položky spolu": cena_spolu_U
    }])
    
    updated_df = pd.concat([df_databaza, novy_riadok], ignore_index=True)
    conn.update(worksheet="databaza_ponuk", data=updated_df)
    st.success("Dáta úspešne uložené do Google Sheetu!")
