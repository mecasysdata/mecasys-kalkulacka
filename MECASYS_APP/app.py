import streamlit as st
import pandas as pd
import math
import xgboost as xgb
import joblib
from streamlit_gsheets import GSheetsConnection
from datetime import datetime

# --- 1. KONFIGURÁCIA STRÁNKY ---
st.set_page_config(page_title="MECASYS Kalkulátor", layout="wide")
st.title("📊 MECASYS - Inteligentný systém riadenia ponúk")

# --- 2. NAČÍTANIE MODELOV (STRIKTNÉ) ---
# Program vyžaduje existenciu týchto súborov v rovnakom priečinku
try:
    # Model M1 (Čas)
    model_cas = xgb.Booster()
    model_cas.load_model('finalny_model.json')
    cols_cas = joblib.load('stlpce_modelu.pkl')

    # Model M2 (Cena)
    model_cena = xgb.Booster()
    model_cena.load_model('xgb_model_cena.json')
    cols_cena = joblib.load('model_columns.pkl')
except Exception as e:
    st.error(f"Chyba pri načítaní AI modelov: {e}")
    st.stop()

# --- 3. PREPOJENIE NA GOOGLE SHEETS (Bod 35 vo Worde) ---
conn = st.connection("gsheets", type=GSheetsConnection)

# Načítanie všetkých 4 potrebných zdrojov
df_materialy = conn.read(worksheet="material_cena")
df_kooperacie = conn.read(worksheet="kooperacie_cennik")
df_lojalita = conn.read(worksheet="zakaznik_lojalita")
df_databaza = conn.read(worksheet="databaza_ponuk")

# --- 4. VSTUPNÉ ÚDAJE (Bod 1-10 vo Worde) ---
st.header("1. Zadanie parametrov dielu")
c1, c2, c3 = st.columns(3)

with c1:
    zakaznik = st.selectbox("Vyber zákazníka", df_lojalita["Meno"].unique())
    cislo_cp = st.text_input("Číslo cenovej ponuky (CP)")
    polozka_item = st.text_input("Názov dielu / ITEM")

with c2:
    d = st.number_input("Priemer (d) [mm]", min_value=0.0, format="%.2f", step=0.1)
    l = st.number_input("Dĺžka (l) [mm]", min_value=0.0, format="%.2f", step=0.1)
    pocet_kusov = st.number_input("Počet kusov [ks]", min_value=1, step=1)

with c3:
    zoznam_mat = df_materialy["Materiál"].unique()
    vybrany_mat = st.selectbox("Materiál polotovaru", zoznam_mat)

# --- 5. GEOMETRICKÉ VÝPOČTY A MATERIÁL ---
# Plocha plášťa (zatiaľ v mm2)
plocha_plasta_mm2 = math.pi * d * l
# Objem pre výpočet hmotnosti
objem_mm3 = math.pi * ((d / 2) ** 2) * l

# Vyhľadanie dát o materiáli z df_materialy
row_mat = df_materialy[df_materialy["Materiál"] == vybrany_mat].iloc[0]
hustota = row_mat["Hustota"]
cena_mat_kg = row_mat["Cena_za_kg"]

hmotnost_ks = objem_mm3 * hustota
naklad_material_O = hmotnost_ks * cena_mat_kg

# --- 6. LOGIKA KOOPERÁCIE (S PREVODOM NA dm2) ---
st.header("2. Externé spracovanie (Kooperácia)")
kooperacia_ano = st.radio("Vyžaduje komponent kooperáciu?", ["Nie", "Áno"])

naklad_kooperacia_P = 0.0

