"""Onglet « Textile cabine » : stock, consommation, commandes et prévision de commandes des références textile.

Repris du dashboard Textile (streamlit_textile_dashboard.py, textile_analytics.py, textile_policy.py).
Imports : État du stock, Commandes (SAP), Références textile ; pour la prévision : Pièces par avion.
"""

import re
from dataclasses import asdict
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from core import cache, charts, dossiers
from core import components as ui
from core import io as sio
from core import prevision as pv
from core import textile as tx
from core import transforms as tf
from core import style
from core.style import CATEGORIES, COLORS

TAB_ID = "textiles"
TAB_LABEL = "Textile cabine"
TAB_ICON = "🧵"
TAB_DESCRIPTION = "Stock, consommation, commandes et prévision de commandes des ceintures, housses, mousses et rideaux."

K = f"{TAB_ID}__"
SECTIONS = ["Synthèse", "Stock", "Commandes", "Fournisseurs", "Consommation", "Prévision"]
TOUTES = "Toutes"

COLONNES_ATTENDUES = {
    "stock": [("PNR", "", True), ("QTE SUR ÉTAGÈRE", "", True), ("QTE EN CDE", "", False), ("DESCRIPTION, CCN", "", False),
              ("QTE CONSO 12M / 18M / 24M", "consommation glissante", False), ("QTE CONSO <année>", "ex. 2021 à 2025", False),
              ("PMP, Dernier PU (achat) Euros", "valorisation au PMP, à défaut dernier prix d'achat", False), ("DATE DERNIERE CONSO", "2001 = jamais consommé", False),
              ("CODE FOURNISSEUR, DERNIER FOURNISSEUR", "fournisseur des PN sans commande", False),
              ("LT observé moyen sur 2 ans, B/O, RP, EOQ", "", False)],
    "commandes": [("PN", "", True), ("Commande", "", True), ("Code fournisseur, Fournisseur", "fournisseur identifié par son code", False),
                  ("Date d'émission de la commande", "", False), ("Date de livraison demandée / promise", "2001, 2030+ : sans date ; 2049 : BFE", False),
                  ("Quantité restant à livrer", "", False)],
    "references": [("pn", "feuille « PN Catalog »", True), ("equipment", "CEINTURE, HOUSSE, MOUSSE, RIDEAUX", True),
                   ("description, ccn", "", False)],
    "pieces": [("equipment, aircraft_type, group, registration", "", True), ("area, ccn, pn, description, qty_per_ac", "", True),
               ("CSV ou Excel", "ex. textile_all_parts", False)],
}

COL_RELANCES = {"Statut commande": "Statut", "Fournisseur": "Fournisseur", "Commande": "Commande", "PNR": "PN", "CCN": "CCN",
                "REF_Equipement": "Catégorie", "Date livraison demandee": "Demandée", "Date livraison promise": "Promise",
                "Jours de retard": "Retard (j)", "Qte restante": "Reste à livrer", "Code acheteur": "Acheteur"}
COL_PREV = {"PNR": "PN", "CCN": "CCN", "DESCRIPTION": "Description", "REF_Equipement": "Catégorie", "Flottes": "Flottes",
            "Part des flottes choisies (%)": "Part des flottes choisies (%)", "Statut prévision": "Statut",
            "Qté à commander maintenant": "À commander", "Date 1ère commande": "1re commande", "QTE SUR ÉTAGÈRE": "Stock",
            "QTE EN CDE": "En commande", "Conso prévue 12 mois (qté)": "Conso prévue 12 mois", "Tendance conso": "Tendance",
            "Stock à tenir (qté)": "Stock à tenir", "Stock à tenir basé sur": "Basé sur", "Délai (mois)": "Délai (mois)",
            "À commander 36 mois (qté)": "À commander sur la période",
            "Valeur à commander maintenant (€)": "Valeur maintenant (€)", "Fournisseur": "Fournisseur"}
COL_PN = {"PNR": "PN", "CCN": "CCN", "DESCRIPTION": "Description", "REF_Equipement": "Catégorie", "Flottes": "Flottes",
          "Statut prévision": "Statut", "Fournisseur": "Fournisseur",
          "Conso 12 mois": "Conso 12 mois", "Évolution conso (%)": "Évolution conso", "Conso prévue 12 mois (qté)": "Conso prévue 12 mois",
          "QTE SUR ÉTAGÈRE": "Stock", "QTE EN CDE": "En commande", "Stock à tenir (qté)": "Stock à tenir",
          "Délai (mois)": "Délai (mois)", "Source délai": "Source délai",
          "Qté à commander maintenant": "Maintenant", "À commander 12 mois (qté)": "12 mois", "À commander 24 mois (qté)": "24 mois",
          "À commander 36 mois (qté)": "36 mois", "Valeur 12 mois (€)": "Valeur 12 mois (€)", "Valeur 36 mois (€)": "Valeur 36 mois (€)"}
GROUPES_PN = [("Pièce", 7), ("Consommation", 3), ("Stock", 3), ("Délai", 2), ("À commander (pièces)", 4), ("Valeur", 2)]
COL_FOUR = {"Valeur maintenant (€)": "Maintenant (€)", "Qté 12 mois": "12 mois · qté", "Valeur 12 mois (€)": "12 mois · €",
            "Qté 24 mois": "24 mois · qté", "Valeur 24 mois (€)": "24 mois · €", "Qté 36 mois": "36 mois · qté",
            "Valeur 36 mois (€)": "36 mois · €"}
GROUPES_FOUR = [("Fournisseur", 3), ("À commander", 7), ("Consommation", 2), ("Suivi", 2)]
COL_TENDANCE = {"PNR": "PN", "CCN": "CCN", "DESCRIPTION": "Description", "REF_Equipement": "Catégorie", "Flottes": "Flottes",
                "Tendance conso": "Tendance", "Conso 12 mois d'avant": "12 mois d'avant", "Conso 12 mois": "12 derniers mois",
                "Conso brute 12 mois (demandes)": "Demandes 12 mois (brut)",
                "Évolution conso (%)": "Évolution conso", "Conso 18 mois": "18 mois", "Conso 24 mois": "24 mois",
                "Conso prévue 12 mois (qté)": "Conso prévue 12 mois", "QTE SUR ÉTAGÈRE": "Stock", "Fournisseur": "Fournisseur"}
CFG = {
    "Demandée": st.column_config.DateColumn("Demandée", format="DD/MM/YYYY"),
    "Promise": st.column_config.DateColumn("Promise", format="DD/MM/YYYY"),
    "Émise": st.column_config.DateColumn("Émise", format="DD/MM/YYYY"),
    "1re commande": st.column_config.DateColumn("1re commande", format="MM/YYYY"),
    "Prochaine commande": st.column_config.DateColumn("Prochaine commande", format="MM/YYYY"),
    "Mois de commande": st.column_config.DateColumn("Mois de commande", format="MM/YYYY"),
    "Mois de livraison souhaité": st.column_config.DateColumn("Mois de livraison souhaité", format="MM/YYYY"),
    "Retard (j)": st.column_config.NumberColumn("Retard (j)", format="%d"),
    "Reste à livrer": st.column_config.NumberColumn("Reste à livrer", format="%d"),
    "Qté sur étagère": st.column_config.NumberColumn("Qté sur étagère", format="%d", help="Stock du PN (État du stock)"),
    "Valeur stock (€)": st.column_config.NumberColumn("Valeur stock (€)", format="%.0f €"),
    "Valeur en commande (€)": st.column_config.NumberColumn("Valeur en commande (€)", format="%.0f €"),
    "Valeur maintenant (€)": st.column_config.NumberColumn("Valeur maintenant (€)", format="%.0f €"),
    "Valeur (€)": st.column_config.NumberColumn("Valeur (€)", format="%.0f €"),
    "Dernière conso": st.column_config.DateColumn("Dernière conso", format="DD/MM/YYYY"),
}
def _avec_stock(cols: dict) -> dict:
    """Colonnes d'un tableau de commandes avec « Qté sur étagère » (stock du PN) juste après le PN."""
    out = {}
    for k, v in cols.items():
        out[k] = v
        if k == "PNR":
            out["QTE SUR ÉTAGÈRE"] = "Qté sur étagère"
    return out


# Statut des lignes de commande : libellé affiché et couleur du badge (core/textile.ORDER_STATUS_COLORS)
STATUT_LIBELLES = {"En retard": "En retard", "Sans date promise": "Sans date promise", "En attente BFE": "En attente BFE",
                   "A l'heure": "À l'heure"}
STATUT_COULEURS = {STATUT_LIBELLES[k]: v for k, v in tx.ORDER_STATUS_COLORS.items()}


# --------------------------------------------------------------------------
# Calculs mis en cache : clé = contenu des fichiers (octets) + paramètres
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner="Croisement stock × commandes × références…", max_entries=4)
def _tables(stock: bytes, cmd: bytes | None, ref: bytes | None, today: date, seulement_textile: bool):
    s_lignes, _ = cache.etat_stock(stock)
    c_lignes = cache.commandes(cmd)[0] if cmd else None
    catalogue = cache.references_textile(ref)[0] if ref else None
    return tx.construire_tables(s_lignes, c_lignes, catalogue, today, seulement_textile)


@st.cache_resource(show_spinner="Lecture des pièces par avion…", max_entries=4)
def _pieces(data: bytes, nom: str, params: pv.Params):
    return pv.preparer_pieces(pv.lire_pieces(data, nom), params)


