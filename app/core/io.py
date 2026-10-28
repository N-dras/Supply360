"""Lecture des fichiers importés, normalisation / validation des colonnes, export Excel.

Aucune dépendance à Streamlit : tout est testable avec pytest. Les fichiers arrivent
sous forme d'octets (`UploadedFile.getvalue()`), jamais via un chemin.

Lecture avec calamine (moteur Rust inclus dans Pyodide, ~10× plus rapide qu'openpyxl) ;
export avec core/xlsx.py (bibliothèque standard).
"""

import html
import io
import re
import unicodedata
import zipfile
from datetime import date

import numpy as np
import pandas as pd

from core import transforms as tf
from core import xlsx


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


# Libellés des sources : identiques dans tous les onglets (CLAUDE.md §2.3).
FICHIER_BESOINS = "Besoins chantier (LOGOPS)"
FICHIER_ASREQ = "Étude ASREQ/NOREQ"
FICHIER_STOCK = "État du stock"
FICHIER_COMMANDES = "Commandes (SAP)"
FICHIER_REFERENCES = "Références textile"


# --------------------------------------------------------------------------
# Reconnaissance des fichiers par leur nom (import groupé d'un dossier SharePoint)
# --------------------------------------------------------------------------
# Mots-clés cherchés dans le nom du fichier (sans accents ni majuscules), par ordre de priorité.
MOTS_CLES_SOURCES = [
    ("besoin_prod", ("besoin_prod",)),
    ("pe", ("pe_mousse",)),
    ("besoins", ("logops",)),
    ("asreq", ("asreq", "noreq")),
    ("pieces", ("piece",)),
    ("references", ("reference", "catalog")),
    ("commandes", ("commande", "sap")),
    ("stock", ("stock",)),
]
CHANTIER_DANS_NOM = re.compile(r"(?<![A-Z0-9])([A-Z]{1,2}-?[A-Z0-9]{3,5})\s*-\s*(\d{2})(\d{2})(\d{2})(?!\d)")


def reconnaitre_fichier(nom: str) -> str | None:
    """Source d'un fichier d'après son nom : besoins, asreq, pieces, references, commandes, stock (ou None)."""
    n = normaliser(nom.rsplit(".", 1)[0])
    for source, mots in MOTS_CLES_SOURCES:
        if any(m in n for m in mots):
            return source
    return None


# Signatures de contenu : mots-clés de la ligne d'en-tête (mêmes règles que les lecteurs ci-dessous).
SIGNATURES_SOURCES = [
    ("besoin_prod", ["ccn", "qty per a/c", "nb_ac"]),
    ("besoins", ["mpn prime", "qty"]),
    ("stock", ["pnr", "qte sur etagere"]),
    ("commandes", ["pn", "code acheteur", "commande"]),
    ("pieces", ["qty_per_ac", "registration"]),
    ("references", ["pn", "equip"]),
]


# --------------------------------------------------------------------------
# Aperçu rapide d'un classeur .xlsx / .xlsm (en-têtes seulement)
# --------------------------------------------------------------------------
def _texte_xml(fragment: str) -> str:
    return html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", fragment, re.S)))


