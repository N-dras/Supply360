"""Onglet « PE mousses » : politique d'entretien des mousses de sièges.

- Année en cours (fichier Besoin Prod) : avions faisables par type d'avion et par classe, CCN à commander (PR).
  Repris du Streamlit « Pilotage Politique d'entretien Mousse » (calculs dans core/pe2026.py).
- Avancement PE et forecast 12 / 24 / 36 mois (fichier PE mousses mensuel) : rendu par modules/_planning_pe.py,
  calculs dans core/pe.py (anciennement sous-onglet « Planning PE » du Textile).
"""

from datetime import date

import pandas as pd
import streamlit as st

from core import cache, charts
from core import components as ui
from core import io as sio
from core import pe
from core import pe2026 as p26
from core import prevision as pv
from core import textile as tx
from core import style
from core.style import COLORS
from modules import _planning_pe as vue_pe

TAB_ID = "pe_mousses"
TAB_LABEL = "PE mousses"
TAB_ICON = "🪑"
TAB_DESCRIPTION = "Politique d'entretien des mousses : avions faisables cette année, CCN à commander, avancement et forecast."

K = f"{TAB_ID}__"
SECTIONS = ["Synthèse", "Avions faisables", "CCN et commandes", "Avancement PE", "Forecast"]

# Dossier Textile : règles de nommage prioritaires (sans accents ni majuscules), puis reconnaissance par le contenu.
NOMS_DOSSIER = {"stock": r"^resultat", "pieces": r"textile_all_parts", "pe": r"^pe_mousse", "besoin_prod": r"besoin_prod"}
NOMMAGE = ("Dossier Textile : « Besoin_Prod… » = Besoin Prod mousses (objectif de l'année), « PE_MOUSSE… » = PE mousses "
           "(mensuel), « Résultat… » = État du stock, « textile_all_parts » = Pièces par avion. À défaut, reconnaissance "
           "par le contenu. Commandes (SAP) : dossier COMMANDE.")
COLONNES_ATTENDUES = {
    "besoin_prod": [("Feuille « QUOTE en euro »", "en-tête détecté automatiquement", False),
                    ("A/C, Flotte, Area, CCN, Qty per A/C, NB_AC", "type d'avion, classe, quantité par avion", True),
                    ("NB_AC PE RESTANT", "avions restants (par défaut) ; recalcul possible (Paramètres) avec PE mousses + textile_all_parts", False),
                    ("P/N OEM Seat Supplier, Seat Supplier, Description, P.U forecast PE", "", False)],
    "stock": [("PNR, QTE SUR ÉTAGÈRE", "", True), ("CCN", "clé du croisement avec le Besoin Prod", True),
              ("QTE EN CDE, Dernier PU (achat) Euros", "", False)],
    "commandes": [("PN, Commande", "", True), ("CCN", "sinon retrouvé par le PN", False),
                  ("Quantité restant à livrer, Date de livraison promise, Fournisseur", "", False)],
    "pe": [("Feuille « … BOTTOM FOAM … »", "assises : âge par classe J / W / Y", True),
           ("Feuille « … BACKREST FOAM … »", "dossiers J", True),
           ("FLEET, AIRCRAFT, AGE (month), PAST / NEXT EXECUTION", "fichier mensuel tel quel", True),
           ("Date dans le nom", "ex. PE_MOUSSE_29092026 : date des âges", False)],
    "pieces": [("equipment, registration, area, ccn, pn, description, qty_per_ac", "lignes MOUSSE", True)],
}
# Premier choix = valeur par défaut : la colonne NB_AC PE RESTANT du Besoin Prod (demande de l'auteur)
RESTANT_LIBELLES = {p26.RESTANT_FICHIER: "Colonne NB_AC PE RESTANT du Besoin Prod (règle d'origine)",
                    p26.RESTANT_AUTO: "Calculé avec le fichier PE mousses (sinon fichier Besoin Prod)"}
