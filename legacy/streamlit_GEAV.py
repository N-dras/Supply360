"""
=============================================================================
 GEAV — Croisement Besoin / Stock / Commandes
 Grand Entretien Avion : identifie les pièces à commander ou les fournisseurs
 à relancer pour sécuriser les équipements avant la GEAV.
=============================================================================
Croise 3 fichiers :
  1) Fichier Besoin GEAV (ex: "Workpages_PartRequirements") -> colonnes Qty / MPN Prime
  2) Fichier Résultat / État du stock -> colonnes PNR, QTE SUR ÉTAGÈRE, QTE EN CDE,
     CODE AGT APPRO, GESTION, CODE FOURNISSEUR
  3) Fichier Tableau de bord (feuille "Toutes les commandes") -> colonnes PN, Commande,
     Code acheteur, Code fournisseur, Fournisseur, Date de livraison promise

La détection des feuilles / colonnes est automatique (par mots-clés, insensible aux
accents/majuscules) afin de fonctionner avec des fichiers d'autres avions dont les
noms de fichiers changeront.

Lancement :  streamlit run streamlit_GEAV.py
Dépendances : streamlit pandas numpy openpyxl
=============================================================================
"""

import io
import re
import unicodedata

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="GEAV — Croisement Besoin / Stock / Commandes",
                    page_icon="✈️", layout="wide")

C = {"critique": "#D7263D", "alerte": "#F46036", "warn": "#F4A261",
     "ok": "#1B998B", "accent": "#2E86AB", "neutre": "#6C757D"}

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');
    
    * {
        font-family: 'Poppins', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    html, body, [data-testid="stAppViewContainer"] {
        background: #F5F7FA;
    }
    
    [data-testid="stSidebar"] {
        background: #FFFFFF;
        border-right: 1px solid #E1E8ED;
    }
    
    .block-container {
        padding-top: 2rem;
        max-width: 1500px;
    }
    
    /* KPI Cards - Clean & Modern */
    .kpi-card {
        background: #FFFFFF;
        border-radius: 10px;
        padding: 18px;
        margin-bottom: 12px;
        border: 1px solid #E1E8ED;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
        transition: all 0.2s ease;
    }
    
    .kpi-card:hover {
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        border-color: #D0D8E0;
    }
    
    .kpi-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 2px;
        background: var(--card-color, #2C5AA0);
        border-radius: 10px 10px 0 0;
    }
    
    .kpi-label {
        font-size: 0.7rem;
        color: #7A8699;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        font-weight: 600;
        margin-bottom: 6px;
    }
    
    .kpi-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0F172A;
        line-height: 1;
        margin: 6px 0;
    }
    
    .kpi-sub {
        font-size: 0.75rem;
        color: #9BA5B5;
        margin-top: 4px;
        font-weight: 500;
    }
    
    /* Headers */
    h1 {
        color: #0F172A;
        font-weight: 700;
        font-size: 2.2rem;
        margin-bottom: 8px;
    }
    
    h2 {
        color: #1F2937;
        font-weight: 700;
        font-size: 1.3rem;
        margin-top: 20px;
        margin-bottom: 12px;
    }
    
    /* Text */
    [data-testid="stCaption"] {
        color: #7A8699 !important;
        font-size: 0.85rem;
    }
    
    /* Tabs */
    [data-testid="stTabs"] {
        margin-bottom: 20px;
    }
    
    /* Alerts */
    [data-testid="stAlert"] {
        border-radius: 8px;
        border-left: 4px solid;
        padding: 14px;
        margin-bottom: 16px;
    }
    
    /* Dataframe */
    [data-testid="stDataFrame"] {
        border-radius: 8px;
        overflow: hidden;
    }
    
    /* Inputs */
    input, select, textarea {
        border-radius: 6px;
        border: 1px solid #D0D8E0 !important;
        font-size: 0.9rem;
    }
    
    input:focus, select:focus, textarea:focus {
        border-color: #2C5AA0 !important;
        box-shadow: 0 0 0 2px rgba(44, 90, 160, 0.1) !important;
    }
    
    /* Buttons */
    button {
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    
    button:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

TODAY = pd.Timestamp.today().normalize()
DEFAULT_GESTIONS = [245, 246, 247, 400, 401, 230]


# --------------------------------------------------------------------------
# HELPERS génériques (détection colonnes / feuilles, insensible accents)
# --------------------------------------------------------------------------
def _norm(s):
    """minuscule, sans accent, espaces normalisés."""
    s = str(s).replace("\n", " ").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def _clean_cols(df):
    df = df.copy()
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    return df


def find_col(df, *candidates, exact=False):
    """Cherche une colonne dont le nom (normalisé) correspond aux candidats.
    Essaie d'abord une correspondance exacte, puis une correspondance partielle."""
    norm_map = {c: _norm(c) for c in df.columns}
    cands_norm = [_norm(c) for c in candidates]
    # 1) exact match
    for col, n in norm_map.items():
        if n in cands_norm:
            return col
    if exact:
        return None
    # 2) partial match (candidat contenu dans le nom de colonne)
    for col, n in norm_map.items():
        for cand in cands_norm:
            if cand in n:
                return col
    return None


def find_header_row(raw, must_have, max_scan=15):
    """Cherche la ligne d'en-tête dans les `max_scan` premières lignes d'une feuille
    lue sans header : doit contenir tous les mots-clés `must_have` (normalisés)."""
    must_have_n = [_norm(m) for m in must_have]
    for i in range(min(max_scan, len(raw))):
        row_n = [_norm(v) for v in raw.iloc[i].tolist()]
        joined = " | ".join(row_n)
        if all(any(m in cell for cell in row_n) or m in joined for m in must_have_n):
            return i
    return None


def pick_sheet_and_header(file_bytes, must_have, prefer_sheet=None):
    """Retourne (nom_feuille, header_row) : cherche la feuille (en priorité `prefer_sheet`
    si son nom matche) contenant les colonnes attendues, sinon scanne toutes les feuilles."""
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    ordered_sheets = list(xl.sheet_names)
    if prefer_sheet:
        ordered_sheets.sort(key=lambda s: 0 if _norm(prefer_sheet) in _norm(s) else 1)
    for s in ordered_sheets:
        try:
            raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=s, header=None, nrows=15)
        except Exception:
            continue
        h = find_header_row(raw, must_have)
        if h is not None:
            return s, h
    return xl.sheet_names[0], 0


def join_unique(series, sep=" | "):
    vals = [str(v).strip() for v in series if pd.notna(v) and str(v).strip() and str(v).strip().lower() != "nan"]
    return sep.join(dict.fromkeys(vals)) if vals else np.nan


def pn_key(series):
    """Normalise une référence pièce pour la jointure : majuscules, sans espaces superflus."""
    return series.astype(str).str.strip().str.upper().replace({"NAN": np.nan, "": np.nan})


