"""Planning de la politique d'entretien (PE) des mousses de sièges et forecast des commandes d'équipements.

Entrées :
  - fichier « PE mousses » (régénéré chaque mois) : une feuille « … BOTTOM FOAM … » (assises, classes J / W / Y)
    et une feuille « … BACKREST FOAM … » (dossiers J). Par immatriculation : flotte, version cabine, âge des
    mousses en mois à la date de l'extraction (« > 60 » = au moins 60 mois), visite liée (texte avec une date) ;
  - textile_all_parts (« Pièces par avion ») : PN et quantité par avion des lignes `equipment` = MOUSSE ;
    classe = `area`, assise / dossier selon la `description` (FOAM BOTTOM / BOTT… ou FOAM BACKREST / BACK…) ;
  - État du stock et Commandes (SAP) : stock, prix, commandes en cours, fournisseur.

Règles :
  - échéance = date du dernier remplacement (date d'extraction − âge) + cycle PE ; âge « > X » : X est pris
    comme âge minimum (échéance au plus tôt) ;
  - statut à la date du jour : En retard (au-delà du délai toléré), Délai toléré, À faire < 3 mois,
    À faire < 12 mois, OK ;
  - date prévue du remplacement : la prochaine visite connue, sinon l'échéance (le mois en cours si dépassée) ;
    puis tous les cycles jusqu'à la fin de l'horizon ;
  - stock de sécurité d'un PN : pour chaque flotte, 10 % des avions qui utilisent le PN (arrondi au-dessus,
    au moins 1) × quantité par avion ;
  - livraisons à prévoir : chaque mois, ce qui manque pour garder le stock projeté (stock + commandes en
    cours − besoins) au niveau du stock de sécurité.

Fonctions pures, testables sans Streamlit.
"""

import math
import re
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from core import io as sio

FICHIER_PE = "PE mousses"
CLASSES = ["J", "W", "Y"]
COMPOSANTS = ["Assise", "Dossier"]
# Cycle PE en mois (0 = jamais remplacé) : PE mousses long-courrier.
CYCLES_DEFAUT = (("J", "Assise", 36), ("J", "Dossier", 72), ("W", "Assise", 36), ("W", "Dossier", 0),
                 ("Y", "Assise", 36), ("Y", "Dossier", 0))
STATUTS = ["En retard", "Délai toléré", "À faire < 3 mois", "À faire < 12 mois", "OK"]
STATUT_COULEURS = {"En retard": "#C62828", "Délai toléré": "#F4A259", "À faire < 3 mois": "#E8A317",
                   "À faire < 12 mois": "#2A9D8F", "OK": "#1E8E5A"}
HORIZONS = (12, 24, 36)
FOURNISSEUR_ABSENT = "Fournisseur non renseigné"