SURPLUS = "#C9D3E3"  # au-delà de l'objectif (gris bleuté)
CFG = {
    "Besoin": st.column_config.NumberColumn("Besoin", format="%d", help="Qté par avion × avions restants"),
    "Stock": st.column_config.NumberColumn("Stock", format="%d"),
    "En commande": st.column_config.NumberColumn("En commande", format="%d", help="Reste à livrer des commandes (SAP)"),
    "Couverture": st.column_config.NumberColumn("Couverture", format="%d", help="Stock + en commande"),
    "Écart": st.column_config.NumberColumn("Écart", format="%d", help="Besoin − couverture"),
    "À demander (PR)": st.column_config.NumberColumn("À demander (PR)", format="%d"),
    "Couverture (%)": st.column_config.ProgressColumn("Couverture (%)", format="%.0f %%", min_value=0, max_value=100),
    "PU (€)": st.column_config.NumberColumn("PU (€)", format="%.0f €"),
    "Valeur stock (€)": st.column_config.NumberColumn("Valeur stock (€)", format="%.0f €"),
    "Valeur à commander (€)": st.column_config.NumberColumn("Valeur à commander (€)", format="%.0f €"),
    "Prochaine livraison": st.column_config.DateColumn("Prochaine livraison", format="DD/MM/YYYY"),
    "Taux (%)": st.column_config.ProgressColumn("Taux (%)", format="%.0f %%", min_value=0, max_value=100,
                                                help="Complets maintenant ÷ objectif"),
}


# --------------------------------------------------------------------------
# Calculs mis en cache (clé = contenu des fichiers + paramètres)
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner="Lecture du Besoin Prod…", max_entries=2)
def _besoin_prod(data: bytes, nom: str):
    return p26.lire_besoin_prod(data, nom)


@st.cache_resource(show_spinner="Lecture des pièces par avion…", max_entries=2)
def _pieces(data: bytes, nom: str):
    return pv.preparer_pieces(pv.lire_pieces(data, nom), pv.Params())[0]


@st.cache_resource(show_spinner="Lecture du fichier PE mousses…", max_entries=2)
def _pe_mousses(data: bytes, nom: str):
    return pe.lire_pe_mousses(data, nom)


@st.cache_resource(show_spinner="Calcul de la PE de l'année…", max_entries=4)
def _annee(besoin: tuple, stock: bytes, cmd: bytes | None, fichier_pe: tuple | None, pieces: tuple | None,
           params: pe.ParamsPE, mode: str, today: date) -> dict:
    bp = _besoin_prod(*besoin)[0]
    parts = _pieces(*pieces) if pieces else None
    rattachement = p26.rattacher_avions(bp, parts)
    date_ref, faits = today, None
    if fichier_pe:
        lignes, dref = _pe_mousses(*fichier_pe)
        date_ref = dref or today
        faits = p26.remplaces_depuis(pe.calendrier(lignes, date_ref, today, params), p26.date_debut_annee(date_ref))
    b = p26.avions_restants(bp, rattachement, faits if faits is not None else pd.DataFrame(), mode)
    m = p26.analyse_ccn(b, cache.etat_stock(stock)[0], cache.commandes(cmd)[0] if cmd else None)
    blocs, detail = p26.avions_faisables(b, m)
    return {"b": b, "m": m, "blocs": blocs, "detail": detail, "rattachement": rattachement, "annee": date_ref.year,
            "avec_cmd": cmd is not None, "calcul_possible": bool(fichier_pe) and len(rattachement) > 0}


@st.cache_resource(show_spinner="Calcul du planning PE…", max_entries=4)
def _planning_pe(stock: bytes | None, cmd: bytes | None, fichier_pe: tuple, pieces: tuple | None, params: pe.ParamsPE,
                 today: date):
    """Planning PE des mousses + forecast (voir core/pe.py)."""
    lignes, date_ref = _pe_mousses(*fichier_pe)
    parts = _pieces(*pieces) if pieces else pd.DataFrame(columns=pv.RAW_COLS)
    cmd_l = cache.commandes(cmd)[0] if cmd else None
    cat = pe.catalogue_mousses(parts) if len(parts) else None
    if stock and cat is not None and len(cat):
        pbi, o = tx.construire_tables(cache.etat_stock(stock)[0], cmd_l, cat, today, True)
    else:
        pbi, o = pd.DataFrame(columns=["PNR", "QTE SUR ÉTAGÈRE"]), None
    return pe.planning_pe(lignes, date_ref or today, parts, pe.articles(pbi), o, today, params)


