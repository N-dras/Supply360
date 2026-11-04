"""Onglet « Textile cabine » : stock, consommation, commandes et prévision de commandes des références textile.

Repris du dashboard Textile (streamlit_textile_dashboard.py, textile_analytics.py, textile_policy.py).
Imports : État du stock, Commandes (SAP), Références textile ; pour la prévision : Pièces par avion.
"""

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
              ("Dernier PU (achat) Euros", "valorisation", False), ("DATE DERNIERE CONSO", "2001 = jamais consommé", False),
              ("CODE FOURNISSEUR, DERNIER FOURNISSEUR", "fournisseur des PN sans commande", False),
              ("LT observé moyen sur 2 ans, B/O, RP, EOQ", "", False)],
    "commandes": [("PN", "", True), ("Commande", "", True), ("Fournisseur, Code fournisseur", "nom retrouvé par le code", False),
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
COL_PREV = {"PNR": "PN", "CCN": "CCN", "DESCRIPTION": "Description", "REF_Equipement": "Catégorie", "Statut prévision": "Statut",
            "Qté à commander maintenant": "À commander", "Date 1ère commande": "1re commande", "QTE SUR ÉTAGÈRE": "Stock",
            "QTE EN CDE": "En commande", "Besoin minimum (qté)": "Stock minimum", "Délai (mois)": "Délai (mois)",
            "Source délai": "Source délai", "Commandes recommandées sur l'horizon (qté)": "À commander sur la période",
            "Valeur à commander maintenant (€)": "Valeur maintenant (€)", "Fournisseur": "Fournisseur"}
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
    "Valeur sur l'horizon (€)": st.column_config.NumberColumn("Valeur sur l'horizon (€)", format="%.0f €"),
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
def _prevision(cle_tables: tuple, pieces: tuple, params: pv.Params, regles: tuple):
    """(pbi avec prévision, résultats) — clé = fichiers + paramètres + règles PE (n-uplets, pas de tables).

    Le Planning PE n'est pas importé pour l'instant : la prévision couvre le stock minimum (avions d'avance).
    """
    s_all, o_all = _tables(*cle_tables)
    parts, fleet, _ = _pieces(*pieces, params)
    parts = pv.rattacher_pieces(parts, s_all)  # PN différent du stock mais même CCN : même pièce
    rules = pd.DataFrame(list(regles), columns=["Equipement", "Classe", "Composant", "Cycle PE (ans)"])
    return pv.run_policy(s_all, o_all, parts, fleet, None, rules, params, pd.Timestamp(cle_tables[3]))


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
def _parametres(parts) -> tuple[pv.Params, tuple]:
    """Paramètres du sous-onglet Prévision (buffer, délais, composants, politique d'entretien)."""
    d = pv.Params()
    st.caption("Réglages du sous-onglet **Prévision** (stock d'avance à garder). Le planning de remplacement des mousses "
               "est dans l'onglet **PE mousses**.")
    if True:
        a, b = st.columns(2)
        ratio = a.slider("Avions d'avance (% du groupe)", 2, 40, int(d.buffer_ratio * 100), key=K + "ratio", persist_state="page",
                         help="10 % : 10 avions → 1, 50 avions → 5.")
        bmin = b.number_input("Minimum d'avions d'avance par groupe", 1, 10, d.buffer_min, key=K + "bmin", persist_state="page")
        hz = a.slider("Période couverte par la prévision (mois)", 12, 60, d.horizon_months, key=K + "hz", persist_state="page")
        never = b.checkbox("Stock d'avance aussi pour les pièces jamais remplacées (cycle 0)", value=d.buffer_on_never,
                           key=K + "never", persist_state="page",
                           help="Coché : toutes les pièces ont un stock d'avance. Décoché : seulement celles qui ont un cycle de remplacement.")
        lt_def = a.number_input("Délai par défaut (jours)", 1, 730, d.lt_default, key=K + "ltdef", persist_state="page",
                                help="Quand ni le fournisseur ni le PN n'ont de délai.")
        lt_basis = b.selectbox("Délai du fournisseur basé sur", ["observe", "promis"], key=K + "ltbasis", persist_state="page",
                               format_func={"observe": "LT observé (historique 2 ans)", "promis": "Délais promis actuels"}.get)
        bfe = a.number_input("Délai supposé si attente de BFE (mois)", 1, 36, d.bfe_delay_months, key=K + "bfe", persist_state="page",
                              help="Commandes datées 2049 (en attente de matière première) : délai de livraison supposé.")
        comp = b.selectbox("Assise ou dossier, si la description ne le dit pas", ["Assise", "Dossier"], key=K + "comp", persist_state="page")
        kw_dos = a.text_input("Mots qui désignent un dossier", d.dossier_kw, key=K + "kwdos", persist_state="page",
                             help="Cherchés dans la description de la pièce, séparés par des virgules. Ils passent avant ceux de l'assise.")
        kw_ass = b.text_input("Mots qui désignent une assise", d.assise_kw, key=K + "kwass", persist_state="page",
                             help="Cherchés dans la description de la pièce, séparés par des virgules.")
        p = pv.Params(buffer_ratio=ratio / 100, buffer_min=int(bmin), buffer_on_never=bool(never), horizon_months=int(hz),
                      lt_default=int(lt_def), lt_basis=lt_basis, bfe_delay_months=int(bfe), assise_kw=kw_ass, dossier_kw=kw_dos,
                      default_component=comp)
        regles = None
        if parts is not None:
            # Grille de champs (et non st.data_editor : indisponible sous stlite, il dépend de pyarrow).
            st.markdown("**Cycle de remplacement (en années)** · 0 = jamais remplacé. Sert seulement si la case "
                        "« Stock d'avance aussi pour les pièces jamais remplacées » est décochée.")
            base = pv.regles_pe_defaut(parts)
            cols = st.columns(3)
            cycles = []
            for i, r in enumerate(base.itertuples(index=False)):
                cle = f"{K}prev_pe__{pv.cle_regle(r.Equipement, r.Classe, r.Composant)}"
                cycles.append(cols[i % 3].number_input(f"{r.Equipement} · {r.Classe} · {r.Composant}", 0.0, 20.0,
                                                       float(r[3]), 0.5, key=cle, persist_state="page"))
            regles = tuple((r.Equipement, r.Classe, r.Composant, float(c)) for r, c in zip(base.itertuples(index=False), cycles))
    return p, regles


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
        with ui.zone_repliable(K + "manuel", "Import manuel (Parcourir) et colonnes attendues"):
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
                                      help="Date des données : âge des commandes, retards, début de la prévision et du planning PE.")
                seul = st.toggle("Uniquement les PN du catalogue textile", value=True, key=K + "seul", persist_state="page",
                                 help="Limite l'analyse aux PN du fichier Références textile.")
            with t_prev:
                params, regles = _parametres(parts)
    return f_stock, f_cmd, f_ref, f_pieces, today, seul, params, regles


