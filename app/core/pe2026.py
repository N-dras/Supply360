"""PE mousses de l'année : objectif du fichier Besoin Prod × État du stock × Commandes (SAP), par CCN.

Repris du Streamlit « Pilotage Politique d'entretien Mousse » (legacy) :
- par CCN : besoin de l'année, stock, en commande, écart, quantité à demander (PR), action ;
- par type d'avion × classe : avions faisables avec le stock, à réception des commandes, à approvisionner ;
- avions restant à traiter : recalculés avec le fichier PE mousses (remplacements faits depuis le 1er janvier).

Fonctions pures (testables sans Streamlit).
"""

from datetime import date

import numpy as np
import pandas as pd

from core import io as sio
from core import pe

FICHIER_BESOIN = "Besoin Prod mousses"

ACTIONS = ["PR à émettre (aucune commande)", "PR complémentaire (commandes insuffisantes)",
           "À réceptionner (commandes en cours)", "Couvert par le stock"]
ACTION_COULEURS = dict(zip(ACTIONS, ["#C62828", "#F4A259", "#1F4E9C", "#1E8E5A"]))
AVANCEMENT = ["Complets maintenant", "Complets à réception", "À approvisionner"]
AVANCEMENT_COULEURS = dict(zip(AVANCEMENT, ["#1E8E5A", "#1F4E9C", "#E4002B"]))
RESTANT_AUTO, RESTANT_FICHIER = "auto", "fichier"


def code_ccn(serie: pd.Series) -> pd.Series:
    """CCN en texte sans décimale (1501513.0 → « 1501513 »)."""
    return sio.texte(serie).str.replace(r"\.0$", "", regex=True)


# --------------------------------------------------------------------------
# Lecture du fichier Besoin Prod (feuille « QUOTE en euro »)
# --------------------------------------------------------------------------
def lire_besoin_prod(data: bytes, nom: str = FICHIER_BESOIN):
    """Une ligne par type d'avion × classe × CCN. Renvoie (lignes, feuille).

    Colonnes utilisées : A/C (type d'avion), Flotte, NB_AC, NB_AC PE RESTANT, Area (classe), CCN,
    P/N OEM Seat Supplier, Seat Supplier, Description, Qty per A/C, prix (P.U forecast PE / P.U OEM).
    """
    xl = sio.ouvrir_excel(data, FICHIER_BESOIN)
    feuille, entete = sio.choisir_feuille(xl, ["ccn", "qty per a/c", "nb_ac"], feuille_preferee="QUOTE en euro")
    df = sio.lire_feuille(xl, feuille, entete)
    col = {
        "type": sio.trouver_colonne(df, "a/c", exact=True),
        "flotte": sio.trouver_colonne(df, "flotte", exact=True),
        "nb": sio.trouver_colonne(df, "nb_ac", exact=True),
        "restant": sio.trouver_colonne(df, "nb_ac pe restant"),
        "area": sio.trouver_colonne(df, "area", exact=True) or sio.trouver_colonne(df, "classe", "area"),
        "ccn": sio.trouver_colonne(df, "ccn", exact=True),
        "pn": sio.trouver_colonne(df, "p/n oem seat supplier", "p/n oem"),
        "fournisseur": sio.trouver_colonne(df, "seat supplier", exact=True),
        "desc": sio.trouver_colonne(df, "description", exact=True),
        "qte": sio.trouver_colonne(df, "qty per a/c"),
        "pu_pe": sio.trouver_colonne(df, "p.u forecast pe"),
        "pu_oem": sio.trouver_colonne(df, "p.u oem"),
    }
    for cle, libelle in [("type", "A/C"), ("ccn", "CCN"), ("qte", "Qty per A/C"), ("nb", "NB_AC"), ("area", "Area")]:
        if col[cle] is None:
            raise sio.ColonneIntrouvable(libelle, FICHIER_BESOIN, feuille, df.columns)

    def num(c):
        return sio.nombre(df[col[c]]) if col[c] else pd.Series(np.nan, index=df.index)

    def txt(c):
        return sio.texte(df[col[c]]) if col[c] else pd.Series(np.nan, index=df.index, dtype=object)

    out = pd.DataFrame({
        "Type avion": txt("type"), "Flotte": txt("flotte"), "Classe": txt("area").str.upper(),
        "CCN": code_ccn(df[col["ccn"]]), "PN": sio.cle_pn(df[col["pn"]]) if col["pn"] else np.nan,
        "Fournisseur": txt("fournisseur"), "Désignation": txt("desc"),
        "Qté par avion": num("qte").fillna(0), "NB_AC": num("nb").fillna(0).astype(int),
        "Restant fichier": num("restant"), "PU devis (€)": num("pu_pe").fillna(num("pu_oem")),
    })
    out["Composant"] = out["Désignation"].map(pe.composant_mousse)
    out = out[out["CCN"].notna() & out["Type avion"].notna()].reset_index(drop=True)
    if out.empty:
        raise sio.FichierIllisible(f"Fichier {FICHIER_BESOIN} : aucune ligne avec un CCN et un type d'avion (A/C).")
    return out, feuille


