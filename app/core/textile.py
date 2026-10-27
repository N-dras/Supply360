"""Calculs de l'onglet Textile cabine : stock, consommation, activité, commandes et retards.

Logique reprise de textile_analytics.py / streamlit_textile_dashboard.py (dashboard Textile
d'origine), sans la partie graphique. La prévision par politique d'entretien (textile_policy.py)
n'est pas reprise : elle exige le fichier des pièces par avion, hors des trois imports retenus.
"""

import re

import numpy as np
import pandas as pd

from core import transforms as tf
from core.style import COLORS

CATEGORY_ORDER = ["CEINTURE", "HOUSSE", "MOUSSE", "RIDEAUX"]
CATEGORY_COLORS = {"CEINTURE": "#2A9D8F", "HOUSSE": COLORS["navy_2"], "MOUSSE": "#F4A259", "RIDEAUX": "#BC4B51",
                   "Non classé": COLORS["gris"]}
ORDER_STATUS_ORDER = ["En retard", "A l'heure", "Sans date promise", "En attente BFE"]
ORDER_STATUS_COLORS = {"En retard": COLORS["ko"], "A l'heure": COLORS["ok"], "Sans date promise": COLORS["warn"],
                       "En attente BFE": COLORS["violet"]}
ACTIVITY_ORDER = ["Actif", "Dormant", "Inactif"]
ACTIVITY_COLORS = {"Actif": COLORS["ok"], "Dormant": "#E67E22", "Inactif": COLORS["gris"]}
DELAY_BUCKETS = [("1 à 20 j", 1, 20), ("21 à 50 j", 21, 50), ("51 à 150 j", 51, 150), ("151 à 300 j", 151, 300),
                 ("301 j et +", 301, None)]
BUCKET_COLORS = ["#F7DC6F", "#F5B041", "#EB984E", "#CB4335", "#7B241C"]
WINDOW_COLUMNS = ["QTE CONSO 12M", "QTE CONSO 18M", "QTE CONSO 24M"]
LATE_BUFFER_DAYS = 10  # tolérance avant de déclarer une ligne en retard

# Noms de colonnes de l'État du stock tels qu'affichés dans l'onglet (et dans l'export).
STOCK_RENOMMAGE = {"PN": "PNR", "Description_stock": "DESCRIPTION", "QTY_STOCK": "QTE SUR ÉTAGÈRE", "QTY_CDE": "QTE EN CDE",
                   "CODE_FOURNISSEUR": "CODE FOURNISSEUR", "DERNIER_FOURNISSEUR": "DERNIER FOURNISSEUR"}


# --------------------------------------------------------------------------
# Outils
# --------------------------------------------------------------------------
def annees_conso(df: pd.DataFrame) -> list[int]:
    """Années présentes dans les colonnes « QTE CONSO <année> » (ex. 2021 … 2025), triées."""
    return sorted(int(m.group(1)) for c in df.columns if (m := re.fullmatch(r"QTE CONSO (20\d\d)", str(c))))


def categorie(df: pd.DataFrame) -> pd.Series:
    return df["REF_Equipement"].fillna("Non classé")


def categories(df: pd.DataFrame) -> list[str]:
    presentes = list(dict.fromkeys(categorie(df)))
    return [c for c in CATEGORY_ORDER if c in presentes] + sorted(c for c in presentes if c not in CATEGORY_ORDER)


def _num(df, col):
    return pd.to_numeric(df[col], errors="coerce").fillna(0) if col in df.columns else pd.Series(0.0, index=df.index)


# --------------------------------------------------------------------------
# Commandes
# --------------------------------------------------------------------------
def nettoyer_dates_promises(serie: pd.Series):
    """2001 ou 2030+ : pas de date donnée par le fournisseur. 2049 : en attente de BFE (matière première)."""
    d = pd.to_datetime(serie, errors="coerce")
    fictive = ((d.dt.year <= 2001) | (d.dt.year >= 2030)).fillna(False)
    bfe = (d.dt.year == 2049).fillna(False)
    return d.mask(fictive), fictive, bfe