# --------------------------------------------------------------------------
# Import et paramètres
# --------------------------------------------------------------------------
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
                f_besoin = ui.fichier(f"{p26.FICHIER_BESOIN} (annuel)", K + "besoin", ["xlsx", "xlsm"], COLONNES_ATTENDUES["besoin_prod"])
                f_pieces = ui.fichier(f"{pv.FICHIER_PIECES} (textile_all_parts)", K + "pieces", ["csv", "xlsx", "xlsm"],
                                      COLONNES_ATTENDUES["pieces"])
            with c2:
                f_stock = ui.fichier(sio.FICHIER_STOCK, K + "stock", ["xlsx", "xlsm"], COLONNES_ATTENDUES["stock"])
                f_pe = ui.fichier(f"{pe.FICHIER_PE} (PE_MOUSSE, mensuel)", K + "pe", ["xlsx", "xlsm"], COLONNES_ATTENDUES["pe"])
            with c3:
                f_cmd = ui.import_commandes(COLONNES_ATTENDUES["commandes"])
        with bilan:
            ui.import_dossier(K + "dossier", {"besoin_prod": K + "besoin", "stock": K + "stock", "pieces": K + "pieces", "pe": K + "pe"},
                              label="Tout le dossier Textile (Ctrl+A pour tout sélectionner)", aide=NOMMAGE, noms=NOMS_DOSSIER,
                              zone=zone_dossier, autres=("references",))
        with puces:
            ui.etat_fichiers([(p26.FICHIER_BESOIN, K + "besoin", True), (sio.FICHIER_STOCK, K + "stock", True),
                              (sio.FICHIER_COMMANDES, "commun__commandes", False), (pe.FICHIER_PE, K + "pe", False),
                              (pv.FICHIER_PIECES, K + "pieces", False)])
        with reglages:
            t_gen, t_an, t_pe = st.tabs(["Général", "Année (Besoin Prod)", "Planning PE"])
            with t_gen:
                today = st.date_input("Date de référence", value=date.today(), format="DD/MM/YYYY", key=K + "date",
                                      persist_state="page", help="Statuts PE, retards et début du forecast.")
            with t_an:
                mode = st.radio("Avions restant à traiter", list(RESTANT_LIBELLES), format_func=RESTANT_LIBELLES.get,
                                key=K + "restant", persist_state="page",
                                help="Par défaut : colonne NB_AC PE RESTANT du Besoin Prod (à défaut NB_AC). "
                                     "Calcul : NB_AC − avions du type dont la mousse (classe, assise ou dossier) a été remplacée "
                                     "depuis le 1er janvier d'après le fichier PE mousses. Le type de chaque avion est "
                                     "retrouvé par ses CCN de mousses (textile_all_parts).")
            with t_pe:
                params_pe = vue_pe.parametres()
    return f_besoin, f_stock, f_cmd, f_pe, f_pieces, today, params_pe, mode


def render() -> None:
    entete = st.container()
    f_besoin, f_stock, f_cmd, f_pe, f_pieces, today, params_pe, mode = _bloc_import()
    with entete:
        date_pe = pe.date_extraction(f_pe[0]) if f_pe else None
        ui.hero(TAB_ICON, "PE mousses", TAB_DESCRIPTION, "Production · Politique d'entretien", ui.contexte(
            *([("Fichier PE du", f"{date_pe:%d/%m/%Y}", "")] if date_pe else []),
            ("Avions restants", "NB_AC PE RESTANT" if mode == p26.RESTANT_FICHIER else "Calculés (PE mousses)", "")))
    with st.container(key="s360barre"):
        section = ui.sous_onglets(K + "section", SECTIONS)
    if section in ("Avancement PE", "Forecast"):
        _section_planning(section, f_stock, f_cmd, f_pe, f_pieces, params_pe, today)
        return
    if not (f_besoin and f_stock):
        with ui.section(f"{TAB_ID}_vide", "PE mousses de l'année"):
            ui.empty_state("Importez le Besoin Prod et l'État du stock",
                           "Avions restants : colonne NB_AC PE RESTANT (recalcul possible dans Paramètres avec le fichier "
                           "PE mousses et textile_all_parts) ; les commandes (SAP) complètent la couverture.",
                           [(p26.FICHIER_BESOIN, bool(f_besoin)), (sio.FICHIER_STOCK, bool(f_stock)),
                            (sio.FICHIER_COMMANDES, bool(f_cmd)), (pe.FICHIER_PE, bool(f_pe)), (pv.FICHIER_PIECES, bool(f_pieces))],
                           icon="✈️")
        return
    try:
        res = _annee((f_besoin[1], f_besoin[0]), f_stock[1], f_cmd[1] if f_cmd else None,
                     (f_pe[1], f_pe[0]) if f_pe else None, (f_pieces[1], f_pieces[0]) if f_pieces else None, params_pe, mode, today)
    except ValueError as exc:
        ui.callout(f"<b>Import impossible.</b> {exc}", "ko", "⛔")
        return
    if not res["avec_cmd"]:
        ui.callout("Sans <b>Commandes (SAP)</b>, « en commande » = QTE EN CDE de l'État du stock.", "warn", "⚠️")
    if mode == p26.RESTANT_AUTO and not res["calcul_possible"]:
        ui.callout("Avions restants lus dans le Besoin Prod (colonne NB_AC PE RESTANT) : ajoutez le fichier <b>PE mousses</b> "
                   "et <b>textile_all_parts</b> pour les recalculer.", "info", "ℹ️")
    {"Synthèse": _synthese, "Avions faisables": _faisables, "CCN et commandes": _ccn}[section](res, today)