def safe_str(series):
    """Convertit en texte tout en préservant les valeurs manquantes (évite la chaîne 'nan')."""
    return series.where(series.notna(), np.nan).astype(object).apply(
        lambda v: str(v).strip() if pd.notna(v) and str(v).strip() else np.nan
    )


# --------------------------------------------------------------------------
# CHARGEMENT FICHIER 1a — Besoin GEAV Classique (Qty / MPN Prime)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_besoin(file_bytes):
    sheet, hdr = pick_sheet_and_header(file_bytes, ["mpn prime", "qty"], prefer_sheet="PartRequirements")
    df = _clean_cols(pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=hdr))

    c_pn = find_col(df, "mpn prime", exact=True) or find_col(df, "mpn prime")
    c_qty = find_col(df, "qty", exact=True) or find_col(df, "quantite", "quantity")
    c_desc = find_col(df, "description")
    c_task = find_col(df, "task trfx", exact=True) or find_col(df, "task trfx", "task name", "task wp line", "trfx")

    if c_pn is None or c_qty is None:
        raise ValueError(
            f"Impossible de trouver les colonnes 'MPN Prime' / 'Qty' dans la feuille "
            f"'{sheet}' du fichier Besoin GEAV. Colonnes détectées : {list(df.columns)}"
        )

    out = pd.DataFrame({
        "PN": pn_key(df[c_pn]),
        "Qty": pd.to_numeric(df[c_qty], errors="coerce").fillna(0),
        "Description": df[c_desc] if c_desc else np.nan,
        "TRFX": safe_str(df[c_task]) if c_task else np.nan,
    })
    out = out[out["PN"].notna()]

    grouped = out.groupby("PN").agg(
        QTY_GEAV=("Qty", "sum"),
        Nb_lignes=("Qty", "size"),
        Description=("Description", lambda s: join_unique(s)),
        TRFX=("TRFX", "first"),
    ).reset_index()
    grouped["QTY_GEAV"] = grouped["QTY_GEAV"].astype(int)
    return grouped, sheet


# --------------------------------------------------------------------------
# CHARGEMENT FICHIER 1b — Besoin ASREQ/NOREQ (depuis XLSM)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_asreq_noreq(file_bytes):
    """Charge le fichier XLSM ASREQ/NOREQ depuis la feuille 'Ordered'.
    Colonnes attendues :
    - ID BARECODE (col 6) = TRFX
    - PN + infos pièce sortie (col 12) = PN
    - Qty (col 16) = Quantité
    Filtre : uniquement les équipements sous notre gestion (voir gestion_scope)
    """
    try:
        # Lire sans header pour trouver la ligne d'en-tête
        raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Ordered", engine="openpyxl", header=None, nrows=10)
        # En-tête est à la ligne 5 (index 5)
        df_raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Ordered", engine="openpyxl", header=5)
        df = _clean_cols(df_raw)
    except Exception as e:
        raise ValueError(f"Impossible de lire la feuille 'Ordered' du fichier ASREQ/NOREQ : {e}")
    
    # Colonnes attendues
    c_barecode = find_col(df, "id barecode")
    c_pn = find_col(df, "pn + infos", "pn")
    c_qty = find_col(df, "qty", exact=True)
    
    if c_pn is None or c_qty is None:
        raise ValueError(
            f"Impossible de trouver les colonnes 'PN + infos pièce sortie' / 'Qty' dans la feuille 'Ordered' "
            f"du fichier ASREQ/NOREQ. Colonnes détectées : {list(df.columns)}"
        )
    
    out = pd.DataFrame({
        "PN": pn_key(df[c_pn]),
        "Qty": pd.to_numeric(df[c_qty], errors="coerce").fillna(0),
        "TRFX": safe_str(df[c_barecode]) if c_barecode else np.nan,
    })
    out = out[out["PN"].notna()]
    
    grouped = out.groupby("PN").agg(
        QTY_GEAV=("Qty", "sum"),
        Nb_lignes=("Qty", "size"),
        TRFX=("TRFX", "first"),
    ).reset_index()
    grouped["QTY_GEAV"] = grouped["QTY_GEAV"].astype(int)
    return grouped, "Ordered"


# --------------------------------------------------------------------------
# CHARGEMENT FICHIER 2 — Résultat / État du stock (stock + gestion)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_stock(file_bytes):
    sheet, hdr = pick_sheet_and_header(file_bytes, ["pnr", "qte sur etagere"], prefer_sheet=None)  # nom de feuille retiré (CLAUDE.md §2)
    df = _clean_cols(pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=hdr))

    c_pnr = find_col(df, "pnr", exact=True) or find_col(df, "pnr")
    c_stock = find_col(df, "qte sur etagere")
    c_cde = find_col(df, "qte en cde")
    c_gestion = find_col(df, "gestion", exact=True) or find_col(df, "gestion")
    c_agent = find_col(df, "code agt appro")
    c_fourn = find_col(df, "code fournisseur")
    c_dernier_fourn = find_col(df, "dernier fournisseur")
    c_desc = find_col(df, "description")
    c_ccn = find_col(df, "ccn", exact=True)
    c_class = find_col(df, "class code", exact=True)

    if c_pnr is None or c_stock is None:
        raise ValueError(
            f"Impossible de trouver les colonnes 'PNR' / 'QTE SUR ÉTAGÈRE' dans la feuille "
            f"'{sheet}' du fichier Résultat. Colonnes détectées : {list(df.columns)}"
        )

    out = pd.DataFrame({
        "PN": pn_key(df[c_pnr]),
        "QTY_STOCK": pd.to_numeric(df[c_stock], errors="coerce").fillna(0) if c_stock else 0,
        "QTY_CDE": pd.to_numeric(df[c_cde], errors="coerce").fillna(0) if c_cde else 0,
        "GESTION": pd.to_numeric(df[c_gestion], errors="coerce") if c_gestion else np.nan,
        "CODE_AGENT": safe_str(df[c_agent]) if c_agent else np.nan,
        "CODE_FOURNISSEUR": safe_str(df[c_fourn]) if c_fourn else np.nan,
        "DERNIER_FOURNISSEUR": safe_str(df[c_dernier_fourn]) if c_dernier_fourn else np.nan,
        "Description_stock": df[c_desc] if c_desc else np.nan,
        "CCN": safe_str(df[c_ccn]).str.replace(r"\.0$", "", regex=True) if c_ccn else np.nan,
        "CLASS_CODE_STOCK": pd.to_numeric(df[c_class], errors="coerce") if c_class else np.nan,
    })
    out = out[out["PN"].notna()]
    # Un PNR est censé être unique dans ce fichier ; en cas de doublon on prend le max du stock/cde.
    grouped = out.groupby("PN").agg(
        QTY_STOCK=("QTY_STOCK", "max"),
        QTY_CDE=("QTY_CDE", "max"),
        GESTION=("GESTION", "first"),
        CODE_AGENT=("CODE_AGENT", "first"),
        CODE_FOURNISSEUR=("CODE_FOURNISSEUR", "first"),
        DERNIER_FOURNISSEUR=("DERNIER_FOURNISSEUR", "first"),
        Description_stock=("Description_stock", "first"),
        CCN=("CCN", "first"),
        CLASS_CODE_STOCK=("CLASS_CODE_STOCK", lambda s: s.isin([8.0, 9.0]).any() and s[s.isin([8.0, 9.0])].iloc[0]
                          or (s.dropna().iloc[0] if s.notna().any() else np.nan)),
    ).reset_index()
    return grouped, sheet