_MOIS = {"JAN": 1, "FEB": 2, "FEV": 2, "MAR": 3, "APR": 4, "AVR": 4, "MAY": 5, "MAI": 5, "JUN": 6, "JUI": 6, "JUL": 7,
         "JUIL": 7, "AUG": 8, "AOU": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
_DATE_TEXTE = re.compile(r"(?<!\d)(\d{1,2})\s*-?\s*(JAN|FEB|FEV|MAR|APR|AVR|MAY|MAI|JUN|JUIL|JUI|JUL|AUG|AOU|SEP|OCT|NOV|DEC)"
                         r"[A-Z]*\.?\s*-?\s*(\d{4}|\d{2})(?!\d)")
_IMMAT = re.compile(r"^[A-Z]{1,2}-?[A-Z0-9]{3,5}$")


@dataclass(frozen=True)
class ParamsPE:
    cycles: tuple = CYCLES_DEFAUT          # ((classe, composant, mois), …) : n-uplet, utilisable comme clé de cache
    tolerance_mois: int = 3                # délai toléré après l'échéance avant « En retard »
    securite_ratio: float = 0.10           # stock de sécurité : part des avions de la flotte
    securite_min: int = 1                  # … au moins N avions (sauf à 0 % : pas de stock de sécurité)
    horizon_mois: int = 36

    def cycle(self, classe: str, composant: str) -> int:
        return next((m for c, p, m in self.cycles if c == classe and p == composant), 0)


# --------------------------------------------------------------------------
# Lecture du fichier PE mousses
# --------------------------------------------------------------------------
def date_texte(texte) -> date | None:
    """Date contenue dans un texte de visite (« … - BOD - 03-FEB-2025 », « 12APR2026 », « 16AOUT2026 », « 11JAN27 »)."""
    if not isinstance(texte, str):
        return None
    t = texte.upper().replace("Û", "U").replace("É", "E")
    for m in _DATE_TEXTE.finditer(t):
        an = int(m.group(3))
        try:
            return date(an + 2000 if an < 100 else an, _MOIS[m.group(2)], int(m.group(1)))
        except (KeyError, ValueError):
            continue
    return None


def date_extraction(nom: str, feuilles=()) -> date | None:
    """Date des âges : JJMMAAAA dans le nom du fichier (PE_MOUSSE_29092026…), sinon None."""
    for m in re.finditer(r"(?<!\d)(\d{2})(\d{2})(20\d{2})(?!\d)", nom):
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
    return None


def est_fichier_pe(feuilles) -> bool:
    noms = [sio.normaliser(f) for f in feuilles]
    return any("bottom_foam" in n for n in noms) or any("backrest_foam" in n for n in noms)


def _lire_feuille(raw: pd.DataFrame, composant: str) -> list[dict]:
    """Une feuille « … FOAM DETAILS » : en-têtes sur 3 lignes (FLEET / AIRCRAFT, classes, AGE (month) …)."""
    norm = raw.map(lambda v: sio.normaliser(v) if isinstance(v, str) else "")
    # ligne des sous-en-têtes : celle qui contient « age » ; la ligne au-dessus porte les classes J / W / Y
    i_age = next((i for i in range(min(10, len(raw))) if norm.iloc[i].str.startswith("age").any()), None)
    if i_age is None or i_age == 0:
        return []
    c_avion = next((j for i in range(i_age) for j in range(raw.shape[1]) if norm.iat[i, j] in ("aircraft", "immat", "registration")), 1)
    c_flotte = next((j for i in range(i_age) for j in range(raw.shape[1]) if norm.iat[i, j] in ("fleet", "flotte")), 0)
    blocs = {}
    for j in range(raw.shape[1]):
        cl = str(raw.iat[i_age - 1, j]).strip().upper()
        if cl in CLASSES and norm.iat[i_age, j].startswith("age"):
            c_vis = next((k for k in range(j + 1, min(j + 4, raw.shape[1])) if "execution" in norm.iat[i_age, k]), None)
            blocs[cl] = (j, c_vis)
    lignes, flotte, version = [], None, None
    for i in range(i_age + 1, len(raw)):
        c0, avion = raw.iat[i, c_flotte], raw.iat[i, c_avion]
        avion = str(avion).strip().upper() if isinstance(avion, str) else ""
        if isinstance(c0, str) and c0.strip():
            if not avion:
                flotte, version = c0.strip(), None
                continue
            version = c0.strip()
        if not _IMMAT.match(avion):
            continue
        for cl, (j_age, j_vis) in blocs.items():
            age, visite = raw.iat[i, j_age], raw.iat[i, j_vis] if j_vis is not None else None
            visite = str(visite).strip() if isinstance(visite, str) and visite.strip() else None
            age_mois, connu = None, True
            if isinstance(age, str):
                m = re.search(r"\d+(?:[.,]\d+)?", age)
                age_mois, connu = (float(m.group(0).replace(",", ".")) if m else None), False
            elif age is not None and not pd.isna(age):
                age_mois = float(age)
            if age_mois is None and visite is None:
                continue
            lignes.append({"Flotte": flotte or version, "Version cabine": version or flotte, "Immatriculation": avion,
                           "Classe": cl, "Composant": composant, "Âge extraction (mois)": age_mois, "Âge exact": connu,
                           "Visite liée": visite, "Date visite": date_texte(visite)})
    return lignes


def lire_pe_mousses(data: bytes, nom: str) -> tuple[pd.DataFrame, date | None]:
    """(lignes immat × classe × composant, date d'extraction) depuis le fichier PE mousses tel qu'il est reçu."""
    xl = sio.ouvrir_excel(data, FICHIER_PE)
    lignes = []
    for feuille in xl.sheet_names:
        n = sio.normaliser(feuille)
        composant = "Assise" if "bottom" in n else "Dossier" if "backrest" in n else None
        if composant:
            lignes += _lire_feuille(xl.parse(feuille, header=None, dtype=object), composant)
    if not lignes:
        raise sio.FichierIllisible(f"Fichier {FICHIER_PE} : aucune feuille « BOTTOM FOAM » / « BACKREST FOAM » lisible "
                                   f"(feuilles : {', '.join(xl.sheet_names)}).")
    return pd.DataFrame(lignes), date_extraction(nom, xl.sheet_names)


# --------------------------------------------------------------------------
# Calendrier : échéances, statuts, dates prévues
# --------------------------------------------------------------------------
def _mois_entre(a, b) -> int:
    """Nombre de mois calendaires de a à b (b − a)."""
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    return (b.year - a.year) * 12 + b.month - a.month


def calendrier(lignes: pd.DataFrame, date_ref: date, today: date, p: ParamsPE) -> pd.DataFrame:
    """Une ligne par immat × classe × composant soumis à la PE (cycle > 0) : âge, échéance, statut, date prévue."""
    d = lignes.copy()
    d["Cycle PE (mois)"] = [p.cycle(c, k) for c, k in zip(d["Classe"], d["Composant"])]
    d = d[d["Cycle PE (mois)"] > 0].copy()
    ref, auj = pd.Timestamp(date_ref), pd.Timestamp(today)
    ecart = _mois_entre(ref, auj)
    d["Âge aujourd'hui (mois)"] = d["Âge extraction (mois)"] + ecart
    d["Dernier remplacement"] = [ref - pd.DateOffset(months=int(round(a))) if pd.notna(a) else pd.NaT
                                 for a in d["Âge extraction (mois)"]]
    d["Échéance"] = [r + pd.DateOffset(months=int(c)) if pd.notna(r) else pd.NaT
                     for r, c in zip(d["Dernier remplacement"], d["Cycle PE (mois)"])]
    tol = pd.DateOffset(months=p.tolerance_mois)
    ech = d["Échéance"]
    d["Statut"] = np.select(
        [ech.isna(), ech + tol < auj, ech < auj, ech <= auj + pd.DateOffset(months=3), ech <= auj + pd.DateOffset(months=12)],
        ["En retard", "En retard", "Délai toléré", "À faire < 3 mois", "À faire < 12 mois"], default="OK")
    d["Mois avant échéance"] = [(e - auj).days / 30.44 if pd.notna(e) else np.nan for e in ech]
    visite = pd.to_datetime(d["Date visite"])
    d["Prochaine visite"] = visite.where(visite >= auj)
    debut_mois = auj.to_period("M").start_time
    d["Date prévue"] = d["Prochaine visite"].fillna(ech.where(ech >= auj)).fillna(debut_mois)
    d["Origine date prévue"] = np.where(d["Prochaine visite"].notna(), "Visite planifiée",
                                        np.where(ech >= auj, "Échéance PE", "Mois en cours (retard)"))
    d["Visite après l'échéance"] = d["Prochaine visite"].notna() & ech.notna() & (d["Prochaine visite"] > ech + tol)
    d["Âge"] = np.where(d["Âge exact"], "", "âge minimum (« > » dans le fichier)")
    d["Statut"] = pd.Categorical(d["Statut"], STATUTS, ordered=True)
    return d.sort_values(["Statut", "Date prévue", "Immatriculation"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Pièces : PN de mousse par immat × classe × composant
# --------------------------------------------------------------------------
def composant_mousse(description: str) -> str | None:
    """FOAM BACKREST / FOAM BACK… → Dossier ; FOAM BOTTOM / FOAM BOTT… → Assise ; sinon None."""
    t = re.sub(r"[^A-Z]+", " ", str(description).upper())
    if re.search(r"\bBACK", t):
        return "Dossier"
    if re.search(r"\b(BOT|BTM)", t):
        return "Assise"
    return None


def classe_cabine(area: str) -> str | None:
    t = str(area).strip().upper()
    if t in CLASSES:
        return t
    for prefixe, cl in (("BUS", "J"), ("AFF", "J"), ("PRE", "W"), ("PEY", "W"), ("ECO", "Y"), ("CLASSE J", "J"),
                        ("CLASSE W", "W"), ("CLASSE Y", "Y")):
        if t.startswith(prefixe):
            return cl
    return None


def _cle_immat(v) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(v).upper())


def pieces_mousses(parts: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(mousses reconnues : immat, classe, composant, PN, qté par avion ; lignes MOUSSE non reconnues)."""
    m = parts[parts["equipment"].str.upper() == "MOUSSE"].copy()
    m["Classe"] = m["area"].map(classe_cabine)
    m["Composant"] = m["description"].map(composant_mousse)
    ok = m["Classe"].notna() & m["Composant"].notna()
    m["cle"] = m["registration"].map(_cle_immat)
    garde = m[ok].groupby(["cle", "Classe", "Composant", "pn"], as_index=False).agg(
        **{"Qté par avion": ("qty_per_ac", "sum"), "Désignation": ("description", "first"), "Type avion": ("aircraft_type", "first")})
    return garde, m[~ok][["registration", "area", "pn", "description"]].drop_duplicates()


# --------------------------------------------------------------------------
# Besoins, stock de sécurité, forecast
# --------------------------------------------------------------------------
def evenements(cal: pd.DataFrame, mousses: pd.DataFrame, today: date, horizon: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(remplacements à faire par PN et par mois sur l'horizon ; lignes du calendrier sans PN connu)."""
    debut = pd.Timestamp(today).to_period("M").start_time
    fin = debut + pd.DateOffset(months=horizon)
    occ = []
    for imm, cl, comp, prevue, cycle, origine in zip(cal["Immatriculation"], cal["Classe"], cal["Composant"], cal["Date prévue"],
                                                     cal["Cycle PE (mois)"], cal["Origine date prévue"]):
        d, k = pd.Timestamp(prevue), 0
        while d < fin:
            occ.append((imm, cl, comp, max(d, debut), k, k == 0 and origine == "Mois en cours (retard)"))
            d, k = d + pd.DateOffset(months=int(cycle)), k + 1
    o = pd.DataFrame(occ, columns=["Immatriculation", "Classe", "Composant", "Date", "Occurrence", "Rattrapage du retard"])
    o["cle"] = o["Immatriculation"].map(_cle_immat)
    o["Mois"] = o["Date"].dt.to_period("M").dt.start_time
    ev = o.merge(mousses, on=["cle", "Classe", "Composant"], how="inner")
    cles_avec_pn = set(zip(mousses["cle"], mousses["Classe"], mousses["Composant"]))
    sans = cal[[(_cle_immat(i), c, k) not in cles_avec_pn
                for i, c, k in zip(cal["Immatriculation"], cal["Classe"], cal["Composant"])]]
    ev = ev.rename(columns={"pn": "PN", "Qté par avion": "Qté"}).drop(columns="cle")
    flotte = cal.drop_duplicates("Immatriculation").set_index("Immatriculation")[["Flotte", "Version cabine"]]
    ev = ev.join(flotte, on="Immatriculation")
    return ev, sans[["Flotte", "Immatriculation", "Classe", "Composant", "Statut"]]


def stock_securite(cal: pd.DataFrame, mousses: pd.DataFrame, p: ParamsPE) -> pd.Series:
    """Par PN : pour chaque flotte, ceil(ratio × avions qui utilisent le PN) (au moins `securite_min`) × qté par avion.
    Ratio à 0 % : aucun stock de sécurité (le minimum ne s'applique pas)."""
    flotte = cal.drop_duplicates("Immatriculation").assign(cle=lambda x: x["Immatriculation"].map(_cle_immat))
    m = mousses.merge(flotte[["cle", "Flotte"]], on="cle", how="inner")
    if m.empty:
        return pd.Series(dtype=float)
    g = m.groupby(["pn", "Flotte"]).agg(avions=("cle", "nunique"), qte=("Qté par avion", "max")).reset_index()
    mini = p.securite_min if p.securite_ratio > 0 else 0
    g["Stock de sécurité"] = [max(math.ceil(p.securite_ratio * a - 1e-9), mini) * q for a, q in zip(g["avions"], g["qte"])]
    return g.groupby("pn")["Stock de sécurité"].sum()


def forecast(ev: pd.DataFrame, articles: pd.DataFrame, livraisons_cmd: pd.DataFrame, securite: pd.Series,
             today: date, horizon: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Calcul mois par mois, par PN : besoin, commandes en cours, livraisons à prévoir, commandes à avancer.

    Les commandes en cours sont déjà passées : elles sont TOUJOURS déduites, quelle que soit leur date promise.
    À commander sur l'horizon = max(0, besoin + stock de sécurité − stock − commandes en cours) ; les livraisons
    sont placées le mois où il en faut. Une commande en cours promise APRÈS le mois où elle est nécessaire est
    signalée « à avancer » (relance fournisseur), au lieu d'être commandée une seconde fois.
    `articles` : PN (index) → Stock, Prix ; `livraisons_cmd` : PN, Mois, Qté (commandes en cours).
    Renvoie (tableau long PN × mois, synthèse par PN avec les totaux à 12 / 24 / 36 mois).
    """
    debut = pd.Timestamp(today).to_period("M").start_time
    mois = pd.date_range(debut, periods=horizon, freq="MS")
    pns = sorted(set(ev["PN"]))
    besoin = ev.groupby(["PN", "Mois"])["Qté"].sum().unstack(fill_value=0).reindex(index=pns, columns=mois, fill_value=0)
    cmd = livraisons_cmd[livraisons_cmd["PN"].isin(pns)].copy()
    cmd["Mois"] = cmd["Mois"].clip(lower=debut)
    arrivees = cmd.groupby(["PN", "Mois"])["Qté"].sum().unstack(fill_value=0).reindex(index=pns, columns=mois, fill_value=0)
    stock = articles.reindex(pns)["Stock"].fillna(0).to_numpy(float)
    ss = securite.reindex(pns).fillna(0).to_numpy(float)
    B, A = besoin.to_numpy(float), arrivees.to_numpy(float)
    en_cmd = cmd.groupby("PN")["Qté"].sum().reindex(pns).fillna(0).to_numpy()
    proj = stock[:, None] + np.cumsum(A - B, axis=1)          # stock projeté sans nouvelle commande (dates promises réelles)
    # Nouvelles commandes : stock + TOUTES les commandes en cours comme point de départ, on livre ce qui manque
    # chaque mois pour rester au stock de sécurité (cumul = besoin + sécurité − stock − commandes en cours).
    dispo = (stock + en_cmd)[:, None] - np.cumsum(B, axis=1)
    cumul = np.maximum.accumulate(np.maximum(ss[:, None] - dispo, 0), axis=1)
    livr = np.diff(cumul, axis=1, prepend=0)
    # Commandes en cours à avancer : manque restant avec leurs vraies dates, une fois les nouvelles livraisons faites.
    reste = np.maximum(ss[:, None] - (proj + cumul), 0)
    a_avancer = np.minimum(reste.max(axis=1), en_cmd)
    long = pd.DataFrame({
        "PN": np.repeat(pns, len(mois)), "Mois": np.tile(mois, len(pns)),
        "Besoin": B.ravel(), "Arrivées commandes": A.ravel(), "Stock projeté sans commande": proj.ravel(),
        "À livrer": livr.ravel(), "Stock projeté": (proj + cumul).ravel(),
    })
    synth = pd.DataFrame(index=pd.Index(pns, name="PN"))
    synth["Stock"] = stock
    synth["En commande"] = en_cmd
    synth["Stock de sécurité"] = ss
    for h in HORIZONS:
        if h <= len(mois):
            synth[f"Besoin {h} mois"] = B[:, :h].sum(axis=1)
            synth[f"À commander {h} mois"] = livr[:, :h].sum(axis=1)
    rupture = [mois[np.argmax(row < 0)] if (row < 0).any() else pd.NaT for row in proj]
    synth["Rupture sans commande"] = rupture
    synth["À avancer (commandes en cours)"] = a_avancer
    synth["À avancer avant"] = [mois[np.argmax(row > 0)] if (row > 0).any() else pd.NaT for row in reste]
    premier = [mois[np.argmax(row > 0)] if (row > 0).any() else pd.NaT for row in B]
    synth["Premier besoin"] = premier
    return long, synth.reset_index()


def catalogue_mousses(parts: pd.DataFrame) -> pd.DataFrame:
    """PN de mousse au format du catalogue textile : sert à filtrer État du stock et commandes sur ces PN."""
    m = parts[parts["equipment"].str.upper() == "MOUSSE"].drop_duplicates("pn")
    return pd.DataFrame({"PN": m["pn"].to_numpy(), "Equipement": "MOUSSE", "Description": m["description"].to_numpy(),
                         "CCN": np.nan})


def articles(pbi: pd.DataFrame) -> pd.DataFrame:
    """Stock, prix et fournisseur par PN (index), depuis la table stock du Textile (voir textile.construire_tables)."""
    from core.prevision import fournisseur_prevision  # même règle que la Prévision : nom, à défaut code fournisseur
    if pbi.empty:
        return pd.DataFrame(columns=["Stock", "Prix", "Fournisseur"])
    a = pd.DataFrame({"Stock": pd.to_numeric(pbi["QTE SUR ÉTAGÈRE"], errors="coerce").to_numpy(),
                      "Prix": pd.to_numeric(pbi.get("Dernier PU (achat) Euros", pd.Series(np.nan, index=pbi.index)), errors="coerce").to_numpy(),
                      "Fournisseur": fournisseur_prevision(pbi).to_numpy()}, index=pbi["PNR"].to_numpy())
    return a[~a.index.duplicated()]


MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def libelles_annees(mois) -> dict[int, str]:
    """{année : libellé} des mois de l'horizon ; année incomplète : « 2026 (oct.–déc.) »."""
    mois = pd.DatetimeIndex(mois)
    out = {}
    for y in sorted(set(mois.year)):
        m = mois[mois.year == y].month
        if len(m) == 12:
            out[y] = str(y)
        else:
            a, b = MOIS_COURTS[m.min() - 1], MOIS_COURTS[m.max() - 1]
            out[y] = f"{y} ({a})" if a == b else f"{y} ({a}–{b})"
    return out


def par_annee(long: pd.DataFrame, mois, index: str = "PN", valeur: str = "À livrer") -> pd.DataFrame:
    """Tableau `index` × année (colonnes libellées par libelles_annees) de `valeur`, sur les mois donnés."""
    noms = libelles_annees(mois)
    d = long[long["Mois"].isin(pd.DatetimeIndex(mois))]
    t = d.assign(Année=d["Mois"].dt.year).pivot_table(index=index, columns="Année", values=valeur, aggfunc="sum", fill_value=0)
    return t.reindex(columns=list(noms), fill_value=0).rename(columns=noms)


def livraisons_commandes(o: pd.DataFrame, today: date) -> pd.DataFrame:
    """Commandes en cours (reste à livrer) par PN et mois de livraison (promise, sinon demandée, sinon tout de suite)."""
    if o is None or o.empty:
        return pd.DataFrame(columns=["PN", "Mois", "Qté"])
    d = o[o["Qte restante"].fillna(0) > 0]
    date_l = d["Date livraison promise"].fillna(d["Date livraison demandee"]).fillna(pd.Timestamp(today))
    return pd.DataFrame({"PN": d["PNR"].to_numpy(), "Mois": date_l.dt.to_period("M").dt.start_time.to_numpy(),
                         "Qté": d["Qte restante"].to_numpy(float)})


def planning_pe(lignes: pd.DataFrame, date_ref: date, parts: pd.DataFrame, articles: pd.DataFrame, o: pd.DataFrame,
                today: date, p: ParamsPE) -> dict:
    """Calcul complet : calendrier, événements, forecast (long + synthèse PN), contrôles de cohérence."""
    cal = calendrier(lignes, date_ref, today, p)
    mousses, non_reconnues = pieces_mousses(parts) if len(parts) else (pd.DataFrame(), pd.DataFrame())
    if mousses.empty:  # sans PN de mousse : avancement de la PE seulement, pas de forecast
        vide = pd.DataFrame()
        return {"cal": cal, "ev": vide, "long": vide, "synth": vide, "sans_pn": vide, "non_reconnues": non_reconnues,
                "pn_absents_stock": [], "date_ref": date_ref}
    ev, sans_pn = evenements(cal, mousses, today, p.horizon_mois)
    ss = stock_securite(cal, mousses, p)
    long, synth = forecast(ev, articles, livraisons_commandes(o, today), ss, today, p.horizon_mois)
    infos = ev.groupby("PN").agg(**{"Désignation": ("Désignation", "first"), "Composant": ("Composant", "first"),
                                    "Classes": ("Classe", lambda s: " / ".join(sorted(set(s)))),
                                    "Flottes": ("Flotte", lambda s: " / ".join(sorted(set(map(str, s))))),
                                    "Avions": ("Immatriculation", "nunique")}) if len(ev) else \
        pd.DataFrame(columns=["Désignation", "Composant", "Classes", "Flottes", "Avions"])
    art = articles.reindex(synth["PN"])
    synth = synth.join(infos, on="PN")
    synth["Fournisseur"] = art["Fournisseur"].fillna(FOURNISSEUR_ABSENT).to_numpy()
    synth["Prix unitaire (€)"] = art["Prix"].to_numpy()
    for h in HORIZONS:
        if f"À commander {h} mois" in synth:
            synth[f"Valeur {h} mois (€)"] = synth[f"À commander {h} mois"] * synth["Prix unitaire (€)"].fillna(0)
    long = long.merge(synth[["PN", "Désignation", "Composant", "Fournisseur", "Prix unitaire (€)"]], on="PN", how="left")
    long["Valeur à livrer (€)"] = long["À livrer"] * long["Prix unitaire (€)"].fillna(0)
    absents = sorted(set(synth["PN"]) - set(articles.index[articles["Stock"].notna()]))
    return {"cal": cal, "ev": ev, "long": long, "synth": synth, "sans_pn": sans_pn, "non_reconnues": non_reconnues,
            "pn_absents_stock": absents, "date_ref": date_ref}