def _section_planning(section, f_stock, f_cmd, f_pe, f_pieces, params_pe, today):
    if not f_pe:
        with ui.section(f"{TAB_ID}_pe_vide", "Planning PE des mousses"):
            ui.empty_state(f"Importez le fichier {pe.FICHIER_PE}", "Le fichier mensuel PE_MOUSSE (feuilles BOTTOM FOAM et "
                           "BACKREST FOAM), tel que vous le recevez. textile_all_parts et l'État du stock ajoutent le forecast "
                           "des mousses à commander.",
                           [(pe.FICHIER_PE, False), (pv.FICHIER_PIECES, bool(f_pieces)), (sio.FICHIER_STOCK, bool(f_stock))],
                           icon="📅")
        return
    try:
        res = _planning_pe(f_stock[1] if f_stock else None, f_cmd[1] if f_cmd else None, (f_pe[1], f_pe[0]),
                           (f_pieces[1], f_pieces[0]) if f_pieces else None, params_pe, today)
    except ValueError as exc:
        ui.callout(f"<b>{pe.FICHIER_PE} illisible.</b> {exc}", "ko", "⛔")
        return
    if pe.date_extraction(f_pe[0]) is None:
        ui.callout("Date des âges introuvable dans le nom du fichier (ex. PE_MOUSSE_29092026) : la date de référence est utilisée.",
                   "warn", "⚠️")
    if section == "Forecast" and not f_stock:
        ui.callout("Ajoutez l'<b>État du stock</b> pour déduire le stock des mousses à commander.", "warn", "⚠️")
    vue_pe.render(res, today, bool(f_pieces), "avancement" if section == "Avancement PE" else "forecast")


# --------------------------------------------------------------------------
# Synthèse
# --------------------------------------------------------------------------
def _kpis_avions(blocs: pd.DataFrame, annee: int) -> list[str]:
    """Cartes de l'objectif. Unité : la CLASSE d'avion (un avion à traiter en J, W et Y compte 3 fois), car chaque
    classe a ses propres CCN et son propre nombre d'avions restants."""
    obj, now = int(blocs["Objectif"].sum()), int(blocs["Complets maintenant"].sum())
    rec, coter, appro = int(blocs["Complets à réception"].sum()), int(blocs["À coter"].sum()), int(blocs["À approvisionner"].sum())
    taux = now / obj * 100 if obj else 0
    return [
        ui.kpi_repartition(f"Objectif {annee} : classes à traiter", charts.entier(obj), "classes d'avion",
                           [(n, int(blocs[n].sum()), p26.AVANCEMENT_COULEURS[n]) for n in p26.AVANCEMENT],
                           note=f"soit {charts.entier(p26.avions_distincts(blocs))} avions", icone="target", tone="violet"),
        ui.kpi_card("Complètes maintenant", charts.entier(now), f"{taux:.0f} % de l'objectif · tous leurs CCN en stock", "ok", "check-circle"),
        ui.kpi_card("Complètes à réception", charts.entier(rec), "une fois les commandes en cours livrées", "info", "truck"),
        ui.kpi_card("À coter", charts.entier(coter), "il ne manque que des CCN sans prix", "orange", "tag"),
        ui.kpi_card("À approvisionner", charts.entier(appro), "CCN manquants à commander", "ko", "cart"),
    ]


def _jauges_blocs(blocs: pd.DataFrame, titre: str) -> str:
    lignes = []
    for _, r in blocs.sort_values(["Type avion", "Classe"]).iterrows():
        if r["Objectif"] <= 0:
            continue
        info = [f"CCN limitant : {r['CCN limitant']}"] if r["Complets maintenant"] < r["Objectif"] else []
        if r["À approvisionner"] and r["CCN communs"]:
            info.append(f"{int(r['CCN communs'])} CCN commun(s) à d'autres types : stock et commandes partagés entre eux")
        if r["À coter"]:
            info.append("Il ne manque que des CCN sans prix : à faire coter avant de commander")
        lignes.append((p26.nom_bloc(r["Type avion"], r["Classe"]), [(n, r[n], p26.AVANCEMENT_COULEURS[n]) for n in p26.AVANCEMENT],
                       None, f"{int(r['Complets maintenant'])} / {int(r['Objectif'])}", info))
    leg = [(n, c, "barre") for n, c in p26.AVANCEMENT_COULEURS.items()]
    return charts.jauges(lignes, titre, leg, fmt=charts.entier, hauteur_max="30rem") if lignes else charts.vide("Aucun avion à traiter")