# --------------------------------------------------------------------------
# Avions restant à traiter : recalcul avec le fichier PE mousses
# --------------------------------------------------------------------------
def rattacher_avions(bp: pd.DataFrame, parts: pd.DataFrame) -> pd.DataFrame:
    """Type d'avion (A/C du Besoin Prod) de chaque immatriculation de textile_all_parts.

    Aucun fichier ne relie directement immatriculation et type d'avion : on compare les CCN de mousses
    de chaque avion (par classe) à ceux de chaque type ; le type qui en partage le plus est retenu.
    Renvoie Immatriculation, cle, Type avion, CCN communs, Ambigu.
    """
    vide = pd.DataFrame(columns=["Immatriculation", "cle", "Type avion", "CCN communs", "Ambigu"])
    if parts is None or parts.empty or "ccn" not in parts:
        return vide
    m = parts[parts["equipment"].astype(str).str.upper() == "MOUSSE"]
    m = pd.DataFrame({"Immatriculation": m["registration"].astype(str), "Classe": m["area"].astype(str).str.strip().str.upper(),
                      "CCN": code_ccn(m["ccn"])}).dropna().drop_duplicates()
    if m.empty:
        return vide
    types = bp[["Type avion", "Classe", "CCN"]].drop_duplicates()
    commun = m.merge(types, on=["Classe", "CCN"]).groupby(["Immatriculation", "Type avion"]).size().rename("CCN communs")
    if commun.empty:
        return vide
    commun = commun.reset_index().sort_values(["Immatriculation", "CCN communs", "Type avion"], ascending=[True, False, True])
    meilleur = commun.groupby("Immatriculation")["CCN communs"].transform("max")
    ex_aequo = commun[commun["CCN communs"] == meilleur].groupby("Immatriculation").size()
    out = commun.drop_duplicates("Immatriculation").copy()
    out["Ambigu"] = out["Immatriculation"].map(ex_aequo).fillna(1) > 1
    out["cle"] = out["Immatriculation"].map(pe._cle_immat)
    return out[["Immatriculation", "cle", "Type avion", "CCN communs", "Ambigu"]].reset_index(drop=True)


def remplaces_depuis(cal: pd.DataFrame, debut: date) -> pd.DataFrame:
    """Éléments (immat, classe, composant) dont la mousse a été remplacée depuis `debut` (âge exact du fichier PE)."""
    if cal is None or cal.empty:
        return pd.DataFrame(columns=["cle", "Classe", "Composant"])
    fait = cal[cal["Âge exact"] & (cal["Dernier remplacement"] >= pd.Timestamp(debut))]
    return pd.DataFrame({"cle": fait["Immatriculation"].map(pe._cle_immat), "Classe": fait["Classe"].astype(str),
                         "Composant": fait["Composant"].astype(str)}).drop_duplicates()