# --------------------------------------------------------------------------
# CHARGEMENT FICHIER 3 — Tableau de bord / "Toutes les commandes"
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_commandes(file_bytes):
    sheet, hdr = pick_sheet_and_header(
        file_bytes, ["pn", "code acheteur", "commande"], prefer_sheet="Toutes les commandes"
    )
    df = _clean_cols(pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet, header=hdr))
    df = df.dropna(axis=1, how="all")

    c_pn = find_col(df, "pn", exact=True)
    c_cmd = find_col(df, "commande", exact=True)
    c_acheteur = find_col(df, "code acheteur")
    c_gestion = find_col(df, "gestion", exact=True)
    c_fourn_code = find_col(df, "code fournisseur")
    c_fourn = find_col(df, "fournisseur", exact=True) or find_col(df, "fournisseur")
    c_psd = find_col(df, "date de livraison promise", "livraison promise")
    c_date_dem = find_col(df, "date de livraison demandee", "livraison demandee")
    c_statut = find_col(df, "statut de la commande", "statut")
    c_qty_restant = find_col(df, "quantite restant a livrer", "restant a livrer")
    c_class_code = find_col(df, "class code", "code classe")
    c_ccn = find_col(df, "ccn", exact=True)

    if c_pn is None:
        raise ValueError(
            f"Impossible de trouver la colonne 'PN' dans la feuille '{sheet}' du fichier "
            f"Tableau de bord. Colonnes détectées : {list(df.columns)}"
        )

    out = pd.DataFrame({"PN": pn_key(df[c_pn])})
    out["Commande"] = safe_str(df[c_cmd]) if c_cmd else np.nan
    out["Code_acheteur"] = safe_str(df[c_acheteur]) if c_acheteur else np.nan
    out["Gestion_cmd"] = pd.to_numeric(df[c_gestion], errors="coerce") if c_gestion else np.nan
    out["Code_fournisseur_cmd"] = safe_str(df[c_fourn_code]) if c_fourn_code else np.nan
    out["Fournisseur"] = safe_str(df[c_fourn]) if c_fourn else np.nan
    out["PSD"] = pd.to_datetime(df[c_psd], errors="coerce") if c_psd else pd.NaT
    out["Date_demandee"] = pd.to_datetime(df[c_date_dem], errors="coerce") if c_date_dem else pd.NaT
    out["Statut"] = safe_str(df[c_statut]) if c_statut else np.nan
    out["Qty_restant"] = pd.to_numeric(df[c_qty_restant], errors="coerce").fillna(0) if c_qty_restant else 0
    out["Class_code"] = pd.to_numeric(df[c_class_code], errors="coerce") if c_class_code else np.nan
    out["CCN_cmd"] = safe_str(df[c_ccn]).str.replace(r"\.0$", "", regex=True) if c_ccn else np.nan
    out = out[out["PN"].notna()]

    # Date de livraison "effective" utilisée pour le pilotage : la PSD si connue,
    # sinon la date demandée par défaut (à défaut d'engagement fournisseur confirmé).
    out["PSD_effective"] = out["PSD"].fillna(out["Date_demandee"])
    out["PSD_est_estimee"] = out["PSD"].isna() & out["Date_demandee"].notna()

    grouped = out.sort_values("PSD_effective").groupby("PN").agg(
        Commande=("Commande", join_unique),
        Code_acheteur=("Code_acheteur", lambda s: join_unique(s)),
        Gestion_cmd=("Gestion_cmd", "first"),  # Ajouter Gestion_cmd !
        Code_fournisseur_cmd=("Code_fournisseur_cmd", lambda s: join_unique(s)),
        Fournisseur=("Fournisseur", lambda s: join_unique(s)),
        PSD=("PSD_effective", "min"),          # date de livraison la plus proche (prochain arrivage)
        PSD_est_estimee=("PSD_est_estimee", "first"),
        Statut=("Statut", lambda s: join_unique(s)),
        Qty_restant_cmd=("Qty_restant", "sum"),
        Nb_commandes=("Commande", "nunique"),
        Class_code=("Class_code", lambda s: s.dropna().iloc[0] if len(s.dropna()) > 0 else np.nan),
        Has_risk_class=("Class_code", lambda s: any(s.isin([8.0, 9.0]))),
        CCN_cmd=("CCN_cmd", "first"),
    ).reset_index()
    return grouped, sheet