if kooperacia_ano == "Áno":
    druh_koop = st.selectbox("Druh kooperácie", df_kooperacie["Druh"].unique())
    
    # Filter cenníka podľa druhu a materiálu
    try:
        mask = (df_kooperacie["Druh"] == druh_koop)
        row_koop = df_kooperacie[mask].iloc[0]
        
        tarifa = row_koop["Tarifa"]
        jednotka = row_koop["Jednotka"]
        min_zakazka = row_koop["Min_zakazka"]
        
        # Výpočet odhadu (Tu prebieha prevod na dm2)
        if jednotka == "kg":
            odhad_koop = tarifa * hmotnost_ks
        elif jednotka == "dm2":
            plocha_dm2 = plocha_plasta_mm2 / 10000
            odhad_koop = tarifa * plocha_dm2
        
        # Kontrola minimálnej zákazky
        if (odhad_koop * pocet_kusov) < min_zakazka:
            naklad_kooperacia_P = min_zakazka / pocet_kusov
            st.warning(f"Uplatnená minimálna zákazka: {naklad_kooperacia_P:.4f} €/ks")
        else:
            naklad_kooperacia_P = odhad_koop
            st.success(f"Vypočítaný náklad: {naklad_kooperacia_P:.4f} €/ks")
    except:
        st.error("Dáta pre túto kombináciu kooperácie neboli nájdené v cenníku.")

# --- 7. PREDIKCIA M1 (ČAS) ---
vstupne_naklady_Q = naklad_material_O + naklad_kooperacia_P

# Príprava dát pre XGBoost (názvy stĺpcov musia sedieť s cols_cas)
input_cas_df = pd.DataFrame([[d, l, hmotnost_ks]], columns=['d', 'l', 'hmotnost'])
d_cas = xgb.DMatrix(input_cas_df)
predikovany_cas_R = model_cas.predict(d_cas)[0]

# --- 8. PREDIKCIA M2 (CENA) A VALIDÁCIA TECHNOLÓGOM ---
# Príprava dát pre M2
input_cena_df = pd.DataFrame([[vstupne_naklady_Q, predikovany_cas_R]], columns=['vstupne_naklady', 'vypocitany_cas'])
d_cena = xgb.DMatrix(input_cena_df)
predikovana_cena_S = model_cena.predict(d_cena)[0]

st.header("3. Výsledná kalkulácia a Validácia")
col_res1, col_res2 = st.columns(2)

with col_res1:
    st.metric("Predikovaný strojný čas [R]", f"{predikovany_cas_R:.2f} min")
    st.metric("Predikovaná cena modelu [S]", f"{predikovana_cena_S:.2f} €")

with col_res2:
    upravit_cenu = st.checkbox("Manuálna korekcia ceny (Technológ)")
    if upravit_cenu:
        finalna_cena_S = st.number_input("Upravená jednotková cena [€/ks]", value=float(predikovana_cena_S))
    else:
        finalna_cena_S = predikovana_cena_S

# Celková cena za položku
cena_spolu_U = finalna_cena_S * pocet_kusov
st.subheader(f"Konečná cena položky [U]: {cena_spolu_U:.2f} €")

# --- 9. ZÁPIS DO DATABÁZY (A-U) ---
if st.button("💾 ULOŽIŤ A GENEROVAŤ ZÁZNAM"):
    novy_riadok = pd.DataFrame([{
        "Dátum": datetime.now().strftime("%d.%m.%Y"),
        "Zákazník": zakaznik,
        "Číslo CP": cislo_cp,
        "ITEM": polozka_item,
        "Priemer d": d,
        "Dĺžka l": l,
        "Hmotnosť [kg]": hmotnost_ks,
        "Náklad materiál [O]": naklad_material_O,
        "Náklad kooperácia [P]": naklad_kooperacia_P,
        "Vstupné náklady [Q]": vstupne_naklady_Q,
        "Čas [R]": predikovany_cas_R,
        "Jednotková cena [S]": finalna_cena_S,
        "Počet kusov [T]": pocet_kusov,
        "Cena spolu [U]": cena_spolu_U
    }])
    
    # Pridanie riadku do Google Sheets
    updated_df = pd.concat([df_databaza, novy_riadok], ignore_index=True)
    conn.update(worksheet="databaza_ponuk", data=updated_df)
    st.success("Ponuka bola zapísaná do centrálnej databázy.")