@st.cache_resource(show_spinner="Calcul de la prévision de commandes…", max_entries=4)
def _prevision(cle_tables: tuple, pieces: tuple | None, params: pv.Params):
    """(pbi avec prévision, résultats) — clé = fichiers + paramètres (n-uplets, pas de tables).

    Demande = consommation (QTE CONSO 12M / 18M / 24M du Résultat). Sans « Pièces par avion », pas de stock minimum par
    flotte : seul le stock de sécurité statistique s'applique.
    """
    s_all, o_all = _tables(*cle_tables)
    if pieces:
        parts, fleet, _ = _pieces(*pieces, params)
        parts = pv.rattacher_pieces(parts, s_all)  # PN différent du stock mais même CCN : même pièce
    else:
        parts = pd.DataFrame(columns=[*pv.RAW_COLS, "Composant"])
        fleet = pd.DataFrame(columns=["equipment", "aircraft_type", "group", "Avions du groupe"])
    return pv.run_policy(s_all, o_all, parts, fleet, pv.regles_pe_defaut(parts), params, pd.Timestamp(cle_tables[3]))


def _dans_perimetre(df: pd.DataFrame, perim: tuple, pn: str = "PNR") -> pd.Series:
    """Lignes du périmètre choisi : perim = (équipements, (PN, CCN) des flottes choisies) ; vide = tout."""
    cats, cles = perim
    garde = pd.Series(True, index=df.index)
    if cats:
        garde &= tx.categorie(df).isin(cats)
    if cles is not None:
        pns, ccns = cles
        ccn = tx.cle_ccn(df["CCN"]) if "CCN" in df else pd.Series(np.nan, index=df.index)
        garde &= df[pn].isin(pns) | ccn.isin(ccns)
    return garde


def _filtrer(s_all, o_all, perim):
    s = s_all[_dans_perimetre(s_all, perim)]
    o = o_all if o_all.empty else o_all[_dans_perimetre(o_all, perim)]
    return s, o


def _cles_flottes(parts: pd.DataFrame | None, flottes: tuple) -> tuple | None:
    """PN et CCN montés sur les flottes choisies (textile_all_parts : aircraft_type, pn, ccn) ; None = toutes."""
    if not flottes or parts is None or not len(parts):
        return None
    p = parts[parts["aircraft_type"].isin(flottes)]
    return frozenset(p["pn"]), frozenset(tx.cle_ccn(p["ccn"].replace("", np.nan)).dropna())


@st.cache_resource(show_spinner=False, max_entries=4)
def _export(cle_tables: tuple, perim: tuple, cle_prev: tuple | None) -> bytes:
    s, o = _filtrer(*_tables(*cle_tables), perim)
    rel = tx.relances(o) if len(o) else o
    feuilles = {
        "Synthèse catégories": tx.resume_categories(s, o),
        "Relances fournisseurs": rel,
        "État des stocks": tx.etat_stocks(s),
        "Stock": s,
        "Commandes": o,
        "Retards": tx.tableau_retards(o),
        "Conso catégories": tx.conso_par_categorie(s),
        "Délais fournisseurs": tx.delais_fournisseurs(o),
    }
    if cle_prev:
        pbi, res = _prevision(*cle_prev)
        pbi = pbi[_dans_perimetre(pbi, perim)]
        plan = res["plan"][res["plan"]["PNR"].isin(set(pbi["PNR"]))]
        feuilles = {"Prévision fournisseurs": pv.par_fournisseur(pbi, plan), "Plan de commande": plan,
                    "Prévision par PN": pbi, "Groupes avions": res["gs"], **feuilles}
    teinte = lambda serie, couleurs: [style.teinte(couleurs.get(v, "")) for v in serie]  # noqa: E731
    cellules = {"Relances fournisseurs": {"Statut commande": teinte(rel["Statut commande"], tx.ORDER_STATUS_COLORS)} if len(rel) else {},
                "État des stocks": {"Statut": teinte(feuilles["État des stocks"]["Statut"], tx.STOCK_STATUT_COULEURS)}}
    return sio.exporter_excel(feuilles, couleurs_cellules=cellules)


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------
def _parametres() -> pv.Params:
    """Paramètres du sous-onglet Prévision (stock minimum par flotte, stock de sécurité, délais)."""
    d = pv.Params()
    st.caption("Réglages du sous-onglet **Prévision**. La demande vient de la consommation (12, 18 et 24 mois du Résultat).")
    a, b = st.columns(2)
    ratio = a.slider("Stock minimum : avions d'avance (% du groupe)", 2, 40, int(d.buffer_ratio * 100), key=K + "ratio",
                     persist_state="page", help="10 % : 10 avions → 1, 50 avions → 5. Nécessite « Pièces par avion ».")
    bmin = b.number_input("Minimum d'avions d'avance par groupe", 1, 10, d.buffer_min, key=K + "bmin", persist_state="page")
    service = a.select_slider("Stock de sécurité : taux de service visé", [0.90, 0.95, 0.98], value=d.taux_service,
                              format_func=lambda v: f"{v:.0%}", key=K + "service", persist_state="page",
                              help="95 % : la marge couvre 95 mois sur 100 sans rupture. Plus haut = plus de stock.")
    lt_def = a.number_input("Délai par défaut (jours)", 1, 730, d.lt_default, key=K + "ltdef", persist_state="page",
                            help="Quand ni le fournisseur ni le PN n'ont de délai.")
    lt_basis = b.selectbox("Délais basés sur", ["observe", "promis"], key=K + "ltbasis", persist_state="page",
                           format_func={"observe": "LT observé (historique 2 ans)", "promis": "Délais promis des commandes"}.get,
                           help="Délai du PN d'abord ; s'il n'en a pas, moyenne des PN de son fournisseur (code fournisseur "
                                "du Résultat) ; sinon le délai par défaut.")
    bfe = a.number_input("Délai supposé si attente de BFE (mois)", 1, 36, d.bfe_delay_months, key=K + "bfe", persist_state="page",
                         help="Commandes datées 2049 (en attente de matière première) : délai de livraison supposé.")
    comp = b.selectbox("Assise ou dossier, si la description ne le dit pas", ["Assise", "Dossier"], key=K + "comp", persist_state="page")
    kw_dos = a.text_input("Mots qui désignent un dossier", d.dossier_kw, key=K + "kwdos", persist_state="page",
                          help="Cherchés dans la description de la pièce, séparés par des virgules. Ils passent avant ceux de l'assise.")
    kw_ass = b.text_input("Mots qui désignent une assise", d.assise_kw, key=K + "kwass", persist_state="page",
                          help="Cherchés dans la description de la pièce, séparés par des virgules.")
    return pv.Params(buffer_ratio=ratio / 100, buffer_min=int(bmin), lt_default=int(lt_def),
                     lt_basis=lt_basis, bfe_delay_months=int(bfe), assise_kw=kw_ass, dossier_kw=kw_dos, default_component=comp,
                     taux_service=float(service))


SHAREPOINT_TEXTILE = ("https://afkl.sharepoint.com/:f:/r/teams/MS-LGT1-Analystes/Shared%20Documents/Textile"
                      "?d=w58572b00036a42e395a6b6435ecf4000&csf=1&web=1&e=ExlJGH")
# Noms des fichiers du dossier Textile (prioritaires sur la reconnaissance par le contenu), sans accents ni majuscules.
# Dossier Textile partagé avec PE mousses : « Résultat … ALL TEXTILE » = État du stock de cet onglet (le plus récent) ;
# « Résultat … PE » est celui de PE mousses (source « stock_pe », ignorée ici sans être signalée).
NOMS_DOSSIER = {"stock_pe": dossiers.RESULTAT_PE, "stock": [dossiers.RESULTAT_ALL_TEXTILE, r"^resultat"],
                "references": r"textile_master_export", "pieces": r"textile_all_parts"}
NOMMAGE = ("Dossier Textile : le « Résultat … ALL TEXTILE » le plus récent = État du stock (les « Résultat … PE » sont "
           "pour l'onglet PE mousses), « textile_master_export » = Références textile, « textile_all_parts » = Pièces par "
           "avion. À défaut, les fichiers sont reconnus par leur contenu ; s'il y en a plusieurs du même type, le plus récent "
           "est retenu (date dans le nom, sinon date de modification). Commandes (SAP) : dossier COMMANDE.")


def _bloc_import():
    with ui.section(f"{TAB_ID}_import", ""):
        a, b, c = st.columns([2.4, 3.3, 1], vertical_alignment="center")
        with a:
            ui.boutons_dossiers("Textile", K + "dossier__upload")
        puces = b.container()
        reglages = c.popover("Paramètres", width="stretch")
        bilan = st.container()
        with ui.zone_repliable(K + "manuel", "Import manuel", interrupteur=c, aide="Choisir les fichiers à la main (Parcourir) et voir les colonnes attendues"):
            zone_dossier = st.container()
            c1, c2, c3 = st.columns(3)
            with c1:
                f_stock = ui.fichier(sio.FICHIER_STOCK, K + "stock", ["xlsx", "xlsm"], COLONNES_ATTENDUES["stock"])
                f_pieces = ui.fichier(f"{pv.FICHIER_PIECES} (textile_all_parts)", K + "pieces", ["csv", "xlsx", "xlsm"],
                                      COLONNES_ATTENDUES["pieces"])
            with c2:
                f_cmd = ui.import_commandes(COLONNES_ATTENDUES["commandes"])
            with c3:
                f_ref = ui.fichier(sio.FICHIER_REFERENCES, K + "references", ["xlsx", "xlsm"], COLONNES_ATTENDUES["references"])
            ui.lien_sharepoint(SHAREPOINT_TEXTILE, "Textile")
        with bilan:
            ui.import_dossier(K + "dossier", {"stock": K + "stock", "references": K + "references", "pieces": K + "pieces"},
                              label="Tout le dossier Textile (Ctrl+A pour tout sélectionner)", aide=NOMMAGE, noms=NOMS_DOSSIER,
                              autres=("pe", "besoin_prod", "stock_pe"),
                              zone=zone_dossier)
        with puces:
            ui.etat_fichiers([(sio.FICHIER_STOCK, K + "stock", True), (sio.FICHIER_COMMANDES, "commun__commandes", False),
                              (sio.FICHIER_REFERENCES, K + "references", False), (pv.FICHIER_PIECES, K + "pieces", False)])
        parts = None
        if f_pieces:
            try:
                parts = _pieces(f_pieces[1], f_pieces[0], pv.Params())[0]
            except ValueError as exc:
                ui.callout(f"<b>{pv.FICHIER_PIECES} illisible.</b> {exc}", "ko", "⛔")
                f_pieces = None
        with reglages:
            t_gen, t_prev = st.tabs(["Général", "Prévision"])
            with t_gen:
                today = st.date_input("Date de référence", value=date.today(), format="DD/MM/YYYY", key=K + "date", persist_state="page",
                                      help="Date des données : âge des commandes, retards, début de la prévision.")
                seul = st.toggle("Uniquement les PN du catalogue textile", value=True, key=K + "seul", persist_state="page",
                                 help="Limite l'analyse aux PN du fichier Références textile.")
            with t_prev:
                params = _parametres()
    return f_stock, f_cmd, f_ref, f_pieces, today, seul, params


