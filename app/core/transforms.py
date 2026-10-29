"""Agrégations et croisements réutilisables : besoins chantier × état du stock × commandes.

Fonctions pures (pandas uniquement), testables sans Streamlit. Logique métier reprise
à l'identique du script d'origine `legacy/streamlit_GEAV.py`, vectorisée pour Pyodide.
"""

import numpy as np
import pandas as pd

CLASSES_RISQUE = [8.0, 9.0]
# Les fournisseurs saisissent une PSD en 2031 quand ils n'ont pas encore donné de date.
ANNEE_PSD_NON_FOURNIE = 2031
SEP = " | "
# Dernier recours, quand ni les commandes ni l'État du stock ne donnent de nom ou de code.
FOURNISSEUR_ABSENT = "fournisseur non renseigné"

# --------------------------------------------------------------------------
# Codes action (du pire au meilleur)
# --------------------------------------------------------------------------
ACTION_ORDRE = ["commander", "relancer_urgent", "relancer", "inconnu", "en_cours", "hors_perimetre", "ok"]
ACTIONS_A_LANCER = ["commander", "relancer_urgent", "relancer", "inconnu"]
ACTION_LABELS = {
    "commander": "À commander",
    "relancer_urgent": "Relance urgente",
    "relancer": "À relancer",
    "inconnu": "PN introuvable",
    "en_cours": "En cours de livraison",
    "hors_perimetre": "Hors périmètre",
    "ok": "Stock suffisant",
}
# Couleur de chaque statut (palette de core/style.py) : badges de l'interface, graphes, cellule Statut de l'export
ACTION_COULEURS = {
    "commander": "#A61B1B", "relancer_urgent": "#E8590C", "relancer": "#DBA100", "inconnu": "#9AA5B1",
    "en_cours": "#2B6CB0", "hors_perimetre": "#B5BDCB", "ok": "#1E8E5A",
}
# Fonds teintés de l'export Excel (mêmes teintes que les badges de l'interface)
ACTION_FILL_HEX = {
    "commander": "FBECEC", "relancer_urgent": "FDF0E7", "relancer": "FDF6DD",
    "en_cours": "E9F1FA", "ok": "E6F4EC", "hors_perimetre": "F3F5F8", "inconnu": "EEF1F5",
}


# --------------------------------------------------------------------------
# Utilitaires d'agrégation
# --------------------------------------------------------------------------
def joindre_uniques(serie: pd.Series, sep: str = SEP):
    """Valeurs non vides, dédoublonnées dans l'ordre, jointes par `sep` (NaN si aucune)."""
    vals = [str(v).strip() for v in serie
            if pd.notna(v) and str(v).strip() and str(v).strip().lower() != "nan"]
    return sep.join(dict.fromkeys(vals)) if vals else np.nan


def joindre_par_groupe(df: pd.DataFrame, cle: str, col: str, sep: str = SEP) -> pd.Series:
    """Équivalent vectorisé de `groupby(cle)[col].agg(joindre_uniques)` (index = clé).

    Sans `groupby().agg` (une fonction Python par groupe, lent sous Pyodide) : tri stable par clé
    puis une seule boucle sur des listes.
    """
    s = df[col].astype(object).map(str, na_action="ignore").astype(object).str.strip()  # colonne vide (tout NaN) acceptée
    garde = s.notna() & (s != "") & (s.str.lower() != "nan")
    tmp = pd.DataFrame({cle: df[cle], col: s})[garde].drop_duplicates()
    if tmp.empty:
        return pd.Series(dtype=object, name=col)
    codes, uniques = pd.factorize(tmp[cle], sort=False)
    ordre = np.argsort(codes, kind="stable")
    c = codes[ordre]
    vals = tmp[col].to_numpy()[ordre].tolist()
    bornes = np.flatnonzero(np.diff(c)) + 1
    debuts, fins = np.r_[0, bornes], np.r_[bornes, len(c)]
    index = pd.Index(uniques.take(c[debuts]), name=cle)
    return pd.Series([sep.join(vals[a:b]) for a, b in zip(debuts, fins)], index=index, name=col)


def _plus_frequent(cles: pd.Series, valeurs: pd.Series) -> pd.Series:
    """Par clé : valeur non vide la plus fréquente (première rencontrée en cas d'égalité)."""
    d = pd.DataFrame({"k": cles, "v": valeurs}).dropna()
    if d.empty:
        return pd.Series(dtype=object)
    n = d.groupby(["k", "v"], sort=False).size().reset_index(name="n")
    return n.sort_values("n", ascending=False, kind="stable").drop_duplicates("k").set_index("k")["v"]


