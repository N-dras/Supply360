"""Prévision de commandes textile, pilotée par la consommation réelle (État du stock « Résultat »).

  1. rythme de consommation de chaque PN : QTE CONSO 12M, 18M et 24M, le plus récent pesant le plus
     (`tendance_conso`) ; évolution des 12 derniers mois par rapport aux 12 mois d'avant ;
  2. stock à tenir = le plus grand de : stock minimum par flotte (de quoi équiper 10 % des avions de chaque groupe
     d'avions, pièces par avion) et stock de sécurité statistique (selon l'irrégularité de la consommation et le délai
     fournisseur, taux de service visé) ;
  3. on commande, en tenant compte du délai fournisseur, pour que le stock reste au-dessus du stock à tenir alors que
     la consommation prévue le fait baisser chaque mois.
Pas de politique d'entretien (PE) ni de sortie de flotte : la PE n'existe pas pour tous les équipements textile.
Fournisseur d'un PN : CODE FOURNISSEUR du Résultat (`fournisseur_prevision`).
"""

import io
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from core import io as sio
from core import textile as tx

MAX_LT = 24
RAW_COLS = ["equipment", "aircraft_type", "group", "registration", "area", "ccn", "pn", "description", "qty_per_ac"]
OBSOLETE = "Obsolète / supprimé : pas de commande"  # classe code 3, 8 ou 9 (textile.fin_de_vie)
HORS = "Hors prévision (ni flotte ni conso)"
STATUS_ORDER = ["A commander", "A planifier", "OK", "Dormant / inactif : pas de commande", OBSOLETE, HORS]
STATUS_COLORS = {"A commander": "#A61B1B", "A planifier": "#DBA100", "OK": "#1E8E5A",
                 "Dormant / inactif : pas de commande": "#7B61C9", OBSOLETE: "#5B6478", HORS: "#B5BDCB"}
# Tendance de consommation : 12 derniers mois comparés aux 12 mois d'avant (± 20 % = stable)
SEUIL_TENDANCE = 0.20
TENDANCES = ["En hausse", "Nouveau", "Stable", "En baisse", "Sans conso", "Non mesurée"]
TENDANCE_COLORS = {"En hausse": "#E8590C", "Nouveau": "#7B61C9", "Stable": "#1E8E5A", "En baisse": "#2B6CB0",
                   "Sans conso": "#8A94A6", "Non mesurée": "#B5BDCB"}
# Taux de service visé → coefficient de la loi normale (stock de sécurité)
Z_SERVICE = {0.90: 1.28, 0.95: 1.65, 0.98: 2.05}
# Prévision donnée pour les 12, 24 et 36 prochains mois (cumuls), à partir du mois en cours
PERIODES = (12, 24, 36)
BLOQUEE = "Commande bloquée (PN dormant, inactif ou obsolète) (qté)"
GROUP_STATUS_ORDER = ["Sous l'objectif", "Couvert si commandes livrées", "Objectif atteint"]
# Même code couleur que partout : vert = stock, bleu = à réception des commandes, rouge = à commander.
GROUP_STATUS_COLORS = {"Sous l'objectif": "#A61B1B", "Couvert si commandes livrées": "#2B6CB0", "Objectif atteint": "#1E8E5A"}
CLASS_ORDER = ["J", "W", "Y"]
DEFAULT_PE = {
    "HOUSSE": {("J", "Assise"): 3, ("J", "Dossier"): 6, ("W", "Assise"): 3, ("W", "Dossier"): 0, ("Y", "Assise"): 3, ("Y", "Dossier"): 0},
    "MOUSSE": {(c, p): 3 for c in CLASS_ORDER for p in ("Assise", "Dossier")},
}
FICHIER_PIECES = "Pièces par avion"


@dataclass(frozen=True)
class Params:
    buffer_ratio: float = 0.10
    buffer_min: int = 1
    buffer_on_never: bool = True
    horizon_months: int = 36                  # = la plus longue des PERIODES (12, 24, 36 mois)
    lt_default: int = 60
    lt_basis: str = "observe"
    bfe_delay_months: int = 6
    assise_kw: str = "bott, btm, seat, cushion, ottoman, legrest, calfrest, footrest, base"
    dossier_kw: str = "back, headrest, head, neck"
    default_component: str = "Assise"
    taux_service: float = 0.95                # stock de sécurité : 95 % des mois sans rupture
    poids_conso: tuple = (0.5, 0.3, 0.2)      # poids des rythmes 12, 18 et 24 mois


def _norm_str(v):
    return "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v).strip()


def _norm_pn(v):
    return "" if v is None or (not isinstance(v, str) and pd.isna(v)) else re.sub(r"\s+", "", str(v)).upper()