def _synthese(res: dict, today: date):
    m, blocs, annee = res["m"], res["blocs"], res["annee"]
    a_pr = m[m["Écart"] > 0]
    resume = (f"{len(a_pr)} PR à émettre pour {charts.entier(a_pr['À demander (PR)'].sum())} mousses "
              f"({charts.euros(a_pr['Valeur à commander (€)'].sum())}) : {(a_pr['Action'] == p26.ACTIONS[0]).sum()} CCN sans commande, "
              f"{(a_pr['Action'] == p26.ACTIONS[1]).sum()} avec des commandes insuffisantes" if len(a_pr)
              else "Stock et commandes couvrent le besoin de l'année")
    with ui.section(f"{TAB_ID}_synthese", f"Synthèse de la PE mousses {annee}", resume, export=_export(res), carte=False):
        ui.kpi_grid(_kpis_avions(blocs, annee))
        ui.valeurs([
            ("Valeur du stock", charts.euros(m["Valeur stock (€)"].sum()), "mousses sur étagère"),
            ("Valeur en commande", charts.euros(m["Valeur en commande (€)"].sum()), "déjà commandé, à recevoir"),
            ("À commander", charts.euros(m["Valeur à commander (€)"].sum()), "PR, hors CCN à coter"),
            (f"Valeur du besoin {annee}", charts.euros(m["Valeur du besoin (€)"].sum()), "avions restants"),
            ("CCN à coter", charts.entier(m["À coter"].sum()), "sans prix : coût sous-estimé"),
        ])
    with ui.section(f"{TAB_ID}_avions_ccn", "Avions et CCN", f"Ce que permettent le stock et les commandes en cours · {m['CCN'].nunique()} CCN"):
        a, b = st.columns([1, 1.5], gap="medium")
        with a:
            n = m["Action"].value_counts()
            ui.graphe(charts.barres_h([(act, n.get(act, 0), charts.entier(n.get(act, 0)), p26.ACTION_COULEURS[act])
                                       for act in p26.ACTIONS], titre="CCN par action"), "Nombre de CCN selon l'action à mener")
        with b:
            ui.graphe(_jauges_blocs(blocs, "Avions par type et par classe, sur l'objectif"),
                      "Une ligne = une classe d'un type d'avion ; survolez une ligne pour le CCN limitant")
    act = m[m["Priorité"] <= 2]
    with ui.section(f"{TAB_ID}_actions", "Actions à lancer", "PR à émettre, du plus urgent au moins urgent", tag=str(len(act)),
                    export=_export(res, "export_actions")):
        if act.empty:
            ui.callout("Aucune PR à émettre : stock et commandes couvrent le besoin de l'année.", "ok", "check-circle")
        else:
            _ccn_html(act, "actions")
        _controles(res)


def _ccn_html(x: pd.DataFrame, cle: str, hauteur: str = "30rem") -> None:
    """Tableau des CCN : action en badge (mêmes couleurs que les graphes), quantité à demander en rouge."""
    ui.tableau_html(_tableau_ccn(x), statut="Action", couleurs=p26.ACTION_COULEURS,
                    num=["Besoin", "Stock", "En commande", "Couverture", "Écart", "Couverture (%)", "PU (€)"],
                    fort=["À demander (PR)"], euros=["Valeur à commander (€)"], pn=["CCN"], fixes=2, cle=f"{TAB_ID}_{cle}",
                    hauteur=hauteur, colonne_config=CFG)


def _tableau_ccn(m: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "Action": m["Action"], "CCN": m["CCN"], "PN": m["PN"], "Désignation": m["Désignation"], "Types avion": m["Types avion"],
        "Classes": m["Classes"], "Fournisseur": m["Fournisseur"], "Besoin": m["Besoin"], "Stock": m["Stock"],
        "En commande": m["En commande"], "Couverture": m["Couverture"], "Écart": m["Écart"],
        "À demander (PR)": m["À demander (PR)"], "Couverture (%)": m["Taux de couverture (%)"].clip(upper=100),
        "PU (€)": m["PU (€)"], "Valeur à commander (€)": m["Valeur à commander (€)"], "À coter": m["À coter"].map({True: "oui", False: ""}),
        "Commandes": m["Commandes"], "Prochaine livraison": m["Prochaine livraison"],
    })