def avions_restants(bp: pd.DataFrame, rattachement: pd.DataFrame, faits: pd.DataFrame, mode: str = RESTANT_AUTO) -> pd.DataFrame:
    """Ajoute à `bp` : Avions rattachés, Remplacés cette année, Restant calculé, Avions restants (retenu), Source restant.

    Restant calculé = NB_AC − avions du type déjà remplacés depuis le 1er janvier (classe et élément de la ligne),
    seulement si des avions du type sont rattachés et l'élément reconnu (assise / dossier).
    Mode « auto » : restant calculé, sinon NB_AC PE RESTANT du fichier, sinon NB_AC.
    Mode « fichier » : NB_AC PE RESTANT du fichier, sinon NB_AC (règle du Streamlit d'origine).
    """
    b = bp.copy()
    nb_rattaches = rattachement.groupby("Type avion").size() if len(rattachement) else pd.Series(dtype=int)
    b["Avions rattachés"] = b["Type avion"].map(nb_rattaches).fillna(0).astype(int)
    if len(rattachement) and len(faits):
        f = faits.merge(rattachement[["cle", "Type avion"]], on="cle")
        n_faits = f.groupby(["Type avion", "Classe", "Composant"]).size()
        cles = list(zip(b["Type avion"], b["Classe"].map(pe.classe_cabine), b["Composant"]))
        b["Remplacés cette année"] = [int(n_faits.get(k, 0)) for k in cles]
    else:
        b["Remplacés cette année"] = 0
    calculable = (b["Avions rattachés"] > 0) & b["Composant"].notna() & b["Classe"].map(pe.classe_cabine).notna()
    b["Restant calculé"] = np.where(calculable, (b["NB_AC"] - b["Remplacés cette année"]).clip(lower=0), np.nan)
    fichier = b["Restant fichier"].where(b["Restant fichier"].notna(), b["NB_AC"])
    if mode == RESTANT_FICHIER:
        b["Avions restants"], b["Source restant"] = fichier, np.where(b["Restant fichier"].notna(), "Fichier", "NB_AC (restant vide)")
    else:
        b["Avions restants"] = b["Restant calculé"].where(calculable, fichier)
        b["Source restant"] = np.where(calculable, "Calculé (PE mousses)",
                                       np.where(b["Restant fichier"].notna(), "Fichier", "NB_AC (restant vide)"))
    b["Avions restants"] = b["Avions restants"].fillna(0).astype(int)
    b["Besoin"] = (b["Qté par avion"] * b["Avions restants"]).round().astype(int)
    return b


# --------------------------------------------------------------------------
# Analyse par CCN
# --------------------------------------------------------------------------
def _joindre(s: pd.Series) -> str:
    vals = [str(v).strip() for v in s if pd.notna(v) and str(v).strip()]
    return ", ".join(dict.fromkeys(vals))


def ccn_commandes(cmd: pd.DataFrame | None, stock: pd.DataFrame, bp: pd.DataFrame) -> pd.DataFrame:
    """Commandes ouvertes (reste à livrer > 0) avec leur CCN : colonne CCN du fichier Commandes si elle existe,
    sinon retrouvé par le PN (État du stock, puis Besoin Prod)."""
    if cmd is None or cmd.empty:
        return pd.DataFrame(columns=["CCN", "PN", "Commande", "Fournisseur", "PSD_effective", "Qty_restant"])
    c = cmd[cmd["Qty_restant"] > 0].copy()
    par_pn = pd.concat([stock.dropna(subset=["CCN"]).drop_duplicates("PN").set_index("PN")["CCN"],
                        bp.dropna(subset=["PN"]).drop_duplicates("PN").set_index("PN")["CCN"]])
    par_pn = par_pn[~par_pn.index.duplicated()]
    propre = c["CCN_cmd"] if "CCN_cmd" in c else pd.Series(np.nan, index=c.index)
    c["CCN"] = propre.where(propre.notna(), c["PN"].map(par_pn))
    return c[c["CCN"].notna()]