def render() -> None:
    entete = st.container()
    f_stock, f_cmd, f_ref, f_pieces, today, seul, params = _bloc_import()
    with entete:
        ui.hero(TAB_ICON, "Textile cabine", TAB_DESCRIPTION, "Supply Chain · Achats",
                ui.contexte(("Données au", f"{today:%d/%m/%Y}", "")))
    if not f_stock:
        with ui.section(f"{TAB_ID}_vide", "Analyse"):
            ui.empty_state("Importez l'État du stock", "Les autres fichiers enrichissent ensuite l'analyse.",
                           [(sio.FICHIER_STOCK, bool(f_stock)), (sio.FICHIER_COMMANDES, bool(f_cmd)), (sio.FICHIER_REFERENCES, bool(f_ref)),
                            (pv.FICHIER_PIECES, bool(f_pieces))])
        return
    cle = (f_stock[1], f_cmd[1] if f_cmd else None, f_ref[1] if f_ref else None, today, seul)
    try:
        s_all, o_all = _tables(*cle)
        cle_prev = (cle, (f_pieces[1], f_pieces[0]) if f_pieces else None, params)
    except ValueError as exc:
        ui.callout(f"<b>Import impossible.</b> {exc}", "ko", "⛔")
        return
    if not f_ref or not f_cmd:
        manquants = " et ".join(n for f, n in [(f_cmd, sio.FICHIER_COMMANDES), (f_ref, sio.FICHIER_REFERENCES)] if not f)
        ui.callout(f"Analyse partielle : ajoutez <b>{manquants}</b> pour la compléter.", "warn", "⚠️")
    if s_all.empty:
        ui.callout("Aucun PN du catalogue textile dans l'État du stock. Vérifiez les fichiers ou désactivez le filtre catalogue.", "warn", "⚠️")
        return

    # Sous-onglets, puis barre « Périmètre » (flotte, équipement) : seule la section choisie est calculée et affichée.
    with st.container(key="s360barre"):
        section = ui.sous_onglets(K + "section", SECTIONS)
    parts = _pieces(f_pieces[1], f_pieces[0], params)[0] if f_pieces else None
    with ui.barre_perimetre(TAB_ID):
        a, b = st.columns([1.3, 1.7], gap="medium")
        types = sorted(x for x in parts["aircraft_type"].dropna().unique() if x) if parts is not None else []
        if types:
            flottes = ui.choix_multiple(a, "Flotte", types, K + "flottes", "Toutes")
        else:
            flottes = []
            a.html('<div class="s360-perimetre-vide"><b>FLOTTE</b><span>Ajoutez « Pièces par avion » (textile_all_parts) '
                   "pour filtrer par flotte</span></div>")
        toutes_cats = tx.categories(s_all)
        cats = ui.choix_multiple(b, "Équipement", toutes_cats, K + "cats", "Tous", {c: c.capitalize() for c in toutes_cats})
    perim = (tuple(c for c in cats if len(cats) < len(toutes_cats)),
             _cles_flottes(parts, tuple(flottes) if types and len(flottes) < len(types) else ()))
    cat = TOUTES if not perim[0] and perim[1] is None else " · ".join(
        ([", ".join(flottes)] if perim[1] is not None else []) + ([", ".join(c.capitalize() for c in cats)] if perim[0] else []))
    s, o = _filtrer(s_all, o_all, perim)
    st.session_state[K + "cle_export"] = (cle, perim, cle_prev)

    if section == "Prévision":  # calculée seulement ici (et pour l'export) : c'est le calcul le plus lourd de l'onglet
        try:
            prev = _prevision(*cle_prev) if cle_prev else None
        except ValueError as exc:
            ui.callout(f"<b>Prévision impossible.</b> {exc}", "ko", "⛔")
            return
        _section_prevision(prev, cat, o, perim, flottes if perim[1] is not None else None, params, today)
    else:
        {"Synthèse": _synthese, "Stock": _stock, "Commandes": _commandes, "Fournisseurs": _fournisseurs,
         "Consommation": _consommation}[section](s, o, today, cat)


# --------------------------------------------------------------------------
# Synthèse
# --------------------------------------------------------------------------
def _export_btn(cle: str) -> tuple:
    """Bouton d'export de l'onglet (même fichier pour tous les sous-onglets), fabriqué au clic."""
    cle_export = st.session_state[K + "cle_export"]
    return (lambda: _export(*cle_export), sio.nom_export(TAB_ID), K + cle)


def _relances_html(rel: pd.DataFrame, cle: str, colonnes: dict | None = None, hauteur: str = "26rem") -> None:
    """Lignes de commande : statut en badge (En retard, Sans date promise, En attente BFE, À l'heure)."""
    cols = colonnes or COL_RELANCES
    t = rel[[c for c in cols if c in rel.columns]].rename(columns=cols)
    t["Statut"] = t["Statut"].map(STATUT_LIBELLES).fillna(t["Statut"])
    if "Catégorie" in t:
        t["Catégorie"] = t["Catégorie"].astype(str).str.capitalize().where(t["Catégorie"].notna())
    ui.tableau_html(t, statut="Statut", couleurs=STATUT_COULEURS, num=["Reste à livrer", "Qté sur étagère", "Écart (j)"],
                    fort=["Retard (j)"], pn=["PN"], fixes=1, cle=f"{TAB_ID}_{cle}", hauteur=hauteur, colonne_config=CFG)


def _synthese(s, o, today, cat):
    r = tx.synthese(s, o)
    rel = tx.relances(o) if len(o) else o
    resume = f"{len(rel)} relance(s) fournisseur à lancer" if len(rel) else "Aucune relance fournisseur à lancer"
    with ui.section(f"{TAB_ID}_syn", "Synthèse", resume, export=_export_btn("export__btn"), carte=False,
                    info=f"{r['en_retard']} en retard, {r['sans_date']} sans date promise, {r['bfe']} en attente de BFE." if len(rel) else ""):
        ui.kpi_grid([
            ui.kpi_card("PN suivis", charts.entier(r["pn"]), f"{len(tx.categories(s))} catégorie(s)", "navy", "layers"),
            ui.kpi_card("Valeur du stock", charts.euros(r["valeur_stock"]), "sur étagère", "teal", "package"),
            ui.kpi_card("Valeur en commande", charts.euros(r["valeur_commande"]), f"{r['lignes']} lignes de commande", "info", "truck"),
            ui.kpi_card("Lignes en retard", charts.entier(r["en_retard"]), f"{r['sans_date']} sans date promise", "ko", "clock"),
            ui.kpi_card("Stock dormant", charts.euros(r["valeur_dormant"]), f"{r['dormants']} PN sans conso depuis 3 ans", "warn", "moon"),
        ])

    with ui.section(f"{TAB_ID}_rel", "Relances fournisseurs", "La plus urgente en premier", tag=str(len(rel))):
        if len(rel):
            _relances_html(rel, "relances")
        else:
            ui.callout("Aucune relance à lancer.", "ok", "check-circle")

    with ui.section(f"{TAB_ID}_cat", "Catégories", "Stock, commandes et activité par catégorie"):
        a, b = st.columns(2, gap="medium")
        cats = tx.categories(s)
        noms = [c.capitalize() for c in cats]
        with a:
            poids = tx.poids_par_categorie(s, o)
            ui.graphe(charts.parts(poids.rename(columns=str.capitalize), {k.capitalize(): v for k, v in tx.CATEGORY_COLORS.items()},
                                   "Poids de chaque catégorie", afficher="pourcent", noms=("Indicateur", "Catégorie")),
                      "Part de chaque catégorie dans chaque indicateur")
        with b:
            g = s.assign(c=tx.categorie(s)).groupby("c")[["Valeur stock (€)", "Valeur stock dormant (€)"]].sum().reindex(cats)
            actif = (g["Valeur stock (€)"] - g["Valeur stock dormant (€)"]).clip(lower=0)
            ui.graphe(charts.barres(noms, {"Stock actif": actif, "Stock dormant": g["Valeur stock dormant (€)"]},
                                    {"Stock actif": CATEGORIES[0], "Stock dormant": COLORS["warn"]}, empile=True, fmt=charts.euros,
                                    titre="Valeur du stock par catégorie", hauteur=220),
                      "Valeur sur étagère, dont stock dormant (sans conso depuis 3 ans)")
        a, b = st.columns(2, gap="medium")
        with a:
            ui.graphe(charts.parts(tx.activite_par_categorie(s).rename(index=str.capitalize), tx.ACTIVITY_COLORS,
                                   "PN actifs, dormants et inactifs"), "Nombre de PN par catégorie selon leur consommation")
        with b:
            g2 = s.assign(c=tx.categorie(s)).groupby("c")[["QTE SUR ÉTAGÈRE", "QTE EN CDE"]].sum().reindex(cats)
            bo = s.assign(c=tx.categorie(s)).groupby("c")["B/O"].sum().reindex(cats) if "B/O" in s.columns else None
            series = {"Stock étagère": g2["QTE SUR ÉTAGÈRE"], "En commande": g2["QTE EN CDE"]}
            if bo is not None:
                series["Back-order"] = bo
            ui.graphe(charts.barres(noms, series, {"Stock étagère": CATEGORIES[0], "En commande": CATEGORIES[1], "Back-order": CATEGORIES[3]},
                                    titre="Stock, commandes et back-orders", hauteur=205), "Quantités par catégorie")
        c1, c2, _ = st.columns([1, 1, 2.5])
        with c1.popover("Tableau par catégorie", width="stretch"):
            ui.tableau(tx.resume_categories(s, o), column_config=CFG, width=1000)
        with c2:
            _pn_dormants(s)