def _export(res: dict, cle: str = "export") -> tuple:
    """Export de l'onglet (fabriqué au clic) : actions, récapitulatif CCN, avions faisables, détail, restants."""
    b, m, blocs, d, rat = res["b"], res["m"], res["blocs"], res["detail"], res["rattachement"]

    def fabriquer() -> bytes:
        feuilles = {
            "Actions à lancer": _tableau_ccn(m[m["Priorité"] <= 2]),
            "CCN (récap)": _tableau_ccn(m),
            "Avions faisables": blocs,
            "Détail CCN par type": d,
            "Avions restants": _table_restants(b),
            "Rattachement avions": rat,
        }
        teintes = lambda t: {"Action": [style.teinte(p26.ACTION_COULEURS.get(v, "")) for v in t["Action"]]}  # noqa: E731
        return sio.exporter_excel(feuilles, couleurs_cellules={n: teintes(feuilles[n]) for n in ("Actions à lancer", "CCN (récap)")})

    return fabriquer, sio.nom_export(TAB_ID), K + cle


def _controles(res: dict):
    m, rat = res["m"], res["rattachement"]
    a, _ = st.columns([1, 3])
    with a, st.popover("Contrôles des données", width="stretch"):
        absents = m[~m["Dans l'État du stock"]]
        st.markdown(f"- **{len(absents)}** CCN du Besoin Prod absents de l'État du stock (stock compté à 0)"
                    + (f" : {', '.join(absents['CCN'].head(20))}" if len(absents) else ""))
        st.markdown(f"- **{int(m['À coter'].sum())}** CCN sans prix (ni Dernier PU de l'État du stock, ni prix du devis) : à coter.")
        partages = m[m["Nb types"] > 1]
        st.markdown(f"- **{len(partages)}** CCN communs à plusieurs types d'avion : leur stock est réparti entre les types.")
        if len(rat):
            amb = int(rat["Ambigu"].sum())
            st.markdown(f"- **{len(rat)}** avions rattachés à un type d'avion par leurs CCN de mousses"
                        + (f", dont **{amb}** ex æquo entre deux types (premier retenu)." if amb else "."))
            ui.tableau(rat.drop(columns=["cle"]), height=220)


def _table_restants(b: pd.DataFrame) -> pd.DataFrame:
    t = b.groupby(["Type avion", "Classe", "Composant"], dropna=False).agg(**{
        "Flotte": ("Flotte", "first"), "NB_AC": ("NB_AC", "max"), "Restant (fichier)": ("Restant fichier", "max"),
        "Avions rattachés": ("Avions rattachés", "max"), "Remplacés cette année": ("Remplacés cette année", "max"),
        "Restant calculé": ("Restant calculé", "max"), "Avions restants (retenu)": ("Avions restants", "max"),
        "Source": ("Source restant", "first")}).reset_index()
    return t[["Type avion", "Flotte", "Classe", "Composant", "NB_AC", "Restant (fichier)", "Avions rattachés",
              "Remplacés cette année", "Restant calculé", "Avions restants (retenu)", "Source"]]


# --------------------------------------------------------------------------
# Avions faisables
# --------------------------------------------------------------------------
def _faisables(res: dict, today: date):
    blocs, d, b, annee = res["blocs"], res["detail"], res["b"], res["annee"]
    with ui.section(f"{TAB_ID}_faisables", f"Avions faisables {annee}",
                    "Un avion d'une classe est complet quand tous ses CCN sont disponibles ; le stock d'un CCN commun est "
                    "réparti entre les types d'avion"):
        ui.kpi_grid(_kpis_avions(blocs, annee))
        ui.graphe(_jauges_blocs(blocs, "Avancement par type d'avion et par classe (nombre d'avions de chaque classe)"))
        t = blocs.assign(Bloc=[p26.nom_bloc(x, y) for x, y in zip(blocs["Type avion"], blocs["Classe"])])
        cols = ["Type avion", "Flotte", "Classe", "Objectif", "Complets maintenant", "Complets à réception", "À coter", "À approvisionner",
                "Taux (%)", "Nb CCN", "CCN couverts", "CCN communs", "CCN limitant", "PN à coter"]
        ui.tableau(t[cols], column_config=CFG, height="content" if len(t) <= 12 else 420)
        with st.popover("ℹ️ Règles de calcul et avions restants", width="content"):
            st.markdown(
                "- **Objectif** = avions restant à traiter (voir tableau ci-dessous et ⚙️ Paramètres).\n"
                "- **Complets maintenant** : avions équipables avec le stock ; un CCN commun à plusieurs types est réparti, "
                "l'avion suivant allant toujours au type le moins avancé.\n"
                "- **Complets à réception** : en plus, une fois les commandes en cours livrées (stock + en commande).\n"
                "- **À approvisionner** : le reste de l'objectif, impossible sans nouvelle commande. Avec un **CCN commun** "
                "à plusieurs types, les commandes en cours peuvent suffire pour un type seul mais pas pour tous : le reste "
                "est alors à approvisionner (voir « CCN communs » et le détail par type).\n"
                "- Le stock est partagé entre classes et types : ces chiffres montrent ce que permet le stock, pas une affectation.")
            ui.tableau(_table_restants(b), width=1100, height=360)
    _detail_type(d, blocs)