# --------------------------------------------------------------------------
# CROISEMENT & CALCUL DES ACTIONS
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def build_cross(besoin, stock, commandes, gestion_scope, geav_date):
    """Croise les trois fichiers et calcule l'action recommandée pour chaque pièce.
    
    Logique de calcul :
    - Deficit = max(0, QTY_GEAV - QTY_STOCK) : quantité manquante maintenant
    - Qty_a_commander = max(0, Deficit - QTY_CDE) : quantité à commander si pas couvert par CDE
    - Action classification : tenir compte de PSD vs geav_date pour prédire la disponibilité réelle
      au moment de la GEAV (consumption planning).
    """
    m = besoin.copy()
    m["GEAV_DATE"] = geav_date
    m["TRFX"] = m.get("TRFX", np.nan)
    
    m = m.merge(stock, on="PN", how="left")
    # Gestion : celle du Tableau de bord (GdC) fait foi, repli sur le fichier Stock
    gest_tdb = commandes[["PN", "Gestion_cmd"]].drop_duplicates("PN")
    m = m.merge(gest_tdb, on="PN", how="left")
    m["GESTION"] = m["Gestion_cmd"].where(m["Gestion_cmd"].notna(), m["GESTION"])
    m = m.drop(columns=["Gestion_cmd"])
    m["in_stock_file"] = m["QTY_STOCK"].notna() | m["QTY_CDE"].notna()
    for c in ["QTY_STOCK", "QTY_CDE"]:
        m[c] = m[c].fillna(0)
    gestion_scope_f = set(float(g) for g in gestion_scope)
    m["gestion_in_scope"] = m["GESTION"].isin(gestion_scope_f)

    m = m.merge(commandes.drop(columns=["Gestion_cmd"]), on="PN", how="left")
    m["Deficit"] = (m["QTY_GEAV"] - m["QTY_STOCK"]).clip(lower=0).astype(int)
    m["Qty_a_commander"] = (m["Deficit"] - m["QTY_CDE"]).clip(lower=0).astype(int)

    def fournisseur_row(r):
        if pd.notna(r.get("Fournisseur")) and str(r.get("Fournisseur")).strip():
            return r["Fournisseur"]
        if pd.notna(r.get("DERNIER_FOURNISSEUR")):
            return r["DERNIER_FOURNISSEUR"]
        return np.nan

    m["FOURNISSEUR"] = m.apply(fournisseur_row, axis=1)
    m["CODE_FOURNISSEUR"] = m["CODE_FOURNISSEUR"].where(m["CODE_FOURNISSEUR"].notna(), m["Code_fournisseur_cmd"])
    # Le code acheteur du fichier Commandes fait foi ; fallback à CODE AGT APPRO du fichier Stock
    m["CODE_ACHETEUR"] = m["Code_acheteur"].where(m["Code_acheteur"].notna(), m["CODE_AGENT"])

    # CCN : fichier Résultat en priorité, sinon Tableau de bord
    m["CCN"] = m["CCN"].where(m["CCN"].notna(), m["CCN_cmd"])
    # Class code : alerte si 8 ou 9 dans le TDB ou dans le fichier Résultat
    m["CLASS_CODE"] = m["Class_code"].where(m["Class_code"].isin([8.0, 9.0]), m["CLASS_CODE_STOCK"])
    m["CLASS_CODE"] = m["CLASS_CODE"].where(m["CLASS_CODE"].notna(), m["Class_code"])
    m["RISK_CLASS"] = m["CLASS_CODE"].isin([8.0, 9.0]) | m["Has_risk_class"].fillna(False).astype(bool)

    def statut_action(r):
        """Détermine l'action recommandée basée sur :
        - Disponibilité réelle en stock vs besoin
        - Dates de promesse de livraison (PSD) vs date GEAV
        - Périmètre de gestion
        """
        if not r["in_stock_file"]:
            return "❓ PN introuvable dans le fichier Stock (à vérifier manuellement)", "inconnu"
        
        agent = r["CODE_ACHETEUR"] if pd.notna(r["CODE_ACHETEUR"]) else "?"
        # Priorité : Fournisseur (tableau de bord) > CODE_FOURNISSEUR (stock/commandes) > "inconnu"
        if pd.notna(r["FOURNISSEUR"]) and str(r["FOURNISSEUR"]).strip():
            fourn = r["FOURNISSEUR"]
        elif pd.notna(r["CODE_FOURNISSEUR"]) and str(r["CODE_FOURNISSEUR"]).strip():
            fourn = r["CODE_FOURNISSEUR"]
        else:
            fourn = "fournisseur inconnu"
        psd = r["PSD"]
        geav_date = r["GEAV_DATE"]
        
        # Vérifier si PSD = 2031 (PSD non fournie par fournisseur, placeholder)
        psd_missing = pd.notna(psd) and psd.year == 2031
        
        # Vérifier si la date limite est respectée (PSD doit être avant ou égale à GEAV_DATE)
        psd_late = pd.notna(geav_date) and pd.notna(psd) and psd.normalize() > geav_date.normalize() and not psd_missing
        
        # Cas 1 : Hors périmètre gestion
        if not r["gestion_in_scope"]:
            g = "?" if pd.isna(r["GESTION"]) else int(r["GESTION"])
            return (f"⚠️ Besoin de {r['Deficit']} — Gestion {g} hors périmètre "
                    f"(contacter {agent})"), "hors_perimetre"
        
        # Cas 2 : Qty_a_commander > 0 : manque de quantité même avec CDE en cours
        if r["Qty_a_commander"] > 0:
            if r["QTY_CDE"] > 0:
                return (f"🔴 Commander le complément ({r['Qty_a_commander']}) + relancer {fourn} "
                        f"(contact: {agent})"), "commander"
            return (f"🔴 Commander {r['Qty_a_commander']} — aucune commande en cours "
                    f"(contact: {agent})"), "commander"
        
        # Cas 3 : Qty_a_commander == 0 mais déficit couvert par CDE
        # Vérifier si la PSD est à temps (consumption planning)
        if r["Deficit"] <= 0:
            # Stock suffisant maintenant, pas besoin de CDE
            return "🟢 Stock suffisant — aucune action", "ok"
        
        # Deficit > 0 mais couvert par CDE (Qty_a_commander == 0)
        if pd.isna(psd) or psd_missing:
            return (f"🟠 Relancer {fourn} — commande en cours, PSD manquante ou à confirmer "
                    f"(contact: {agent})"), "relancer"
        
        if psd_late:
            return (f"🔴 Relancer {fourn} — PSD {psd:%d/%m/%Y} après la date limite GEAV "
                    f"(contact: {agent})"), "relancer_urgent"
        
        return f"🔵 Livraison en cours — PSD {psd:%d/%m/%Y} ({fourn})", "en_cours"

    res = m.apply(lambda r: statut_action(r), axis=1)
    m["ACTION"] = res.apply(lambda t: t[0])
    m["ACTION_CODE"] = res.apply(lambda t: t[1])
    # Classe 8/9 : alerte ajoutée à l'action (PN critique, à traiter en priorité)
    risk_mask = m["RISK_CLASS"] & (m["ACTION_CODE"] != "inconnu")
    m.loc[risk_mask, "ACTION"] = "🚨 CLASSE 8/9 — PRIORITÉ : " + m.loc[risk_mask, "ACTION"]
    return m


ACTION_LABELS = {
    "commander": "🔴 À commander",
    "relancer_urgent": "🔴 Relance urgente (retard vs GEAV)",
    "relancer": "🟠 À relancer",
    "en_cours": "🔵 En cours de livraison",
    "ok": "🟢 Stock suffisant",
    "hors_perimetre": "⚠️ Hors périmètre gestion",
    "inconnu": "❓ PN introuvable",
}
ACTION_COLORS = {
    "commander": C["critique"], "relancer_urgent": C["critique"], "relancer": C["alerte"],
    "en_cours": C["accent"], "ok": C["ok"], "hors_perimetre": C["warn"], "inconnu": C["neutre"],
}
# Couleurs de surlignage (fond pastel) utilisées dans l'export Excel, alignées sur ACTION_COLORS.
ACTION_FILL_HEX = {
    "commander": "F8D7DA", "relancer_urgent": "F5B7B1", "relancer": "FCE4D6",
    "en_cours": "D6E4F0", "ok": "D9F2E6", "hors_perimetre": "FDF0D5", "inconnu": "E2E3E5",
}