# --------------------------------------------------------------------------
# Stock : état des stocks de tout le textile
# --------------------------------------------------------------------------
def _stock(s, o, today, cat):
    seuil = float(st.session_state.get(K + "seuil_stock", 1.0))
    etat = tx.etat_stocks(s, seuil)
    n = etat["Statut"].value_counts()
    valeur = etat.groupby("Statut")["Valeur stock (€)"].sum()
    dormants = etat[etat["Statut"] == tx.DORMANT]
    n_cde = int((dormants["En commande"] > 0).sum())
    obsolete, n_obs = valeur.get("Obsolète / supprimé", 0), int(n.get("Obsolète / supprimé", 0))
    with ui.section(f"{TAB_ID}_stock", "État des stocks", "" if cat == TOUTES else cat,
                    export=_export_btn("export_stock__btn"), carte=False):
        ui.kpi_grid([
            ui.kpi_repartition("PN par niveau de stock", len(etat), "PN", [(v, int(n.get(v, 0)), tx.STOCK_STATUT_COULEURS[v])
                                                                       for v in tx.STOCK_STATUTS], icone="layers"),
            ui.kpi_card("En rupture", charts.entier(n.get("Rupture", 0)), "sortent encore, stock à 0", "ko", "box-off"),
            ui.kpi_card("Critiques", charts.entier(n.get("Critique", 0)), f"moins de {seuil:g} mois de stock".replace(".", ","),
                        "orange", "alert"),
            ui.kpi_card("Surstock (dormants)", charts.euros(valeur.get(tx.DORMANT, 0)),
                        f"{len(dormants)} PN sans sortie depuis 3 ans" + (f", dont {n_cde} encore en commande" if n_cde else ""),
                        "info", "moon"),
            ui.kpi_card("Obsolète / supprimé", charts.euros(obsolete), f"{n_obs} PN classe code 3, 8 ou 9 : à écouler",
                        "violet", "x"),
        ])
        with st.popover("Règles de calcul et seuil"):
            st.number_input("Seuil « stock presque nul » (mois de consommation)", 0.5, 6.0, 1.0, 0.5, format="%.1f", key=K + "seuil_stock",
                            persist_state="page", help="En dessous de ce nombre de mois de consommation, le PN est « Critique ».")
            st.markdown(regles_stock(seuil))
    with ui.section(f"{TAB_ID}_stock_graphes", "Où en est le stock", carte=False):
        a, b = st.columns(2, gap="medium")
        with a:
            ct = etat.groupby(["Catégorie", "Statut"]).size().unstack(fill_value=0)
            ct = ct.reindex(columns=[c for c in tx.STOCK_STATUTS if c in ct.columns], fill_value=0)
            ui.graphe(charts.parts(ct, tx.STOCK_STATUT_COULEURS, "Niveau de stock par catégorie"), "Nombre de PN de chaque catégorie")
        with b:
            ui.graphe(charts.barres_h([(st_, valeur.get(st_, 0), charts.euros(valeur.get(st_, 0)), tx.STOCK_STATUT_COULEURS[st_])
                                       for st_ in tx.STOCK_STATUTS if valeur.get(st_, 0) > 0], titre="Valeur du stock par statut"),
                      "Montant immobilisé dans chaque statut")
    _etat_stocks_table(etat)


def regles_stock(seuil: float) -> str:
    """Règles du sous-onglet Stock, en mots simples (popover « Règles de calcul et seuil »)."""
    s = f"{seuil:g}".replace(".", ",")
    return f"""
**Couverture** = combien de mois le stock peut tenir au rythme actuel.
Exemple : 30 pièces en stock et 10 sorties par mois → **3 mois** de couverture.
Le rythme est la consommation des 12 derniers mois divisée par 12.

**Ce que veut dire chaque statut**

| Statut | Ce que ça veut dire | Que faire |
|---|---|---|
| **Rupture** | La pièce sort encore, mais il n'y en a plus en stock | Commander ou relancer en urgence |
| **Critique** | Moins de {s} mois de stock (seuil réglable ci-dessus) | Commander vite |
| **Bas** | Moins de 3 mois de stock | Prévoir une commande |
| **Correct** | Entre 3 et 24 mois de stock | Rien à faire |
| **Couverture élevée** | Plus de 24 mois de stock, mais la pièce sort encore | Ne pas recommander pour l'instant |
| **Surstock (dormant)** | Du stock, mais **aucune sortie depuis 3 ans** | Écouler, transférer ou réformer |
| **Obsolète / supprimé** | Classe code 3, 8 ou 9 : la pièce n'est plus réapprovisionnée | Écouler le stock restant |
| **Jamais consommé** | Aucune sortie enregistrée (date « 2001 » dans le fichier) | Vérifier si la pièce sert encore |
| **Sans conso** | Aucune sortie depuis 1 an, mais une sortie il y a moins de 3 ans | Surveiller |

Une pièce ne reçoit qu'un statut. Si plusieurs conviennent, l'ordre est : Obsolète / supprimé, puis Jamais
consommé, puis Surstock, puis Sans conso, puis le niveau de stock (Rupture → Couverture élevée).
"""


@st.fragment
def _etat_stocks_table(etat):
    with ui.section(f"{TAB_ID}_stock_pn", "Stock par PN", "Du plus urgent au moins urgent",
                    tag=str(len(etat))):
        d = etat
        ui.tableau_html(d, statut="Statut", couleurs=tx.STOCK_STATUT_COULEURS,
                        num=["Stock", "En commande", "Conso 12 mois", "Conso / mois", "Couverture (mois)", "Couverture avec commandes (mois)"],
                        euros=["Valeur stock (€)"], pn=["PN"], fixes=2, filtres=True, cle=f"{TAB_ID}_stock_pn", hauteur="32rem",
                        colonne_config=CFG)


@st.fragment
def _pn_dormants(s):
    d = s[s["Statut activité"] == "Dormant"].sort_values("Valeur stock (€)", ascending=False)
    if d.empty:
        return
    with st.popover(f"PN dormants ({len(d)})", width="stretch"):
        cols = {"PNR": "PN", "CCN": "CCN", "DESCRIPTION": "Description", "REF_Equipement": "Catégorie", "QTE SUR ÉTAGÈRE": "Stock",
                "Valeur stock (€)": "Valeur stock (€)", "DATE DERNIERE CONSO": "Dernière conso", "Motif activité": "Motif"}
        ui.tableau(d[[c for c in cols if c in d.columns]].rename(columns=cols), column_config=CFG, width=1000, height=420)


# --------------------------------------------------------------------------
# Commandes
# --------------------------------------------------------------------------
REGLES_COMMANDES = f"""
Chaque ligne de commande est comparée à la date que vous aviez **demandée** au fournisseur.

| Statut | Ce que ça veut dire | Que faire |
|---|---|---|
| **En retard** | Le fournisseur promet une livraison plus de {tx.LATE_BUFFER_DAYS} jours après la date demandée | Relancer le fournisseur |
| **Sans date promise** | Le fournisseur n'a pas donné de date (vide, 2001, ou 2030 et après dans le fichier) | Demander une date |
| **En attente BFE** | Date « 2049 » : la commande attend la matière première (BFE) | Suivre |
| **À l'heure** | Date promise au plus {tx.LATE_BUFFER_DAYS} jours après la date demandée | Rien à faire |

**Jours de retard** = date promise − date demandée − {tx.LATE_BUFFER_DAYS} jours de tolérance.
Exemple : demandée le 1er mars, promise le 31 mars → 30 jours d'écart → **20 jours de retard**.
"""


def _commandes(s, o, today, cat):
    if o.empty:
        ui.callout(f"Importez le fichier <b>{sio.FICHIER_COMMANDES}</b> pour voir les commandes.", "info", "📦")
        return
    r = tx.synthese(s, o)
    with ui.section(f"{TAB_ID}_cmd", "Commandes", "Statut de chaque ligne de commande", export=_export_btn("export_cmd__btn")):
        ui.kpi_grid([
            ui.kpi_card("Lignes de commande", charts.entier(r["lignes"])),
            ui.kpi_card("En retard", charts.entier(r["en_retard"]), "", "ko"),
            ui.kpi_card("Sans date promise", charts.entier(r["sans_date"]), "dates 2001 / 2030+ / vides", "warn"),
            ui.kpi_card("En attente BFE", charts.entier(r["bfe"]), "date 2049", "violet"),
            ui.kpi_card("Fournisseurs", charts.entier(r["fournisseurs"]), "", "info"),
        ])
        with st.popover("Règles de calcul"):
            st.markdown(REGLES_COMMANDES)
        a, b = st.columns(2, gap="large")
        with a:
            ui.graphe(charts.parts(tx.statut_commandes_par_categorie(o), tx.ORDER_STATUS_COLORS, "Statut des commandes par catégorie"))
        with b:
            em = tx.commandes_emises_par_mois(o)
            ui.graphe(charts.barres(em.index, {c: em[c] for c in em.columns}, tx.CATEGORY_COLORS, empile=True, temporel=True,
                                    fenetre=tx.fenetre_emissions(today), titre="Lignes émises par mois")
                      if len(em) else charts.vide())
    with ui.section(f"{TAB_ID}_liv", "Livraisons et retards"):
        pl = tx.planning_livraisons(o)
        ui.graphe(charts.barres(pl.index, {c: pl[c] for c in pl.columns},
                                {"Avec date promise": COLORS["navy_2"], "Sans date promise (date demandée)": COLORS["warn"]},
                                empile=True, temporel=True, fenetre=tx.fenetre_planning(today),
                                titre="Planning des livraisons (lignes par mois)") if len(pl) else charts.vide())
        a, b = st.columns([1.4, 1], gap="large")
        with a:
            pr = tx.profondeur_retards(o)
            ui.graphe(charts.barres(pr.index, {c: pr[c] for c in pr.columns}, tx.CATEGORY_COLORS, empile=True,
                                    titre="Profondeur des retards (lignes)") if len(pr.columns) else charts.vide("Aucune commande en retard"))
        with b:
            st.markdown("**Détail par classe de retard**")
            ui.tableau(tx.tableau_retards(o))
    _lignes(o)


