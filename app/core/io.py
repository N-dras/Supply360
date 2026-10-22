"""Lecture des fichiers importés, normalisation / validation des colonnes, export Excel.

Aucune dépendance à Streamlit : tout est testable avec pytest. Les fichiers arrivent
sous forme d'octets (`UploadedFile.getvalue()`), jamais via un chemin.
"""

import io
import re
import unicodedata
from datetime import date

import numpy as np
import pandas as pd

NAVY_HEX = "002157"


class ColonneIntrouvable(ValueError):
    """Erreur métier lisible : une colonne attendue manque dans un fichier importé."""

    def __init__(self, libelle: str, fichier: str, feuille: str | None = None, colonnes=None):
        msg = f"Colonne « {libelle} » introuvable dans le fichier {fichier}"
        msg += f" (feuille « {feuille} »)." if feuille else "."
        if colonnes is not None:
            msg += " Colonnes détectées : " + ", ".join(str(c) for c in colonnes)
        super().__init__(msg)


class FichierIllisible(ValueError):
    """Le fichier importé ne peut pas être lu (format, feuille absente…)."""


# --------------------------------------------------------------------------
# Normalisation des en-têtes et recherche de colonnes
# --------------------------------------------------------------------------
def normaliser(s) -> str:
    """Minuscules, sans accents, espaces → `_` (« Qté sur\\nÉtagère » → « qte_sur_etagere »)."""
    s = str(s).replace("\n", " ").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", "_", s).strip("_").lower()


def nettoyer_entetes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    return df


def trouver_colonne(df: pd.DataFrame, *alias: str, exact: bool = False):
    """Renvoie la première colonne dont le nom normalisé correspond à un alias.

    Correspondance exacte d'abord, puis partielle (alias contenu dans le nom) sauf si
    `exact=True`. Renvoie None si rien ne correspond.
    """
    noms = {c: normaliser(c) for c in df.columns}
    cibles = [normaliser(a) for a in alias]
    for col, n in noms.items():
        if n in cibles:
            return col
    if exact:
        return None
    for col, n in noms.items():
        for cible in cibles:
            if cible in n:
                return col
    return None


def trouver_ligne_entete(raw: pd.DataFrame, mots_cles, max_scan: int = 15):
    """Indice de la ligne d'en-tête (feuille lue sans header) contenant tous les mots-clés."""
    cles = [normaliser(m) for m in mots_cles]
    for i in range(min(max_scan, len(raw))):
        cellules = [normaliser(v) for v in raw.iloc[i].tolist()]
        jointes = "|".join(cellules)
        if all(any(m in c for c in cellules) or m in jointes for m in cles):
            return i
    return None


# --------------------------------------------------------------------------
# Ouverture des classeurs
# --------------------------------------------------------------------------
def ouvrir_excel(data: bytes, fichier: str) -> pd.ExcelFile:
    try:
        return pd.ExcelFile(io.BytesIO(data), engine="openpyxl")
    except Exception as exc:  # format non Excel, fichier corrompu ou protégé
        raise FichierIllisible(
            f"Le fichier {fichier} n'a pas pu être ouvert comme classeur Excel ({exc})."
        ) from exc


def choisir_feuille(xl: pd.ExcelFile, mots_cles, feuille_preferee: str | None = None):
    """(nom_feuille, ligne_entete) de la feuille contenant les colonnes attendues.

    La feuille dont le nom contient `feuille_preferee` est testée en premier ; à défaut
    on renvoie la première feuille avec l'en-tête en ligne 0.
    """
    feuilles = list(xl.sheet_names)
    if feuille_preferee:
        cible = normaliser(feuille_preferee)
        feuilles.sort(key=lambda s: 0 if cible in normaliser(s) else 1)
    for s in feuilles:
        try:
            raw = xl.parse(s, header=None, nrows=15)
        except Exception:
            continue
        h = trouver_ligne_entete(raw, mots_cles)
        if h is not None:
            return s, h
    return xl.sheet_names[0], 0


def lire_feuille(xl: pd.ExcelFile, feuille: str, entete: int) -> pd.DataFrame:
    """Lit une feuille en conservant les types bruts d'Excel (dtype=object) :
    un PN numérique reste un entier (pas de « 12345.0 »)."""
    return nettoyer_entetes(xl.parse(feuille, header=entete, dtype=object))


