import streamlit as st
import pandas as pd
from xgboost import XGBRegressor
import pickle

st.set_page_config(page_title="TEST – Overenie dát a modelov", layout="wide")

st.title("TEST APLIKÁCIE – KROK 1")
st.write("Overíme načítanie všetkých Google Sheets, modelov a ich vstupov.")

# -----------------------------
# Cesty k modelom – správne pre Streamlit Cloud
# (app.py je v MECASYS_APP, modely sú v MECASYS_APP)
# -----------------------------
M1_MODEL_PATH = "finaly_model.json"
M1_COLUMNS_PATH = "stlpce_modelu.pkl"

M2_MODEL_PATH = "xgb_model_cena.json"
M2_COLUMNS_PATH = "model_columns.pkl"

# -----------------------------
# URL Google Sheets
# -----------------------------
URLS = {
    "databaza_ponuk": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=0&single=true&output=csv",
    "kooperacie_cennik": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1180392224&single=true&output=csv",
    "material_akost_hustota": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1281008948&single=true&output=csv",
    "material_cena": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=901617097&single=true&output=csv",
    "zakaznik_lojalita": "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=324957857&single=true&output=csv",
}

# -----------------------------
# TEST 1: Načítanie všetkých Google Sheets
# -----------------------------
st.header("1️⃣ Test načítania Google Sheets")

for name, url in URLS.items():
    st.subheader(f"Sheet: **{name}**")
    try:
        df = pd.read_csv(url)
        st.success(f"Načítané OK – {len(df)} riadkov")

        st.write("### Stĺpce:")
        st.write(list(df.columns))

        st.write("### Prvých 5 riadkov:")
        st.dataframe(df.head())

        st.write("### Typy stĺpcov:")
        st.write(df.dtypes)

    except Exception as e:
        st.error(f"Chyba pri načítaní {name}: {e}")

# -----------------------------
# TEST 2: Načítanie modelu M1
# -----------------------------
st.header("2️⃣ Test načítania modelu M1 (čas)")

try:
    m1 = XGBRegressor()
    m1.load_model(M1_MODEL_PATH)
    st.success("Model M1 načítaný!")
except Exception as e:
    st.error(f"Chyba pri načítaní modelu M1: {e}")

try:
    with open(M1_COLUMNS_PATH, "rb") as f:
        cols_m1 = pickle.load(f)
    st.success("Stĺpce M1 načítané!")

    st.write("### Vstupy modelu M1:")
    st.write(cols_m1)
    st.write("### Počet vstupov:", len(cols_m1))

except Exception as e:
    st.error(f"Chyba pri načítaní stĺpcov M1: {e}")

# -----------------------------
# TEST 3: Načítanie modelu M2
# -----------------------------
st.header("3️⃣ Test načítania modelu M2 (cena)")

try:
    m2 = XGBRegressor()
    m2.load_model(M2_MODEL_PATH)
    st.success("Model M2 načítaný!")
except Exception as e:
    st.error(f"Chyba pri načítaní modelu M2: {e}")

try:
    with open(M2_COLUMNS_PATH, "rb") as f:
        cols_m2 = pickle.load(f)
    st.success("Stĺpce M2 načítané!")

    st.write("### Vstupy modelu M2:")
    st.write(cols_m2)
    st.write("### Počet vstupov:", len(cols_m2))

except Exception as e:
    st.error(f"Chyba pri načítaní stĺpcov M2: {e}")