def kpi_card(col, label, value, sub=None, color=None):
    cstyle = f"color:{color};" if color else ""
    subhtml = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    col.markdown(
        f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value" style="{cstyle}">{value}</div>{subhtml}</div>',
        unsafe_allow_html=True)


def to_excel_bytes(dfs, action_codes=None):
    """Écrit un dict {nom_feuille: DataFrame} dans un classeur Excel.
    `action_codes` est un dict optionnel {nom_feuille: Series de codes ACTION_CODE
    alignée sur l'index du DataFrame correspondant} : chaque ligne de la feuille est
    alors surlignée avec la couleur associée à son action (cf. ACTION_FILL_HEX)."""
    from openpyxl.styles import PatternFill

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as wr:
        for name, d in dfs.items():
            sheet_name = name[:31]
            d.to_excel(wr, sheet_name=sheet_name, index=False)
            codes = (action_codes or {}).get(name)
            if codes is None or d.empty:
                continue
            ws = wr.sheets[sheet_name]
            ncols = len(d.columns)
            for row_i, code in enumerate(codes.tolist(), start=2):  # ligne 1 = en-têtes
                hex_color = ACTION_FILL_HEX.get(code)
                if not hex_color:
                    continue
                fill = PatternFill(start_color=hex_color, end_color=hex_color, fill_type="solid")
                for col_i in range(1, ncols + 1):
                    ws.cell(row=row_i, column=col_i).fill = fill
    return buf.getvalue()


# --------------------------------------------------------------------------
# SIDEBAR
# --------------------------------------------------------------------------
st.sidebar.title("📥 Import des fichiers GEAV")
st.sidebar.caption("Les noms de fichiers peuvent varier (autre avion) : la détection des "
                   "colonnes/feuilles se fait automatiquement par mots-clés.")

# Choix du type d'étude
etude_type = st.sidebar.radio(
    "📋 Type d'étude",
    options=["Classique", "ASREQ/NOREQ"],
    help="Choisir le type d'analyse à effectuer. Les fichiers 'Tableau de bord' et 'Résultat' sont communs."
)

if etude_type == "Classique":
    f_besoin = st.sidebar.file_uploader("1) Besoin GEAV (Qty / MPN Prime)", type=["xlsx"], key="besoin_classique")
    f_besoin_asreq = None
else:
    f_besoin = None
    f_besoin_asreq = st.sidebar.file_uploader("1) Étude ASREQ/NOREQ (fichier XLSM 'Ordered')", 
                                              type=["xlsm"], key="besoin_asreq")

f_stock = st.sidebar.file_uploader("2) Résultat — stock (PNR / QTE SUR ÉTAGÈRE)", type=["xlsx"])
f_cmd = st.sidebar.file_uploader("3) Tableau de bord — commandes (PN / Commande)", type=["xlsx"])

st.sidebar.divider()
gestion_scope = st.sidebar.multiselect(
    "Codes Gestion à croiser avec les commandes",
    options=sorted(set(DEFAULT_GESTIONS) | {230, 245, 246, 247, 251, 256, 300, 375, 400, 401, 443, 487, 500}),
    default=DEFAULT_GESTIONS,
    help="Le croisement avec le fichier 'Commandes' n'est fait que pour ces codes de gestion. "
         "Les autres codes sont signalés comme hors périmètre.")
geav_date = pd.Timestamp(st.sidebar.date_input("📅 Date de la GEAV", value=TODAY.date(),
                                                help="Date de la Grand Entretien Avion — utilisée pour évaluer "
                                                     "si les commandes en cours arriveront à temps."))

st.sidebar.divider()
st.sidebar.markdown("**Légende des actions**")
for code, label in ACTION_LABELS.items():
    st.sidebar.markdown(f"- {label}")

# --------------------------------------------------------------------------
# CORPS
# --------------------------------------------------------------------------
st.title("✈️ GEAV — Croisement Besoin / Stock / Commandes")

# Vérifier les fichiers requis selon le type d'étude
if etude_type == "Classique":
    files_ok = f_besoin and f_stock and f_cmd
    besoin_file = f_besoin
else:
    files_ok = f_besoin_asreq and f_stock and f_cmd
    besoin_file = f_besoin_asreq

if not files_ok:
    col1, col2 = st.columns([2, 1])
    with col1:
        if etude_type == "Classique":
            st.info(
                "⬅️ **Importez les trois fichiers requis** dans la barre latérale pour lancer l'analyse :\n\n"
                "1. **Besoin GEAV** — feuille avec colonnes Qty et MPN Prime\n"
                "2. **Résultat / Stock** — feuille État du stock avec PNR, QTE SUR ÉTAGÈRE, QTE EN CDE, GESTION\n"
                "3. **Tableau de bord** — feuille 'Toutes les commandes' avec PN, commandes, dates de livraison"
            )
        else:
            st.info(
                "⬅️ **Importez les trois fichiers requis** dans la barre latérale pour lancer l'analyse :\n\n"
                "1. **Étude ASREQ/NOREQ** — fichier XLSM avec feuille 'Ordered' (colonnes : ID BARECODE, PN, Qty)\n"
                "2. **Résultat / Stock** — feuille État du stock avec PNR, QTE SUR ÉTAGÈRE, QTE EN CDE, GESTION\n"
                "3. **Tableau de bord** — feuille 'Toutes les commandes' avec PN, commandes, dates de livraison"
            )
    st.stop()

try:
    if etude_type == "Classique":
        besoin, sheet1 = load_besoin(besoin_file.getvalue())
        etude_label = "Étude Classique"
    else:
        besoin, sheet1 = load_asreq_noreq(besoin_file.getvalue())
        etude_label = "Étude ASREQ/NOREQ"
    
    stock, sheet2 = load_stock(f_stock.getvalue())
    commandes, sheet3 = load_commandes(f_cmd.getvalue())
except ValueError as e:
    st.error(str(e))
    st.stop()

st.caption(f"Analyse du {TODAY:%d/%m/%Y} — {etude_label} · sécurisation des équipements pour la Grand Entretien Avion")

st.caption(f"{etude_label} — Feuilles détectées → Besoin: **{sheet1}** · Stock: **{sheet2}** · Commandes: **{sheet3}**")

# Assurer que stock a toujours la colonne GESTION (sinon créer avec NaN)
if 'GESTION' not in stock.columns:
    stock['GESTION'] = np.nan

M = build_cross(besoin, stock, commandes, gestion_scope, geav_date)

# Seules les références dont le code Gestion fait partie du périmètre sélectionné
# entrent dans le tableau croisé principal et les KPIs. Le reste (hors périmètre /
# PN introuvable dans le fichier stock) est disponible en annexe tout en bas.
M_scope = M[M["gestion_in_scope"]].copy()
M_hors_scope = M[~M["gestion_in_scope"]].copy()

