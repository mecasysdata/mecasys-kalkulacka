import math
import pickle
from datetime import date
import io

import numpy as np
import pandas as pd
import streamlit as st
from xgboost import XGBRegressor
from streamlit_gsheets import GSheetsConnection

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


# ==========================
# KONFIGURÁCIA
# ==========================

st.set_page_config(page_title="Predikcia ceny komponenty", layout="wide")

# Public CSV linky
URL_DATABAZA_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=0&single=true&output=csv"
URL_KOOPERACIE = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1180392224&single=true&output=csv"
URL_MATERIAL_AKOST_HUSTOTA = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=1281008948&single=true&output=csv"
URL_MATERIAL_CENA = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=901617097&single=true&output=csv"
URL_ZAKAZNIK_LOJALITA = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRfPBZ4TCpQyiqybU0ADu3AMwHCi2qOKifQAOnnTWnorVNJ1SVxtN6zJzXthOxCVwtXWp__Bp_-nto0/pub?gid=324957857&single=true&output=csv"

# Plná URL databázy pre GSheetsConnection
URL_DATABAZA_GSHEETS = "https://docs.google.com/spreadsheets/d/1kOAKlZRCsoIUn-_438n0NFjO0tQJ2td8VydXHGmV00U/edit"

# Cesty k modelom v repozitári
M1_MODEL_PATH = "finalny_model.json"
M1_COLUMNS_PATH = "stlpce_modelu.pkl"

M2_MODEL_PATH = "xgb_model_cena.json"
M2_COLUMNS_PATH = "model.columns.pkl"


# ==========================
# NAČÍTANIE DÁT A MODELOV
# ==========================

def load_csv(url: str) -> pd.DataFrame:
    df = pd.read_csv(url)
    df.columns = df.columns.astype(str).str.strip()
    return df


def load_m1_model():
    model = XGBRegressor()
    model.load_model(M1_MODEL_PATH)
    with open(M1_COLUMNS_PATH, "rb") as f:
        cols = pickle.load(f)
    return model, cols


def load_m2_model():
    model = XGBRegressor()
    model.load_model(M2_MODEL_PATH)
    with open(M2_COLUMNS_PATH, "rb") as f:
        cols = pickle.load(f)
    return model, cols


def get_gsheets_connection():
    conn = st.connection("gsheets", type=GSheetsConnection)
    return conn


# ==========================
# POMOCNÉ FUNKCIE
# ==========================

def normalize_text(x: str) -> str:
    return str(x).strip().upper()


def compute_hustota(material: str, akost: str, df_mat: pd.DataFrame) -> float:
    material_u = normalize_text(material)
    akost_u = normalize_text(akost)

    if material_u in ["OCEĽ", "OCEL"]:
        return 7900.0
    if material_u == "NEREZ":
        return 8000.0
    if material_u == "PLAST":
        mask = (df_mat["material"].astype(str).str.strip().str.upper() == "PLAST") & (
            df_mat["akost"].astype(str).str.strip().str.upper() == akost_u
        )
        row = df_mat[mask]
        return float(row["hustota"].iloc[0])
    if material_u in ["FAREBNÉ KOVY", "FAREBNE KOVY"]:
        if akost_u.startswith("3.7"):
            return 4500.0
        if akost_u.startswith("3."):
            return 2900.0
        if akost_u.startswith("2."):
            return 9000.0
    return 0.0


def prepare_m1_input_row(d, l, pocet_kusov, material, akost, narocnost, df_mat: pd.DataFrame, m1_columns):
    material_u = normalize_text(material)
    akost_u = normalize_text(akost)
    narocnost_u = normalize_text(narocnost)

    hustota = compute_hustota(material_u, akost_u, df_mat)
    plocha_prierezu = (math.pi * d**2) / 4.0
    plocha_plasta = math.pi * d * l

    base = {
        "d": d,
        "l": l,
        "pocet_kusov": np.log1p(pocet_kusov),
        "hustota": hustota,
        "plocha_prierezu": plocha_prierezu,
        "plocha_plasta": plocha_plasta,
        "material": material_u,
        "akost": akost_u,
        "narocnost": narocnost_u,
    }

    df = pd.DataFrame([base])
    df = pd.get_dummies(df, columns=["material", "akost", "narocnost"], drop_first=True)

    for col in m1_columns:
        if col not in df.columns:
            df[col] = 0
    df = df[m1_columns]

    return df, hustota, plocha_prierezu, plocha_plasta