# --------------------------------------------------------------------------
# Lecture des fichiers « Pièces par avion » et « Planning PE »
# --------------------------------------------------------------------------
def lire_pieces(data: bytes, nom: str) -> pd.DataFrame:
    """CSV ou Excel avec les colonnes equipment, aircraft_type, group, registration, area, ccn, pn, description, qty_per_ac."""
    if nom.lower().endswith(".csv"):
        df = pd.read_csv(io.BytesIO(data), sep=None, engine="python")
        if set(RAW_COLS) <= set(df.columns):
            return df
    else:
        xl = sio.ouvrir_excel(data, FICHIER_PIECES)
        for feuille in sorted(xl.sheet_names, key=lambda n: 0 if "registration" in n.lower() else 1):
            df = xl.parse(feuille)
            if set(RAW_COLS) <= set(df.columns):
                return df
    raise sio.FichierIllisible(f"Fichier {FICHIER_PIECES} : aucune feuille avec les colonnes {', '.join(RAW_COLS)}.")


# --------------------------------------------------------------------------
# Pièces par avion / groupe
# --------------------------------------------------------------------------
def _group_num(g):
    m = re.search(r"(\d+)\s*$", str(g))
    return int(m.group(1)) if m else 0


def preparer_pieces(raw: pd.DataFrame, p: Params):
    """Nettoie les lignes (par immatriculation), classe Assise/Dossier. Retourne (pièces, flotte par groupe, lignes sans PN)."""
    manquantes = [c for c in RAW_COLS if c not in raw.columns]
    if manquantes:
        raise sio.ColonneIntrouvable(", ".join(manquantes), FICHIER_PIECES)
    d = raw[RAW_COLS].copy()
    for c in ["equipment", "aircraft_type", "group", "registration", "area", "ccn", "description"]:
        d[c] = d[c].map(_norm_str)
    d["equipment"] = d["equipment"].str.upper()
    d["registration"] = d["registration"].str.upper()
    d["pn"] = d["pn"].map(_norm_pn)
    d["area"] = d["area"].replace("", "NA")
    d["qty_per_ac"] = pd.to_numeric(d["qty_per_ac"], errors="coerce").fillna(0)
    fleet = d.groupby(["equipment", "aircraft_type", "group"])["registration"].nunique().rename("Avions du groupe").reset_index()
    no_pn = d[d["pn"] == ""].reset_index(drop=True)
    d = d[d["pn"] != ""].copy()
    kw = lambda t: "|".join(re.escape(k.strip().lower()) for k in t.split(",") if k.strip())  # noqa: E731
    desc = d["description"].str.lower()
    k_dos, k_ass = kw(p.dossier_kw), kw(p.assise_kw)
    is_dos = desc.str.contains(k_dos, regex=True) if k_dos else pd.Series(False, index=d.index)
    is_ass = desc.str.contains(k_ass, regex=True) if k_ass else pd.Series(False, index=d.index)
    seat = d["equipment"].isin(["HOUSSE", "MOUSSE"])
    d["Composant"] = np.where(~seat, "Ensemble", np.where(is_dos, "Dossier", np.where(is_ass, "Assise", p.default_component)))
    return d.reset_index(drop=True), fleet, no_pn


def rattacher_pieces(parts: pd.DataFrame, pbi: pd.DataFrame) -> pd.DataFrame:
    """Pièces par avion dont le PN n'existe pas sous ce nom dans l'État du stock : rattachées au PN du stock de même
    CCN (celui qui a le plus de stock). Sans effet si le PN est déjà connu ou si le CCN est inconnu."""
    if not len(parts) or "CCN" not in pbi or "ccn" not in parts:
        return parts
    par_ccn = (pbi.assign(_c=tx.cle_ccn(pbi["CCN"]), _s=pd.to_numeric(pbi["QTE SUR ÉTAGÈRE"], errors="coerce").fillna(0))
               .dropna(subset=["_c"]).sort_values("_s", ascending=False, kind="stable").drop_duplicates("_c").set_index("_c")["PNR"])
    inconnu = ~parts["pn"].isin(set(pbi["PNR"]))
    via = tx.cle_ccn(parts["ccn"].replace("", np.nan)).map(par_ccn)
    parts = parts.copy()
    parts.loc[inconnu & via.notna(), "pn"] = via[inconnu & via.notna()]
    return parts


def group_pn_table(parts):
    """1 ligne par groupe x classe x composant x PN : quantité par avion."""
    base = parts.drop_duplicates(["equipment", "group", "registration", "area", "ccn", "pn", "description", "qty_per_ac"])
    per_reg = base.groupby(["equipment", "aircraft_type", "group", "registration", "area", "Composant", "pn"], as_index=False)["qty_per_ac"].sum()
    g = per_reg.groupby(["equipment", "aircraft_type", "group", "area", "Composant", "pn"]).agg(
        qty_per_ac=("qty_per_ac", "median"), avions_avec_pn=("registration", "nunique")).reset_index()
    g["qty_per_ac"] = np.ceil(g["qty_per_ac"])
    return g


def cle_regle(equipement, classe, composant) -> str:
    """Identifiant ASCII d'une règle PE (clé de widget)."""
    return re.sub(r"[^A-Za-z0-9]+", "_", f"{equipement}_{classe}_{composant}").strip("_").lower()