@st.fragment
def _lignes(o):
    with ui.section(f"{TAB_ID}_lignes", "Toutes les lignes"):
        d = o
        pn_cmd = {"PN commandé": "PN commandé"} if "PN commandé" in d and (d["PN commandé"] != d["PNR"]).any() else {}
        _relances_html(d, "lignes", _avec_stock({**COL_RELANCES, **pn_cmd, "Date emission commande": "Émise", "Classe de retard": "Classe de retard"}),
                       "30rem")


# --------------------------------------------------------------------------
# Fournisseurs
# --------------------------------------------------------------------------
def _fournisseurs(s, o, today, cat):
    if o.empty:
        ui.callout(f"Importez le fichier <b>{sio.FICHIER_COMMANDES}</b> pour voir les fournisseurs.", "info", "🏭")
        return
    with ui.section(f"{TAB_ID}_four", "Fournisseurs", "Volumes, retards et délais", export=_export_btn("export_four__btn")):
        # Barres horizontales : les noms des fournisseurs se lisent en entier (pas d'étiquettes inclinées)
        vc = o["Fournisseur"].value_counts().head(10)
        part = (vc / max(len(o.dropna(subset=["Fournisseur"])), 1) * 100)
        late = o[o["Statut commande"] == "En retard"]
        g = late.groupby("Fournisseur").agg(n=("PNR", "size"), j=("Jours de retard", "mean")).sort_values("n", ascending=False).head(10)
        dl = tx.delais_fournisseurs(o).head(10)
        bfe = o[o["Statut commande"] == "En attente BFE"]["Fournisseur"].value_counts().head(10)
        graphes = [
            charts.barres_h([(f, n, f"{n} ligne{'s' if n > 1 else ''} · {p_:.0f} %") for (f, n), p_ in zip(vc.items(), part)],
                            titre="Lignes de commande en cours", max_lignes=10),
            charts.barres_h([(f, r["n"], f"{int(r['n'])} ligne{'s' if r['n'] > 1 else ''} · {r['j']:.0f} j en moyenne") for f, r in g.iterrows()],
                            couleur=COLORS["ko"], titre="Fournisseurs avec le plus de retards", max_lignes=10)
            if len(g) else charts.vide("Aucune commande en retard"),
        ]
        if len(dl):  # carte affichée seulement s'il y a assez de lignes datées
            graphes.append(charts.barres_h([(r["Fournisseur"], r["Délai moyen promis (j)"], f"{r['Délai moyen promis (j)']:.0f} j")
                                            for _, r in dl.iterrows()], titre="Délai moyen promis (commande → livraison)"))
        if len(bfe):
            graphes.append(charts.barres_h(list(bfe.items()), couleur=COLORS["violet"], titre="Lignes en attente de BFE"))
        for i in range(0, len(graphes), 2):
            cols = st.columns(2, gap="medium")
            for col, h in zip(cols, graphes[i:i + 2]):
                with col:
                    ui.graphe(h)
        ch = tx.chaleur_livraisons(o, today)
        ui.graphe(charts.chaleur(ch, "Livraisons promises par fournisseur et par mois"))
    _vue_fournisseur(o)


def _nom_fournisseur(lignes) -> None:
    """Sous la liste des codes : nom du fournisseur tel qu'écrit dans les commandes (le plus fréquent)."""
    if lignes is None or not len(lignes) or "Nom fournisseur" not in lignes:
        return
    noms = lignes["Nom fournisseur"].dropna()
    noms = noms[~noms.astype(str).str.startswith("Code ")]
    if len(noms) and noms.mode().iloc[0] != lignes["Fournisseur"].iloc[0]:
        st.caption(f"Nom dans les commandes : **{noms.mode().iloc[0]}**")


@st.fragment
def _vue_fournisseur(o):
    fours = list(o["Fournisseur"].dropna().value_counts().index)
    if not fours:
        return
    with ui.section(f"{TAB_ID}_vf", "Vue par fournisseur"):
        f = st.selectbox("Code fournisseur", fours, key=K + "fournisseur", persist_state="page", label_visibility="collapsed")
        d = o[o["Fournisseur"] == f]
        _nom_fournisseur(d)
        late = d[d["Statut commande"] == "En retard"]
        ui.kpi_grid([
            ui.kpi_card("Lignes", charts.entier(len(d))),
            ui.kpi_card("En retard", charts.entier(len(late)), "", "ko"),
            ui.kpi_card("Retard moyen", f"{late['Jours de retard'].mean():.0f} j" if len(late) else "—", "", "warn"),
            ui.kpi_card("Reste à livrer", charts.entier(d["Qte restante"].fillna(0).sum()), "pièces", "info"),
        ])
        _relances_html(d.sort_values("Date livraison promise"), "vf",
                       _avec_stock({**COL_RELANCES, "Date emission commande": "Émise", "Ecart promis vs demandé (j)": "Écart (j)"}), "24rem")


# --------------------------------------------------------------------------
# Consommation
# --------------------------------------------------------------------------
MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def _periode(fin: pd.Timestamp) -> str:
    """12 mois qui se terminent au mois de `fin` : « nov. 2025 → oct. 2026 »."""
    debut = fin - pd.DateOffset(months=11)
    return f"{MOIS_COURTS[debut.month - 1]} {debut.year} → {MOIS_COURTS[fin.month - 1]} {fin.year}"


def _consommation(s, o, today, cat):
    annees = tx.annees_conso(s)
    cats = tx.categories(s)
    fin = pd.Timestamp(today) - pd.DateOffset(months=1)                 # dernier mois complet
    recent, avant = _periode(fin), _periode(fin - pd.DateOffset(months=12))
    c12 = s["QTE CONSO 12M"].fillna(0) if "QTE CONSO 12M" in s else pd.Series(0.0, index=s.index)
    c_av = s["Conso 12 mois précédents"].fillna(0) if "Conso 12 mois précédents" in s else pd.Series(0.0, index=s.index)
    pu = (s[tf.PRIX] if tf.PRIX in s else tf.prix_unitaire(s)).fillna(0)
    evol = (c12.sum() / c_av.sum() - 1) * 100 if c_av.sum() > 0 else None
    with ui.section(f"{TAB_ID}_conso", "Consommation", "Pièces sorties du stock", carte=False, export=_export_btn("export_conso__btn")):
        ui.kpi_grid([
            ui.kpi_card("Sorties sur 12 mois", charts.entier(c12.sum()), recent, "navy", "trend"),
            ui.kpi_card("Valeur sortie", charts.euros((c12 * pu).sum()), "au PMP", "teal", "euro"),
            ui.kpi_card("Les 12 mois d'avant", charts.entier(c_av.sum()), avant, "info", "calendar"),
            ui.kpi_card("Tendance", "—" if evol is None else f"{evol:+.0f} %".replace("-", "−"),
                        "par rapport aux 12 mois d'avant", "ok" if evol is None or evol <= 0 else "orange", "gauge"),
            ui.kpi_card("PN consommés", charts.entier((c12 > 0).sum()), f"sur {charts.entier(len(s))} PN", "violet", "layers"),
        ])
    with ui.section(f"{TAB_ID}_conso_g", "Qui consomme quoi", carte=False):
        a, b = st.columns(2, gap="medium")
        with a:
            if annees:
                par_an = {c: [s.loc[tx.categorie(s) == c, f"QTE CONSO {an}"].fillna(0).sum() for an in annees] for c in cats}
                ui.graphe(charts.barres([str(an) for an in annees], {c.capitalize(): v for c, v in par_an.items()},
                                        {c.capitalize(): tx.CATEGORY_COLORS.get(c) for c in cats}, empile=True, titre="Sorties par année"),
                          "Pièces sorties chaque année civile, par équipement")
            else:
                ui.graphe(charts.vide("Pas de consommation par année dans l'État du stock"))
        with b:
            d = s.assign(_c=c12, _a=c_av).sort_values("_c", ascending=False).head(10)
            d = d[d["_c"] > 0]
            def _tendance(r):
                return "nouveau" if r["_a"] <= 0 else f"{(r['_c'] / r['_a'] - 1) * 100:+.0f} %".replace("-", "−")
            lignes = [(f"{r['PNR']} · {str(r.get('DESCRIPTION') or '')[:28]}", r["_c"],
                       f"{charts.entier(r['_c'])} · {_tendance(r)}") for _, r in d.iterrows()]
            ui.graphe(charts.barres_h(lignes, titre="Les 10 PN qui sortent le plus", max_lignes=10)
                      if lignes else charts.vide("Aucune sortie sur 12 mois"),
                      f"Pièces sorties ({recent}) · % = évolution par rapport à {avant}")
        with st.popover("Tableau par équipement"):
            ui.tableau(tx.conso_par_categorie(s), width=1000)
    _conso_pn(s, annees)