def prepare_m2_input_row(cas_min, hmotnost, plocha_prierezu, vstupne_naklady, krajina, m2_columns):
    krajina_str = str(krajina).strip()

    base = {
        "cas": cas_min,
        "hmotnost": hmotnost,
        "plocha_prierezu": plocha_prierezu,
        "vstupne_naklady": vstupne_naklady,
        "krajina": krajina_str,
    }

    df = pd.DataFrame([base])
    df = pd.get_dummies(df, columns=["krajina"])

    for col in m2_columns:
        if col not in df.columns:
            df[col] = 0
    df = df[m2_columns]

    return df


def find_material_price(d, akost, df_mat_cena: pd.DataFrame):
    akost_u = normalize_text(akost)
    df = df_mat_cena.copy()
    df["akost_u"] = df["akost"].astype(str).str.strip().str.upper()

    subset = df[df["akost_u"] == akost_u].copy()
    subset["d"] = pd.to_numeric(subset["d"], errors="coerce")
    subset = subset.dropna(subset=["d"])

    exact = subset[subset["d"] == d]
    if not exact.empty:
        row = exact.iloc[0]
        return float(row["J.cena/m"]), float(row["d"])

    higher = subset[subset["d"] > d].sort_values("d")
    if not higher.empty:
        row = higher.iloc[0]
        return float(row["J.cena/m"]), float(row["d"])

    return None, None


def compute_kooperacia(material, druh_kooperacie, hmotnost, plocha_plasta, pocet_kusov, df_koop: pd.DataFrame):
    material_u = normalize_text(material)
    druh_u = normalize_text(druh_kooperacie)

    df = df_koop.copy()
    df["material_u"] = df["material"].astype(str).str.strip().str.upper()
    df["druh_u"] = df["druh"].astype(str).str.strip().str.upper()

    subset = df[(df["material_u"] == material_u) & (df["druh_u"] == druh_u)]
    row = subset.iloc[0]

    tarifa = float(row["tarifa"])
    jednotka = str(row["jednotka"]).strip().lower()
    minimalna_zakazka = float(row["minimalna zakazka"])

    if jednotka == "kg":
        odhad_kooperacie = tarifa * hmotnost
    else:
        odhad_kooperacie = (plocha_plasta / 10000.0) * tarifa

    celkom = pocet_kusov * odhad_kooperacie

    if celkom < minimalna_zakazka:
        naklad_kooperacia = minimalna_zakazka / pocet_kusov
    else:
        naklad_kooperacia = odhad_kooperacie

    return naklad_kooperacia, odhad_kooperacie


def generate_pdf(df_kosik: pd.DataFrame, header: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("MECASYS – Quotation", styles["Title"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"Date of issue: {header['datum_cp']}", styles["Normal"]))
    story.append(Paragraph(f"Quotation Nbr.: {header['cislo_cp']}", styles["Normal"]))
    story.append(Paragraph(f"Customer: {header['zakaznik']} ({header['krajina']})", styles["Normal"]))
    story.append(Spacer(1, 12))

    data = [["Item", "Q'ty", "Price per Item", "Total price"]]
    for _, row in df_kosik.iterrows():
        data.append([
            str(row["ITEM"]),
            int(row["Počet kusov"]),
            f"{row['Jednotková cena']:.2f} €",
            f"{row['Cena položky spolu']:.2f} €",
        ])

    table = Table(data, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))

    total = df_kosik["Cena položky spolu"].sum()
    story.append(Paragraph(f"Total price w/o VAT: {total:.2f} €", styles["Heading3"]))

    doc.build(story)
    pdf_value = buffer.getvalue()
    buffer.close()
    return pdf_value


def append_to_databaza(df_new_rows: pd.DataFrame):
    conn = get_gsheets_connection()
    conn.create(
        spreadsheet=URL_DATABAZA_GSHEETS,
        worksheet="databaza_ponuk",
        data=df_new_rows,
    )


# ==========================
# HLAVNÁ APLIKÁCIA
# ==========================