def apercu_xlsx(data: bytes, max_lignes: int = 15, max_feuilles: int = 10, octets: int = 400_000):
    """[(feuille, lignes)] : les premières lignes de chaque feuille, en ne lisant que le début du fichier XML.

    Le moteur Excel charge une feuille ENTIÈRE même pour en lire 15 lignes : sous Pyodide, reconnaître un gros État
    du stock prenait plusieurs secondes et beaucoup de mémoire, pendant lesquelles la page semblait figée. Ici, on
    décompresse seulement le début de chaque feuille (et des textes partagés). None si le fichier n'est pas un .xlsx.
    """
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        classeur = z.read("xl/workbook.xml").decode("utf-8", "ignore")
        liens = z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "ignore")
    except Exception:
        return None
    cibles = {}
    for rel in re.findall(r"<Relationship\b[^>]*>", liens):
        i, t = re.search(r'\bId="([^"]+)"', rel), re.search(r'\bTarget="([^"]+)"', rel)
        if i and t:
            cibles[i.group(1)] = t.group(1).lstrip("/") if t.group(1).startswith("/") else "xl/" + t.group(1)
    feuilles = []
    for balise in re.findall(r"<sheet\b[^>]*>", classeur):
        n, r = re.search(r'\bname="([^"]*)"', balise), re.search(r'\br:id="([^"]+)"', balise)
        if n and r and r.group(1) in cibles:
            feuilles.append((html.unescape(n.group(1)), cibles[r.group(1)]))
    lignes_par_feuille, besoins = [], set()
    for nom, chemin in feuilles[:max_feuilles]:
        try:
            with z.open(chemin) as f:
                xml = f.read(octets).decode("utf-8", "ignore")
        except KeyError:
            continue
        lignes = []
        for attrs_ligne, ligne in re.findall(r"<row\b([^>]*)>(.*?)</row>", xml, re.S):
            num = re.search(r'\br="(\d+)"', attrs_ligne)
            rang = int(num.group(1)) - 1 if num else len(lignes)  # rang réel (lignes vides absentes du XML)
            if rang >= max_lignes:
                break
            lignes += [[] for _ in range(rang - len(lignes))]
            cellules = []
            for attrs, corps in re.findall(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", ligne, re.S):
                v = re.search(r"<v>(.*?)</v>", corps or "", re.S)
                if 't="s"' in attrs and v:
                    besoins.add(int(v.group(1)))
                    cellules.append(("s", int(v.group(1))))
                elif 't="inlineStr"' in attrs:
                    cellules.append(("t", _texte_xml(corps or "")))
                else:
                    cellules.append(("t", html.unescape(v.group(1)) if v else ""))
            lignes.append(cellules)
        lignes_par_feuille.append((nom, lignes))
    partages = []
    if besoins and "xl/sharedStrings.xml" in z.namelist():
        with z.open("xl/sharedStrings.xml") as f:  # lecture progressive jusqu'au dernier texte utile
            reste = ""
            while len(partages) <= max(besoins):
                bloc = f.read(262_144)
                if not bloc:
                    break
                reste += bloc.decode("utf-8", "ignore")
                fin = reste.rfind("</si>")
                if fin < 0:
                    continue
                partages += [_texte_xml(si) for si in re.findall(r"<si>(.*?)</si>", reste[:fin + 5], re.S)]
                reste = reste[fin + 5:]
    return [(nom, [[(partages[v] if v < len(partages) else "") if k == "s" else v for k, v in l] for l in lignes])
            for nom, lignes in lignes_par_feuille]


def detecter_source(data: bytes, nom: str) -> str | None:
    """Source d'un fichier d'après son CONTENU (en-têtes des 15 premières lignes de chaque feuille).

    Indépendant du nom du fichier, qui peut changer. None si rien ne correspond ou fichier illisible.
    """
    if nom.lower().endswith(".csv"):
        tete = normaliser(data[:4000].decode("utf-8-sig", errors="ignore").split("\n", 1)[0])
        return "pieces" if "qty_per_ac" in tete and "registration" in tete else None
    apercu = apercu_xlsx(data)
    if apercu is None:  # pas un .xlsx (ex. .xls) : lecture classique
        try:
            xl = ouvrir_excel(data, nom)
        except FichierIllisible:
            return None
        noms = list(xl.sheet_names)
        lire = lambda f: xl.parse(f, header=None, nrows=15)  # noqa: E731
    else:
        noms, contenus = [n for n, _ in apercu], dict(apercu)
        lire = lambda f: pd.DataFrame(contenus[f])  # noqa: E731
    if "Ordered" in noms:  # étude ASREQ/NOREQ (classeur .xlsm, feuille « Ordered »)
        return "asreq"
    if any("bottom_foam" in normaliser(f) or "backrest_foam" in normaliser(f) for f in noms):
        return "pe"  # fichier PE mousses (feuilles BOTTOM FOAM / BACKREST FOAM)
    for feuille in noms[:10]:
        try:
            raw = lire(feuille)
        except Exception:
            continue
        for source, mots in SIGNATURES_SOURCES:
            if trouver_ligne_entete(raw, mots) is not None:
                return source
    return None


def identifier_fichier(data: bytes, nom: str) -> str | None:
    """Source d'un fichier : par son contenu d'abord, à défaut par les mots-clés de son nom."""
    return detecter_source(data, nom) or reconnaitre_fichier(nom.replace("\\", "/").rsplit("/", 1)[-1])


def chantier_depuis_nom(nom: str) -> tuple[str, date] | None:
    """« F-XKAA - 151126 - LOGOPS.xlsx » → ("F-XKAA", date(2026, 11, 15)) ; None si absent ou date invalide."""
    m = CHANTIER_DANS_NOM.search(nom.upper())
    if not m:
        return None
    try:
        return m.group(1), date(2000 + int(m.group(4)), int(m.group(3)), int(m.group(2)))
    except ValueError:
        return None


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
def _moteur() -> str:
    try:
        import python_calamine  # noqa: F401
        return "calamine"
    except ImportError:  # développement local sans calamine
        return "openpyxl"


def ouvrir_excel(data: bytes, fichier: str) -> pd.ExcelFile:
    try:
        xl = pd.ExcelFile(io.BytesIO(data), engine=_moteur())
        xl.s360_octets = data  # pour choisir_feuille : aperçu rapide des en-têtes (apercu_xlsx)
        return xl
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
    apercu = apercu_xlsx(xl.s360_octets) if getattr(xl, "s360_octets", None) is not None else None
    apercu = dict(apercu) if apercu else None
    for s in feuilles:
        try:  # aperçu rapide (début du XML) plutôt que le chargement de toute la feuille
            raw = pd.DataFrame(apercu[s]) if apercu is not None and s in apercu else xl.parse(s, header=None, nrows=15)
        except Exception:
            continue
        h = trouver_ligne_entete(raw, mots_cles)
        if h is not None:
            return s, h
    return xl.sheet_names[0], 0


def _cellule(v):
    """Comme pandas : nombre entier → int, texte vide → None."""
    if type(v) is float and v.is_integer():
        return int(v)
    return None if v == "" else v


def lire_colonnes(xl: pd.ExcelFile, feuille: str, entete: int, mots_cles, garder) -> pd.DataFrame:
    """Lecture ÉCONOME EN MÉMOIRE : seules les colonnes dont le nom normalisé satisfait `garder(nom)` sont gardées.

    pandas crée un objet Python par cellule de TOUTES les colonnes (≈ 80 Mo pour 30 000 lignes × 23 colonnes sous
    Pyodide, où la mémoire ne redescend jamais) : un gros État du stock pouvait saturer la mémoire du navigateur et
    figer la page. Ici, les lignes sont lues une à une (moteur calamine) et seules les colonnes utiles sont gardées.
    Sans calamine (développement local), lecture pandas classique.
    """
    livre = getattr(xl, "book", None)
    if not hasattr(livre, "get_sheet_by_name"):
        return lire_feuille(xl, feuille, entete)
    lignes = livre.get_sheet_by_name(feuille).iter_rows()
    cles = [normaliser(m) for m in mots_cles]
    for i, ligne in enumerate(lignes):  # ligne d'en-tête : celle qui contient les mots-clés (comme trouver_ligne_entete)
        cellules = [normaliser(v) for v in ligne]
        jointes = "|".join(cellules)
        if all(any(m in c for c in cellules) or m in jointes for m in cles):
            break
        if i >= 30:
            return lire_feuille(xl, feuille, entete)
    else:
        return lire_feuille(xl, feuille, entete)
    noms, vus = [], {}
    for j, v in enumerate(ligne):  # noms de colonnes comme pandas : vides → « Unnamed: j », doublons → « X.1 »
        n = str(v).replace("\n", " ").strip() if v not in (None, "") else f"Unnamed: {j}"
        if n in vus:
            vus[n] += 1
            n = f"{n}.{vus[n]}"
        else:
            vus[n] = 0
        noms.append(n)
    idx = [j for j, n in enumerate(noms) if garder(normaliser(n))]
    valeurs = {j: [] for j in idx}
    for ligne in lignes:
        n = len(ligne)
        for j in idx:
            valeurs[j].append(_cellule(ligne[j]) if j < n else None)
    df = pd.DataFrame({noms[j]: pd.Series(valeurs[j], dtype=object) for j in idx})
    return df.dropna(how="all").reset_index(drop=True)


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
    """Référence pièce en texte pour les jointures : majuscules, sans aucun espace.

    Les zéros en tête sont conservés s'ils sont saisis en texte dans Excel.
    """
    s = serie.map(_sans_decimale, na_action="ignore")
    s = s.map(str, na_action="ignore").str.replace("[\\s\u00a0\u202f]+", "", regex=True).str.upper()
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
    # Unité fixée (ns) : la précision dépend sinon du type des cellules (objets datetime ou Timestamp).
    return pd.to_datetime(serie, errors="coerce", dayfirst=True, format="mixed").astype("datetime64[ns]")


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
    return xlsx.classeur(feuilles, couleurs_lignes)


# --------------------------------------------------------------------------
# Lecture des sources (une ligne par ligne de fichier, colonnes normalisées)
# --------------------------------------------------------------------------
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


# Colonnes complémentaires de l'État du stock (consommation, valeur…), lues si présentes.
STOCK_COMPLEMENTS = {
    "QTE CONSO 12M": "qte_conso_12m", "QTE CONSO 18M": "qte_conso_18m", "QTE CONSO 24M": "qte_conso_24m",
    "TDD 6M": "tdd_6m", "TDD 12M": "tdd_12m", "QTE COUVERTURE": "qte_couverture", "QTE SAR": "qte_sar",
    "Stock réservé": "stock_reserve", "B/O": "b/o", "Dernier PU (achat) Euros": "dernier_pu_(achat)_euros",
    "RP": "rp", "EOQ": "eoq", "LT observé moyen sur 2 ans": "lt_observe_moyen_sur_2_ans",
}


_STOCK_EXACT = {"pnr", "pn", "finalpnr", "gestion", "ccn", "class_code"}
_STOCK_CONTIENT = ("pnr", "qte_sur_etagere", "qte_en_cde", "code_agt_appro", "code_fournisseur", "dernier_fournisseur",
                   "description", "tracking_level", "qte_conso", "date_derniere_conso", *STOCK_COMPLEMENTS.values())


def _garder_stock(n: str) -> bool:
    return n in _STOCK_EXACT or any(c in n for c in _STOCK_CONTIENT)


def lire_etat_stock(data: bytes):
    """État du stock (PNR, QTE SUR ÉTAGÈRE, QTE EN CDE, GESTION…). Renvoie (lignes, feuille).

    Les colonnes de consommation (QTE CONSO 12M…, QTE CONSO <année>), de prix et la date de
    dernière consommation sont ajoutées quand elles existent (utilisées par l'onglet Textile).
    """
    xl = ouvrir_excel(data, FICHIER_STOCK)
    feuille, entete = choisir_feuille(xl, ["pnr", "qte sur etagere"])
    df = lire_colonnes(xl, feuille, entete, ["pnr", "qte sur etagere"], _garder_stock)

    c_pnr = (trouver_colonne(df, "pnr", exact=True) or trouver_colonne(df, "pnr")
             or trouver_colonne(df, "pn", "finalpnr", exact=True))
    c_stock = trouver_colonne(df, "qte sur etagere")
    c_cde = trouver_colonne(df, "qte en cde")
    c_gestion = trouver_colonne(df, "gestion", exact=True) or trouver_colonne(df, "gestion")
    c_agent = trouver_colonne(df, "code agt appro")
    c_fourn = trouver_colonne(df, "code fournisseur")
    c_dernier = trouver_colonne(df, "dernier fournisseur")
    c_desc = trouver_colonne(df, "description")
    c_ccn = trouver_colonne(df, "ccn", exact=True)
    c_class = trouver_colonne(df, "class code", exact=True)
    c_tl = trouver_colonne(df, "tracking level")
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
        # TRACKING LEVEL → TL : « 0 » (consommable) ou « 1 » (réparable), quelle que soit l'écriture (TL0, 1, 1.0…)
        "TL": texte(df[c_tl]).str.extract(r"([01])", expand=False) if c_tl else np.full(n, np.nan),
    })
    noms = {normaliser(c): c for c in df.columns}
    for cible, norm in STOCK_COMPLEMENTS.items():
        if norm in noms:
            out[cible] = nombre(df[noms[norm]])
    for norm, col in noms.items():
        m = re.fullmatch(r"qte_conso_(20\d\d)", norm)
        if m:
            out[f"QTE CONSO {m.group(1)}"] = nombre(df[col])
    if "date_derniere_conso" in noms:
        out["DATE DERNIERE CONSO"] = dates(df[noms["date_derniere_conso"]])
    return out[out["PN"].notna()], feuille