def render() -> None:
    entete = st.container()
    f_stock, f_cmd, f_ref, f_pieces, today, seul, params, regles = _bloc_import()
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
        cle_prev = (cle, (f_pieces[1], f_pieces[0]), params, regles) if f_pieces else None
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
    resume = (f"{len(rel)} relance(s) fournisseur : {r['en_retard']} en retard, {r['sans_date']} sans date promise, "
              f"{r['bfe']} en attente de BFE" if len(rel) else "Aucune relance fournisseur à lancer")
    with ui.section(f"{TAB_ID}_syn", "Synthèse", f"{'Toutes catégories' if cat == TOUTES else cat.capitalize()} · {resume}",
                    export=_export_btn("export__btn"), carte=False):
        ui.kpi_grid([
            ui.kpi_card("PN suivis", charts.entier(r["pn"]), f"{len(tx.categories(s))} catégorie(s)", "navy", "layers"),
            ui.kpi_card("Valeur du stock", charts.euros(r["valeur_stock"]), "sur étagère", "teal", "package"),
            ui.kpi_card("Valeur en commande", charts.euros(r["valeur_commande"]), f"{r['lignes']} lignes de commande", "info", "truck"),
            ui.kpi_card("Lignes en retard", charts.entier(r["en_retard"]), f"{r['sans_date']} sans date promise", "ko", "clock"),
            ui.kpi_card("Stock dormant", charts.euros(r["valeur_dormant"]), f"{r['dormants']} PN sans conso depuis 3 ans", "warn", "moon"),
        ])

    with ui.section(f"{TAB_ID}_rel", "Relances fournisseurs", "Du plus urgent au moins urgent", tag=str(len(rel)),
                    export=_export_btn("export_rel__btn")):
        if len(rel):
            _relances_html(rel, "relances")
        else:
            ui.callout("Aucune relance à lancer.", "ok", "check-circle")

    with ui.section(f"{TAB_ID}_cat", "Catégories", "Répartition du stock, des commandes et de l'activité par catégorie"):
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
    with ui.section(f"{TAB_ID}_stock_pn", "Stock par PN", "Du plus urgent au moins urgent · cliquez sur un titre de colonne pour trier ou filtrer",
                    tag=str(len(etat)), export=_export_btn("export_stock_pn__btn")):
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
    with ui.section(f"{TAB_ID}_cmd", "Commandes", "Statut de chaque ligne de commande : voir « Règles de calcul »"):
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
    with ui.section(f"{TAB_ID}_lignes", "Toutes les lignes", "Cliquez sur un titre de colonne pour trier ou filtrer"):
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
    with ui.section(f"{TAB_ID}_four", "Fournisseurs"):
        a, b = st.columns(2, gap="large")
        with a:
            vc = o["Fournisseur"].value_counts().head(12)
            cum = (o["Fournisseur"].value_counts().cumsum() / len(o.dropna(subset=["Fournisseur"])) * 100).head(12)
            ui.graphe(charts.barres(vc.index, {"Lignes de commande": vc.values}, {"Lignes de commande": COLORS["navy_2"]},
                                    ligne={"% cumulé": cum.values}, fmt_ligne=charts.pourcent, titre="Volume de lignes (Pareto)"))
        with b:
            late = o[o["Statut commande"] == "En retard"]
            if late.empty:
                ui.graphe(charts.vide("Aucune commande en retard"))
            else:
                g = late.groupby("Fournisseur").agg(n=("PNR", "size"), j=("Jours de retard", "mean")).sort_values("n", ascending=False).head(12)
                ui.graphe(charts.barres(g.index, {"Lignes en retard": g["n"]}, {"Lignes en retard": COLORS["ko"]},
                                        ligne={"Retard moyen (j)": g["j"]}, fmt_ligne=lambda v: f"{v:.0f} j",
                                        titre="Fournisseurs avec le plus de retards"))
        a, b = st.columns(2, gap="large")
        with a:
            dl = tx.delais_fournisseurs(o).head(12)
            ui.graphe(charts.barres_h([(r["Fournisseur"], r["Délai moyen promis (j)"], f"{r['Délai moyen promis (j)']:.0f} j")
                                       for _, r in dl.iterrows()], titre="Délai moyen promis (émission → livraison)")
                      if len(dl) else charts.vide("Pas assez de lignes avec délai (3 minimum par fournisseur)"))
        with b:
            bfe = o[o["Statut commande"] == "En attente BFE"]
            vb = bfe["Fournisseur"].value_counts().head(12)
            ui.graphe(charts.barres_h(list(vb.items()), couleur=COLORS["violet"], titre="Lignes en attente de BFE")
                      if len(vb) else charts.vide("Aucune commande en attente de BFE"))
        ch = tx.chaleur_livraisons(o, today)
        ui.graphe(charts.chaleur(ch, "Livraisons promises par fournisseur et par mois"))
    _vue_fournisseur(o)