@st.fragment
def _detail_type(d: pd.DataFrame, blocs: pd.DataFrame):
    types = sorted(blocs["Type avion"].unique())
    if not types:
        return
    with ui.section(f"{TAB_ID}_detail_type", "Détail par type d'avion",
                    "Avions de l'objectif couverts par chaque CCN : par le stock (vert), à réception des commandes (bleu), "
                    "manquants (orange : à coter, rouge : à approvisionner) ; trait = objectif de la classe"):
        a, b = st.columns([1.2, 2], vertical_alignment="center")
        typ = a.selectbox("Type d'avion", types, key=K + "type", persist_state="page", label_visibility="collapsed")
        x = d[d["Type avion"] == typ].sort_values(["Classe", "Avions (stock)"])
        bt = blocs[blocs["Type avion"] == typ]
        with b:
            st.html('<div class="s360-note">' + " · ".join(
                f"<b>{r['Classe']}</b> : {int(r['Complets maintenant'])} / {int(r['Objectif'])} complets maintenant"
                + (f", {int(r['Complets à réception'])} à réception" if r["Complets à réception"] else "")
                + (f" (limitant : {r['CCN limitant']})" if r["Complets maintenant"] < r["Objectif"] else "")
                for _, r in bt.iterrows()) + "</div>")
        lignes = []
        for _, r in x.iterrows():
            commun = r["Types partageant le CCN"] > 1
            libelle = f"{r['Classe']} · {r['CCN']} · {r['PN']}" + (f" · commun à {r['Types partageant le CCN']} types" if commun else "")
            manque = int(r[p26.SEGMENTS_CCN[2]])
            couleur_manque = p26.ORANGE if r["À coter"] else p26.ROUGE
            segs = [("Avions couverts par le stock", r[p26.SEGMENTS_CCN[0]], p26.VERT),
                    ("Avions couverts à réception des commandes", r[p26.SEGMENTS_CCN[1]], p26.BLEU),
                    ("Avions manquants : " + ("CCN à coter" if r["À coter"] else "à approvisionner"), manque, couleur_manque),
                    ("Au-delà de l'objectif", r[p26.SEGMENTS_CCN[3]], SURPLUS)]
            info = [f"Statut : {r['Statut CCN']}",
                    f"Stock {charts.entier(r['Stock'])} · stock + commandes {charts.entier(r['Couverture'])} "
                    f"· {charts.entier(r['Qté par avion'])} par avion"
                    + (f" (part de ce type sur un CCN commun ; besoin total {charts.entier(r['Besoin total CCN'])})" if commun else "")]
            texte = f"manque {manque}" if manque else "✓ couvert"
            lignes.append((libelle, segs, r["Objectif"], texte, info))
        leg = [("Couvert par le stock", p26.VERT, "barre"), ("Couvert à réception des commandes", p26.BLEU, "barre"),
               ("À coter (sans prix)", p26.ORANGE, "barre"), ("À approvisionner", p26.ROUGE, "barre"),
               ("Au-delà de l'objectif", SURPLUS, "barre"), ("Objectif de la classe", COLORS["text"], "trait")]
        ui.graphe(charts.jauges(lignes, f"{typ} : avions couvrables par CCN", leg, repere_nom="Objectif", fmt=charts.entier,
                                hauteur_max="34rem"))
        t = x[["Statut CCN", "Classe", "CCN", "PN", "Désignation", "Qté par avion", "Objectif", "Besoin", "Besoin total CCN", "Stock",
               "Couverture", "Avions (stock)", "Avions (stock + commandes)", "Manque (unités)", "PU (€)", "Types partageant le CCN"]]
        ui.tableau(t, column_config=CFG, height="content" if len(t) <= 10 else 380)