def completer_fournisseurs(lignes: pd.DataFrame) -> pd.Series:
    """Fournisseur de chaque ligne de commande, sans jamais laisser « fournisseur inconnu ».

    Règle (demande métier) quand la colonne Fournisseur est vide :
    1. nom associé au même code fournisseur sur les autres lignes du fichier ;
    2. sinon, fournisseur le plus fréquent sur les autres lignes du même PN ;
    3. sinon, le code fournisseur lui-même (« Code F123 ») ;
    4. sinon, via le code fournisseur le plus fréquent du même PN.
    Reste vide uniquement si la ligne et son PN n'ont ni nom ni code.
    """
    nom = lignes["Fournisseur"].where(lignes["Fournisseur"].notna(), np.nan)
    code = lignes["Code_fournisseur_cmd"]
    nom_par_code = _plus_frequent(code, nom)
    nom = nom.fillna(code.map(nom_par_code))
    nom = nom.fillna(lignes["PN"].map(_plus_frequent(lignes["PN"], nom)))
    nom = nom.fillna(("Code " + code.astype(object)).where(code.notna()))
    code_pn = lignes["PN"].map(_plus_frequent(lignes["PN"], code))
    nom = nom.fillna(code_pn.map(nom_par_code)).fillna(("Code " + code_pn.astype(object)).where(code_pn.notna()))
    return nom.astype(object)


def _premier_prioritaire(df: pd.DataFrame, cle: str, col: str, prioritaires) -> pd.Series:
    """Par groupe : première valeur figurant dans `prioritaires`, sinon première non vide."""
    rang = (~df[col].isin(prioritaires)).astype(int)
    ordonne = df.assign(_rang=rang).sort_values("_rang", kind="stable")
    return ordonne.groupby(cle)[col].first()