# ---- Alerte sur les codes de classe risqués ----
risk_refs = M_scope[M_scope["RISK_CLASS"]]
if len(risk_refs) > 0:
    st.warning(
        f"⚠️ **Alerte : {len(risk_refs)} référence(s) avec classe code 8 ou 9 détectée(s) !**\n\n"
        f"Ces pièces sont critiques. Vérifier les délais de livraison et les stocks en priorité. "
        f"Pièces concernées : {', '.join(risk_refs['PN'].unique()[:5])}"
        f"{'...' if len(risk_refs['PN'].unique()) > 5 else ''}"
    )

# ---- KPIs (uniquement sur le périmètre de gestion sélectionné) ----
n_total = len(M_scope)
n_commander = (M_scope["ACTION_CODE"] == "commander").sum()
n_relance = M_scope["ACTION_CODE"].isin(["relancer", "relancer_urgent"]).sum()
n_encours = (M_scope["ACTION_CODE"] == "en_cours").sum()
n_ok = (M_scope["ACTION_CODE"] == "ok").sum()
qty_total_a_commander = int(M_scope.loc[M_scope["ACTION_CODE"] == "commander", "Qty_a_commander"].sum())

c1, c2, c3, c4, c5 = st.columns(5)
kpi_card(c1, "Références GEAV (périmètre)", n_total)
kpi_card(c2, "À commander", n_commander, f"{qty_total_a_commander} unités", C["critique"])
kpi_card(c3, "À relancer", n_relance, color=C["alerte"])
kpi_card(c4, "En cours de livraison", n_encours, color=C["accent"])
kpi_card(c5, "Stock suffisant", n_ok, color=C["ok"])

st.divider()

# ---- Définition des colonnes à afficher ----
display_cols = {
    "PN": "PN",
    "CCN": "CCN",
    "TRFX": "TRFX",
    "QTY_GEAV": "QTY GEAV",
    "QTY_STOCK": "QTY en stock",
    "QTY_CDE": "QTY en cmd",
    "CODE_ACHETEUR": "Code acheteur",
    "GESTION": "Gestion",
    "CLASS_CODE": "Class code",
    "Commande": "N° Commande",
    "PSD": "PSD",
    "CODE_FOURNISSEUR": "Code fournisseur",
    "FOURNISSEUR": "Fournisseur",
    "GEAV_DATE": "Date GEAV",
    "Qty_a_commander": "QTY à commander",
    "ACTION": "Action",
}

# ---- Onglets : Indicateurs, Tableau croisé, Annexe ----
tab1, tab2, tab3 = st.tabs(["📊 Indicateurs", "📋 Tableau croisé", "📎 Annexe"])

# ========== TAB 1: INDICATEURS ==========
with tab1:
    st.markdown("### Vue d'ensemble des actions requises")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("À commander", n_commander, f"{qty_total_a_commander} unités")
    with col2:
        st.metric("À relancer", n_relance)
    with col3:
        st.metric("En cours", n_encours)
    with col4:
        st.metric("Stock OK", n_ok)
    
    st.divider()
    
    # ---- Graphique Plotly : Actions requises ----
    actions_data = [
        {"action": "À commander", "count": (M_scope["ACTION_CODE"] == "commander").sum(), "color": C["critique"]},
        {"action": "À relancer (urgent)", "count": (M_scope["ACTION_CODE"] == "relancer_urgent").sum(), "color": C["alerte"]},
        {"action": "À relancer", "count": (M_scope["ACTION_CODE"] == "relancer").sum(), "color": "#FF9500"},
        {"action": "Livraison en cours", "count": (M_scope["ACTION_CODE"] == "en_cours").sum(), "color": C["accent"]},
        {"action": "Stock suffisant", "count": (M_scope["ACTION_CODE"] == "ok").sum(), "color": C["ok"]},
        {"action": "Hors périmètre", "count": (M_scope["ACTION_CODE"] == "hors_perimetre").sum(), "color": "#A0A0A0"},
        {"action": "PN introuvable", "count": (M_scope["ACTION_CODE"] == "inconnu").sum(), "color": C["neutre"]},
    ]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[a["action"] for a in actions_data],
        y=[a["count"] for a in actions_data],
        marker=dict(color=[a["color"] for a in actions_data]),
        text=[a["count"] for a in actions_data],
        textposition="auto",
        hovertemplate="<b>%{x}</b><br>Références: %{y}<extra></extra>",
    ))
    
    fig.update_layout(
        title="Distribution des actions requises",
        xaxis_title="Action",
        yaxis_title="Nombre de références",
        height=400,
        margin=dict(l=50, r=50, t=80, b=100),
        font=dict(family="Poppins, sans-serif", size=12),
        plot_bgcolor="#F5F7FA",
        paper_bgcolor="#F5F7FA",
        xaxis_tickangle=-45,
        showlegend=False,
    )
    
    st.plotly_chart(fig, use_container_width=True)

# ========== TAB 2: TABLEAU CROISÉ ==========
with tab2:
    # Filtres tableau
    fc1, fc2, fc3 = st.columns([2, 2, 1])
    with fc1:
        search = st.text_input("🔎 Rechercher un PN")
    with fc2:
        action_filter = st.multiselect("Filtrer par action", options=list(ACTION_LABELS.keys()),
                                       format_func=lambda k: ACTION_LABELS[k], default=[])
    with fc3:
        expand_btn = st.checkbox("⛶ Plein écran", value=False)
    
    view = M_scope.copy()
    if search:
        view = view[view["PN"].str.contains(search.strip().upper(), na=False)]
    if action_filter:
        view = view[view["ACTION_CODE"].isin(action_filter)]
    
    table = view[list(display_cols.keys())].rename(columns=display_cols).sort_values(
        by="QTY à commander", ascending=False)
    
    st.markdown(f"**{len(table)} référence(s)** correspondant aux critères — "
                f"Codes Gestion : {sorted(int(g) for g in gestion_scope)}")
    
    # Hauteur dynamique basée sur fullscreen
    df_height = 600 if expand_btn else 400
    
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        height=df_height,
        column_config={
            "PSD": st.column_config.DatetimeColumn("PSD", format="DD/MM/YYYY"),
            "Date GEAV": st.column_config.DatetimeColumn("Date GEAV", format="DD/MM/YYYY"),
            "Gestion": st.column_config.NumberColumn("Gestion", format="%d"),
        },
    )
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.download_button(
            "⬇️ Exporter le tableau (Excel)",
            data=to_excel_bytes(
                {"Croisement GEAV": table, "Détail complet": M_scope},
                action_codes={
                    "Croisement GEAV": view.loc[table.index, "ACTION_CODE"],
                    "Détail complet": M_scope["ACTION_CODE"],
                },
            ),
            file_name=f"Croisement_GEAV_{TODAY:%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    with col2:
        st.caption(f"📥 Excel avec surlignage par action")
    
    with st.expander("ℹ️ Colonnes détaillées"):
        st.dataframe(M_scope, use_container_width=True, hide_index=True)

# ========== TAB 3: ANNEXE ==========
with tab3:
    st.markdown(f"### Toutes les références ({len(M)} au total)")
    st.caption("Inclut codes Gestion non sélectionnés et PN introuvables dans le fichier Stock")
    
    annex_table = M[list(display_cols.keys())].rename(columns=display_cols).sort_values(
        by="QTY à commander", ascending=False)
    
    st.dataframe(
        annex_table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "PSD": st.column_config.DatetimeColumn("PSD", format="DD/MM/YYYY"),
            "Date GEAV": st.column_config.DatetimeColumn("Date GEAV", format="DD/MM/YYYY"),
            "Gestion": st.column_config.NumberColumn("Gestion", format="%d"),
        },
    )