def preparer_commandes(lignes: pd.DataFrame) -> pd.DataFrame:
    """Lignes du fichier Commandes (SAP) → colonnes du dashboard textile (une ligne par ligne de commande)."""
    o = pd.DataFrame({
        "PNR": lignes["PN"],
        "Commande": lignes["Commande"],
        "Code acheteur": lignes["Code_acheteur"],
        "CCN": lignes["CCN_cmd"],
        "Code fournisseur": lignes["Code_fournisseur_cmd"],
        "Fournisseur": lignes["Fournisseur"],
        "Date emission commande": lignes["Date_emission"],
        "Date livraison demandee": lignes["Date_demandee"],
        "Date livraison promise": lignes["PSD"],
        "Qte restante": pd.to_numeric(lignes["Qty_restant"], errors="coerce"),
    })
    for c in ["Date emission commande", "Date livraison demandee"]:
        o[c] = pd.to_datetime(o[c], errors="coerce")
    o["Date livraison promise"], o["Promesse fictive supprimée"], o["Attente BFE"] = nettoyer_dates_promises(o["Date livraison promise"])
    return o.drop_duplicates().reset_index(drop=True)


def ajouter_metriques_commandes(o: pd.DataFrame, today) -> pd.DataFrame:
    """Retard = date promise - date demandée (au-delà de 10 j de tolérance). Statuts à part : sans date promise, BFE."""
    o = o.copy()
    today = pd.Timestamp(today).normalize()
    promise, demandee = o["Date livraison promise"], o["Date livraison demandee"]
    o["Ecart promis vs demandé (j)"] = (promise - demandee).dt.days
    o["Jours de retard"] = (o["Ecart promis vs demandé (j)"] - LATE_BUFFER_DAYS).clip(lower=0)
    bfe = o["Attente BFE"].fillna(False).astype(bool)
    o["Statut commande"] = np.select([bfe, promise.isna(), o["Ecart promis vs demandé (j)"] > LATE_BUFFER_DAYS],
                                     ["En attente BFE", "Sans date promise", "En retard"], default="A l'heure")
    o["Age commande (j)"] = (today - o["Date emission commande"]).dt.days
    o["Demande dépassée (j)"] = (today - demandee).dt.days.clip(lower=0)
    classe = pd.Series(np.nan, index=o.index, dtype=object)
    retard = o["Jours de retard"]
    for label, lo, hi in DELAY_BUCKETS:
        m = (retard >= lo) & ((retard <= hi) if hi is not None else True) & (o["Statut commande"] == "En retard")
        classe[m] = label
    o["Classe de retard"] = classe
    return o


def fournisseur_principal(o: pd.DataFrame) -> pd.Series:
    """Fournisseur le plus fréquent de chaque PN (index = PNR)."""
    d = o.dropna(subset=["Fournisseur"])
    if d.empty:
        return pd.Series(dtype=object, name="Fournisseur principal")
    n = d.groupby(["PNR", "Fournisseur"]).size().reset_index(name="n")
    n = n.sort_values(["PNR", "n"], ascending=[True, False], kind="stable").drop_duplicates("PNR")
    return n.set_index("PNR")["Fournisseur"].rename("Fournisseur principal")