@st.fragment
def _conso_pn(s, annees):
    if not annees:
        return
    with ui.section(f"{TAB_ID}_pn", "Sorties par année d'un PN", "Les 6 PN les plus consommés, ou ceux que vous choisissez"):
        pool = s.sort_values("QTE CONSO 12M", ascending=False) if "QTE CONSO 12M" in s.columns else s
        libelles = dict(zip(pool["PNR"], pool["PNR"] + " — " + pool.get("DESCRIPTION", pd.Series("", index=pool.index)).fillna("").astype(str).str[:40]))
        choix = st.multiselect("PN", list(libelles), format_func=libelles.get, key=K + "pn", max_selections=9,
                               placeholder="Choisir des PN (par défaut : les 6 plus consommés)", label_visibility="collapsed",
                               persist_state="page")
        sel = pool[pool["PNR"].isin(choix)] if choix else pool.head(6)
        ui.graphe(charts.multiples({r["PNR"]: ([str(a) for a in annees], [r.get(f"QTE CONSO {a}", 0) for a in annees])
                                    for _, r in sel.iterrows()}, {}, hauteur=140))



# --------------------------------------------------------------------------
# Prévision de commandes
# --------------------------------------------------------------------------
EXPLICATION = """
**L'idée** : commander à temps ce qui va être consommé, sans descendre sous un stock à tenir. La prévision est donnée
pour les **12, 24 et 36 prochains mois** ({periode}), commandes de ce mois comprises : chaque chiffre est un cumul
(les 24 mois comprennent les 12 premiers).

1. **Consommation prévue d'un PN** : on part de sa **consommation nette** du Résultat (QTE CONSO NETTE REINT 12M et
   24M) : ce que la production a demandé, **moins les équipements remis sur étagère** parce qu'ils n'ont pas été
   consommés. C'est ce qui a vraiment été consommé. Le plus récent compte le plus : 70 % pour les 12 mois, 30 % pour
   les 24 mois. Exemple : 120 sur 12 mois (10 / mois) et 192 sur 24 mois (8 / mois) → **9,4 pièces par mois**,
   soit **113 sur les 12 prochains mois** (colonne « Conso prévue 12 mois »).
   Si le Résultat ne contient pas la conso nette, la prévision utilise les demandes brutes (QTE CONSO 12M, 18M, 24M ;
   50 / 30 / 20 %), qui peuvent nettement surestimer le besoin.
2. **Tendance** : conso nette des 12 derniers mois comparée aux 12 mois d'avant (24 mois − 12 mois).
   Exemple : 120 contre 72 → **+67 %, en hausse**. Entre −20 % et +20 % : **stable**.
3. **Stock à tenir** = le plus grand des deux :
   - **stock minimum par flotte** : de quoi équiper {ratio} des avions de chaque groupe d'avions (pièces par avion) ;
   - **stock de sécurité** : une marge qui grandit avec le délai du fournisseur et avec l'irrégularité de la
     consommation (écart entre les 12 derniers mois et les 12 mois d'avant), pour éviter la rupture {service} des mois.
4. **Ce qui manque** = stock à tenir + consommation prévue − (stock en rayon + commandes déjà passées).
5. **Quand commander ?** Assez tôt pour que la pièce arrive avant le manque. **Délai** : celui du PN (LT observé sur
   2 ans, ou délais promis de ses commandes selon Paramètres) ; s'il n'en a pas, la moyenne des PN de son fournisseur
   (au moins 3) ; sinon le délai par défaut (60 jours). Arrondi au mois supérieur : 45 jours → 2 mois.
   Si c'est déjà trop tard, la commande est à passer tout de suite et la quantité qui manquera en attendant est indiquée.
6. **Statuts** : **A commander** = à passer maintenant ; **A planifier** = plus tard sur la période ; **OK** = rien à faire.
7. **Jamais de commande** pour les pièces dormantes (aucune sortie depuis 3 ans), inactives, obsolètes ou supprimées
   (classe code 3, 8 ou 9).
8. **Fournisseur** : le **CODE FOURNISSEUR** du Résultat ; à défaut, celui des commandes.
9. **Flottes** : un PN monté sur plusieurs flottes apparaît sous chacune d'elles. Avec un filtre Flotte, la colonne
   « Part des flottes choisies » indique la part des pièces installées sur ces flottes ; la quantité à commander reste
   celle du PN entier.
"""

TENDANCE_TONS = {"En hausse": "orange", "Nouveau": "violet", "Stable": "ok", "En baisse": "info", "Sans conso": "muted", "Non mesurée": "muted"}


def _section_prevision(prev, cat, o, perim, flottes=None, params=None, today=None):
    if prev is None:
        return
    params = params or pv.Params()
    pbi, res = prev
    if res["gp"].empty:
        ui.callout(f"Sans <b>{pv.FICHIER_PIECES}</b> (textile_all_parts), la prévision repose sur la consommation et le stock "
                   "de sécurité seulement : pas de stock minimum par flotte, pas de filtre Flotte.", "info", "ℹ️")
    s = pbi[_dans_perimetre(pbi, perim)]
    s = s.join(pv.flottes_pn(res["gp"], flottes), on="PNR")  # flottes du PN ; part des flottes filtrées
    plan = res["plan"][res["plan"]["PNR"].isin(set(s["PNR"]))]
    gs = res["gs"]
    if perim[0]:
        gs = gs[gs["equipment"].isin(perim[0])]
    if flottes:
        gs = gs[gs["aircraft_type"].isin(flottes)]
    now = s[s["Qté à commander maintenant"] > 0]
    tr = pv.tranches(today or date.today())
    periodes = {k: f"{tr[0][2].split(' · ')[1].split(' → ')[0]} → {tr[i][2].split(' → ')[1]}" for i, k in enumerate(pv.PERIODES)}
    suivis = s[s["Dans la prévision"]] if "Dans la prévision" in s else s
    hausse, baisse = (suivis["Tendance conso"] == "En hausse").sum(), (suivis["Tendance conso"] == "En baisse").sum()
    communs = int(s["Flottes"].fillna("").str.contains("·").sum()) if "Flottes" in s else 0

    def tuile(k):
        q, v = s[f"À commander {k} mois (qté)"], s[f"Valeur {k} mois (€)"]
        return ui.kpi_card(f"{k} prochains mois", charts.euros(v.sum()),
                           f"{charts.entier(q.sum())} pièces · {(q > 0).sum()} PN · {periodes[k]}",
                           {12: "warn", 24: "orange", 36: "navy"}[k], "calendar",
                           info=f"Cumul des commandes à passer de {periodes[k]}, commandes de ce mois comprises.")

    with ui.section(f"{TAB_ID}_prev", "Prévision de commandes", "Les 12, 24 et 36 prochains mois", carte=False,
                    export=_export_btn("export_prev__btn"),
                    info="Demande = consommation nette (demandes moins réintégrations) des 12 et 24 derniers mois. "
                         "Stock à tenir = stock minimum par flotte ou stock de sécurité, le plus grand des deux."):
        ui.kpi_grid([
            ui.kpi_card("À commander maintenant", charts.euros(now["Valeur à commander maintenant (€)"].sum()),
                        f"{charts.entier(now['Qté à commander maintenant'].sum())} pièces · {len(now)} PN · "
                        f"{now['Fournisseur'].nunique()} fournisseur(s)", "ko", "cart"),
            *[tuile(k) for k in pv.PERIODES],
            ui.kpi_card("Conso en hausse", charts.entier(hausse), f"PN · {charts.entier(baisse)} en baisse",
                        "orange", "trend", info="12 derniers mois comparés aux 12 mois d'avant : hausse ou baisse de plus de 20 %."),
        ])
        c1, c2, _ = st.columns([1, 1, 1])
        with c1.popover("Comment c'est calculé", width="stretch"):
            st.markdown(EXPLICATION.replace("{periode}", periodes[36]).replace("{ratio}", f"{params.buffer_ratio:.0%}")
                        .replace("{service}", f"{params.taux_service:.0%}"))
        with c2.popover("Autres tableaux", width="stretch"):
            _tableaux_prevision(s, plan, gs, res)
        if len(s) and "Base conso" in s and (s["Base conso"] == "Brute (demandes)").all():
            ui.callout("Le Résultat ne contient pas la <b>conso nette</b> (QTE CONSO NETTE REINT 12M / 24M) : la prévision "
                       "repose sur les demandes brutes de la production, qui comptent aussi les équipements remis sur "
                       "étagère. Elle peut fortement surestimer les commandes.", "warn", "⚠️")
        if flottes and communs:
            ui.callout(f"<b>{communs} PN</b> sont aussi montés sur d'autres flottes : la colonne « Part des flottes choisies » "
                       "indique la part qui revient aux flottes filtrées.", "info", "ℹ️")

    with ui.section(f"{TAB_ID}_prev_parpn", "Prévision par PN", "À commander sur 12, 24 et 36 mois, et évolution de la conso",
                    tag=str(int((suivis["À commander 36 mois (qté)"] > 0).sum())),
                    info="Évolution : 12 derniers mois comparés aux 12 mois d'avant. ▲ hausse, ▼ baisse (plus de 20 %)."):
        d = suivis[suivis["À commander 36 mois (qté)"] > 0].sort_values("Valeur 12 mois (€)", ascending=False)
        if len(d):
            cols, groupes = _colonnes_pn(d)
            ui.tableau_html(d[list(cols)].rename(columns=cols), statut="Statut", couleurs=pv.STATUS_COLORS, colonne_config=CFG,
                            pn=["PN"], fixes=2, groupes=groupes, hauteur="30rem")
        else:
            ui.callout("Aucune commande à prévoir sur les 36 prochains mois.", "ok", "check-circle")

    _tendance_pn(suivis)
    fours = pv.par_fournisseur(s, plan)
    with ui.section(f"{TAB_ID}_prev_four", "Forecast par fournisseur", "12, 24 et 36 prochains mois", tag=str(len(fours)),
                    info="Valeur des commandes à passer chez chaque fournisseur (code fournisseur), année par année."):
        top = fours[fours["Valeur 36 mois (€)"] > 0].head(12)
        an = {lib.split(" · ")[0]: (top[f"Valeur {k} mois (€)"] - (top[f"Valeur {k - 12} mois (€)"] if k > 12 else 0)).to_numpy()
              for (_, k, lib) in tr}
        ui.graphe(charts.barres(list(top["Fournisseur"]), an,
                                {lib.split(" · ")[0]: col for (_, _, lib), col in zip(tr, [COLORS["ko"], COLORS["warn"], COLORS["navy_2"]])},
                                empile=True, fmt=charts.euros, titre="Valeur à commander par fournisseur, année par année")
                  if len(top) else charts.vide("Aucune commande sur les 36 prochains mois"),
                  " · ".join(lib for _, _, lib in tr))
        ui.tableau_html(fours.rename(columns=COL_FOUR), colonne_config=CFG, pn=["Fournisseur"], fixes=1, groupes=GROUPES_FOUR,
                        hauteur="26rem" if len(fours) > 8 else "none")
    _vue_fournisseur_prev(s, o, fours, plan, today or date.today())
    with ui.section(f"{TAB_ID}_prev_statut", "Statut des PN et des groupes d'avions"):
        a, b = st.columns(2, gap="large")
        with a:
            ct = s.assign(c=tx.categorie(s)).groupby(["c", "Statut prévision"]).size().unstack(fill_value=0)
            ct = ct.reindex(columns=[c for c in pv.STATUS_ORDER if c in ct.columns], fill_value=0)
            ui.graphe(charts.parts(ct.reindex([c for c in tx.categories(s) if c in ct.index]), pv.STATUS_COLORS, "PN par statut"))
        with b:
            if len(gs):
                cg = gs.groupby(["equipment", "Statut groupe"]).size().unstack(fill_value=0)
                cg = cg.reindex(columns=[c for c in pv.GROUP_STATUS_ORDER if c in cg.columns], fill_value=0)
                ui.graphe(charts.parts(cg, pv.GROUP_STATUS_COLORS, "Groupes × classe × composant"))
            else:
                ui.graphe(charts.vide("Aucun groupe d'avions"))
    _detail_pn(s, res)