def main():
    st.title("Predikcia ceny komponenty")

    df_materialy = load_csv(URL_MATERIAL_AKOST_HUSTOTA)
    df_zakaznici = load_csv(URL_ZAKAZNIK_LOJALITA)
    df_kooperacie = load_csv(URL_KOOPERACIE)
    df_material_cena = load_csv(URL_MATERIAL_CENA)

    m1_model, m1_columns = load_m1_model()
    m2_model, m2_columns = load_m2_model()

    if "kosik" not in st.session_state:
        st.session_state["kosik"] = []

    st.subheader("Hlavička cenovej ponuky")

    col_h1, col_h2, col_h3 = st.columns(3)
    with col_h1:
        datum_cp = st.date_input("Dátum CP", value=date.today())
    with col_h2:
        cislo_cp = st.text_input("Číslo CP")
    with col_h3:
        existujuci_zakaznik = st.selectbox(
            "Zákazník (existujúci alebo 'NOVÝ')",
            options=["NOVÝ"] + sorted(df_zakaznici["zakaznik"].astype(str).unique().tolist()),
        )

    if existujuci_zakaznik != "NOVÝ":
        row_z = df_zakaznici[df_zakaznici["zakaznik"] == existujuci_zakaznik].iloc[0]
        zakaznik_nazov = existujuci_zakaznik
        krajina = row_z["krajina"]
        lojalita = float(row_z["lojalita"])
    else:
        zakaznik_nazov = st.text_input("Názov nového zákazníka")
        krajina = st.text_input("Krajina nového zákazníka")
        lojalita = 0.5

    st.subheader("Parametre komponentu (ITEM)")

    col1, col2, col3 = st.columns(3)
    with col1:
        item_nazov = st.text_input("ITEM (označenie komponentu)")
        d = st.number_input("d [mm]", min_value=0.0, value=20.0, step=1.0)
        l = st.number_input("l [mm]", min_value=0.0, value=100.0, step=1.0)
    with col2:
        pocet_kusov = st.number_input("Počet kusov", min_value=1, value=10, step=1)
        narocnost = st.selectbox("Náročnosť", options=["1", "2", "3", "4", "5"])
    with col3:
        material = st.selectbox("Materiál", options=["OCEĽ", "NEREZ", "PLAST", "FAREBNÉ KOVY"])
        mask_mat = df_materialy["material"].astype(str).str.strip().str.upper() == normalize_text(material)
        akosti_moznosti = sorted(df_materialy[mask_mat]["akost"].astype(str).unique().tolist())
        akost = st.selectbox("Akosť", options=akosti_moznosti)

    st.subheader("Kooperácia")
    kooperacia_needed = st.radio("Vyžaduje diel kooperáciu?", options=["Nie", "Áno"], horizontal=True)
    druh_kooperacie = None
    if kooperacia_needed == "Áno":
        druhy = sorted(df_kooperacie["druh"].astype(str).unique().tolist())
        druh_kooperacie = st.selectbox("Druh kooperácie", options=druhy)

    if st.button("Pridať položku do košíka"):
        df_m1_input, hustota, plocha_prierezu, plocha_plasta = prepare_m1_input_row(
            d=d,
            l=l,
            pocet_kusov=pocet_kusov,
            material=material,
            akost=akost,
            narocnost=narocnost,
            df_mat=df_materialy,
            m1_columns=m1_columns,
        )

        # M1 – predikcia času (log -> expm1)
        y_log = m1_model.predict(df_m1_input)
        cas_min = float(np.expm1(y_log)[0])

        # Hmotnosť – deterministický výpočet
        hmotnost = hustota * (math.pi / 4.0) * (d / 1000.0) ** 2 * (l / 1000.0)

        # Materiál – deterministický výpočet z cenníka
        j_cena_m, d_pouzite = find_material_price(d, akost, df_material_cena)
        if j_cena_m is None:
            naklad_material = st.number_input("Náklad materiál [€/ks] (ručný vstup)", min_value=0.0, value=0.0, step=0.1)
        else:
            naklad_material = (l / 1000.0) * j_cena_m

        # Kooperácia – deterministický výpočet z cenníka
        if kooperacia_needed == "Áno" and druh_kooperacie is not None:
            naklad_kooperacia, _ = compute_kooperacia(
                material=material,
                druh_kooper