# --------------------------------------------------------------------------
# Typage explicite
# --------------------------------------------------------------------------
def _sans_decimale(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def cle_pn(serie: pd.Series) -> pd.Series:
    """Référence pièce en texte pour les jointures : majuscules, espaces de bord retirés.

    Les zéros en tête sont conservés s'ils sont saisis en texte dans Excel.
    """
    s = serie.map(_sans_decimale, na_action="ignore")
    s = s.map(str, na_action="ignore").str.strip().str.upper()
    return s.where(~s.isin(["", "NAN", "NONE", "NAT"]), np.nan).astype(object)


def texte(serie: pd.Series) -> pd.Series:
    """Texte nettoyé, valeurs vides → NaN (évite la chaîne « nan »)."""
    s = serie.map(_sans_decimale, na_action="ignore").map(str, na_action="ignore").str.strip()
    return s.where(s.notna() & (s != ""), np.nan).astype(object)


def nombre(serie: pd.Series, defaut=None) -> pd.Series:
    s = pd.to_numeric(serie, errors="coerce")
    return s.fillna(defaut) if defaut is not None else s


def dates(serie: pd.Series) -> pd.Series:
    """Dates Excel ou texte JJ/MM/AAAA → datetime64 (NaT si invalide)."""
    return pd.to_datetime(serie, errors="coerce", dayfirst=True, format="mixed")


# --------------------------------------------------------------------------
# Export Excel
# --------------------------------------------------------------------------
def nom_export(tab_id: str, jour: date | None = None) -> str:
    jour = jour or date.today()
    return f"Supply360_{tab_id}_{jour:%Y%m%d}.xlsx"


def exporter_excel(feuilles: dict, couleurs_lignes: dict | None = None) -> bytes:
    """Écrit {nom_feuille: DataFrame} dans un classeur mis en forme.

    En-têtes en gras sur fond bleu marine, volets figés, filtres automatiques, largeurs
    ajustées, dates au format JJ/MM/AAAA. `couleurs_lignes` = {nom_feuille: liste de
    couleurs hexa (ou None) alignée sur les lignes} pour surligner certaines lignes.
    """
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    entete_fill = PatternFill("solid", start_color=NAVY_HEX, end_color=NAVY_HEX)
    entete_font = Font(bold=True, color="FFFFFF")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as wr:
        for nom, df in feuilles.items():
            onglet = nom[:31]
            df = df.copy()
            col_dates = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
            df.to_excel(wr, sheet_name=onglet, index=False)
            ws = wr.sheets[onglet]
            nrows, ncols = len(df), len(df.columns)

            for j in range(1, ncols + 1):
                cell = ws.cell(row=1, column=j)
                cell.fill, cell.font = entete_fill, entete_font
                cell.alignment = Alignment(vertical="center", wrap_text=True)
            ws.freeze_panes = "A2"
            if ncols and nrows:
                ws.auto_filter.ref = f"A1:{get_column_letter(ncols)}{nrows + 1}"

            for j, col in enumerate(df.columns, start=1):
                echantillon = df[col].head(500)
                if col in col_dates:
                    largeur = 12
                    for i in range(2, nrows + 2):
                        ws.cell(row=i, column=j).number_format = "DD/MM/YYYY"
                else:
                    longueurs = echantillon.map(lambda v: len(str(v)) if pd.notna(v) else 0)
                    largeur = int(longueurs.max()) if nrows else 0
                largeur = max(largeur, len(str(col))) + 2
                ws.column_dimensions[get_column_letter(j)].width = min(max(largeur, 8), 60)

            couleurs = (couleurs_lignes or {}).get(nom)
            if couleurs is not None and nrows:
                fills = {}
                for i, hexa in enumerate(couleurs, start=2):
                    if not hexa:
                        continue
                    fill = fills.setdefault(hexa, PatternFill("solid", start_color=hexa, end_color=hexa))
                    for j in range(1, ncols + 1):
                        ws.cell(row=i, column=j).fill = fill
    return buf.getvalue()


# --------------------------------------------------------------------------
# Lecture des sources (une ligne par ligne de fichier, colonnes normalisées)
# --------------------------------------------------------------------------
FICHIER_BESOINS = "Besoins chantier (LOGOPS)"
FICHIER_ASREQ = "Étude ASREQ/NOREQ"
FICHIER_STOCK = "État du stock"
FICHIER_COMMANDES = "Commandes (SAP)"


def lire_besoins_geav(data: bytes):
    """Besoins chantier « classiques » (colonnes MPN Prime / Qty). Renvoie (lignes, feuille)."""
    xl = ouvrir_excel(data, FICHIER_BESOINS)
    feuille, entete = choisir_feuille(xl, ["mpn prime", "qty"], feuille_preferee="PartRequirements")
    df = lire_feuille(xl, feuille, entete)

    c_pn = trouver_colonne(df, "mpn prime", exact=True) or trouver_colonne(df, "mpn prime")
    c_qty = trouver_colonne(df, "qty", exact=True) or trouver_colonne(df, "quantite", "quantity")
    c_desc = trouver_colonne(df, "description")
    c_task = trouver_colonne(df, "task trfx", exact=True) or trouver_colonne(
        df, "task trfx", "task name", "task wp line", "trfx")
    if c_pn is None:
        raise ColonneIntrouvable("MPN Prime", FICHIER_BESOINS, feuille, df.columns)
    if c_qty is None:
        raise ColonneIntrouvable("Qty", FICHIER_BESOINS, feuille, df.columns)

    out = pd.DataFrame({
        "PN": cle_pn(df[c_pn]),
        "Qty": nombre(df[c_qty], 0),
        "Description": df[c_desc] if c_desc else np.nan,
        "TRFX": texte(df[c_task]) if c_task else np.nan,
    })
    return out[out["PN"].notna()], feuille


def lire_besoins_asreq(data: bytes):
    """Étude ASREQ/NOREQ (classeur .xlsm, feuille « Ordered », en-tête en ligne 6)."""
    xl = ouvrir_excel(data, FICHIER_ASREQ)
    if "Ordered" not in xl.sheet_names:
        raise FichierIllisible(
            f"Feuille « Ordered » introuvable dans le fichier {FICHIER_ASREQ}. "
            f"Feuilles présentes : {', '.join(xl.sheet_names)}")
    df = lire_feuille(xl, "Ordered", 5)

    c_barecode = trouver_colonne(df, "id barecode")
    c_pn = trouver_colonne(df, "pn + infos", "pn")
    c_qty = trouver_colonne(df, "qty", exact=True)
    if c_pn is None:
        raise ColonneIntrouvable("PN + infos pièce sortie", FICHIER_ASREQ, "Ordered", df.columns)
    if c_qty is None:
        raise ColonneIntrouvable("Qty", FICHIER_ASREQ, "Ordered", df.columns)

    out = pd.DataFrame({
        "PN": cle_pn(df[c_pn]),
        "Qty": nombre(df[c_qty], 0),
        "TRFX": texte(df[c_barecode]) if c_barecode else np.nan,
    })
    return out[out["PN"].notna()], "Ordered"


def _code(serie: pd.Series) -> pd.Series:
    return texte(serie).str.replace(r"\.0$", "", regex=True)


def lire_etat_stock(data: bytes):
    """État du stock (PNR, QTE SUR ÉTAGÈRE, QTE EN CDE, GESTION…). Renvoie (lignes, feuille)."""
    xl = ouvrir_excel(data, FICHIER_STOCK)
    feuille, entete = choisir_feuille(xl, ["pnr", "qte sur etagere"])
    df = lire_feuille(xl, feuille, entete)

    c_pnr = trouver_colonne(df, "pnr", exact=True) or trouver_colonne(df, "pnr")
    c_stock = trouver_colonne(df, "qte sur etagere")
    c_cde = trouver_colonne(df, "qte en cde")
    c_gestion = trouver_colonne(df, "gestion", exact=True) or trouver_colonne(df, "gestion")
    c_agent = trouver_colonne(df, "code agt appro")
    c_fourn = trouver_colonne(df, "code fournisseur")
    c_dernier = trouver_colonne(df, "dernier fournisseur")
    c_desc = trouver_colonne(df, "description")
    c_ccn = trouver_colonne(df, "ccn", exact=True)
    c_class = trouver_colonne(df, "class code", exact=True)
    if c_pnr is None:
        raise ColonneIntrouvable("PNR", FICHIER_STOCK, feuille, df.columns)
    if c_stock is None:
        raise ColonneIntrouvable("QTE SUR ÉTAGÈRE", FICHIER_STOCK, feuille, df.columns)

    n = len(df)
    out = pd.DataFrame({
        "PN": cle_pn(df[c_pnr]),
        "QTY_STOCK": nombre(df[c_stock], 0),
        "QTY_CDE": nombre(df[c_cde], 0) if c_cde else pd.Series(0.0, index=df.index),
        "GESTION": nombre(df[c_gestion]) if c_gestion else np.nan,
        "CODE_AGENT": texte(df[c_agent]) if c_agent else np.nan,
        "CODE_FOURNISSEUR": texte(df[c_fourn]) if c_fourn else np.nan,
        "DERNIER_FOURNISSEUR": texte(df[c_dernier]) if c_dernier else np.nan,
        "Description_stock": df[c_desc] if c_desc else np.nan,
        "CCN": _code(df[c_ccn]) if c_ccn else np.nan,
        "CLASS_CODE_STOCK": nombre(df[c_class]) if c_class else np.full(n, np.nan),
    })
    return out[out["PN"].notna()], feuille


def lire_commandes_sap(data: bytes):
    """Commandes (SAP), feuille « Toutes les commandes » de préférence. Renvoie (lignes, feuille)."""
    xl = ouvrir_excel(data, FICHIER_COMMANDES)
    feuille, entete = choisir_feuille(xl, ["pn", "code acheteur", "commande"],
                                      feuille_preferee="Toutes les commandes")
    df = lire_feuille(xl, feuille, entete).dropna(axis=1, how="all")

    c_pn = trouver_colonne(df, "pn", exact=True)
    c_cmd = trouver_colonne(df, "commande", exact=True)
    c_acheteur = trouver_colonne(df, "code acheteur")
    c_gestion = trouver_colonne(df, "gestion", exact=True)
    c_fourn_code = trouver_colonne(df, "code fournisseur")
    c_fourn = trouver_colonne(df, "fournisseur", exact=True) or trouver_colonne(df, "fournisseur")
    c_psd = trouver_colonne(df, "date de livraison promise", "livraison promise")
    c_date_dem = trouver_colonne(df, "date de livraison demandee", "livraison demandee")
    c_statut = trouver_colonne(df, "statut de la commande", "statut")
    c_restant = trouver_colonne(df, "quantite restant a livrer", "restant a livrer")
    c_class = trouver_colonne(df, "class code", "code classe")
    c_ccn = trouver_colonne(df, "ccn", exact=True)
    if c_pn is None:
        raise ColonneIntrouvable("PN", FICHIER_COMMANDES, feuille, df.columns)

    nat = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    out = pd.DataFrame({
        "PN": cle_pn(df[c_pn]),
        "Commande": texte(df[c_cmd]) if c_cmd else np.nan,
        "Code_acheteur": texte(df[c_acheteur]) if c_acheteur else np.nan,
        "Gestion_cmd": nombre(df[c_gestion]) if c_gestion else np.nan,
        "Code_fournisseur_cmd": texte(df[c_fourn_code]) if c_fourn_code else np.nan,
        "Fournisseur": texte(df[c_fourn]) if c_fourn else np.nan,
        "PSD": dates(df[c_psd]) if c_psd else nat,
        "Date_demandee": dates(df[c_date_dem]) if c_date_dem else nat,
        "Statut": texte(df[c_statut]) if c_statut else np.nan,
        "Qty_restant": nombre(df[c_restant], 0) if c_restant else 0.0,
        "Class_code": nombre(df[c_class]) if c_class else np.nan,
        "CCN_cmd": _code(df[c_ccn]) if c_ccn else np.nan,
    })
    out = out[out["PN"].notna()].copy()
    # Date de livraison « effective » : la PSD si connue, sinon la date demandée.
    out["PSD_effective"] = out["PSD"].fillna(out["Date_demandee"])
    out["PSD_est_estimee"] = out["PSD"].isna() & out["Date_demandee"].notna()
    return out, feuille