def _colonnes_pn(d) -> tuple[dict, list | None]:
    """Colonnes du tableau « Prévision par PN » (et du détail fournisseur) et groupes d'en-têtes ; avec un filtre
    Flotte, « Part des flottes choisies » suit la colonne Flottes."""
    cols = {}
    for k, v in COL_PN.items():
        cols[k] = v
        if k == "Flottes" and "Part des flottes choisies (%)" in d and d["Part des flottes choisies (%)"].notna().any():
            cols["Part des flottes choisies (%)"] = "Part des flottes choisies (%)"
    cols = {k: v for k, v in cols.items() if k in d.columns}
    if set(COL_PN) <= set(cols):
        return cols, [("Pièce", 7 + (len(cols) - len(COL_PN)))] + GROUPES_PN[1:]
    return cols, None


def _tendance_pn(s):
    """Évolution de la consommation par PN : répartition par tendance et tableau (hausse d'abord)."""
    if s.empty or "Tendance conso" not in s:
        return
    with ui.section(f"{TAB_ID}_prev_tendance", "Évolution de la consommation", "12 derniers mois comparés aux 12 mois d'avant",
                    tag=str(int((s["Tendance conso"] == "En hausse").sum())),
                    info="Tendance : plus de 20 % de sorties en plus (hausse) ou en moins (baisse) sur les 12 derniers mois. "
                         "« Nouveau » : aucune sortie les 12 mois d'avant."):
        a, b = st.columns([1, 1.6], gap="large")
        with a:
            ct = s.assign(c=tx.categorie(s)).groupby(["c", "Tendance conso"]).size().unstack(fill_value=0)
            ct = ct.reindex(columns=[t for t in pv.TENDANCES if t in ct.columns], fill_value=0)
            ui.graphe(charts.parts(ct.reindex([c for c in tx.categories(s) if c in ct.index]), pv.TENDANCE_COLORS, "PN par tendance"))
        with b:
            top = s[s["Tendance conso"].isin(["En hausse", "Nouveau"])].assign(
                _d=lambda d: d["Conso 12 mois"].fillna(0) - d["Conso 12 mois d'avant"].fillna(0)).nlargest(12, "_d")
            ui.graphe(charts.barres_h([(r["PNR"], r["_d"], f"+{charts.entier(r['_d'])} pièces · "
                                        + (f"{r['Évolution conso (%)']:+.0f} %" if pd.notna(r["Évolution conso (%)"]) else "nouveau"))
                                       for _, r in top.iterrows()], couleur=pv.TENDANCE_COLORS["En hausse"],
                                      titre="Plus fortes hausses (pièces en plus sur 12 mois)", max_lignes=12)
                      if len(top) else charts.vide("Aucun PN en hausse"))
        rang = {t: i for i, t in enumerate(pv.TENDANCES)}
        d = s.assign(_r=s["Tendance conso"].map(rang)).sort_values(["_r", "Conso 12 mois"], ascending=[True, False])
        t = d[[c for c in COL_TENDANCE if c in d.columns and d[c].notna().any()]].rename(columns=COL_TENDANCE)
        ui.tableau(t, column_config=CFG, height=380, statut="Tendance", couleurs=pv.TENDANCE_COLORS)


def _tableaux_prevision(s, plan, gs, res):
    choix = st.selectbox("Tableau", ["À commander maintenant", "Plan de commande", "Manque avant livraison",
                                     "PN non commandés (dormants, inactifs, obsolètes)", "Groupes d'avions", "Besoin par groupe et PN"],
                         key=K + "tab_prev", persist_state="page", label_visibility="collapsed")
    if choix == "À commander maintenant":
        d = s[s["Qté à commander maintenant"] > 0].sort_values("Valeur à commander maintenant (€)", ascending=False)
        d = d[[c for c in COL_PREV if c in d.columns]].rename(columns=COL_PREV)
    elif choix == "Plan de commande":
        d = plan.sort_values(["Mois de commande", "PNR"])
    elif choix == "Manque avant livraison":
        d = s[s["Manque avant livraison possible (qté)"] > 0].sort_values("Manque avant livraison possible (qté)", ascending=False)
        d = d[[c for c in [*COL_PREV, "Manque avant livraison possible (qté)"] if c in d.columns]].rename(columns=COL_PREV)
    elif choix == "PN non commandés (dormants, inactifs, obsolètes)":
        d = s[s["Statut prévision"].isin(["Dormant / inactif : pas de commande", pv.OBSOLETE])]
        d = d.sort_values(pv.BLOQUEE, ascending=False)
        d = d[[c for c in [*COL_PREV, "Statut activité", "CLASS CODE", pv.BLOQUEE] if c in d.columns]].rename(
            columns={**COL_PREV, "CLASS CODE": "Classe code"})
    elif choix == "Groupes d'avions":
        d = gs.sort_values(["equipment", "Ecart vs objectif (avions)"])
    else:
        d = res["gp"][res["gp"]["pn"].isin(s["PNR"])]
    ui.tableau(d, column_config=CFG, width=1100, height=440, statut="Statut", couleurs=pv.STATUS_COLORS)