@st.fragment
def _vue_fournisseur(o):
    fours = list(o["Fournisseur"].dropna().value_counts().index)
    if not fours:
        return
    with ui.section(f"{TAB_ID}_vf", "Vue par fournisseur"):
        f = st.selectbox("Fournisseur", fours, key=K + "fournisseur", persist_state="page", label_visibility="collapsed")
        d = o[o["Fournisseur"] == f]
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
    pu = pd.to_numeric(s.get("Dernier PU (achat) Euros", pd.Series(0.0, index=s.index)), errors="coerce").fillna(0)
    evol = (c12.sum() / c_av.sum() - 1) * 100 if c_av.sum() > 0 else None
    with ui.section(f"{TAB_ID}_conso", "Consommation", "Pièces sorties du stock, d'après l'État du stock", carte=False):
        ui.kpi_grid([
            ui.kpi_card("Sorties sur 12 mois", charts.entier(c12.sum()), recent, "navy", "trend"),
            ui.kpi_card("Valeur sortie", charts.euros((c12 * pu).sum()), "au dernier prix d'achat", "teal", "euro"),
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
**L'idée** : toujours avoir assez de pièces pour équiper une partie des avions de chaque groupe (ex. « A320 Group 1 »).
La prévision couvre la période **{periode}** (réglable dans Paramètres › Horizon).

1. **Combien d'avions d'avance ?** 10 % des avions du groupe, au moins 1 (réglable dans Paramètres).
   Exemple : un groupe de 50 avions → 5 avions d'avance.
2. **Stock minimum d'une pièce** = nombre de pièces par avion × avions d'avance, pour chaque groupe qui l'utilise.
   Exemple : 30 housses par avion × 5 avions = **150 housses** à garder.
3. **Remplacements prévus (PE)** : les pièces qui seront remplacées sur les avions augmentent le besoin le mois prévu.
4. **Ce qui manque** = stock minimum + remplacements prévus − (stock en rayon + commandes déjà passées).
5. **Quand commander ?** Assez tôt pour que la pièce arrive avant le manque, en tenant compte du délai du fournisseur.
   Si c'est déjà trop tard, la commande est à passer tout de suite, et la quantité qui manquera en attendant la
   livraison est indiquée.
6. **Statuts** : **A commander** = déjà sous le minimum ; **A planifier** = passera sous le minimum plus tard ;
   **OK** = rien à faire.
7. **Jamais de commande proposée** pour les pièces dormantes (aucune sortie depuis 3 ans), inactives (ni stock, ni
   sortie, ni commande), obsolètes ou supprimées (classe code 3, 8 ou 9). La quantité qui aurait été commandée est
   affichée à part.
8. **Fournisseur proposé** : celui des commandes habituelles de la pièce ; à défaut, celui de l'État du stock.
"""


def _section_prevision(prev, cat, o, perim, flottes=None, params=None, today=None):
    if prev is None:
        with ui.section(f"{TAB_ID}_prev_vide", "Prévision de commandes"):
            ui.empty_state(f"Importez le fichier {pv.FICHIER_PIECES}", "La prévision s'appuie sur les pièces par avion. "
                           "Les paramètres sont réglables dans « Paramètres » › Prévision.",
                           [(pv.FICHIER_PIECES, False)], icon="🧮")
        return
    params = params or pv.Params()
    pbi, res = prev
    s = pbi[_dans_perimetre(pbi, perim)]
    plan = res["plan"][res["plan"]["PNR"].isin(set(s["PNR"]))]
    gs = res["gs"]
    if perim[0]:
        gs = gs[gs["equipment"].isin(perim[0])]
    if flottes:
        gs = gs[gs["aircraft_type"].isin(flottes)]
    now = s[s["Qté à commander maintenant"] > 0]
    # Période couverte par la prévision (paramètre « Horizon ») : écrite en clair, jamais « horizon » seul
    debut = pd.Timestamp(today or date.today()).to_period("M").to_timestamp()
    fin = debut + pd.DateOffset(months=params.horizon_months - 1)
    periode = f"{MOIS_COURTS[debut.month - 1]} {debut.year} → {MOIS_COURTS[fin.month - 1]} {fin.year}"
    v_now = now["Valeur à commander maintenant (€)"].sum()
    v_total = s["Valeur commandes recommandées (€)"].sum()
    plus_tard = s[(s["Commandes recommandées sur l'horizon (qté)"] > s["Qté à commander maintenant"])]
    with ui.section(f"{TAB_ID}_prev", "Prévision de commandes",
                    f"Garder assez de pièces pour équiper {params.buffer_ratio:.0%} des avions de chaque groupe · "
                    f"période de {params.horizon_months} mois : {periode}", carte=False):
        ui.kpi_grid([
            ui.kpi_card("À commander maintenant", charts.euros(v_now), f"{len(now)} PN, chez {now['Fournisseur'].nunique()} fournisseur(s)",
                        "ko", "cart"),
            ui.kpi_card("À commander plus tard", charts.euros(max(v_total - v_now, 0)),
                        f"{len(plus_tard)} PN, d'ici {MOIS_COURTS[fin.month - 1]} {fin.year}", "warn", "calendar"),
            ui.kpi_card("Total sur la période", charts.euros(v_total), periode, "navy", "euro"),
            ui.kpi_card("Groupes d'avions sous l'objectif", charts.entier((gs["Statut groupe"] == "Sous l'objectif").sum()),
                        f"sur {charts.entier(len(gs))} (groupe × classe × assise / dossier)", "accent", "plane"),
            ui.kpi_card("Jamais commandés", charts.entier(s["Statut prévision"].isin(["Dormant / inactif : pas de commande", pv.OBSOLETE]).sum()),
                        "PN dormants, inactifs ou obsolètes", "violet", "x"),
        ])
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1.popover("Comment c'est calculé", width="stretch"):
            st.markdown(EXPLICATION.replace("{periode}", periode))
        with c2.popover("Autres tableaux", width="stretch"):
            _tableaux_prevision(s, plan, gs, res)
        with c3:
            cle_export = st.session_state[K + "cle_export"]
            ui.telecharger(lambda: _export(*cle_export), sio.nom_export(TAB_ID), K + "export_prev__btn")

    with ui.section(f"{TAB_ID}_prev_now", "À commander maintenant", "Commandes à passer ce mois-ci, la plus grosse valeur en premier",
                    tag=str(len(now))):
        if len(now):
            d = now.sort_values("Valeur à commander maintenant (€)", ascending=False)
            ui.tableau(d[[c for c in COL_PREV if c in d.columns]].rename(columns=COL_PREV), column_config=CFG, height=360,
                       statut="Statut", couleurs=pv.STATUS_COLORS)
        else:
            ui.callout("Rien à commander maintenant.", "ok", "check-circle")

    fours = pv.par_fournisseur(s, plan)
    with ui.section(f"{TAB_ID}_prev_four", "Par fournisseur", f"Ce qu'il faut commander chez chacun, maintenant et d'ici {periode.split(' → ')[1]}",
                    tag=str(len(fours))):
        top = fours[fours["Valeur sur l'horizon (€)"] > 0].head(12)
        ui.graphe(charts.barres(list(top["Fournisseur"]), {"Maintenant": top["Valeur maintenant (€)"].to_numpy(),
                                                            "Plus tard": (top["Valeur sur l'horizon (€)"] - top["Valeur maintenant (€)"]).clip(lower=0).to_numpy()},
                                {"Maintenant": COLORS["ko"], "Plus tard": COLORS["warn"]}, empile=True, fmt=charts.euros,
                                titre="Valeur à commander par fournisseur") if len(top) else charts.vide("Aucune commande sur la période"),
                  f"Rouge : à commander maintenant · jaune : plus tard, d'ici {periode.split(' → ')[1]}")
        ui.tableau(fours.rename(columns={"Valeur maintenant (€)": "À commander maintenant (€)", "Valeur sur l'horizon (€)": "Total sur la période (€)",
                                         "Qté à commander maintenant": "Qté maintenant", "PN suivis": "PN suivis"}),
                   column_config=CFG, height=min(38 + 35 * len(fours), 420))
    _vue_fournisseur_prev(s, o, fours)
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
def _vue_fournisseur_prev(s, o, fours):
    if fours.empty:
        return
    with ui.section(f"{TAB_ID}_prev_vf", "Détail d'un fournisseur"):
        f1, f2 = st.columns([2, 1], vertical_alignment="center")
        seuls = f2.toggle("Uniquement les fournisseurs avec des PN à commander", value=True, key=K + "vf_seuls", persist_state="page")
        opts = fours[fours["PN à commander"] > 0] if seuls and (fours["PN à commander"] > 0).any() else fours
        libelles = {r["Fournisseur"]: f"{r['Fournisseur']}  ·  {int(r['PN à commander'])} PN à commander · {charts.euros(r['Valeur maintenant (€)'])}"
                    for _, r in opts.iterrows()}
        f = f1.selectbox("Fournisseur", list(libelles), format_func=libelles.get, key=K + "vf", persist_state="page",
                         label_visibility="collapsed")
        cand = pv.suivis(s)
        cand = cand[cand["Fournisseur"] == f]
        d = cand.sort_values("Qté à commander maintenant", ascending=False)
        a_cmd = d[d["Qté à commander maintenant"] > 0]
        lignes = o[o["Fournisseur"] == f] if len(o) else o
        ec = lignes.dropna(subset=["Ecart promis vs demandé (j)"]) if len(lignes) else lignes
        ec = ec[ec["Statut commande"] != "En attente BFE"] if len(ec) else ec
        ui.kpi_grid([
            ui.kpi_card("PN à commander", charts.entier(len(a_cmd)), f"sur {len(d)} PN suivis", "ko"),
            ui.kpi_card("Valeur à commander", charts.euros(d["Valeur à commander maintenant (€)"].sum()),
                        f"{charts.entier(d['Qté à commander maintenant'].sum())} pièces maintenant", "ko"),
            ui.kpi_card("Sur l'horizon", charts.euros(d["Valeur commandes recommandées (€)"].sum()), "commandes recommandées", "warn"),
            ui.kpi_card("Déjà en commande", charts.entier(d["QTE EN CDE"].fillna(0).sum()), "pièces", "info"),
            ui.kpi_card("Écart promis − demandé", f"{ec['Ecart promis vs demandé (j)'].mean():+.0f} j" if len(ec) else "—",
                        f"moyenne sur {len(ec)} ligne(s)" if len(ec) else "aucune date promise", "navy"),
        ])
        g = (a_cmd if len(a_cmd) else d).head(30)
        ui.graphe(charts.barres(g["PNR"], {"En stock": g["QTE SUR ÉTAGÈRE"].fillna(0), "Déjà en commande": g["QTE EN CDE"].fillna(0),
                                           "À commander": g["Qté à commander maintenant"].fillna(0)},
                                {"En stock": COLORS["navy_2"], "Déjà en commande": CATEGORIES[2], "À commander": COLORS["ko"]},
                                empile=True, repere={"Stock minimum à tenir": g["Besoin minimum (qté)"]},
                                survol=list(g["DESCRIPTION"].fillna("").astype(str)) if "DESCRIPTION" in g else None,
                                titre="Par PN : en stock, déjà en commande, à commander", hauteur=260)
                  if len(g) else charts.vide("Aucun PN actif suivi chez ce fournisseur"))
        _ecarts_lignes(ec, lignes)
        t1, t2 = st.columns(2)
        with t1.popover(f"PN du fournisseur ({len(d)})", width="stretch"):
            ui.tableau(d[[c for c in COL_PREV if c in d.columns]].rename(columns=COL_PREV), column_config=CFG, width=1100, height=420,
                       statut="Statut", couleurs=pv.STATUS_COLORS)
        with t2.popover("Commandes en cours chez ce fournisseur", width="stretch"):
            if o.empty:
                st.caption("Aucun fichier de commandes chargé.")
            else:
                oc = o[((o["Fournisseur"] == f) | o["PNR"].isin(d["PNR"])) & (o["Qte restante"].fillna(0) > 0)]
                cols = {**COL_RELANCES, "Date emission commande": "Émise", "Ecart promis vs demandé (j)": "Écart (j)"}
                t = oc.sort_values("Date livraison promise")[[c for c in cols if c in oc.columns]].rename(columns=cols)
                t["Statut"] = t["Statut"].map(STATUT_LIBELLES).fillna(t["Statut"])
                ui.tableau(t, column_config=CFG, width=1100, height=420)


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
    pool = s[s["Dans un groupe avion"]].sort_values(["Statut prévision", "PNR"])
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
            ui.kpi_card("Stock minimum", charts.entier(r["Besoin minimum (qté)"]), "avions d'avance", "warn"),
            ui.kpi_card("Délai", f"{int(r['Délai (mois)'])} mois", r["Source délai"]),
            ui.kpi_card("À commander", charts.entier(r["Qté à commander maintenant"]),
                        charts.entier(r["Commandes recommandées sur l'horizon (qté)"]) + " sur l'horizon", "ko"),
        ])
        st.caption(f"Fournisseur : **{r['Fournisseur']}** · statut : **{r['Statut prévision']}**")
        st.markdown("**Groupes d'avions qui utilisent ce PN**")
        detail = pv.explain_pn(pn, res["gp"])
        ui.tableau(detail, height=min(38 + 35 * max(len(detail), 1), 300))