# --------------------------------------------------------------------------
# CCN et commandes
# --------------------------------------------------------------------------
def _ccn(res: dict, today: date):
    m, annee = res["m"], res["annee"]
    with ui.section(f"{TAB_ID}_ccn", "CCN et commandes",
                    f"Besoin {annee} face au stock et aux commandes en cours, par CCN : quantités à demander (PR)"):
        ui.kpi_grid([
            ui.kpi_card("CCN suivis", charts.entier(len(m)), "dans le Besoin Prod", "navy", "layers"),
            ui.kpi_card("Stock", charts.entier(m["Stock"].sum()), "mousses sur étagère", "ok", "package"),
            ui.kpi_card("CCN à approvisionner", charts.entier((m["Écart"] > 0).sum()), "= PR à émettre", "orange", "send"),
            ui.kpi_card("Quantité à demander", charts.entier(m["À demander (PR)"].sum()), "toutes PR confondues", "ko", "cart"),
            ui.kpi_card("CCN couverts", charts.entier((m["Écart"] <= 0).sum()), "stock + commandes suffisent", "ok", "check-circle"),
        ])
        acoter = m[m["À coter"]]
        if len(acoter):
            ui.callout(f"<b>{len(acoter)} CCN à faire coter</b> (aucun prix) : coût à commander sous-estimé.", "warn", "tag")
        _liste_ccn(m)


@st.fragment
def _liste_ccn(m: pd.DataFrame):
    a, b, c = st.columns([1.2, 2, 1], vertical_alignment="center")
    q = a.text_input("Recherche", placeholder="CCN, PN, fournisseur", key=K + "q", label_visibility="collapsed")
    actions = b.multiselect("Action", p26.ACTIONS, key=K + "actions", placeholder="Toutes les actions", label_visibility="collapsed")
    coter = c.toggle("À coter seulement", key=K + "coter")
    x = m
    if q:
        cle = q.strip().upper()
        x = x[x["CCN"].str.upper().str.contains(cle, regex=False) | x["PN"].str.upper().str.contains(cle, regex=False)
              | x["Fournisseur"].fillna("").str.upper().str.contains(cle, regex=False)]
    if actions:
        x = x[x["Action"].isin(actions)]
    if coter:
        x = x[x["À coter"]]
    ui.graphe(_graphe_couverture(x))
    _ccn_html(x, "ccn", "34rem")




def _graphe_couverture(x: pd.DataFrame) -> str:
    """Une barre par CCN = 100 % de son besoin de l'année : part couverte par le stock, par les commandes en cours,
    et ce qui manque (à commander). Les moins couverts en premier ; au-delà de 100 %, le surplus est indiqué à droite."""
    v = x[x["Besoin"] > 0].copy()
    if v.empty:
        return charts.vide("Aucun besoin sur la sélection")
    b = v["Besoin"].astype(float)
    v["p_stock"] = (v["Stock"].clip(upper=b) / b * 100)
    v["p_cde"] = (v["En commande"].clip(upper=(b - v["Stock"]).clip(lower=0)) / b * 100)
    v["p_manque"] = (100 - v["p_stock"] - v["p_cde"]).clip(lower=0)
    v = v.sort_values(["p_manque", "Besoin"], ascending=[False, False])
    lignes = []
    for _, r in v.iterrows():
        manque = int(r["À demander (PR)"])
        surplus = r["Couverture"] - r["Besoin"]
        texte = f"manque {charts.entier(manque)}" if manque > 0 else (f"✓ +{charts.entier(surplus)}" if surplus > 0 else "✓ couvert")
        info = [f"Besoin {charts.entier(r['Besoin'])} · stock {charts.entier(r['Stock'])} · en commande {charts.entier(r['En commande'])}",
                f"À demander (PR) : {charts.entier(manque)}" if manque > 0 else "Couvert" + (" par le stock" if r["Stock"] >= r["Besoin"] else " avec les commandes")]
        if pd.notna(r.get("Prochaine livraison")):
            info.append(f"Prochaine livraison : {pd.Timestamp(r['Prochaine livraison']):%d/%m/%Y}")
        lignes.append((f"{r['CCN']} · {r['PN']}",
                       [("Stock", r["p_stock"], p26.VERT), ("Commandes en cours", r["p_cde"], p26.BLEU),
                        ("Manque : " + ("à coter" if r["À coter"] else "à commander"), r["p_manque"],
                         p26.ORANGE if r["À coter"] else p26.ROUGE)], None, texte, info))
    leg = [("Couvert par le stock", p26.VERT, "barre"), ("Couvert par les commandes en cours", p26.BLEU, "barre"),
           ("À coter (sans prix)", p26.ORANGE, "barre"), ("Manque : à commander", p26.ROUGE, "barre")]
    return charts.jauges(lignes, f"Couverture du besoin de l'année par CCN, en % du besoin ({len(v)} CCN, les moins couverts en haut)",
                         leg, fmt=lambda val: f"{val:.0f} %", hauteur_max="34rem")