def analyse_ccn(b: pd.DataFrame, stock: pd.DataFrame, cmd: pd.DataFrame | None) -> pd.DataFrame:
    """Une ligne par CCN : besoin, stock, en commande, couverture, écart, à demander (PR), valeur, action.

    Stock par CCN = max de QTE SUR ÉTAGÈRE des lignes du CCN (niveau recopié sur chaque PNR, règle d'origine).
    En commande = reste à livrer des commandes (SAP) ; sans fichier Commandes : QTE EN CDE de l'État du stock.
    Prix = Dernier PU (achat) de l'État du stock, à défaut le prix du devis (Besoin Prod) ; sans prix : « à coter ».
    """
    pv = b.groupby("CCN").agg(**{
        "PN": ("PN", _joindre), "Désignation": ("Désignation", "first"), "Fournisseur devis": ("Fournisseur", "first"),
        "Types avion": ("Type avion", _joindre), "Nb types": ("Type avion", "nunique"), "Classes": ("Classe", _joindre),
        "Besoin": ("Besoin", "sum"), "PU devis (€)": ("PU devis (€)", "max"),
    }).reset_index()
    s = stock.dropna(subset=["CCN"])
    st_ = s.groupby("CCN").agg(**{"Stock": ("QTY_STOCK", "max"), "En cde (stock)": ("QTY_CDE", "max"),
                                   "PNR stock": ("PN", _joindre)})
    if "Dernier PU (achat) Euros" in s:
        st_["PU stock (€)"] = s.groupby("CCN")["Dernier PU (achat) Euros"].max()
    m = pv.merge(st_.reset_index(), on="CCN", how="left")
    m["Dans l'État du stock"] = m["CCN"].isin(set(s["CCN"]))
    c = ccn_commandes(cmd, stock, b)
    if cmd is not None:
        g = c.groupby("CCN").agg(**{"En commande": ("Qty_restant", "sum"), "Nb commandes": ("Commande", "nunique"),
                                    "Commandes": ("Commande", _joindre), "Fournisseur": ("Fournisseur", "first"),
                                    "Prochaine livraison": ("PSD_effective", "min"), "Dernière livraison": ("PSD_effective", "max")})
        m = m.merge(g.reset_index(), on="CCN", how="left")
    else:
        m["En commande"] = m["En cde (stock)"]
        for k in ["Nb commandes", "Commandes", "Fournisseur", "Prochaine livraison", "Dernière livraison"]:
            m[k] = np.nan
    m["Fournisseur"] = m["Fournisseur"].fillna(m["Fournisseur devis"])
    for k in ["Stock", "En commande", "Nb commandes"]:
        m[k] = m[k].fillna(0)
    m["Commandes"] = m["Commandes"].fillna("")
    m["Couverture"] = m["Stock"] + m["En commande"]
    m["Écart"] = m["Besoin"] - m["Couverture"]
    m["À demander (PR)"] = m["Écart"].clip(lower=0)
    m["Taux de couverture (%)"] = np.where(m["Besoin"] > 0, (m["Couverture"] / m["Besoin"] * 100).round(0), np.nan)
    pu = m["PU stock (€)"] if "PU stock (€)" in m else pd.Series(np.nan, index=m.index)
    m["PU (€)"] = pu.where(pu > 0, m["PU devis (€)"]).fillna(0)
    m["À coter"] = (m["PU (€)"] <= 0) & (m["Besoin"] > 0)
    m["Valeur stock (€)"] = m["Stock"] * m["PU (€)"]
    m["Valeur en commande (€)"] = m["En commande"] * m["PU (€)"]
    m["Valeur à commander (€)"] = m["À demander (PR)"] * m["PU (€)"]
    m["Valeur du besoin (€)"] = m["Besoin"] * m["PU (€)"]
    commande = m["En commande"] > 0
    m["Action"] = np.select([(m["Écart"] > 0) & ~commande, m["Écart"] > 0, m["Stock"] < m["Besoin"]], ACTIONS[:3], ACTIONS[3])
    m["Priorité"] = m["Action"].map({a: i + 1 for i, a in enumerate(ACTIONS)})
    return m.sort_values(["Priorité", "À demander (PR)"], ascending=[True, False]).reset_index(drop=True)


# --------------------------------------------------------------------------
# Avions faisables (stock commun réparti entre les types d'avion)
# --------------------------------------------------------------------------
def repartir(blocs: list[tuple], dispo: dict) -> dict:
    """Avions complets par bloc, le stock d'un CCN commun étant partagé entre les blocs.

    `blocs` : [(clé, objectif, {CCN: qté par avion})] ; `dispo` : {CCN: quantité}. Un avion n'est équipé que si
    tous les CCN du bloc sont disponibles. À chaque tour, l'avion suivant va au bloc le moins avancé
    (avions équipés / objectif) : la répartition reste équilibrée entre types d'avion.
    """
    reste = {k: float(v) for k, v in dispo.items()}
    fait = {cle: 0 for cle, _, _ in blocs}
    actifs = [(cle, obj, {c: q for c, q in besoins.items() if q > 0}) for cle, obj, besoins in blocs if obj > 0 and besoins]
    while True:
        possibles = [(fait[cle] / obj, -obj, i) for i, (cle, obj, besoins) in enumerate(actifs)
                     if fait[cle] < obj and all(reste.get(c, 0) >= q for c, q in besoins.items())]
        if not possibles:
            return fait
        cle, _, besoins = actifs[min(possibles)[2]]
        for c, q in besoins.items():
            reste[c] -= q
        fait[cle] += 1


