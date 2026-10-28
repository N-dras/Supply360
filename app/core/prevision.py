"""Prévision de commandes textile, pilotée par la politique d'entretien (PE) et les groupes d'avions.

Logique reprise de textile_policy.py (dashboard Textile d'origine), sans la partie graphique :
  1. chaque groupe d'avions (ex. « A320 Group 1 ») a une quantité de pièces par avion pour chaque PN ;
  2. on veut toujours avoir en stock de quoi équiper N avions d'avance (buffer = ratio de la taille du groupe) ;
  3. les PE planifiées (immatriculation + date) consomment du stock ; on commande, en tenant compte du délai
     fournisseur, pour que le stock reste au-dessus du besoin (buffer + PE à venir).
Ajout : `par_fournisseur` regroupe la prévision par fournisseur (nom, ou à défaut code fournisseur).
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
STATUS_ORDER = ["A commander", "A planifier", "OK", "Dormant / inactif : pas de commande", "Hors groupe avion"]
STATUS_COLORS = {"A commander": "#C62828", "A planifier": "#E8A317", "OK": "#1E8E5A",
                 "Dormant / inactif : pas de commande": "#6D28D9", "Hors groupe avion": "#9AA5B1"}
GROUP_STATUS_ORDER = ["Sous l'objectif", "Couvert si commandes livrées", "Objectif atteint"]
# Même code couleur que partout : vert = stock, bleu = à réception des commandes, rouge = à commander.
GROUP_STATUS_COLORS = {"Sous l'objectif": "#C62828", "Couvert si commandes livrées": "#1F4E9C", "Objectif atteint": "#1E8E5A"}
CLASS_ORDER = ["J", "W", "Y"]
DEFAULT_PE = {
    "HOUSSE": {("J", "Assise"): 3, ("J", "Dossier"): 6, ("W", "Assise"): 3, ("W", "Dossier"): 0, ("Y", "Assise"): 3, ("Y", "Dossier"): 0},
    "MOUSSE": {(c, p): 3 for c in CLASS_ORDER for p in ("Assise", "Dossier")},
}
FICHIER_PIECES = "Pièces par avion"
FICHIER_PLANNING = "Planning PE"


@dataclass(frozen=True)
class Params:
    buffer_ratio: float = 0.10
    buffer_min: int = 1
    buffer_on_never: bool = True
    horizon_months: int = 36
    lt_default: int = 60
    lt_basis: str = "observe"
    bfe_delay_months: int = 6
    assise_kw: str = "bott, btm, seat, cushion, ottoman, legrest, calfrest, footrest, base"
    dossier_kw: str = "back, headrest, head, neck"
    default_component: str = "Assise"


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


def lire_planning(data: bytes, nom: str) -> pd.DataFrame:
    bio = io.BytesIO(data)
    df = pd.read_csv(bio, sep=None, engine="python") if nom.lower().endswith(".csv") else \
        sio.ouvrir_excel(data, FICHIER_PLANNING).parse(0)
    cols = {sio.normaliser(c).replace("_", ""): c for c in df.columns}

    def pick(*alias):
        for a in alias:
            k = sio.normaliser(a).replace("_", "")
            if k in cols:
                return cols[k]
        return None
    reg, dte = pick("Immatriculation", "registration"), pick("Date prochaine PE", "date PE", "prochaine PE", "date")
    if not reg or not dte:
        raise sio.ColonneIntrouvable("Immatriculation / Date prochaine PE", FICHIER_PLANNING)
    eq, cl, comp, cyc = pick("Equipement", "equipment"), pick("Classe", "area", "class"), pick("Composant", "component"), pick("Cycle PE (ans)", "cycle")
    out = pd.DataFrame({
        "registration": df[reg].map(_norm_str).str.upper(),
        "date": pd.to_datetime(df[dte], errors="coerce", dayfirst=True),
        "pl_equipment": df[eq].map(_norm_str).str.upper() if eq else "",
        "pl_area": df[cl].map(_norm_str) if cl else "",
        "pl_comp": df[comp].map(_norm_str).str.capitalize() if comp else "",
        "pl_cycle": pd.to_numeric(df[cyc], errors="coerce").fillna(0) if cyc else 0.0,
    })
    return out.dropna(subset=["date"]).query("registration != ''").reset_index(drop=True)


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


def registration_parts(parts):
    """Quantité par immatriculation (un avion présent dans deux groupes n'est compté qu'une fois)."""
    base = parts.drop_duplicates(["equipment", "registration", "area", "ccn", "pn", "description", "qty_per_ac"])
    return base.groupby(["equipment", "aircraft_type", "registration", "area", "Composant", "pn"], as_index=False)["qty_per_ac"].sum()


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
def ajouter_delais(pbi: pd.DataFrame, orders: pd.DataFrame, p: Params) -> pd.DataFrame:
    """« Délai fournisseur (j) » par fournisseur principal : délais promis ou LT observé (selon `lt_basis`)."""
    pbi = pbi.drop(columns=[c for c in ["Délai fournisseur (j)", "Nb délais fournisseur"] if c in pbi.columns])
    sup_lt = tx.delais_fournisseurs(orders).rename(columns={"Délai moyen promis (j)": "Délai fournisseur (j)",
                                                             "Lignes avec délai": "Nb délais fournisseur"})
    if p.lt_basis == "observe" and "LT observé moyen sur 2 ans" in pbi.columns:
        obs = pbi[pbi["Fournisseur principal"].notna() & (pd.to_numeric(pbi["LT observé moyen sur 2 ans"], errors="coerce") > 0)]
        sup_lt = obs.groupby("Fournisseur principal")["LT observé moyen sur 2 ans"].agg(["mean", "count"]).reset_index()
        sup_lt.columns = ["Fournisseur", "Délai fournisseur (j)", "Nb délais fournisseur"]
        sup_lt = sup_lt[sup_lt["Nb délais fournisseur"] >= 3]
    return pbi.merge(sup_lt[["Fournisseur", "Délai fournisseur (j)", "Nb délais fournisseur"]]
                     .rename(columns={"Fournisseur": "Fournisseur principal"}), on="Fournisseur principal", how="left")


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
# Planning PE
# --------------------------------------------------------------------------
def month_index(dates, today):
    t = pd.Timestamp(today)
    return ((dates.dt.year - t.year) * 12 + (dates.dt.month - t.month)).astype(int)


def expand_events(planning, reg_parts, rules, today, horizon):
    """Occurrences de PE (cycle répété) par PN : registration x composant x mois."""
    cols = ["registration", "aircraft_type", "equipment", "area", "Composant", "pn", "qty", "idx", "overdue"]
    if planning is None or planning.empty:
        return pd.DataFrame(columns=cols)
    m = planning.merge(reg_parts.rename(columns={"qty_per_ac": "qty"}), on="registration", how="inner")
    for a, b in [("pl_equipment", "equipment"), ("pl_area", "area"), ("pl_comp", "Composant")]:
        m = m[(m[a] == "") | (m[a] == m[b])]
    m = m.merge(rules.rename(columns={"Equipement": "equipment", "Classe": "area"}), on=["equipment", "area", "Composant"], how="left")
    m["cycle"] = np.where(m["pl_cycle"] > 0, m["pl_cycle"], m["Cycle PE (ans)"].fillna(0))
    m["idx0"] = month_index(m["date"], today)
    T = horizon + MAX_LT
    step = np.round(m["cycle"] * 12).astype(int)
    out = []
    for k in range(0, 12):
        idx = m["idx0"] + step * k
        keep = (idx <= T - 1) & ((k == 0) | (step > 0)) & ((idx >= 0) | (k == 0))
        if not keep.any():
            continue
        e = m[keep].copy()
        e["idx"] = idx[keep].clip(lower=0)
        e["overdue"] = (idx[keep] < 0)
        out.append(e[cols])
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=cols)


# --------------------------------------------------------------------------
# Délais et livraisons
# --------------------------------------------------------------------------
def lead_time_months(pbi, p):
    sup = pd.to_numeric(pbi.get("Délai fournisseur (j)"), errors="coerce")
    obs = pd.to_numeric(pbi.get("LT observé moyen sur 2 ans"), errors="coerce")
    days = np.where(sup > 0, sup, np.where(obs > 0, obs, p.lt_default))
    src = np.where(sup > 0, "Fournisseur", np.where(obs > 0, "PN (observé)", "Défaut"))
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
def project_orders(pbi, orders, events, p, today):
    """Pour chaque PN : stock projeté, PE à venir, commandes à passer (délai fournisseur inclus)."""
    H = p.horizon_months
    T = H + MAX_LT
    pns = pbi["PNR"].tolist()
    n = len(pns)
    pos = {pn: i for i, pn in enumerate(pns)}
    lt_m, lt_days, lt_src = lead_time_months(pbi, p)
    deliv = deliveries_matrix(orders, pns, today, p, T)
    pe = np.zeros((n, T))
    if events is not None and len(events):
        ev = events[events["pn"].isin(pos)]
        np.add.at(pe, (ev["pn"].map(pos).to_numpy(), ev["idx"].to_numpy(int)), ev["qty"].to_numpy(float))
    req = pbi["Besoin minimum (qté)"].fillna(0).to_numpy(float)
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
    blocked_qty = np.where(inactive, orders_m.sum(axis=1), 0.0)
    orders_m[inactive] = 0.0
    in_group = pbi["Nb groupes avions"].fillna(0).to_numpy() > 0
    ord_now = orders_m[:, 0]
    ord_total = orders_m.sum(axis=1)
    first_ord = np.array([int(np.argmax(r > 0)) if r.any() else -1 for r in orders_m])
    t0 = pd.Period(today, "M")
    to_month = lambda k: pd.NaT if k < 0 else (t0 + int(k)).start_time  # noqa: E731
    out = pbi.copy()
    out["Délai (mois)"], out["Source délai"] = lt_m, lt_src
    out["PE planifiée sur l'horizon (qté)"] = pe[:, :H].sum(axis=1)
    out["Stock minimum respecté"] = np.where(in_group, stock0 >= req - 1e-9, np.nan)
    out["Qté à commander maintenant"] = ord_now
    out["Valeur à commander maintenant (€)"] = (ord_now * pu).round(0)
    out["Date 1ère commande"] = [to_month(k) for k in first_ord]
    out["Commandes recommandées sur l'horizon (qté)"] = ord_total
    out["Valeur commandes recommandées (€)"] = (ord_total * pu).round(0)
    out["Manque avant livraison possible (qté)"] = shortfall
    out["Premier mois sous le minimum (sans commande)"] = [to_month(k) for k in first_short]
    out["Valeur stock hors groupe avion (€)"] = np.where(in_group, 0, out["Valeur stock (€)"].fillna(0))
    out["Statut prévision"] = np.select(
        [~in_group, inactive, ord_now > 0, ord_total > 0], ["Hors groupe avion", "Dormant / inactif : pas de commande", "A commander", "A planifier"], default="OK")
    out["Commande bloquée PN dormant/inactif (qté)"] = blocked_qty
    out["Stock / besoin minimum (%)"] = np.where(req > 0, (stock0 / np.where(req > 0, req, 1) * 100).round(0), np.nan)

    months = [(t0 + k).start_time for k in range(H)]
    rep = lambda a: a[:, :H].ravel()  # noqa: E731
    monthly = pd.DataFrame({
        "PNR": np.repeat(pns, H), "Catégorie": np.repeat(tx.categorie(pbi).to_numpy(), H), "Mois": np.tile(months, n),
        "Livraisons attendues": rep(deliv), "PE planifiée (pièces)": rep(pe), "Commande à passer": orders_m.ravel(),
        "Arrivée des commandes recommandées": rep(np.diff(add_cum, axis=1, prepend=0.0)),
        "Stock sans nouvelle commande": rep(supply - cum_pe), "Stock avec commandes recommandées": rep(supply + add_cum - cum_pe),
        "Niveau à tenir (minimum + PE cumulée)": rep(need), "Stock minimum": np.repeat(req, H),
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


def run_policy(pbi, orders, parts, fleet, planning, rules, p, today):
    reg_parts = registration_parts(parts)
    gp = group_pn_table(parts)
    pbi = ajouter_delais(pbi, orders, p)
    g = build_requirements(gp, fleet, rules, pbi, p)
    req = pn_requirement(g)
    pbi = pbi.merge(req, on="PNR", how="left")
    pbi["Dans un groupe avion"] = pbi["Nb groupes avions"].fillna(0) > 0
    pbi["Besoin minimum (qté)"] = pbi["Besoin minimum (qté)"].fillna(0)
    events = expand_events(planning, reg_parts, rules, today, p.horizon_months)
    pbi, monthly, plan = project_orders(pbi, orders, events, p, today)
    pbi["Fournisseur"] = fournisseur_prevision(pbi)
    plan = plan.merge(pbi[["PNR", "Fournisseur"]].drop_duplicates("PNR"), on="PNR", how="left")
    gs = group_summary(g)
    return pbi, {"gp": g, "gs": gs, "events": events, "monthly": monthly, "plan": plan, "reg_parts": reg_parts}


def explain_pn(pn, gp):
    """Calcul détaillé d'un PN : groupes d'avions, objectif, besoin et stock réparti."""
    d = gp[gp["pn"] == pn][["group", "area", "Composant", "qty_per_ac", "Avions du groupe", "Objectif avions d'avance", "Cycle PE (ans)",
                           "Besoin minimum (qté)", "Stock alloué", "Commandes allouées", "Avions équipables (stock)"]].copy()
    d.columns = ["Groupe", "Classe", "Composant", "Qté par avion", "Avions du groupe", "Objectif avions d'avance", "Cycle PE (ans)",
                 "Besoin minimum (qté)", "Stock alloué", "Commandes allouées", "Avions équipables (stock)"]
    return d.round(1)


# --------------------------------------------------------------------------
# Vue par fournisseur
# --------------------------------------------------------------------------
FOURNISSEUR_ABSENT = "Fournisseur non renseigné"


def fournisseur_prevision(pbi: pd.DataFrame) -> pd.Series:
    """Fournisseur d'un PN pour la prévision : nom, ou à défaut code fournisseur.

    Ordre : fournisseur habituel des commandes (nom) → dernier fournisseur de l'État du stock →
    code fournisseur (commandes, puis État du stock) → « Fournisseur non renseigné ».
    """
    princ = pbi.get("Fournisseur principal", pd.Series(np.nan, index=pbi.index))
    est_code = princ.astype(str).str.startswith("Code ")
    nom = princ.where(princ.notna() & ~est_code)
    nom = nom.fillna(pbi.get("DERNIER FOURNISSEUR", pd.Series(np.nan, index=pbi.index)))
    nom = nom.fillna(princ.where(est_code))
    code = pbi.get("CODE FOURNISSEUR", pd.Series(np.nan, index=pbi.index))
    nom = nom.fillna(("Code " + code.astype(object)).where(code.notna()))
    return nom.fillna(FOURNISSEUR_ABSENT)


def par_fournisseur(s: pd.DataFrame, plan: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par fournisseur (PN actifs rattachés à un groupe d'avions) : quoi commander, quand, pour combien."""
    cand = s[s["Dans un groupe avion"] & (s["Statut activité"] == "Actif")]
    if cand.empty:
        return pd.DataFrame(columns=["Fournisseur", "PN suivis", "PN à commander", "Qté à commander maintenant",
                                     "Valeur maintenant (€)", "Valeur sur l'horizon (€)", "Prochaine commande", "Délai moyen (mois)"])
    g = cand.assign(a_cmd=cand["Qté à commander maintenant"] > 0).groupby("Fournisseur").agg(
        **{"PN suivis": ("PNR", "nunique"), "PN à commander": ("a_cmd", "sum"),
           "Qté à commander maintenant": ("Qté à commander maintenant", "sum"),
           "Valeur maintenant (€)": ("Valeur à commander maintenant (€)", "sum"),
           "Valeur sur l'horizon (€)": ("Valeur commandes recommandées (€)", "sum"),
           "Prochaine commande": ("Date 1ère commande", "min"), "Délai moyen (mois)": ("Délai (mois)", "mean")})
    g["Délai moyen (mois)"] = g["Délai moyen (mois)"].round(1)
    g["PN à commander"] = g["PN à commander"].astype(int)
    return g.reset_index().sort_values(["Valeur maintenant (€)", "Valeur sur l'horizon (€)"], ascending=False, kind="stable") \
        .reset_index(drop=True)