def delais_fournisseurs(o: pd.DataFrame, min_lignes=3) -> pd.DataFrame:
    """Délai moyen promis (émission → livraison promise) par fournisseur ; dates fictives et BFE exclues."""
    cols = ["Fournisseur", "Délai moyen promis (j)", "Délai médian promis (j)", "Lignes avec délai"]
    d = o.dropna(subset=["Fournisseur"]).copy()
    d["lt"] = (d["Date livraison promise"] - d["Date emission commande"]).dt.days
    d = d[(d["lt"] >= 1) & (d["lt"] <= 730)]
    if d.empty:
        return pd.DataFrame(columns=cols)
    g = d.groupby("Fournisseur")["lt"].agg(["mean", "median", "count"]).reset_index()
    g.columns = cols
    g = g[g["Lignes avec délai"] >= min_lignes]
    g["Délai moyen promis (j)"] = g["Délai moyen promis (j)"].round(0)
    return g.sort_values("Lignes avec délai", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# Stock et consommation
# --------------------------------------------------------------------------
def ajouter_consommation(pbi: pd.DataFrame) -> pd.DataFrame:
    """Évolutions de consommation, valeurs (€) et statut d'activité (Actif / Dormant / Inactif)."""
    pbi = pbi.copy()
    annees = annees_conso(pbi)
    c12, c24 = _num(pbi, "QTE CONSO 12M"), _num(pbi, "QTE CONSO 24M")
    shelf, ordered, pu = _num(pbi, "QTE SUR ÉTAGÈRE"), _num(pbi, "QTE EN CDE"), _num(pbi, "Dernier PU (achat) Euros")
    c3y = sum((_num(pbi, f"QTE CONSO {a}") for a in annees[-3:]), pd.Series(0.0, index=pbi.index))
    prev12 = (c24 - c12).clip(lower=0)
    pbi["Conso 12 mois précédents"] = prev12
    pbi["Evolution 12M vs 12M précédents (%)"] = np.where(prev12 > 0, (c12 / prev12.where(prev12 > 0) - 1) * 100, np.nan).round(0)
    if len(annees) >= 2:
        a, b = annees[-1], annees[-2]
        ya, yb = _num(pbi, f"QTE CONSO {a}"), _num(pbi, f"QTE CONSO {b}")
        pbi[f"Evolution {a} vs {b} (%)"] = np.where(yb > 0, (ya / yb.where(yb > 0) - 1) * 100, np.nan).round(0)
    pbi["Valeur stock (€)"] = (shelf * pu).round(0)
    pbi["Valeur en commande (€)"] = (ordered * pu).round(0)
    last = pd.to_datetime(pbi["DATE DERNIERE CONSO"], errors="coerce") if "DATE DERNIERE CONSO" in pbi.columns \
        else pd.Series(pd.NaT, index=pbi.index)
    jamais = (last.dt.year <= 2001).fillna(False).to_numpy()  # 2001 = jamais consommé (date fictive)
    consomme = ((c24 > 0) | (c3y > 0)).to_numpy()
    sh, od = (shelf > 0).to_numpy(), (ordered > 0).to_numpy()
    pbi["Statut activité"] = np.select([consomme, sh & jamais, od], ["Actif"] * 3, default=np.where(sh, "Dormant", "Inactif"))
    pbi["Motif activité"] = np.select([consomme, sh & jamais, od & ~sh, od],
                                      [f"Consommé sur {len(annees[-3:])} ans" if annees else "Consommé sur 24 mois",
                                       "Stock jamais consommé (2001)", "Commande en cours sur PN sans stock", "Commande en cours"],
                                      default="")
    pbi["Valeur stock dormant (€)"] = pbi["Valeur stock (€)"].where(pbi["Statut activité"] == "Dormant", 0)
    pbi["Valeur commande sur PN inactif (€)"] = pbi["Valeur en commande (€)"].where(pbi["Statut activité"] == "Inactif", 0)
    return pbi


def construire_tables(stock_lignes: pd.DataFrame, cmd_lignes: pd.DataFrame | None, catalogue: pd.DataFrame | None,
                      today, seulement_textile=True):
    """(pbi, commandes) : 1 ligne par PNR du stock (avec commandes et références), 1 ligne par ligne de commande."""
    if seulement_textile and catalogue is not None and len(catalogue):
        # Filtre en amont (calculs PN par PN : même résultat, beaucoup plus rapide sur un gros État du stock).
        pns = set(catalogue["PN"])
        stock_lignes = stock_lignes[stock_lignes["PN"].isin(pns)]
        cmd_lignes = cmd_lignes[cmd_lignes["PN"].isin(pns)] if cmd_lignes is not None else None
    pbi = stock_lignes.rename(columns=STOCK_RENOMMAGE)
    garder = ["PNR", "CCN", "DESCRIPTION", "QTE SUR ÉTAGÈRE", "QTE EN CDE", *WINDOW_COLUMNS, "TDD 6M", "TDD 12M",
              *[f"QTE CONSO {a}" for a in annees_conso(pbi)], "QTE COUVERTURE", "QTE SAR", "Stock réservé", "B/O",
              "Dernier PU (achat) Euros", "RP", "EOQ", "LT observé moyen sur 2 ans", "DATE DERNIERE CONSO",
              "CODE FOURNISSEUR", "DERNIER FOURNISSEUR"]
    pbi = pbi[[c for c in garder if c in pbi.columns]].copy()

    catalogue = catalogue if catalogue is not None else pd.DataFrame(columns=["PN", "Equipement", "Description", "CCN"])
    ref = catalogue.rename(columns={"PN": "PNR", "Equipement": "REF_Equipement", "Description": "REF_Description"})
    pbi = pbi.merge(ref[["PNR", "REF_Equipement", "REF_Description"]], on="PNR", how="left")

    o = preparer_commandes(cmd_lignes) if cmd_lignes is not None and len(cmd_lignes) else \
        preparer_commandes(pd.DataFrame(columns=["PN", "Commande", "Code_acheteur", "CCN_cmd", "Code_fournisseur_cmd", "Fournisseur",
                                                 "Date_emission", "Date_demandee", "PSD", "Qty_restant"]))
    if len(o):
        g = o.groupby("PNR")
        agg = pd.DataFrame({
            "Nb lignes commande": g.size(),
            "Prochaine livraison promise": g["Date livraison promise"].min(),
            "Prochaine livraison demandee": g["Date livraison demandee"].min(),
        })
        for col, nom in [("Commande", "Commandes (liste)"), ("Fournisseur", "Fournisseurs (liste)")]:
            agg[nom] = tf.joindre_par_groupe(o, "PNR", col, " ; ")
        pbi = pbi.merge(agg, left_on="PNR", right_index=True, how="left")
        pbi = pbi.merge(fournisseur_principal(o), left_on="PNR", right_index=True, how="left")
    else:
        pbi["Fournisseur principal"] = np.nan
    pbi["Nb lignes commande"] = pbi.get("Nb lignes commande", pd.Series(0, index=pbi.index)).fillna(0).astype(int)
    pbi = ajouter_consommation(pbi)

    o = o[o["PNR"].isin(set(pbi["PNR"]))]  # commandes des PN présents au stock (cohérent avec la table stock)
    stock_pn = pbi.drop_duplicates("PNR").set_index("PNR")["QTE SUR ÉTAGÈRE"]
    o = o.assign(**{"QTE SUR ÉTAGÈRE": o["PNR"].map(stock_pn)})  # stock du PN, à côté de chaque ligne de commande
    o = o.merge(ref[["PNR", "REF_Equipement", "REF_Description"]], on="PNR", how="left")
    o = ajouter_metriques_commandes(o, today)
    if seulement_textile and len(catalogue):
        pbi = pbi[pbi["REF_Equipement"].notna()]
        o = o[o["REF_Equipement"].notna()]
    return pbi.reset_index(drop=True), o.reset_index(drop=True)


# --------------------------------------------------------------------------
# Synthèses
# --------------------------------------------------------------------------
def synthese(s: pd.DataFrame, o: pd.DataFrame) -> dict:
    statut = o["Statut commande"] if len(o) else pd.Series(dtype=object)
    return {
        "pn": int(len(s)),
        "valeur_stock": float(s["Valeur stock (€)"].sum()),
        "valeur_commande": float(s["Valeur en commande (€)"].sum()),
        "valeur_dormant": float(s["Valeur stock dormant (€)"].sum()),
        "lignes": int(len(o)),
        "en_retard": int((statut == "En retard").sum()),
        "sans_date": int((statut == "Sans date promise").sum()),
        "bfe": int((statut == "En attente BFE").sum()),
        "fournisseurs": int(o["Fournisseur"].nunique()) if len(o) else 0,
        "dormants": int((s["Statut activité"] == "Dormant").sum()),
        "inactifs": int((s["Statut activité"] == "Inactif").sum()),
    }


def resume_categories(s: pd.DataFrame, o: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in categories(s):
        d = s[categorie(s) == c]
        od = o[categorie(o) == c] if len(o) else o
        rows.append({
            "Catégorie": c, "PN": len(d), "Stock étagère": d["QTE SUR ÉTAGÈRE"].sum(), "Valeur stock (€)": d["Valeur stock (€)"].sum(),
            "En commande": d["QTE EN CDE"].sum(), "Valeur en commande (€)": d["Valeur en commande (€)"].sum(),
            "Conso 12M": _num(d, "QTE CONSO 12M").sum(),
            "PN actifs": int((d["Statut activité"] == "Actif").sum()), "PN dormants": int((d["Statut activité"] == "Dormant").sum()),
            "PN inactifs": int((d["Statut activité"] == "Inactif").sum()), "Lignes de commande": len(od),
            "Commandes en retard": int((od["Statut commande"] == "En retard").sum()) if len(od) else 0,
        })
    df = pd.DataFrame(rows)
    if len(df) > 1:
        df = pd.concat([df, pd.DataFrame([{"Catégorie": "TOTAL", **df.drop(columns="Catégorie").sum().to_dict()}])], ignore_index=True)
    return df


def poids_par_categorie(s: pd.DataFrame, o: pd.DataFrame) -> pd.DataFrame:
    """Lignes = indicateurs, colonnes = catégories : part de chaque catégorie dans chaque indicateur."""
    cats = categories(s)
    ind = {"PN": lambda d, od: len(d), "Valeur du stock": lambda d, od: d["Valeur stock (€)"].sum(),
           "Valeur en commande": lambda d, od: d["Valeur en commande (€)"].sum(),
           "Conso 12 mois": lambda d, od: _num(d, "QTE CONSO 12M").sum(), "Lignes de commande": lambda d, od: len(od)}
    t = pd.DataFrame(index=list(ind), columns=cats, dtype=float)
    for c in cats:
        d = s[categorie(s) == c]
        od = o[categorie(o) == c] if len(o) else o
        for k, f in ind.items():
            t.loc[k, c] = float(f(d, od))
    return t


def activite_par_categorie(s: pd.DataFrame) -> pd.DataFrame:
    ct = s.assign(c=categorie(s)).groupby(["c", "Statut activité"]).size().unstack(fill_value=0)
    return ct.reindex(index=categories(s), columns=[a for a in ACTIVITY_ORDER if a in ct.columns], fill_value=0)


def conso_par_categorie(s: pd.DataFrame) -> pd.DataFrame:
    annees = annees_conso(s)
    rows = []
    for c in categories(s):
        d = s[categorie(s) == c]
        r = {"Catégorie": c}
        for a in annees:
            r[str(a)] = _num(d, f"QTE CONSO {a}").sum()
        if len(annees) >= 2:
            a, b = str(annees[-1]), str(annees[-2])
            r[f"Evolution {a} vs {b} (%)"] = round((r[a] / r[b] - 1) * 100) if r[b] else np.nan
        r["12M"], r["18M"], r["24M"] = (_num(d, w).sum() for w in WINDOW_COLUMNS)
        prev = r["24M"] - r["12M"]
        r["Evolution 12M vs 12M précédents (%)"] = round((r["12M"] / prev - 1) * 100) if prev > 0 else np.nan
        rows.append(r)
    return pd.DataFrame(rows)


def statut_commandes_par_categorie(o: pd.DataFrame) -> pd.DataFrame:
    ct = o.assign(c=categorie(o)).groupby(["c", "Statut commande"]).size().unstack(fill_value=0)
    ct = ct.reindex(columns=[c for c in ORDER_STATUS_ORDER if c in ct.columns], fill_value=0)
    return ct.reindex([c for c in categories(o) if c in ct.index])


def profondeur_retards(o: pd.DataFrame) -> pd.DataFrame:
    """Lignes en retard par classe de retard (lignes) et catégorie (colonnes)."""
    late = o[o["Statut commande"] == "En retard"]
    labels = [b[0] for b in DELAY_BUCKETS]
    if late.empty:
        return pd.DataFrame(index=labels)
    ct = late.assign(c=categorie(late)).groupby(["Classe de retard", "c"]).size().unstack(fill_value=0).reindex(labels, fill_value=0)
    return ct[[c for c in categories(late) if c in ct.columns]]


def tableau_retards(o: pd.DataFrame) -> pd.DataFrame:
    late = o[o["Statut commande"] == "En retard"]
    labels = [b[0] for b in DELAY_BUCKETS]
    if late.empty:
        return pd.DataFrame({"Classe de retard": labels, "Lignes": 0, "Part (%)": 0.0, "Retard moyen (j)": np.nan, "Fournisseurs": 0})
    g = late.groupby("Classe de retard").agg(Lignes=("PNR", "size"), **{"Retard moyen (j)": ("Jours de retard", "mean")},
                                              Fournisseurs=("Fournisseur", "nunique")).reindex(labels)
    g["Lignes"] = g["Lignes"].fillna(0).astype(int)
    g["Fournisseurs"] = g["Fournisseurs"].fillna(0).astype(int)
    g["Part (%)"] = (g["Lignes"] / g["Lignes"].sum() * 100).round(1)
    g["Retard moyen (j)"] = g["Retard moyen (j)"].round(0)
    return g.reset_index().rename(columns={"index": "Classe de retard"})[["Classe de retard", "Lignes", "Part (%)", "Retard moyen (j)", "Fournisseurs"]]


def commandes_emises_par_mois(o: pd.DataFrame) -> pd.DataFrame:
    """Lignes émises par mois (index = début de mois) et par catégorie."""
    d = o.dropna(subset=["Date emission commande"])
    if d.empty:
        return pd.DataFrame()
    d = d.assign(m=d["Date emission commande"].dt.to_period("M").dt.start_time, c=categorie(d))
    mois = pd.date_range(d["m"].min(), d["m"].max(), freq="MS")
    ct = d.groupby(["m", "c"]).size().unstack(fill_value=0).reindex(mois, fill_value=0)
    return ct[[c for c in categories(d) if c in ct.columns]]


def fenetre_emissions(today):
    """Période affichée au départ : depuis janvier de l'année précédente (on peut dézoomer)."""
    t = pd.Timestamp(today)
    return pd.Timestamp(t.year - 1, 1, 1), t + pd.DateOffset(months=1)


def planning_livraisons(o: pd.DataFrame) -> pd.DataFrame:
    """Lignes à livrer par mois (index = début de mois) : date promise si connue, sinon date demandée."""
    pro = o["Date livraison promise"].dropna().dt.to_period("M").dt.start_time.value_counts()
    dem = o.loc[o["Date livraison promise"].isna(), "Date livraison demandee"].dropna().dt.to_period("M").dt.start_time.value_counts()
    if pro.empty and dem.empty:
        return pd.DataFrame()
    debut, fin = min(pro.index.min() if len(pro) else dem.index.min(), dem.index.min() if len(dem) else pro.index.min()), \
        max(pro.index.max() if len(pro) else dem.index.max(), dem.index.max() if len(dem) else pro.index.max())
    mois = pd.date_range(debut, fin, freq="MS")
    return pd.DataFrame({"Avec date promise": pro.reindex(mois, fill_value=0),
                         "Sans date promise (date demandée)": dem.reindex(mois, fill_value=0)})


def fenetre_planning(today, passe=3, horizon=9):
    t = pd.Timestamp(today)
    return (t - pd.DateOffset(months=passe)).to_period("M").start_time, (t + pd.DateOffset(months=horizon)).to_period("M").start_time


def chaleur_livraisons(o: pd.DataFrame, today, top=12, passe=2, horizon=10) -> pd.DataFrame:
    d = o.dropna(subset=["Date livraison promise", "Fournisseur"])
    if d.empty:
        return pd.DataFrame()
    t = pd.Timestamp(today)
    debut, fin = (t - pd.DateOffset(months=passe)).to_period("M"), (t + pd.DateOffset(months=horizon)).to_period("M")
    axe = [m.strftime("%m/%y") for m in pd.period_range(debut, fin, freq="M")]
    top_f = d["Fournisseur"].value_counts().head(top).index
    p = d["Date livraison promise"].dt.to_period("M")
    d = d[d["Fournisseur"].isin(top_f) & (p >= debut) & (p <= fin)]
    d = d.assign(m=d["Date livraison promise"].dt.strftime("%m/%y"))
    return d.groupby(["Fournisseur", "m"]).size().unstack(fill_value=0).reindex(index=top_f, columns=axe, fill_value=0)


def relances(o: pd.DataFrame) -> pd.DataFrame:
    """Lignes à relancer, de la pire à la meilleure : retards (plus gros retard d'abord), sans date promise, BFE.

    Seules les lignes avec une quantité restant à livrer (ou non renseignée) sont proposées.
    """
    reste = o["Qte restante"].isna() | (o["Qte restante"] > 0)
    d = o[reste & o["Statut commande"].isin(["En retard", "Sans date promise", "En attente BFE"])].copy()
    rang = {"En retard": 0, "Sans date promise": 1, "En attente BFE": 2}
    d["_r"] = d["Statut commande"].map(rang)
    d["_k"] = np.select([d["_r"] == 0, d["_r"] == 1], [d["Jours de retard"], d["Demande dépassée (j)"]], default=d["Age commande (j)"])
    return d.sort_values(["_r", "_k"], ascending=[True, False], kind="stable").drop(columns=["_r", "_k"])