def avions_faisables(b: pd.DataFrame, m: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(blocs, détail) — blocs : une ligne par type d'avion × classe ; détail : une ligne par bloc × CCN.

    Objectif = avions restant à traiter. Complets maintenant = répartition du stock ; complets à réception =
    répartition du stock + commandes, moins les complets maintenant ; à approvisionner = le reste.
    Détail : avions couvrables par chaque CCN seul (⌊stock ÷ qté par avion⌋), sans partage avec les autres types.
    """
    d = b.groupby(["Type avion", "Classe", "CCN"], sort=False).agg(**{
        "Flotte": ("Flotte", "first"), "Qté par avion": ("Qté par avion", "first"), "Objectif": ("Avions restants", "max"),
        "Besoin": ("Besoin", "sum"), "PN": ("PN", _joindre), "Désignation": ("Désignation", "first")}).reset_index()
    info = m.set_index("CCN")
    d["Stock"] = d["CCN"].map(info["Stock"]).fillna(0)
    d["Couverture"] = d["CCN"].map(info["Couverture"]).fillna(0)
    d["PU (€)"] = d["CCN"].map(info["PU (€)"]).fillna(0)
    d["À coter"] = d["CCN"].map(info["À coter"]).fillna(False).astype(bool)
    d["Types partageant le CCN"] = d["CCN"].map(info["Nb types"]).fillna(1).astype(int)
    q = d["Qté par avion"].where(d["Qté par avion"] > 0)
    d["Avions (stock)"] = np.floor(d["Stock"] / q).fillna(0).astype(int)
    d["Avions (stock + commandes)"] = np.floor(d["Couverture"] / q).fillna(0).astype(int)
    d["Manque (unités)"] = d["CCN"].map(info["À demander (PR)"]).fillna(0).astype(int)
    d["CCN couvert"] = d["CCN"].map(info["Écart"]).fillna(1) <= 0  # stock + commandes ≥ besoin du CCN, tous types confondus

    blocs = d.groupby(["Type avion", "Classe"], sort=False).agg(**{
        "Flotte": ("Flotte", "first"), "Objectif": ("Objectif", "max"), "Nb CCN": ("CCN", "nunique")}).reset_index()
    cles = list(zip(blocs["Type avion"], blocs["Classe"]))
    besoins = {k: dict(zip(g["CCN"], g["Qté par avion"])) for k, g in d.groupby(["Type avion", "Classe"], sort=False)}
    entree = [(k, int(o), besoins.get(k, {})) for k, o in zip(cles, blocs["Objectif"])]
    maintenant = repartir(entree, info["Stock"].to_dict())
    avec_cde = repartir(entree, info["Couverture"].to_dict())
    blocs["Complets maintenant"] = [maintenant[k] for k in cles]
    blocs["Complets à réception"] = [max(avec_cde[k] - maintenant[k], 0) for k in cles]
    blocs["À approvisionner"] = blocs["Objectif"] - blocs["Complets maintenant"] - blocs["Complets à réception"]
    blocs["Taux (%)"] = np.where(blocs["Objectif"] > 0, (blocs["Complets maintenant"] / blocs["Objectif"] * 100).round(0), np.nan)
    pire = d.sort_values("Avions (stock)").drop_duplicates(["Type avion", "Classe"]).set_index(["Type avion", "Classe"])
    blocs["CCN limitant"] = [pire["CCN"].get(k) for k in cles]
    par_bloc = d.groupby(["Type avion", "Classe"], sort=False).agg(couverts=("CCN couvert", "sum"), a_coter=("À coter", "sum"))
    blocs["CCN couverts"] = [int(par_bloc["couverts"].get(k, 0)) for k in cles]
    blocs["Tout commandé"] = blocs["CCN couverts"] == blocs["Nb CCN"]
    blocs["PN à coter"] = [int(par_bloc["a_coter"].get(k, 0)) for k in cles]
    return blocs, d


def date_debut_annee(date_ref: date) -> date:
    return date(date_ref.year, 1, 1)


def nom_bloc(type_avion: str, classe: str) -> str:
    return f"{type_avion} · {classe}"