@st.fragment
def _vue_fournisseur_prev(s, o, fours, plan, today):
    """Forecast d'un fournisseur sur 12, 24 et 36 mois : chiffres, PN, export à lui envoyer."""
    if fours.empty:
        return
    with ui.section(f"{TAB_ID}_prev_vf", "Forecast d'un fournisseur", "À envoyer au fournisseur : 12, 24 et 36 prochains mois"):
        f1, f2 = st.columns([2, 1], vertical_alignment="center")
        seuls = f2.toggle("Uniquement les fournisseurs avec des commandes à prévoir", value=True, key=K + "vf_seuls", persist_state="page")
        opts = fours[fours["Qté 36 mois"] > 0] if seuls and (fours["Qté 36 mois"] > 0).any() else fours
        libelles = {r["Fournisseur"]: f"{r['Fournisseur']}  ·  12 mois : {charts.euros(r['Valeur 12 mois (€)'])}  ·  "
                                      f"36 mois : {charts.euros(r['Valeur 36 mois (€)'])}" for _, r in opts.iterrows()}
        f = f1.selectbox("Fournisseur", list(libelles), format_func=libelles.get, key=K + "vf", persist_state="page",
                         label_visibility="collapsed")
        cand = pv.suivis(s)
        d = cand[cand["Fournisseur"] == f].sort_values("Valeur 12 mois (€)", ascending=False)
        lignes = o[o["Fournisseur"] == f] if len(o) else o
        _nom_fournisseur(lignes)
        ec = lignes.dropna(subset=["Ecart promis vs demandé (j)"]) if len(lignes) else lignes
        ec = ec[ec["Statut commande"] != "En attente BFE"] if len(ec) else ec
        tr = pv.tranches(today)
        ui.kpi_grid([
            ui.kpi_card("Maintenant", charts.euros(d["Valeur à commander maintenant (€)"].sum()),
                        f"{charts.entier(d['Qté à commander maintenant'].sum())} pièces", "ko", "cart"),
            *[ui.kpi_card(f"{k} prochains mois", charts.euros(d[f"Valeur {k} mois (€)"].sum()),
                          f"{charts.entier(d[f'À commander {k} mois (qté)'].sum())} pièces · {(d[f'À commander {k} mois (qté)'] > 0).sum()} PN",
                          {12: "warn", 24: "orange", 36: "navy"}[k], "calendar") for k in pv.PERIODES],
            ui.kpi_card("PN en hausse", charts.entier(d["Tendance conso"].isin(["En hausse", "Nouveau"]).sum()),
                        f"{charts.entier((d['Tendance conso'] == 'En baisse').sum())} en baisse · sur {len(d)} PN suivis", "orange", "trend",
                        info="Consommation des 12 derniers mois comparée aux 12 mois d'avant (plus ou moins 20 %)."),
            ui.kpi_card("Écart promis − demandé", f"{ec['Ecart promis vs demandé (j)'].mean():+.0f} j" if len(ec) else "—",
                        f"moyenne sur {len(ec)} ligne(s)" if len(ec) else "aucune date promise", "navy"),
        ])
        pm = plan[plan["PNR"].isin(set(d["PNR"]))]
        cols, groupes = _colonnes_pn(d)
        cols.pop("Fournisseur", None)
        if groupes:
            groupes = [(groupes[0][0], groupes[0][1] - 1)] + groupes[1:]
        ui.tableau_html(d[list(cols)].rename(columns=cols), statut="Statut", couleurs=pv.STATUS_COLORS, colonne_config=CFG,
                        pn=["PN"], fixes=2, groupes=groupes, hauteur="24rem" if len(d) > 6 else "none")
        e1, e2, e3 = st.columns([1.2, 1, 1])
        with e1:
            ui.telecharger(lambda: _export_forecast_fournisseur(f, d, pm, lignes, today), _nom_forecast(f),
                           K + "export_forecast_four", label="Exporter le forecast du fournisseur (Excel)")
        with e2.popover("Commandes en cours chez ce fournisseur", width="stretch"):
            if o.empty:
                st.caption("Aucun fichier de commandes chargé.")
            else:
                oc = o[((o["Fournisseur"] == f) | o["PNR"].isin(d["PNR"])) & (o["Qte restante"].fillna(0) > 0)]
                cols_o = {**COL_RELANCES, "Date emission commande": "Émise", "Ecart promis vs demandé (j)": "Écart (j)"}
                t = oc.sort_values("Date livraison promise")[[c for c in cols_o if c in oc.columns]].rename(columns=cols_o)
                t["Statut"] = t["Statut"].map(STATUT_LIBELLES).fillna(t["Statut"])
                ui.tableau(t, column_config=CFG, width=1100, height=420)
        with e3.popover("Écart promis − demandé", width="stretch"):
            _ecarts_lignes(ec, lignes)


def _nom_forecast(fournisseur: str) -> str:
    return f"Supply360_forecast_{re.sub(r'[^A-Za-z0-9]+', '_', str(fournisseur)).strip('_')}_{date.today():%Y%m%d}.xlsx"


def _export_forecast_fournisseur(f, d, pm, lignes, today) -> bytes:
    """Forecast à envoyer au fournisseur : synthèse 12 / 24 / 36 mois, détail par PN, quantités mois par mois,
    commandes en cours."""
    tr = pv.tranches(today)
    synth = pd.DataFrame([{"Période": f"{k} prochains mois ({tr[0][2].split(' · ')[1].split(' → ')[0]} → {tr[i][2].split(' → ')[1]})",
                           "Pièces à commander": d[f"À commander {k} mois (qté)"].sum(), "PN": int((d[f"À commander {k} mois (qté)"] > 0).sum()),
                           "Valeur (€)": d[f"Valeur {k} mois (€)"].sum()} for i, k in enumerate(pv.PERIODES)])
    par_pn = d[[c for c in ["PNR", "CCN", "DESCRIPTION", "REF_Equipement", "Conso brute 12 mois (demandes)", "Conso 12 mois", "Conso 12 mois d'avant",
                            "Évolution conso (%)", "Conso prévue 12 mois (qté)", "QTE SUR ÉTAGÈRE", "QTE EN CDE",
                            "Qté à commander maintenant", "À commander 12 mois (qté)", "À commander 24 mois (qté)",
                            "À commander 36 mois (qté)", "Prix unitaire (€)", "Prix basé sur", "Valeur 12 mois (€)", "Valeur 24 mois (€)",
                            "Valeur 36 mois (€)"] if c in d.columns]].rename(columns={
        "PNR": "PN", "DESCRIPTION": "Description", "REF_Equipement": "Catégorie", "QTE SUR ÉTAGÈRE": "Stock",
        "Conso brute 12 mois (demandes)": "Demandes 12 mois (brut)", "Conso 12 mois": "Conso nette 12 mois",
        "Conso 12 mois d'avant": "Conso nette 12 mois d'avant",
        "QTE EN CDE": "En commande", "Qté à commander maintenant": "Maintenant", "Prix unitaire (€)": "Prix unitaire PMP (€)"})
    mois = pv.plan_par_mois(pm, today).reset_index().rename(columns={"PNR": "PN"}) if len(pm) else pd.DataFrame()
    feuilles = {"Synthèse": synth, "Par PN": par_pn, "Par mois (pièces)": mois}
    if lignes is not None and len(lignes):
        oc = lignes[lignes["Qte restante"].fillna(0) > 0]
        cols = {"Commande": "Commande", "PNR": "PN", "CCN": "CCN", "Date emission commande": "Émise le",
                "Date livraison demandee": "Livraison demandée", "Date livraison promise": "Livraison promise",
                "Qte restante": "Reste à livrer", "Statut commande": "Statut"}
        feuilles["Commandes en cours"] = oc[[c for c in cols if c in oc.columns]].rename(columns=cols)
    return sio.exporter_excel(feuilles)


def _ecarts_lignes(ec, lignes):
    """Graphe « Écart promis − demandé par ligne » du fournisseur (du plus gros retard au plus en avance)."""
    titre = "Écart promis − demandé par ligne (jours)"
    if len(lignes) == 0:
        ui.graphe(charts.vide(f"{titre} : aucune commande chez ce fournisseur dans le fichier {sio.FICHIER_COMMANDES}."))
        return
    if ec.empty:
        ui.graphe(charts.vide(f"{titre} : aucune ligne avec date promise et date demandée."))
        return
    e = ec.sort_values("Ecart promis vs demandé (j)", ascending=False).head(40)
    date = lambda v: v.strftime("%d/%m/%Y") if pd.notna(v) else "—"
    infos = [[f"PN {r['PNR']}", f"Demandée : {date(r['Date livraison demandee'])}", f"Promise : {date(r['Date livraison promise'])}",
              f"Reste à livrer : {charts.entier(r.get('Qte restante'))}"] for _, r in e.iterrows()]
    ui.graphe(charts.ecarts(e["Commande"].astype(str) + " · " + e["PNR"], e["Ecart promis vs demandé (j)"], infos,
                            seuil=tx.LATE_BUFFER_DAYS, titre=titre + (f" · 40 plus gros écarts sur {len(ec)}" if len(ec) > 40 else "")))


@st.fragment
def _detail_pn(s, res):
    pool = s[s["Dans la prévision"]].sort_values(["Statut prévision", "PNR"])
    if pool.empty:
        return
    with ui.section(f"{TAB_ID}_prev_pn", "Détail du calcul pour un PN"):
        libelles = dict(zip(pool["PNR"], pool["PNR"] + " — " + pool.get("DESCRIPTION", pd.Series("", index=pool.index)).fillna("").astype(str).str[:40]
                            + " · " + pool["Statut prévision"]))
        pn = st.selectbox("PN", list(libelles), format_func=libelles.get, key=K + "pn_prev", persist_state="page", label_visibility="collapsed")
        r = pool[pool["PNR"] == pn].iloc[0]
        ui.kpi_grid([
            ui.kpi_card("Stock étagère", charts.entier(r["QTE SUR ÉTAGÈRE"] or 0)),
            ui.kpi_card("En commande", charts.entier(r["QTE EN CDE"] or 0), "", "info"),
            ui.kpi_card("Conso prévue (12 mois)", charts.entier(r["Conso prévue 12 mois (qté)"]),
                        f"{r['Tendance conso']} · 12 mois : {charts.entier(r['Conso 12 mois'])}", TENDANCE_TONS.get(r["Tendance conso"], "navy"),
                        "trend"),
            ui.kpi_card("Stock à tenir", charts.entier(r["Stock à tenir (qté)"]),
                        f"minimum flotte {charts.entier(r['Besoin minimum (qté)'])} · sécurité {charts.entier(r['Stock de sécurité (qté)'])}",
                        "warn"),
            ui.kpi_card("Délai", f"{int(r['Délai (mois)'])} mois", r["Source délai"]),
            ui.kpi_card("À commander", charts.entier(r["Qté à commander maintenant"]),
                        f"12 mois : {charts.entier(r['À commander 12 mois (qté)'])} · 24 : {charts.entier(r['À commander 24 mois (qté)'])}"
                        f" · 36 : {charts.entier(r['À commander 36 mois (qté)'])}", "ko"),
        ])
        c12, c24, av, br = (r.get(k) for k in ("Conso 12 mois", "Conso 24 mois", "Conso 12 mois d'avant",
                                                "Conso brute 12 mois (demandes)"))
        st.caption(f"Fournisseur : **{r['Fournisseur']}** · statut : **{r['Statut prévision']}** · conso "
                   f"{str(r.get('Base conso', '')).lower()} : 12 mois **{charts.entier(c12)}**, 24 mois **{charts.entier(c24)}** "
                   f"(12 mois d'avant : {charts.entier(av)}) · demandes brutes 12 mois : {charts.entier(br)}")
        detail = pv.explain_pn(pn, res["gp"])
        if len(detail):
            st.markdown("**Flottes et groupes d'avions qui utilisent ce PN** (stock minimum)")
            ui.tableau(detail, height=min(38 + 35 * max(len(detail), 1), 300))