# --------------------------------------------------------------------------
# DOCUMENTATION
# --------------------------------------------------------------------------
st.divider()

with st.expander("📖 **Documentation complète du fonctionnement de l'outil**", expanded=False):
    st.markdown("""
### 📊 Vue d'ensemble de l'analyse
Cet outil croise **trois fichiers Excel** pour identifier quelles pièces doivent être commandées 
ou relancées avant la date de la Grand Entretien Avion (GEAV), et lesquelles ont un stock suffisant.

---

### 📁 Fichiers d'entrée requis

#### 1️⃣ **Fichier Besoin GEAV** — *Quantités requises par pièce*
- **Source** : Cahier des charges de la maintenance
- **Colonnes essentielles** :
  - `MPN Prime` : Référence fabricant de la pièce (clé de croisement)
  - `Qty` : Quantité requise pour la GEAV
  - `Task Name` / `Task WP Line` (optionnel) : Code TRFX (traçabilité du travail)
  - `Description` (optionnel) : Description de la pièce
- **Traitement** : 
  - Les doublons (même MPN) sont **agrégés par somme** (cas courant : plusieurs pièces commandées)
  - Exemple : si le même MPN apparaît 3 fois avec Qty = 2, 3, 1 → QTY_GEAV = 6

---

#### 2️⃣ **Fichier Résultat / Stock** (feuille État du stock) — *État du stock actuel*
- **Source** : Système de gestion des stocks (outil d'optimisation du stock)
- **Colonnes essentielles** :
  - `PNR` : Référence pièce en stock (clé de croisement, normalisée vers PN)
  - `QTE SUR ÉTAGÈRE` : Quantité disponible immédiatement
  - `QTE EN CDE` : Quantité déjà commandée mais pas encore livrée
  - `GESTION` : Code de gestion (245, 246, 247, 400, 401, 230, etc.)
  - `CODE AGT APPRO` : Code agent approvisionneur (contact par défaut)
  - `CODE FOURNISSEUR` (optionnel) : Code du dernier fournisseur utilisé
- **Traitement** :
  - Les doublons sont résolus en prenant le **max** du stock/CDE (cas courant : mise à jour partielle)
  - Un PNR peut correspondre à plusieurs PN normalisés → merge par clé normalisée

---

#### 3️⃣ **Fichier Tableau de bord** (feuille "Toutes les commandes") — *Historique des commandes*
- **Source** : Système de suivi des achats
- **Colonnes essentielles** :
  - `PN` : Référence pièce (clé de croisement)
  - `Commande` : Numéro de commande
  - `Code acheteur` : Personne qui a passé la commande
  - `Date de livraison promise` (PSD) : Date d'arrivage engagée par le fournisseur
  - `Date de livraison demandée` (fallback) : Date souhaitée si PSD inconnue
  - `Statut` (optionnel) : État de la commande (En cours, Livrée, Annulée, etc.)
  - `Quantité restant à livrer` (optionnel) : Qty déjà livrée ≠ Qty commandée
  - `Class code` (optionnel) : Classification de risque (8, 9 = critique)
- **Traitement** :
  - Groupement par PN, sélection de la **date de livraison la plus proche** (prochain arrivage)
  - Concat unique des numéros de commande (si plusieurs pour le même PN)
  - **Alerte** si Class_code ∈ {8, 9} détecté

---

### 🔢 Variables de calcul

| Variable | Formule | Signification |
|----------|---------|---------------|
| **Deficit** | `max(0, QTY_GEAV - QTY_STOCK)` | Quantité manquante maintenant en stock |
| **Qty_a_commander** | `max(0, Deficit - QTY_CDE)` | Quantité supplémentaire à commander (non couverte par CDE) |
| **Qty_couvert_par_cde** | `min(Deficit, QTY_CDE)` | Quantité du déficit couverte par une commande en cours |

**Exemple** :
- QTY_GEAV = 10, QTY_STOCK = 3, QTY_CDE = 5
- Deficit = max(0, 10 - 3) = 7
- Qty_a_commander = max(0, 7 - 5) = 2 ← **À commander !**

---

### 🎯 Logique de classification des actions

L'outil évalue chaque pièce et recommande une **action** selon le contexte :

#### 🟢 **"Stock suffisant"** — Aucune action
- **Condition** : `Deficit ≤ 0` (c'est-à-dire QTY_STOCK ≥ QTY_GEAV)
- **Signification** : Le stock actuel couvre entièrement le besoin
- **Action requise** : ✅ Aucune

#### 🟡 **"À commander"** — Commande manquante
- **Condition** : `Qty_a_commander > 0` (manque de quantité même avec CDE)
- **Variantes** :
  - **Avec CDE existant** : `Qty_a_commander > 0 ET QTY_CDE > 0`
    - Signification : Il faut commander le complément en plus de la CDE en cours
    - Message : 🔴 *Commander le complément (X unités) + relancer le fournisseur*
  - **Sans CDE** : `Qty_a_commander > 0 ET QTY_CDE = 0`
    - Signification : Aucune commande n'existe, il faut en lancer une
    - Message : 🔴 *Commander X unités — aucune commande en cours*
- **Action requise** : 📧 Contacter le Code acheteur → lancer une nouvelle commande

#### 🟠 **"À relancer"** — Commande en cours mais PSD inconnue
- **Condition** : `Qty_a_commander = 0 ET PSD = NULL`
- **Signification** : Le déficit est couvert par une CDE, mais on ignore quand elle arrivera
- **Risque** : Impossible de prédire si la pièce arrivera à temps pour la GEAV
- **Action requise** : ☎️ Relancer le fournisseur pour confirmer la PSD

#### 🔴 **"Relance urgente"** — Commande en retard vs GEAV
- **Condition** : `Qty_a_commander = 0 ET PSD > DATE_GEAV`
- **Signification** : La pièce arrivera APRÈS la date de GEAV (consommation / indisponibilité)
- **Risque** : La pièce ne sera pas disponible au moment de la maintenance
- **Action requise** : 🚨 Relancer d'urgence le fournisseur pour avancer la PSD

#### 🔵 **"Livraison en cours"** — Situation nominale
- **Condition** : `Qty_a_commander = 0 ET PSD ≤ DATE_GEAV ET PSD ≠ NULL`
- **Signification** : Le besoin est couvert par une commande qui arrivera à temps
- **Action requise** : ✅ Aucune, suivi de la livraison (vérifier que la PSD est respectée)

#### ⚠️ **"Hors périmètre gestion"** — Codes Gestion non gérés
- **Condition** : `GESTION ∉ {codes sélectionnés}`
- **Signification** : La pièce ne fait pas partie des codes Gestion à traiter (ex: code 300 = pièces de réserve)
- **Exemple** : Code Gestion = 375, mais périmètre sélectionné = {245, 246, 247, 400, 401}
- **Action requise** : 👤 Contacter l'agent approvisionneur (CODE AGT APPRO) pour confirmation

#### ❓ **"PN introuvable"** — Absence de données de stock
- **Condition** : Le PN du Besoin n'existe pas dans le fichier Stock
- **Signification** : Impossible d'évaluer le stock ou les commandes (données manquantes)
- **Risque** : Pièce peut être en rupture de stock sans le savoir
- **Action requise** : 🔍 Vérifier manuellement le PN dans le système (erreur de saisie ? pièce obsolète ?)

---

### 🔗 Logique de croisement (Merge)

L'outil effectue une **fusion progressive LEFT JOIN** :

1. **Croisement 1** : Besoin + Stock (clé = PN normalisé)
   - Conserve TOUS les PN du Besoin
   - Complète avec stock/CDE si dispo
   - Marque `in_stock_file = False` si PN absent du Stock

2. **Croisement 2** : Résultat + Commandes (clé = PN normalisé)
   - Conserve TOUS les PN précédents
   - Ajoute infos commande (N° cmd, PSD, Code acheteur) si disponible
   - Permet de détecter les pièces sans aucune commande

3. **Filtrage par périmètre** :
   - Affichage principal : uniquement codes Gestion ∈ périmètre sélectionné
   - Annexe : toutes les pièces (y compris hors périmètre + PN introuvables)

---

### ⚙️ Paramètres utilisateur

#### **Date de la GEAV** 📅
- **Usage** : Utilisée pour comparer avec la PSD (Date de livraison Promise)
- **Logique** :
  - Si PSD ≤ DATE_GEAV → ✅ Pièce arrivera à temps → "En cours de livraison"
  - Si PSD > DATE_GEAV → 🔴 Pièce arrivera trop tard → "Relance urgente"

#### **Codes Gestion à analyser** 🏷️
- **Usage** : Restreindre l'analyse à certains types de pièces (ex: pièces critiques vs stock de réserve)
- **Défaut** : {245, 246, 247, 400, 401, 230}
- **Étendu** : {230, 245, 246, 247, 251, 256, 300, 375, 400, 401, 443, 487, 500}
- Les pièces hors périmètre sélectionné n'apparaissent que dans l'annexe

---

### 📊 Indicateurs clés (KPI)

Les cartes en haut affichent les **statistiques du périmètre sélectionné** :

- **Références GEAV (périmètre)** : Total des pièces à analyser
- **À commander** : Nombre de pièces manquantes + quantité totale à commander
- **À relancer** : Commandes en cours sans PSD ou avec retard
- **En cours de livraison** : Commandes nominales arrivant à temps
- **Stock suffisant** : Aucune action requise

---

### 🎨 Surlignage dans l'export Excel

Le fichier Excel exporté utilise des **couleurs de fond** pour rapidement repérer les urgences :

| Couleur | Signification | Codes ACTION |
|---------|---------------|--------------|
| 🔴 Rouge | Urgence critique | "commander", "relancer_urgent" |
| 🟠 Orange | Attention | "relancer" |
| 🔵 Bleu | Suivi normal | "en_cours" |
| 🟢 Vert | Stock OK | "ok" |
| 🟡 Jaune | Hors périmètre | "hors_perimetre" |
| ⚫ Gris | Données manquantes | "inconnu" |

---

### ⚠️ Pièges et cas limites

#### 1. **Doublons dans le fichier Besoin**
- **Problème** : Le même PN apparaît plusieurs fois (ex: pièce commandée en deux lots)
- **Traitement** : Les Qty sont **sommées** (QTY_GEAV = 2 + 3 + 1 = 6)
- **Besoin** : Vérifier que c'est intentionnel (vs erreur de saisie)

#### 2. **PSD manquante**
- **Problème** : Une commande existe mais sans date de promesse enregistrée
- **Traitement** : Fallback à "Date de livraison demandée"
- **Fallback échoue** : ~15% des commandes → Action = "À relancer"

#### 3. **Class code 8/9**
- **Problème** : Pièces classées comme critiques (risque haut)
- **Traitement** : 🚨 Alerte en haut du tableau, besoin de surveillance accrue
- **Source** : Colonne "Class code" du fichier "Toutes les commandes"

#### 4. **PN normalisé vs original**
- **Normalisation** : Uppercase + sans espaces (ex: "abc 123" → "ABC123")
- **Avantage** : Gère les variations mineures (majuscules, espaces)
- **Limitation** : Ne réconcilie pas les vrais doublons (ex: code interne ≠ code fabricant)

#### 5. **Dates manquantes (NaT)**
- **Affichage** : Colonne vide ou "NaT"
- **Impact** : Logique de classification passe à l'action suivante
- **Exemple** : Pas de PSD + pas de "Date demandée" → "À relancer"

---

### 📤 Export Excel

Le bouton **"⬇️ Exporter le tableau"** génère un fichier `.xlsx` avec deux feuilles :

1. **"Croisement GEAV"** : Tableau filtré (uniquement périmètre sélectionné)
2. **"Détail complet"** : Toutes les colonnes de M_scope (pour vérifications)

Chaque ligne est **surlignée** selon son ACTION_CODE (cf. tableau des couleurs ci-dessus).

---

### 🛠️ Limitations et améliorations futures

- **Pas de prévision de consommation** : On ne tient pas compte du taux d'usage des pièces
- **Pas de saisonnalité** : Tous les délais fournisseurs sont égaux
- **Pas de regroupement de commandes** : Les pièces sont traitées indépendamment
- **Pas d'optimisation coût** : On ne compare pas les prix entre fournisseurs

---

### 📞 Support

En cas de problème :
1. Vérifier que les **trois fichiers** sont au bon format (Excel .xlsx)
2. Vérifier que les **noms de colonnes** sont présents (détection par mots-clés)
3. Consulter la section "Détails / colonnes non affichées" pour déboguer

    """)