# --------------------------------------------------------------------------
# Agrégation par PN
# --------------------------------------------------------------------------
def agreger_besoins(lignes: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par PN : quantités SOMMÉES sur toutes les lignes du fichier besoins (un même PN demandé par
    plusieurs TRFX / RRS = un seul besoin, total) ; TRFX et RRS listés (« A | B »)."""
    g = lignes.groupby("PN")
    out = pd.DataFrame({"QTY_GEAV": g["Qty"].sum(), "Nb_lignes": g["Qty"].size()})
    if "Description" in lignes.columns:
        out["Description"] = joindre_par_groupe(lignes, "PN", "Description").reindex(out.index)
    for col in ("TRFX", "RRS"):
        out[col] = joindre_par_groupe(lignes, "PN", col).reindex(out.index) if col in lignes.columns else np.nan
    out["QTY_GEAV"] = out["QTY_GEAV"].astype(int)
    return out.reset_index()


def agreger_stock(lignes: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par PN. Un PNR est censé être unique ; en cas de doublon on prend le max
    du stock / des quantités en commande et la classe 8/9 si elle apparaît."""
    g = lignes.groupby("PN")
    out = pd.DataFrame({
        "QTY_STOCK": g["QTY_STOCK"].max(),
        "QTY_CDE": g["QTY_CDE"].max(),
        "GESTION": g["GESTION"].first(),
        "CODE_AGENT": g["CODE_AGENT"].first(),
        "CODE_FOURNISSEUR": g["CODE_FOURNISSEUR"].first(),
        "DERNIER_FOURNISSEUR": g["DERNIER_FOURNISSEUR"].first(),
        "Description_stock": g["Description_stock"].first(),
        "CCN": g["CCN"].first(),
        "TL": g["TL"].first() if "TL" in lignes else np.nan,
        # QTE SAR et Purchase Req. (quantité en demande d'achat) : comme le stock, maximum en cas de doublon
        "QTE_SAR": g["QTE SAR"].max() if "QTE SAR" in lignes else np.nan,
        "QTE_PR": g["Purchase Req."].max() if "Purchase Req." in lignes else np.nan,
    })
    out["CLASS_CODE_STOCK"] = _premier_prioritaire(lignes, "PN", "CLASS_CODE_STOCK", CLASSES_RISQUE)
    return out.reset_index()


def agreger_commandes(lignes: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par PN, triée par date de livraison : la PSD retenue est la plus proche."""
    d = lignes.sort_values("PSD_effective", kind="stable")
    g = d.groupby("PN")
    out = pd.DataFrame({
        "Commande": joindre_par_groupe(d, "PN", "Commande"),
        "Code_acheteur": joindre_par_groupe(d, "PN", "Code_acheteur"),
    }).reindex(g.size().index)
    out["Gestion_cmd"] = g["Gestion_cmd"].first()
    out["Code_fournisseur_cmd"] = joindre_par_groupe(d, "PN", "Code_fournisseur_cmd")
    out["Fournisseur"] = joindre_par_groupe(d, "PN", "Fournisseur")
    out["PSD"] = g["PSD_effective"].min()
    out["PSD_est_estimee"] = g["PSD_est_estimee"].first()
    out["Statut"] = joindre_par_groupe(d, "PN", "Statut")
    out["Qty_restant_cmd"] = g["Qty_restant"].sum()
    out["Nb_commandes"] = g["Commande"].nunique()
    out["Class_code"] = g["Class_code"].first()
    out["Has_risk_class"] = d["Class_code"].isin(CLASSES_RISQUE).groupby(d["PN"]).any()
    out["CCN_cmd"] = g["CCN_cmd"].first()
    return out.reset_index()


# --------------------------------------------------------------------------
# Croisement besoins × stock × commandes et action recommandée
# --------------------------------------------------------------------------
def _non_vide(s: pd.Series) -> pd.Series:
    return s.notna() & (s.astype(str).str.strip() != "")


def croiser_geav(besoin: pd.DataFrame, stock: pd.DataFrame, commandes: pd.DataFrame,
                 gestion_scope, date_chantier) -> pd.DataFrame:
    """Croise les trois sources (agrégées par PN) et calcule l'action recommandée.

    - Deficit = max(0, QTY_GEAV - QTY_STOCK) : quantité manquante maintenant ;
    - Qty_a_commander = max(0, Deficit - QTY_CDE) : quantité non couverte par les commandes ;
    - la PSD est comparée à la date de début du chantier pour savoir si la livraison
      arrivera à temps.
    """
    date_chantier = pd.Timestamp(date_chantier)
    m = besoin.copy()
    m["GEAV_DATE"] = date_chantier
    for col in ("TRFX", "RRS"):
        if col not in m.columns:
            m[col] = np.nan

    m = m.merge(stock, on="PN", how="left")
    # Gestion : celle du fichier Commandes fait foi, repli sur l'État du stock.
    gest_cmd = commandes[["PN", "Gestion_cmd"]].drop_duplicates("PN")
    m = m.merge(gest_cmd, on="PN", how="left")
    m["GESTION"] = m["Gestion_cmd"].where(m["Gestion_cmd"].notna(), m["GESTION"])
    m = m.drop(columns=["Gestion_cmd"])
    m["in_stock_file"] = m["QTY_STOCK"].notna() | m["QTY_CDE"].notna()
    m[["QTY_STOCK", "QTY_CDE"]] = m[["QTY_STOCK", "QTY_CDE"]].fillna(0)
    m["gestion_in_scope"] = m["GESTION"].isin({float(g) for g in gestion_scope})

    m = m.merge(commandes.drop(columns=["Gestion_cmd"]), on="PN", how="left")
    m["Deficit"] = (m["QTY_GEAV"] - m["QTY_STOCK"]).clip(lower=0).astype(int)
    m["Qty_a_commander"] = (m["Deficit"] - m["QTY_CDE"]).clip(lower=0).astype(int)

    m["FOURNISSEUR"] = m["Fournisseur"].where(_non_vide(m["Fournisseur"]), m["DERNIER_FOURNISSEUR"])
    m["CODE_FOURNISSEUR"] = m["CODE_FOURNISSEUR"].where(m["CODE_FOURNISSEUR"].notna(), m["Code_fournisseur_cmd"])
    # Contact : CODE AGT APPRO de l'État du stock (« Code agent ») ; le code acheteur des commandes n'est plus utilisé.
    m["CCN"] = m["CCN"].where(m["CCN"].notna(), m["CCN_cmd"])
    # Classe 8/9 : alerte si présente dans les commandes ou dans l'État du stock.
    m["CLASS_CODE"] = m["Class_code"].where(m["Class_code"].isin(CLASSES_RISQUE), m["CLASS_CODE_STOCK"])
    m["CLASS_CODE"] = m["CLASS_CODE"].where(m["CLASS_CODE"].notna(), m["Class_code"])
    m["RISK_CLASS"] = m["CLASS_CODE"].isin(CLASSES_RISQUE) | m["Has_risk_class"].eq(True)

    code, message = _actions(m)
    m["ACTION"] = message
    m["ACTION_CODE"] = code
    risque = m["RISK_CLASS"] & (m["ACTION_CODE"] != "inconnu")
    m.loc[risque, "ACTION"] = "🚨 CLASSE 8/9 — PRIORITÉ : " + m.loc[risque, "ACTION"]
    return m


def _actions(m: pd.DataFrame):
    """(codes, messages) de l'action recommandée, ligne à ligne mais vectorisé."""
    agent = m["CODE_AGENT"].where(_non_vide(m["CODE_AGENT"]), "?").astype(str)
    fourn = (m["FOURNISSEUR"].where(_non_vide(m["FOURNISSEUR"]),
                                    m["CODE_FOURNISSEUR"].where(_non_vide(m["CODE_FOURNISSEUR"]),
                                                                FOURNISSEUR_ABSENT))
             .astype(str))
    psd = pd.to_datetime(m["PSD"])
    psd_txt = psd.dt.strftime("%d/%m/%Y")
    psd_manquante = psd.notna() & (psd.dt.year == ANNEE_PSD_NON_FOURNIE)
    psd_tardive = (m["GEAV_DATE"].notna() & psd.notna()
                   & (psd.dt.normalize() > m["GEAV_DATE"].dt.normalize()) & ~psd_manquante)
    gestion = m["GESTION"].map(lambda g: "?" if pd.isna(g) else str(int(g)))
    deficit = m["Deficit"].astype(str)
    a_cmd = m["Qty_a_commander"].astype(str)
    contact = " (contact: " + agent + ")"

    regles = [  # (condition, code, message) — la première condition vraie l'emporte
        (~m["in_stock_file"], "inconnu",
         pd.Series("❓ PN introuvable dans le fichier État du stock (à vérifier manuellement)", index=m.index)),
        (~m["gestion_in_scope"], "hors_perimetre",
         "⚠️ Besoin de " + deficit + " — Gestion " + gestion + " hors périmètre (contacter " + agent + ")"),
        ((m["Qty_a_commander"] > 0) & (m["QTY_CDE"] > 0), "commander",
         "🔴 Commander le complément (" + a_cmd + ") + relancer " + fourn + contact),
        (m["Qty_a_commander"] > 0, "commander",
         "🔴 Commander " + a_cmd + " — aucune commande en cours" + contact),
        (m["Deficit"] <= 0, "ok",
         pd.Series("🟢 Stock suffisant — aucune action", index=m.index)),
        (psd.isna() | psd_manquante, "relancer",
         "🟠 Relancer " + fourn + " — commande en cours, PSD manquante ou à confirmer" + contact),
        (psd_tardive, "relancer_urgent",
         "🔴 Relancer " + fourn + " — PSD " + psd_txt.fillna("") + " après la date limite GEAV" + contact),
        (pd.Series(True, index=m.index), "en_cours",
         "🔵 Livraison en cours — PSD " + psd_txt.fillna("") + " (" + fourn + ")"),
    ]
    code = pd.Series(None, index=m.index, dtype=object)
    message = pd.Series(None, index=m.index, dtype=object)
    for cond, c, msg in regles:
        libre = code.isna() & cond.fillna(False).astype(bool)
        code[libre] = c
        message[libre] = msg[libre]
    return code, message


# --------------------------------------------------------------------------
# Synthèse et priorisation
# --------------------------------------------------------------------------
def synthese_geav(m_scope: pd.DataFrame) -> dict:
    codes = m_scope["ACTION_CODE"]
    return {
        "n_total": int(len(m_scope)),
        "n_commander": int((codes == "commander").sum()),
        "qty_a_commander": int(m_scope.loc[codes == "commander", "Qty_a_commander"].sum()),
        "n_relance": int(codes.isin(["relancer", "relancer_urgent"]).sum()),
        "n_relance_urgente": int((codes == "relancer_urgent").sum()),
        "n_en_cours": int((codes == "en_cours").sum()),
        "n_ok": int((codes == "ok").sum()),
        "n_inconnu": int((codes == "inconnu").sum()),
        "n_risque": int(m_scope["RISK_CLASS"].sum()),
    }


def actions_a_lancer(m_scope: pd.DataFrame) -> pd.DataFrame:
    """Lignes qui demandent une action, du pire au meilleur : classe 8/9 d'abord,
    puis commander > relance urgente > relancer > PN introuvable, puis quantité."""
    a = m_scope[m_scope["ACTION_CODE"].isin(ACTIONS_A_LANCER)].copy()
    a["_ordre"] = a["ACTION_CODE"].map({c: i for i, c in enumerate(ACTION_ORDRE)})
    a = a.sort_values(["RISK_CLASS", "_ordre", "Qty_a_commander", "PSD"],
                      ascending=[False, True, False, True], kind="stable")
    return a.drop(columns="_ordre")


def jours_avant(date_debut, aujourd_hui) -> int:
    return int((pd.Timestamp(date_debut).normalize() - pd.Timestamp(aujourd_hui).normalize()).days)