_CMD_EXACT = {"pn", "p/n", "part_number", "commande", "gestion", "ccn", "fournisseur", "statut"}
_CMD_CONTIENT = ("code_acheteur", "code_fournisseur", "fournisseur", "livraison_promise", "livraison_demandee", "emission",
                 "statut", "restant_a_livrer", "class_code", "code_classe")


def _garder_commandes(n: str) -> bool:
    return n in _CMD_EXACT or any(c in n for c in _CMD_CONTIENT)


def lire_commandes_sap(data: bytes):
    """Commandes (SAP), feuille « Toutes les commandes » de préférence. Renvoie (lignes, feuille).

    Le fournisseur manquant est complété à partir du code fournisseur (voir
    transforms.completer_fournisseurs).
    """
    xl = ouvrir_excel(data, FICHIER_COMMANDES)
    feuille, entete = choisir_feuille(xl, ["pn", "code acheteur", "commande"],
                                      feuille_preferee="Toutes les commandes")
    df = lire_colonnes(xl, feuille, entete, ["pn", "code acheteur", "commande"], _garder_commandes).dropna(axis=1, how="all")

    c_pn = trouver_colonne(df, "pn", exact=True) or trouver_colonne(df, "p/n", "part number", exact=True)
    c_cmd = trouver_colonne(df, "commande", exact=True)
    c_acheteur = trouver_colonne(df, "code acheteur")
    c_gestion = trouver_colonne(df, "gestion", exact=True)
    c_fourn_code = trouver_colonne(df, "code fournisseur")
    c_fourn = trouver_colonne(df, "fournisseur", exact=True) or trouver_colonne(df, "fournisseur")
    c_psd = trouver_colonne(df, "date de livraison promise", "livraison promise")
    c_date_dem = trouver_colonne(df, "date de livraison demandee", "livraison demandee")
    c_emission = trouver_colonne(df, "date d'emission de la commande", "date emission de la commande", "date emission",
                                 "date d'emission")
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
        "Code_fournisseur_cmd": _code(df[c_fourn_code]) if c_fourn_code else np.nan,
        "Fournisseur": texte(df[c_fourn]) if c_fourn else np.nan,
        "PSD": dates(df[c_psd]) if c_psd else nat,
        "Date_demandee": dates(df[c_date_dem]) if c_date_dem else nat,
        "Date_emission": dates(df[c_emission]) if c_emission else nat,
        "Statut": texte(df[c_statut]) if c_statut else np.nan,
        "Qty_restant": nombre(df[c_restant], 0) if c_restant else 0.0,
        "Class_code": nombre(df[c_class]) if c_class else np.nan,
        "CCN_cmd": _code(df[c_ccn]) if c_ccn else np.nan,
    })
    out = out[out["PN"].notna()].copy()
    out["Fournisseur"] = tf.completer_fournisseurs(out)
    # Date de livraison « effective » : la PSD si connue, sinon la date demandée.
    out["PSD_effective"] = out["PSD"].fillna(out["Date_demandee"])
    out["PSD_est_estimee"] = out["PSD"].isna() & out["Date_demandee"].notna()
    return out, feuille