def regles_pe_defaut(parts) -> pd.DataFrame:
    keys = parts[["equipment", "area", "Composant"]].drop_duplicates()
    df = pd.DataFrame({
        "Equipement": keys["equipment"].to_numpy(), "Classe": keys["area"].to_numpy(), "Composant": keys["Composant"].to_numpy(),
        "Cycle PE (ans)": [float(DEFAULT_PE.get(e, {}).get((a, c), 0)) for e, a, c in keys.itertuples(index=False)],
    })
    eq_rank = {e: i for i, e in enumerate(tx.CATEGORY_ORDER)}
    cl_rank = {c: i for i, c in enumerate(CLASS_ORDER)}
    df["_a"], df["_b"] = df["Equipement"].map(lambda x: eq_rank.get(x, 9)), df["Classe"].map(lambda x: cl_rank.get(x, 9))
    return df.sort_values(["_a", "_b", "Classe", "Composant"]).drop(columns=["_a", "_b"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Délai fournisseur (repris de build_pbi_tables)
# --------------------------------------------------------------------------
def _delais_promis_pn(orders: pd.DataFrame) -> pd.Series:
    """Délai promis moyen de chaque PN (émission → livraison promise, 1 à 730 jours ; dates fictives et BFE exclues)."""
    if orders is None or len(orders) == 0 or "Date livraison promise" not in orders:
        return pd.Series(dtype=float)
    lt = (orders["Date livraison promise"] - orders["Date emission commande"]).dt.days
    d = orders.assign(_lt=lt)[(lt >= 1) & (lt <= 730)]
    return d.groupby("PNR")["_lt"].mean().round(0)


def ajouter_delais(pbi: pd.DataFrame, orders: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Délais du PN et de son fournisseur (CODE FOURNISSEUR du Résultat, `fournisseur_prevision`), selon `lt_basis` :
    - « observe » : « Délai PN (j) » = LT observé moyen sur 2 ans du PN ; « Délai fournisseur (j) » = moyenne de ce LT
      sur les PN du fournisseur (au moins 3) ;
    - « promis » : délais promis des lignes de commande (émission → livraison promise), par PN, et par fournisseur
      (au moins 3 lignes).
    `lead_time_months` prend le délai du PN d'abord, la moyenne du fournisseur ensuite, le défaut en dernier."""
    pbi = pbi.drop(columns=[c for c in ["Délai PN (j)", "Délai fournisseur (j)", "Nb délais fournisseur"] if c in pbi.columns])
    four = fournisseur_prevision(pbi).replace(FOURNISSEUR_ABSENT, np.nan)
    if p.lt_basis == "promis":
        pbi["Délai PN (j)"] = pbi["PNR"].map(_delais_promis_pn(orders)).to_numpy()
        sup = tx.delais_fournisseurs(orders).set_index("Fournisseur")
        pbi["Délai fournisseur (j)"] = four.map(sup["Délai moyen promis (j)"]).to_numpy() if len(sup) else np.nan
        pbi["Nb délais fournisseur"] = four.map(sup["Lignes avec délai"]).to_numpy() if len(sup) else np.nan
        return pbi
    obs = pd.to_numeric(pbi.get("LT observé moyen sur 2 ans", pd.Series(np.nan, index=pbi.index)), errors="coerce")
    pbi["Délai PN (j)"] = obs.where(obs > 0)
    g = pd.DataFrame({"f": four, "lt": obs.where(obs > 0)}).dropna().groupby("f")["lt"].agg(["mean", "count"])
    g = g[g["count"] >= 3]
    pbi["Délai fournisseur (j)"] = four.map(g["mean"].round(0)).to_numpy()
    pbi["Nb délais fournisseur"] = four.map(g["count"]).to_numpy()
    return pbi


# --------------------------------------------------------------------------
# Besoin par groupe et PN
# --------------------------------------------------------------------------
def build_requirements(gp, fleet, rules, pbi, p):
    """Besoin minimum (buffer) par groupe x PN et répartition du stock entre les groupes qui utilisent le PN."""
    g = gp.merge(fleet, on=["equipment", "aircraft_type", "group"], how="left")
    g = g.merge(rules.rename(columns={"Equipement": "equipment", "Classe": "area"}), on=["equipment", "area", "Composant"], how="left")
    g["Cycle PE (ans)"] = g["Cycle PE (ans)"].fillna(0)
    g["Objectif avions d'avance"] = np.minimum(np.maximum(p.buffer_min, np.ceil(p.buffer_ratio * g["Avions du groupe"] - 1e-9)), g["Avions du groupe"])
    applies = (g["Cycle PE (ans)"] > 0) | p.buffer_on_never
    g["Besoin minimum (qté)"] = np.where(applies, g["qty_per_ac"] * g["Objectif avions d'avance"], 0.0)
    g["_w"] = g["qty_per_ac"] * g["Objectif avions d'avance"]
    st = pbi[["PNR", "QTE SUR ÉTAGÈRE", "QTE EN CDE"]].rename(columns={"PNR": "pn"})
    g = g.merge(st, on="pn", how="left")
    wsum = g.groupby("pn")["_w"].transform("sum").replace(0, np.nan)
    share = (g["_w"] / wsum).fillna(0)
    g["Stock alloué"] = g["QTE SUR ÉTAGÈRE"].fillna(0) * share
    g["Commandes allouées"] = g["QTE EN CDE"].fillna(0) * share
    q = g["qty_per_ac"].replace(0, np.nan)
    g["Avions équipables (stock)"] = (g["Stock alloué"] / q).fillna(0)
    g["Avions équipables (stock + commandes)"] = ((g["Stock alloué"] + g["Commandes allouées"]) / q).fillna(0)
    g["Manque (stock + commandes)"] = np.maximum(0, g["Besoin minimum (qté)"] - g["Stock alloué"] - g["Commandes allouées"])
    return g.drop(columns=["_w", "QTE SUR ÉTAGÈRE", "QTE EN CDE"])


def group_summary(g):
    """1 ligne par groupe x classe x composant : combien d'avions le stock peut équiper, face à l'objectif."""
    key = ["equipment", "aircraft_type", "group", "area", "Composant"]
    g = g[g["qty_per_ac"] > 0].sort_values("Avions équipables (stock + commandes)")
    if g.empty:
        return pd.DataFrame(columns=key + ["Statut groupe"])
    first = g.groupby(key).first()
    agg = g.groupby(key).agg(
        **{"Avions du groupe": ("Avions du groupe", "first"), "Objectif avions d'avance": ("Objectif avions d'avance", "first"),
           "Cycle PE (ans)": ("Cycle PE (ans)", "first"), "Nb PN": ("pn", "nunique"),
           "Avions équipables (stock)": ("Avions équipables (stock)", "min"),
           "Avions équipables (stock + commandes)": ("Avions équipables (stock + commandes)", "min"),
           "Manque (qté)": ("Manque (stock + commandes)", "sum")})
    agg["PN goulot"] = first["pn"]
    sous = g[g["Avions équipables (stock + commandes)"] < g["Objectif avions d'avance"] - 1e-9]
    agg["PN sous l'objectif"] = sous.groupby(key).size().reindex(agg.index).fillna(0).astype(int)
    agg["Avions équipables (stock)"] = np.floor(agg["Avions équipables (stock)"] + 1e-9)
    agg["Avions équipables (stock + commandes)"] = np.floor(agg["Avions équipables (stock + commandes)"] + 1e-9)
    obj = agg["Objectif avions d'avance"]
    agg["Ecart vs objectif (avions)"] = agg["Avions équipables (stock + commandes)"] - obj
    agg["Statut groupe"] = np.select([agg["Avions équipables (stock + commandes)"] < obj, agg["Avions équipables (stock)"] < obj],
                                     ["Sous l'objectif", "Couvert si commandes livrées"], default="Objectif atteint")
    return agg.reset_index()


def pn_requirement(g):
    a = g.groupby("pn").agg(**{"Nb groupes avions": ("group", "nunique"), "Avions concernés": ("Avions du groupe", "sum"),
                               "Besoin minimum (qté)": ("Besoin minimum (qté)", "sum")}).reset_index().rename(columns={"pn": "PNR"})
    eq = g.groupby("pn").agg(**{"Avions équipables (stock)": ("Avions équipables (stock)", "sum"),
                                "Avions équipables (stock + commandes)": ("Avions équipables (stock + commandes)", "sum")}).reset_index().rename(columns={"pn": "PNR"})
    eq["Avions équipables (stock)"] = np.floor(eq["Avions équipables (stock)"] + 1e-9)
    eq["Avions équipables (stock + commandes)"] = np.floor(eq["Avions équipables (stock + commandes)"] + 1e-9)
    return a.merge(eq, on="PNR", how="left")


# --------------------------------------------------------------------------
# Consommation : rythme, tendance, stock de sécurité
# --------------------------------------------------------------------------
def tendance_conso(pbi: pd.DataFrame, p: Params, today) -> pd.DataFrame:
    """Par PN (même index que `pbi`) : consommations 12 / 18 / 24 mois, 12 mois d'avant, évolution, tendance, rythme
    prévu par mois et irrégularité (écart type mensuel).

    Rythme prévu = moyenne des rythmes mensuels 12, 18 et 24 mois pondérée par `p.poids_conso` (le plus récent pèse le
    plus ; une fenêtre absente du fichier est ignorée). Irrégularité = écart entre les années civiles complètes
    (3 dernières), ramené au mois ; au moins la racine du rythme (une conso régulière varie aussi d'un mois à l'autre).
    """
    num = lambda c: pd.to_numeric(pbi[c], errors="coerce") if c in pbi else pd.Series(np.nan, index=pbi.index)  # noqa: E731
    c12, c18, c24 = num("QTE CONSO 12M"), num("QTE CONSO 18M"), num("QTE CONSO 24M")
    haut = pd.Series(0.0, index=pbi.index)
    bas = pd.Series(0.0, index=pbi.index)
    for c, mois, w in zip((c12, c18, c24), (12, 18, 24), p.poids_conso):
        ok = c.notna()
        haut += (c.fillna(0) / mois * w).where(ok, 0.0)
        bas += pd.Series(np.where(ok, w, 0.0), index=pbi.index)
    rythme = (haut / bas.replace(0, np.nan)).fillna(0).clip(lower=0)
    avant = (c24 - c12).clip(lower=0)
    evol = ((c12 - avant) / avant.replace(0, np.nan))
    sans = (c12.fillna(0) <= 0) & (avant.fillna(0) <= 0)
    tendance = np.select([sans, c24.isna(), avant.fillna(0) <= 0, evol > SEUIL_TENDANCE, evol < -SEUIL_TENDANCE],
                         ["Sans conso", "Non mesurée", "Nouveau", "En hausse", "En baisse"], "Stable")
    annees = [a for a in tx.annees_conso(pbi) if a < pd.Timestamp(today).year][-3:]
    if len(annees) >= 2:
        sigma_an = pd.concat([num(f"QTE CONSO {a}") for a in annees], axis=1).std(axis=1, ddof=1).fillna(0)
    else:
        sigma_an = pd.Series(0.0, index=pbi.index)
    sigma = np.maximum(np.sqrt(rythme), sigma_an / np.sqrt(12)).where(rythme > 0, 0.0)
    return pd.DataFrame({
        "Conso 12 mois": c12, "Conso 18 mois": c18, "Conso 24 mois": c24, "Conso 12 mois d'avant": avant,
        "Évolution conso (%)": (evol * 100).round(0), "Tendance conso": tendance,
        "Conso prévue / mois": rythme.round(2), "Irrégularité (pièces / mois)": sigma.round(2),
    }, index=pbi.index)


def stock_securite(rythme, sigma, delai_mois, taux_service: float) -> np.ndarray:
    """Stock de sécurité = coefficient du taux de service × irrégularité mensuelle × racine du délai (en mois),
    arrondi au-dessus ; 0 pour un PN sans consommation prévue."""
    z = Z_SERVICE.get(round(float(taux_service), 2), 1.65)
    ss = np.ceil(z * np.asarray(sigma, float) * np.sqrt(np.maximum(np.asarray(delai_mois, float), 1)) - 1e-9)
    return np.where(np.asarray(rythme, float) > 0, np.maximum(ss, 0), 0.0)


def flottes_pn(gp: pd.DataFrame, flottes=None) -> pd.DataFrame:
    """Par PN : flottes qui l'utilisent (« A320 · A350 ») et, si `flottes` est donné, part des pièces installées sur
    ces flottes (un PN commun à plusieurs flottes n'appartient pas qu'à la flotte filtrée)."""
    if gp is None or gp.empty:
        return pd.DataFrame(columns=["Flottes", "Part des flottes choisies (%)"])
    d = gp.assign(_q=gp["qty_per_ac"] * gp.get("avions_avec_pn", 1))
    par = d.groupby(["pn", "aircraft_type"])["_q"].sum()
    out = pd.DataFrame({"Flottes": par.reset_index().groupby("pn")["aircraft_type"].agg(lambda s: " · ".join(sorted(set(map(str, s)))))})
    if flottes:
        tot = par.groupby(level=0).sum()
        sel = par[par.index.get_level_values(1).isin(list(flottes))].groupby(level=0).sum()
        out["Part des flottes choisies (%)"] = (sel.reindex(out.index).fillna(0) / tot.replace(0, np.nan) * 100).round(0)
    return out


def month_index(dates, today):
    t = pd.Timestamp(today)
    return ((dates.dt.year - t.year) * 12 + (dates.dt.month - t.month)).astype(int)


# --------------------------------------------------------------------------
# Délais et livraisons
# --------------------------------------------------------------------------
def lead_time_months(pbi, p):
    """Délai de chaque PN en mois (arrondi au-dessus, 1 à 24) : celui du PN, à défaut la moyenne de son fournisseur,
    à défaut le délai par défaut. Renvoie (mois, jours, source)."""
    vide = pd.Series(np.nan, index=pbi.index)
    pn = pd.to_numeric(pbi.get("Délai PN (j)", vide), errors="coerce").to_numpy(float)
    sup = pd.to_numeric(pbi.get("Délai fournisseur (j)", vide), errors="coerce").to_numpy(float)
    days = np.where(pn > 0, pn, np.where(sup > 0, sup, p.lt_default))
    src = np.where(pn > 0, "PN", np.where(sup > 0, "Fournisseur (moyenne)", "Défaut"))
    return np.clip(np.ceil(days / 30), 1, MAX_LT).astype(int), days, src


def deliveries_matrix(orders, pns, today, p, T):
    mat = np.zeros((len(pns), T))
    if orders is None or len(orders) == 0:
        return mat
    pos = {pn: i for i, pn in enumerate(pns)}
    o = orders[orders["PNR"].isin(pos)].copy()
    o = o[o["Qte restante"].fillna(0) > 0]
    if o.empty:
        return mat
    t0 = pd.Timestamp(today)
    arr = o["Date livraison promise"]
    arr = arr.mask(o["Attente BFE"].fillna(False).astype(bool), t0 + pd.DateOffset(months=int(p.bfe_delay_months)))
    arr = arr.fillna(o["Date livraison demandee"]).fillna(t0 + pd.Timedelta(days=int(p.lt_default)))
    idx = month_index(arr, today).clip(0, T - 1).to_numpy()
    rows = o["PNR"].map(pos).to_numpy()
    np.add.at(mat, (rows, idx), o["Qte restante"].to_numpy(float))
    return mat


# --------------------------------------------------------------------------
# Projection et plan de commande
# --------------------------------------------------------------------------
def project_orders(pbi, orders, p, today):
    """Pour chaque PN : stock projeté (consommation prévue chaque mois), commandes à passer (délai fournisseur inclus)."""
    H = p.horizon_months
    T = H + MAX_LT
    pns = pbi["PNR"].tolist()
    n = len(pns)
    pos = {pn: i for i, pn in enumerate(pns)}
    lt_m, lt_days, lt_src = lead_time_months(pbi, p)
    deliv = deliveries_matrix(orders, pns, today, p, T)
    rythme = pbi["Conso prévue / mois"].fillna(0).to_numpy(float) if "Conso prévue / mois" in pbi else np.zeros(n)
    pe = np.repeat(rythme[:, None], T, axis=1)  # consommation prévue, chaque mois
    sigma = pbi["Irrégularité (pièces / mois)"].fillna(0).to_numpy(float) if "Irrégularité (pièces / mois)" in pbi else np.zeros(n)
    ss = stock_securite(rythme, sigma, lt_m, p.taux_service)
    stock_min = pbi["Besoin minimum (qté)"].fillna(0).to_numpy(float)
    req = np.maximum(stock_min, ss)  # stock à tenir
    stock0 = pbi["QTE SUR ÉTAGÈRE"].fillna(0).to_numpy(float)
    pu = pd.to_numeric(pbi.get("Dernier PU (achat) Euros", pd.Series(0.0, index=pbi.index)), errors="coerce").fillna(0).to_numpy(float)
    cum_pe, cum_dl = np.cumsum(pe, axis=1), np.cumsum(deliv, axis=1)
    supply = stock0[:, None] + cum_dl
    need = req[:, None] + cum_pe
    gap = need - supply
    add_cum = np.zeros((n, T))
    orders_m = np.zeros((n, H))
    shortfall = np.zeros(n)
    first_short = np.full(n, -1)
    for i in range(n):
        L = int(lt_m[i])
        run = np.maximum.accumulate(np.maximum(gap[i, L:], 0))
        add_cum[i, L:] = np.ceil(run - 1e-9)
        arr = np.diff(add_cum[i], prepend=0.0)
        orders_m[i] = arr[L:L + H]
        if L > 0:
            shortfall[i] = max(0.0, gap[i, :L].max())
        below = np.where(gap[i, :H] > 1e-9)[0]
        first_short[i] = below[0] if len(below) else -1
    inactive = pbi["Statut activité"].isin(["Inactif", "Dormant"]).to_numpy() if "Statut activité" in pbi.columns else np.zeros(n, dtype=bool)
    obsolete = tx.fin_de_vie(pbi).to_numpy()  # classe code 3 / 8 / 9 : plus de réapprovisionnement
    blocked_qty = np.where(inactive | obsolete, orders_m.sum(axis=1), 0.0)
    orders_m[inactive | obsolete] = 0.0
    shortfall_mask = obsolete  # PN qu'on ne réapprovisionne plus : pas de « manque avant livraison »
    in_group = pbi["Dans la prévision"].fillna(False).to_numpy(bool) if "Dans la prévision" in pbi \
        else pbi["Nb groupes avions"].fillna(0).to_numpy() > 0
    ord_now = orders_m[:, 0]
    ord_total = orders_m.sum(axis=1)
    first_ord = np.array([int(np.argmax(r > 0)) if r.any() else -1 for r in orders_m])
    t0 = pd.Period(today, "M")
    to_month = lambda k: pd.NaT if k < 0 else (t0 + int(k)).start_time  # noqa: E731
    out = pbi.copy()
    out["Délai (mois)"], out["Délai retenu (j)"], out["Source délai"] = lt_m, np.round(lt_days, 0), lt_src
    out["Stock de sécurité (qté)"] = ss
    out["Stock à tenir (qté)"] = req
    out["Stock à tenir basé sur"] = np.where(req <= 0, "—", np.where(ss > stock_min, "Conso (sécurité)", "Flotte (minimum)"))
    out["Conso prévue sur la période (qté)"] = np.ceil(pe[:, :H].sum(axis=1) - 1e-9)
    out["Stock minimum respecté"] = np.where(in_group, stock0 >= req - 1e-9, np.nan)
    out["Qté à commander maintenant"] = ord_now
    out["Valeur à commander maintenant (€)"] = (ord_now * pu).round(0)
    out["Date 1ère commande"] = [to_month(k) for k in first_ord]
    for k in PERIODES:  # cumuls 12 / 24 / 36 prochains mois (mois en cours compris)
        q = orders_m[:, :k].sum(axis=1)
        out[f"À commander {k} mois (qté)"] = q
        out[f"Valeur {k} mois (€)"] = (q * pu).round(0)
        out[f"Conso prévue {k} mois (qté)"] = np.ceil(rythme * k - 1e-9)
    out["Manque avant livraison possible (qté)"] = np.where(shortfall_mask, 0.0, shortfall)
    out["Premier mois sous le minimum (sans commande)"] = [to_month(k) for k in first_short]
    out["Valeur stock hors groupe avion (€)"] = np.where(in_group, 0, out["Valeur stock (€)"].fillna(0))
    out["Statut prévision"] = np.select(
        [~in_group, obsolete, inactive, ord_now > 0, ord_total > 0],
        [HORS, OBSOLETE, "Dormant / inactif : pas de commande", "A commander", "A planifier"], default="OK")
    out[BLOQUEE] = blocked_qty
    out["Stock / besoin minimum (%)"] = np.where(req > 0, (stock0 / np.where(req > 0, req, 1) * 100).round(0), np.nan)

    months = [(t0 + k).start_time for k in range(H)]
    rep = lambda a: a[:, :H].ravel()  # noqa: E731
    monthly = pd.DataFrame({
        "PNR": np.repeat(pns, H), "Catégorie": np.repeat(tx.categorie(pbi).to_numpy(), H), "Mois": np.tile(months, n),
        "Livraisons attendues": rep(deliv), "Conso prévue (pièces)": rep(pe), "Commande à passer": orders_m.ravel(),
        "Arrivée des commandes recommandées": rep(np.diff(add_cum, axis=1, prepend=0.0)),
        "Stock sans nouvelle commande": rep(supply - cum_pe), "Stock avec commandes recommandées": rep(supply + add_cum - cum_pe),
        "Niveau à tenir (stock à tenir + conso cumulée)": rep(need), "Stock à tenir": np.repeat(req, H),
    })
    sel = np.argwhere(orders_m > 0)
    cat = tx.categorie(pbi).to_numpy()
    plan = pd.DataFrame({
        "PNR": [pns[i] for i, _ in sel], "Catégorie": [cat[i] for i, _ in sel],
        "Mois de commande": [(t0 + int(m)).start_time for _, m in sel],
        "Mois de livraison souhaité": [(t0 + int(m) + int(lt_m[i])).start_time for i, m in sel],
        "Qté à commander": [orders_m[i, m] for i, m in sel], "Délai (mois)": [int(lt_m[i]) for i, _ in sel],
        "Valeur (€)": [round(orders_m[i, m] * pu[i]) for i, m in sel],
    })
    plan["Année de commande"] = pd.to_datetime(plan["Mois de commande"]).dt.year
    return out, monthly, plan


def run_policy(pbi, orders, parts, fleet, rules, p, today):
    """Prévision complète : stock minimum par flotte, tendance de consommation, plan de commande."""
    gp = group_pn_table(parts)
    pbi = ajouter_delais(pbi, orders, p)
    g = build_requirements(gp, fleet, rules, pbi, p)
    req = pn_requirement(g)
    pbi = pbi.merge(req, on="PNR", how="left")
    pbi["Dans un groupe avion"] = pbi["Nb groupes avions"].fillna(0) > 0
    pbi["Besoin minimum (qté)"] = pbi["Besoin minimum (qté)"].fillna(0)
    pbi = pd.concat([pbi, tendance_conso(pbi, p, today)], axis=1)
    pbi["Dans la prévision"] = pbi["Dans un groupe avion"] | (pbi["Conso prévue / mois"] > 0)
    pbi, monthly, plan = project_orders(pbi, orders, p, today)
    pbi["Fournisseur"] = fournisseur_prevision(pbi)
    plan = plan.merge(pbi[["PNR", "Fournisseur"]].drop_duplicates("PNR"), on="PNR", how="left")
    gs = group_summary(g)
    return pbi, {"gp": g, "gs": gs, "monthly": monthly, "plan": plan}


def explain_pn(pn, gp):
    """Calcul détaillé d'un PN : groupes d'avions, objectif, besoin et stock réparti."""
    d = gp[gp["pn"] == pn][["aircraft_type", "group", "area", "Composant", "qty_per_ac", "Avions du groupe", "Objectif avions d'avance",
                           "Besoin minimum (qté)", "Stock alloué", "Commandes allouées", "Avions équipables (stock)"]].copy()
    d.columns = ["Flotte", "Groupe", "Classe", "Composant", "Qté par avion", "Avions du groupe", "Objectif avions d'avance",
                 "Stock minimum (qté)", "Stock alloué", "Commandes allouées", "Avions équipables (stock)"]
    return d.round(1)


# --------------------------------------------------------------------------
# Vue par fournisseur
# --------------------------------------------------------------------------
FOURNISSEUR_ABSENT = "Fournisseur non renseigné"


def fournisseur_prevision(pbi: pd.DataFrame) -> pd.Series:
    """Fournisseur d'un PN, identifié par son CODE fournisseur : un même fournisseur n'apparaît qu'une fois.

    Ordre : CODE FOURNISSEUR de l'État du stock (« Résultat », un code par PN) → code habituel des commandes →
    nom habituel des commandes → DERNIER FOURNISSEUR de l'État du stock → « Fournisseur non renseigné ».
    """
    vide = lambda s: s.isna() | s.astype(str).str.strip().isin(["", "nan", "None"])  # noqa: E731
    col = lambda c: pbi[c].astype(object).where(~vide(pbi[c])) if c in pbi else pd.Series(np.nan, index=pbi.index, dtype=object)  # noqa: E731
    princ = col("Fournisseur principal")
    est_code = pbi["Fournisseur principal (code)"].eq(True) if "Fournisseur principal (code)" in pbi \
        else pd.Series(False, index=pbi.index)
    f = col("CODE FOURNISSEUR").astype(object)
    f = f.fillna(princ.where(est_code)).fillna(princ).fillna(col("DERNIER FOURNISSEUR"))
    return f.fillna(FOURNISSEUR_ABSENT).astype(object)


def suivis(s: pd.DataFrame) -> pd.DataFrame:
    """PN réapprovisionnés : actifs, dans la prévision (flotte connue ou consommation), hors classe code 3 / 8 / 9."""
    col = "Dans la prévision" if "Dans la prévision" in s else "Dans un groupe avion"
    return s[s[col] & (s["Statut activité"] == "Actif") & (s["Statut prévision"] != OBSOLETE)]


def par_fournisseur(s: pd.DataFrame, plan: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par fournisseur (PN actifs de la prévision) : à commander maintenant et sur les 12, 24 et 36 prochains
    mois (quantité, valeur), PN dont la consommation monte ou baisse, prochaine commande."""
    cols = ["Fournisseur", "PN suivis", "PN à commander", "Valeur maintenant (€)"]
    for k in PERIODES:
        cols += [f"Qté {k} mois", f"Valeur {k} mois (€)"]
    cols += ["PN en hausse", "PN en baisse", "Prochaine commande", "Délai moyen (mois)"]
    cand = suivis(s)
    if cand.empty:
        return pd.DataFrame(columns=cols)
    agg = {"PN suivis": ("PNR", "nunique"), "PN à commander": ("a_cmd", "sum"),
           "Valeur maintenant (€)": ("Valeur à commander maintenant (€)", "sum")}
    for k in PERIODES:
        agg[f"Qté {k} mois"] = (f"À commander {k} mois (qté)", "sum")
        agg[f"Valeur {k} mois (€)"] = (f"Valeur {k} mois (€)", "sum")
    agg.update({"PN en hausse": ("hausse", "sum"), "PN en baisse": ("baisse", "sum"),
                "Prochaine commande": ("Date 1ère commande", "min"), "Délai moyen (mois)": ("Délai (mois)", "mean")})
    tend = cand["Tendance conso"] if "Tendance conso" in cand else pd.Series("", index=cand.index)
    g = cand.assign(a_cmd=cand["À commander 36 mois (qté)"] > 0, hausse=tend.isin(["En hausse", "Nouveau"]),
                    baisse=tend.eq("En baisse")).groupby("Fournisseur").agg(**agg)
    g["Délai moyen (mois)"] = g["Délai moyen (mois)"].round(1)
    for c in ["PN à commander", "PN en hausse", "PN en baisse"]:
        g[c] = g[c].astype(int)
    return g.reset_index().sort_values(["Valeur 12 mois (€)", "Valeur 36 mois (€)"], ascending=False, kind="stable") \
        .reset_index(drop=True)[cols]


def tranches(today) -> list[tuple[int, int, str]]:
    """Années glissantes de la prévision : (premier mois, dernier mois exclu, libellé « Année 1 · nov. 2026 → oct. 2027 »)."""
    mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    t0 = pd.Period(pd.Timestamp(today), "M")
    out = []
    for i, (a, b) in enumerate(zip((0, 12, 24), PERIODES), 1):
        d, f = t0 + a, t0 + b - 1
        out.append((a, b, f"Année {i} · {mois[d.month - 1]} {d.year} → {mois[f.month - 1]} {f.year}"))
    return out


def plan_par_mois(plan: pd.DataFrame, today, valeur: str = "Qté à commander", index: str = "PNR") -> pd.DataFrame:
    """Tableau `index` × mois de commande (36 prochains mois, colonnes « 11/2026 »…) de `valeur`."""
    t0 = pd.Period(pd.Timestamp(today), "M")
    mois = [(t0 + k).start_time for k in range(PERIODES[-1])]
    if plan is None or plan.empty:
        return pd.DataFrame(columns=[m.strftime("%m/%Y") for m in mois])
    t = plan.pivot_table(index=index, columns="Mois de commande", values=valeur, aggfunc="sum", fill_value=0)
    t = t.reindex(columns=mois, fill_value=0)
    t.columns = [m.strftime("%m/%Y") for m in mois]
    return t