def lire_references_textile(data: bytes):
    """Références textile (feuille « PN Catalog » : pn, equipment, description, ccn). Renvoie (catalogue, feuille)."""
    xl = ouvrir_excel(data, FICHIER_REFERENCES)
    feuille, entete = choisir_feuille(xl, ["pn", "equip"], feuille_preferee="PN Catalog")
    df = lire_feuille(xl, feuille, entete)
    c_pn = trouver_colonne(df, "pn", exact=True)
    c_eq = trouver_colonne(df, "equipment", "equipement", exact=True) or trouver_colonne(df, "equipment", "equipement")
    if c_pn is None:
        raise ColonneIntrouvable("pn", FICHIER_REFERENCES, feuille, df.columns)
    if c_eq is None:
        raise ColonneIntrouvable("equipment", FICHIER_REFERENCES, feuille, df.columns)
    c_desc = trouver_colonne(df, "description", exact=True)
    c_ccn = trouver_colonne(df, "ccn", exact=True)
    out = pd.DataFrame({
        "PN": cle_pn(df[c_pn]),
        "Equipement": texte(df[c_eq]).str.upper(),
        "Description": texte(df[c_desc]) if c_desc else np.nan,
        "CCN": _code(df[c_ccn]) if c_ccn else np.nan,
    })
    out = out[out["PN"].notna()].drop_duplicates("PN").reset_index(drop=True)
    return out, feuille
