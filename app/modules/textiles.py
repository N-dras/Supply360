"""Onglet « Textile cabine » : stock, consommation, commandes et prévision de commandes des références textile.

Repris du dashboard Textile (streamlit_textile_dashboard.py, textile_analytics.py, textile_policy.py).
Imports : État du stock, Commandes (SAP), Références textile ; pour la prévision : Pièces par avion.
"""

from dataclasses import asdict
from datetime import date

import pandas as pd
import streamlit as st

from core import cache, charts
from core import components as ui
from core import io as sio
from core import prevision as pv
from core import textile as tx
from core.style import COLORS

TAB_ID = "textiles"
TAB_LABEL = "Textile cabine"
TAB_ICON = "🧵"
TAB_DESCRIPTION = "Stock, consommation, commandes et prévision de commandes des ceintures, housses, mousses et rideaux."

K = f"{TAB_ID}__"
SECTIONS = ["Synthèse", "Prévision", "Commandes", "Fournisseurs", "Consommation"]
ICONES = {"Synthèse": "📊", "Prévision": "🧮", "Commandes": "📦", "Fournisseurs": "🏭", "Consommation": "📈"}
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
               ("CSV ou Excel", "ex. textile_by_registration", False)],
}

COL_RELANCES = {"Statut commande": "Statut", "Fournisseur": "Fournisseur", "Commande": "Commande", "PNR": "PN",
                "REF_Equipement": "Catégorie", "Date livraison demandee": "Demandée", "Date livraison promise": "Promise",
                "Jours de retard": "Retard (j)", "Qte restante": "Reste à livrer", "Code acheteur": "Acheteur"}
COL_PREV = {"PNR": "PN", "DESCRIPTION": "Description", "REF_Equipement": "Catégorie", "Statut prévision": "Statut",
            "Qté à commander maintenant": "À commander", "Date 1ère commande": "1re commande", "QTE SUR ÉTAGÈRE": "Stock",
            "QTE EN CDE": "En commande", "Besoin minimum (qté)": "Stock minimum", "Délai (mois)": "Délai (mois)",
            "Source délai": "Source délai", "Commandes recommandées sur l'horizon (qté)": "À commander (horizon)",
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
    "Valeur stock (€)": st.column_config.NumberColumn("Valeur stock (€)", format="%.0f €"),
    "Valeur en commande (€)": st.column_config.NumberColumn("Valeur en commande (€)", format="%.0f €"),
    "Valeur maintenant (€)": st.column_config.NumberColumn("Valeur maintenant (€)", format="%.0f €"),
    "Valeur sur l'horizon (€)": st.column_config.NumberColumn("Valeur sur l'horizon (€)", format="%.0f €"),
    "Valeur (€)": st.column_config.NumberColumn("Valeur (€)", format="%.0f €"),
    "Dernière conso": st.column_config.DateColumn("Dernière conso", format="DD/MM/YYYY"),
}
STATUT_ICONES = {"En retard": "🔴 En retard", "Sans date promise": "🟠 Sans date promise", "En attente BFE": "🟣 En attente BFE",
                 "A l'heure": "🟢 À l'heure"}


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
    rules = pd.DataFrame(list(regles), columns=["Equipement", "Classe", "Composant", "Cycle PE (ans)"])
    return pv.run_policy(s_all, o_all, parts, fleet, None, rules, params, pd.Timestamp(cle_tables[3]))


def _filtrer(s_all, o_all, cat):
    s = s_all if cat == TOUTES else s_all[tx.categorie(s_all) == cat]
    o = o_all if cat == TOUTES or o_all.empty else o_all[tx.categorie(o_all) == cat]
    return s, o


@st.cache_resource(show_spinner=False, max_entries=4)
def _export(cle_tables: tuple, cat: str, cle_prev: tuple | None) -> bytes:
    s, o = _filtrer(*_tables(*cle_tables), cat)
    rel = tx.relances(o) if len(o) else o
    feuilles = {
        "Synthèse catégories": tx.resume_categories(s, o),
        "Relances fournisseurs": rel,
        "Stock": s,
        "Commandes": o,
        "Retards": tx.tableau_retards(o),
        "Conso catégories": tx.conso_par_categorie(s),
        "Délais fournisseurs": tx.delais_fournisseurs(o),
    }
    if cle_prev:
        pbi, res = _prevision(*cle_prev)
        pbi = pbi if cat == TOUTES else pbi[tx.categorie(pbi) == cat]
        plan = res["plan"] if cat == TOUTES else res["plan"][res["plan"]["Catégorie"] == cat]
        feuilles = {"Prévision fournisseurs": pv.par_fournisseur(pbi, plan), "Plan de commande": plan,
                    "Prévision par PN": pbi, "Groupes avions": res["gs"], **feuilles}
    return sio.exporter_excel(feuilles, couleurs_lignes={"Relances fournisseurs": rel["Statut commande"].map(
        {"En retard": "F8D7DA", "Sans date promise": "FCE4D6", "En attente BFE": "E9DDF8"}).tolist()})


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------
def _parametres(parts) -> tuple[pv.Params, tuple]:
    """Popover des paramètres de la prévision (buffer, délais, composants, politique d'entretien)."""
    d = pv.Params()
    with st.popover("⚙️ Paramètres de la prévision", width="stretch"):
        a, b = st.columns(2)
        ratio = a.slider("Avions d'avance (% du groupe)", 2, 40, int(d.buffer_ratio * 100), key=K + "ratio", persist_state="page",
                         help="10 % : 10 avions → 1, 50 avions → 5.")
        bmin = b.number_input("Minimum d'avions d'avance par groupe", 1, 10, d.buffer_min, key=K + "bmin", persist_state="page")
        hz = a.slider("Horizon de prévision (mois)", 12, 60, d.horizon_months, key=K + "hz", persist_state="page")
        never = b.checkbox("Buffer aussi pour les composants sans PE (cycle 0)", value=d.buffer_on_never, key=K + "never",
                           persist_state="page")
        lt_def = a.number_input("Délai par défaut (jours)", 1, 730, d.lt_default, key=K + "ltdef", persist_state="page",
                                help="Quand ni le fournisseur ni le PN n'ont de délai.")
        lt_basis = b.selectbox("Délai du fournisseur basé sur", ["observe", "promis"], key=K + "ltbasis", persist_state="page",
                               format_func={"observe": "LT observé (historique 2 ans)", "promis": "Délais promis actuels"}.get)
        bfe = a.number_input("Délai supposé si attente de BFE (mois)", 1, 36, d.bfe_delay_months, key=K + "bfe", persist_state="page")
        comp = b.selectbox("Composant si aucun mot-clé", ["Assise", "Dossier"], key=K + "comp", persist_state="page")
        kw_dos = a.text_input("Mots-clés Dossier (prioritaires)", d.dossier_kw, key=K + "kwdos", persist_state="page")
        kw_ass = b.text_input("Mots-clés Assise", d.assise_kw, key=K + "kwass", persist_state="page")
        p = pv.Params(buffer_ratio=ratio / 100, buffer_min=int(bmin), buffer_on_never=bool(never), horizon_months=int(hz),
                      lt_default=int(lt_def), lt_basis=lt_basis, bfe_delay_months=int(bfe), assise_kw=kw_ass, dossier_kw=kw_dos,
                      default_component=comp)
        regles = None
        if parts is not None:
            # Grille de champs (et non st.data_editor : indisponible sous stlite, il dépend de pyarrow).
            st.markdown("**Politique d'entretien : cycle PE (ans)** · 0 = jamais remplacé · pris en compte si "
                        "« Buffer aussi pour les composants sans PE » est décoché")
            base = pv.regles_pe_defaut(parts)
            cols = st.columns(3)
            cycles = []
            for i, r in enumerate(base.itertuples(index=False)):
                cle = f"{K}pe__{pv.cle_regle(r.Equipement, r.Classe, r.Composant)}"
                cycles.append(cols[i % 3].number_input(f"{r.Equipement} · {r.Classe} · {r.Composant}", 0.0, 20.0,
                                                       float(r[3]), 0.5, key=cle, persist_state="page"))
            regles = tuple((r.Equipement, r.Classe, r.Composant, float(c)) for r, c in zip(base.itertuples(index=False), cycles))
    return p, regles


SHAREPOINT_TEXTILE = ("https://afkl.sharepoint.com/:f:/r/teams/MS-LGT1-Analystes/Shared%20Documents/Textile"
                      "?d=w58572b00036a42e395a6b6435ecf4000&csf=1&web=1&e=ExlJGH")
# Noms des fichiers du dossier Textile (prioritaires sur la reconnaissance par le contenu), sans accents ni majuscules.
NOMS_DOSSIER = {"stock": r"^resultat", "references": r"textile_master_export", "pieces": r"textile_all_parts"}
NOMMAGE = ("Dossier Textile : « Résultat… » = État du stock, « textile_master_export » = Références textile, "
           "« textile_all_parts » = Pièces par avion. À défaut, les fichiers sont reconnus par leur contenu ; s'il y en a "
           "plusieurs du même type, le plus récent (date dans le nom) est retenu. Commandes (SAP) : dossier COMMANDE.")


def _bloc_import():
    with ui.section(f"{TAB_ID}_import", "Import et paramètres"):
        d1, d2, d3 = st.columns([1.1, 1.1, 1], vertical_alignment="center")
        with d1:
            ui.bouton_dossier("Textile", K + "dossier__upload")
        with d2:
            ui.bouton_commandes()
        with d3:
            ui.lien_sharepoint(SHAREPOINT_TEXTILE, "Textile")
        ui.import_dossier(K + "dossier", {"stock": K + "stock", "references": K + "references", "pieces": K + "pieces"},
                          label="… ou importer les fichiers avec Parcourir (Ctrl+A pour tout sélectionner)", aide=NOMMAGE,
                          noms=NOMS_DOSSIER)
        c1, c2, c3 = st.columns(3)
        with c1:
            f_stock = ui.fichier(sio.FICHIER_STOCK, K + "stock", ["xlsx", "xlsm"], COLONNES_ATTENDUES["stock"])
        with c2:
            f_cmd = ui.import_commandes(COLONNES_ATTENDUES["commandes"])
        with c3:
            f_ref = ui.fichier(sio.FICHIER_REFERENCES, K + "references", ["xlsx", "xlsm"], COLONNES_ATTENDUES["references"])
        d1, d2, d3 = st.columns(3)
        with d1:
            f_pieces = ui.fichier(f"{pv.FICHIER_PIECES} (prévision)", K + "pieces", ["csv", "xlsx", "xlsm"], COLONNES_ATTENDUES["pieces"])
        with d2:
            today = st.date_input("Date de référence", value=date.today(), format="DD/MM/YYYY", key=K + "date", persist_state="page",
                                  help="Date des données : âge des commandes, retards, début de la prévision.")
            seul = st.toggle("Uniquement les PN du catalogue textile", value=True, key=K + "seul", persist_state="page")
        with d3:
            parts = None
            if f_pieces:
                try:
                    parts = _pieces(f_pieces[1], f_pieces[0], pv.Params())[0]
                except ValueError as exc:
                    ui.callout(f"<b>{pv.FICHIER_PIECES} illisible.</b> {exc}", "ko", "⛔")
                    f_pieces = None
            params, regles = _parametres(parts)
    return f_stock, f_cmd, f_ref, f_pieces, today, seul, params, regles


def render() -> None:
    ui.hero(TAB_ICON, "Textile cabine", TAB_DESCRIPTION)
    f_stock, f_cmd, f_ref, f_pieces, today, seul, params, regles = _bloc_import()
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
        prev = _prevision(*cle_prev) if cle_prev else None
    except ValueError as exc:
        ui.callout(f"<b>Import impossible.</b> {exc}", "ko", "⛔")
        return
    if not f_ref or not f_cmd:
        manquants = " et ".join(n for f, n in [(f_cmd, sio.FICHIER_COMMANDES), (f_ref, sio.FICHIER_REFERENCES)] if not f)
        ui.callout(f"Analyse partielle : ajoutez <b>{manquants}</b> pour la compléter.", "warn", "⚠️")
    if s_all.empty:
        ui.callout("Aucun PN du catalogue textile dans l'État du stock. Vérifiez les fichiers ou désactivez le filtre catalogue.", "warn", "⚠️")
        return

    # Barre de sous-onglets + filtre catégorie : seule la section choisie est calculée et affichée.
    with st.container(key="s360barre"):
        n1, n2 = st.columns([2.6, 1.6], vertical_alignment="center")
        with n1:
            section = ui.sous_onglets(K + "section", SECTIONS, ICONES)
        with n2, st.container(key="s360pills_" + K + "cat"):
            cats = [TOUTES] + tx.categories(s_all)
            cat = st.pills("Catégorie", cats, default=TOUTES, key=K + "cat", label_visibility="collapsed", persist_state="page") or TOUTES
    s, o = _filtrer(s_all, o_all, cat)
    st.session_state[K + "cle_export"] = (cle, cat, cle_prev)

    if section == "Prévision":
        _section_prevision(prev, cat, o)
    else:
        {"Synthèse": _synthese, "Commandes": _commandes, "Fournisseurs": _fournisseurs, "Consommation": _consommation}[section](s, o, today, cat)


# --------------------------------------------------------------------------
# Synthèse
# --------------------------------------------------------------------------
def _synthese(s, o, today, cat):
    r = tx.synthese(s, o)
    rel = tx.relances(o) if len(o) else o
    with ui.section(f"{TAB_ID}_syn", "Synthèse", "Toutes catégories" if cat == TOUTES else cat):
        if len(rel):
            ui.callout(f"<b>{len(rel)} relance(s) fournisseur</b> : {r['en_retard']} en retard, {r['sans_date']} sans date promise, "
                       f"{r['bfe']} en attente de BFE.", "ko" if r["en_retard"] else "warn", "📌")
        if r["valeur_dormant"]:
            ui.callout(f"<b>{charts.euros(r['valeur_dormant'])}</b> de stock dormant sur {r['dormants']} PN (aucune consommation sur 3 ans).",
                       "warn", "💤")
        ui.kpi_grid([
            ui.kpi_card("PN suivis", charts.entier(r["pn"])),
            ui.kpi_card("Valeur du stock", charts.euros(r["valeur_stock"]), "", "info"),
            ui.kpi_card("Valeur en commande", charts.euros(r["valeur_commande"]), f"{r['lignes']} lignes", "navy"),
            ui.kpi_card("Lignes en retard", charts.entier(r["en_retard"]), f"{r['sans_date']} sans date promise", "ko"),
            ui.kpi_card("Stock dormant", charts.euros(r["valeur_dormant"]), f"{r['dormants']} PN", "warn"),
        ])
        ui.telecharger(_export(*st.session_state[K + "cle_export"]), sio.nom_export(TAB_ID), K + "export__btn")

    with ui.section(f"{TAB_ID}_rel", "Relances fournisseurs", "Du plus urgent au moins urgent", tag=str(len(rel))):
        if len(rel):
            t = rel[[c for c in COL_RELANCES if c in rel.columns]].rename(columns=COL_RELANCES)
            t["Statut"] = t["Statut"].map(STATUT_ICONES)
            ui.tableau(t, column_config=CFG, height=min(38 + 35 * len(t), 380))
        else:
            ui.callout("Aucune relance à lancer.", "ok", "✅")

    with ui.section(f"{TAB_ID}_cat", "Catégories"):
        a, b = st.columns(2, gap="large")
        with a:
            poids = tx.poids_par_categorie(s, o)
            ui.graphe(charts.parts(poids, tx.CATEGORY_COLORS, "Poids de chaque catégorie", afficher="pourcent",
                                   noms=("Indicateur", "Catégorie")))
        with b:
            cats = tx.categories(s)
            g = s.assign(c=tx.categorie(s)).groupby("c")[["Valeur stock (€)", "Valeur en commande (€)", "Valeur stock dormant (€)"]].sum().reindex(cats)
            part = (g["Valeur stock dormant (€)"] / g["Valeur stock (€)"].where(g["Valeur stock (€)"] > 0) * 100)
            ui.graphe(charts.barres(cats, {"Valeur du stock": g["Valeur stock (€)"], "Valeur en commande": g["Valeur en commande (€)"]},
                                    {"Valeur du stock": COLORS["navy_2"], "Valeur en commande": "#F4A259"},
                                    ligne={"Part dormante": part}, fmt=charts.euros, fmt_ligne=charts.pourcent,
                                    titre="Valeur du stock et part dormante", hauteur=220))
        a, b = st.columns(2, gap="large")
        with a:
            ui.graphe(charts.parts(tx.activite_par_categorie(s), tx.ACTIVITY_COLORS, "PN actifs, dormants et inactifs"))
        with b:
            g2 = s.assign(c=tx.categorie(s)).groupby("c")[["QTE SUR ÉTAGÈRE", "QTE EN CDE"]].sum().reindex(cats)
            bo = s.assign(c=tx.categorie(s)).groupby("c")["B/O"].sum().reindex(cats) if "B/O" in s.columns else None
            series = {"Stock étagère": g2["QTE SUR ÉTAGÈRE"], "En commande": g2["QTE EN CDE"]}
            if bo is not None:
                series["Back-order"] = bo
            ui.graphe(charts.barres(cats, series, {"Stock étagère": COLORS["navy_2"], "En commande": "#F4A259", "Back-order": "#BC4B51"},
                                    titre="Stock, commandes et back-orders (qté)", hauteur=205))
        with st.popover("📋 Tableau par catégorie"):
            ui.tableau(tx.resume_categories(s, o), column_config=CFG, width=1000)
        _pn_dormants(s)


@st.fragment
def _pn_dormants(s):
    d = s[s["Statut activité"] == "Dormant"].sort_values("Valeur stock (€)", ascending=False)
    if d.empty:
        return
    with st.popover(f"💤 PN dormants ({len(d)})"):
        cols = {"PNR": "PN", "DESCRIPTION": "Description", "REF_Equipement": "Catégorie", "QTE SUR ÉTAGÈRE": "Stock",
                "Valeur stock (€)": "Valeur stock (€)", "DATE DERNIERE CONSO": "Dernière conso", "Motif activité": "Motif"}
        ui.tableau(d[[c for c in cols if c in d.columns]].rename(columns=cols), column_config=CFG, width=1000, height=420)


# --------------------------------------------------------------------------
# Commandes
# --------------------------------------------------------------------------
def _commandes(s, o, today, cat):
    if o.empty:
        ui.callout(f"Importez le fichier <b>{sio.FICHIER_COMMANDES}</b> pour voir les commandes.", "info", "📦")
        return
    r = tx.synthese(s, o)
    with ui.section(f"{TAB_ID}_cmd", "Commandes", "Retard = date promise − date demandée, au-delà de 10 jours de tolérance"):
        ui.kpi_grid([
            ui.kpi_card("Lignes de commande", charts.entier(r["lignes"])),
            ui.kpi_card("En retard", charts.entier(r["en_retard"]), "", "ko"),
            ui.kpi_card("Sans date promise", charts.entier(r["sans_date"]), "dates 2001 / 2030+ / vides", "warn"),
            ui.kpi_card("En attente BFE", charts.entier(r["bfe"]), "date 2049", "violet"),
            ui.kpi_card("Fournisseurs", charts.entier(r["fournisseurs"]), "", "info"),
        ])
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
        f1, f2 = st.columns([1, 2])
        q = f1.text_input("Rechercher", placeholder="🔎 PN, commande ou fournisseur", key=K + "q", persist_state="page",
                          label_visibility="collapsed")
        statut = f2.multiselect("Statut", tx.ORDER_STATUS_ORDER, key=K + "statut", placeholder="Tous les statuts",
                                label_visibility="collapsed", persist_state="page")
        d = o
        if q:
            qq = q.strip().upper()
            d = d[d["PNR"].str.contains(qq.replace(" ", ""), na=False, regex=False)
                  | d["Commande"].astype(str).str.upper().str.contains(qq, na=False, regex=False)
                  | d["Fournisseur"].astype(str).str.upper().str.contains(qq, na=False, regex=False)]
        if statut:
            d = d[d["Statut commande"].isin(statut)]
        cols = {**COL_RELANCES, "Date emission commande": "Émise", "Classe de retard": "Classe de retard"}
        t = d[[c for c in cols if c in d.columns]].rename(columns=cols)
        t["Statut"] = t["Statut"].map(STATUT_ICONES)
        ui.tableau(t, column_config=CFG, height=420)


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
        cols = {**COL_RELANCES, "Date emission commande": "Émise", "Ecart promis vs demandé (j)": "Écart (j)"}
        t = d.sort_values("Date livraison promise")[[c for c in cols if c in d.columns]].rename(columns=cols)
        t["Statut"] = t["Statut"].map(STATUT_ICONES)
        ui.tableau(t, column_config=CFG, height=min(38 + 35 * len(t), 380))


# --------------------------------------------------------------------------
# Consommation
# --------------------------------------------------------------------------
def _consommation(s, o, today, cat):
    annees = tx.annees_conso(s)
    cats = tx.categories(s)
    with ui.section(f"{TAB_ID}_conso", "Consommation", "Quantités consommées, issues de l'État du stock"):
        if annees:
            ui.graphe(charts.multiples({c: ([str(a) for a in annees], [s.loc[tx.categorie(s) == c, f"QTE CONSO {a}"].fillna(0).sum()
                                                                       for a in annees]) for c in cats},
                                       tx.CATEGORY_COLORS, titre="Par année"))
        fen = [w for w in tx.WINDOW_COLUMNS if w in s.columns]
        if fen:
            ui.graphe(charts.multiples({c: (["12 mois", "18 mois", "24 mois"][:len(fen)], [s.loc[tx.categorie(s) == c, w].fillna(0).sum() for w in fen])
                                        for c in cats}, tx.CATEGORY_COLORS, titre="Sur 12 / 18 / 24 mois glissants"))
        with st.popover("📋 Tableau par catégorie"):
            ui.tableau(tx.conso_par_categorie(s), width=1000)
    if "QTE CONSO 12M" in s.columns:
        with ui.section(f"{TAB_ID}_top", "PN les plus consommés", "12 derniers mois face aux 12 mois précédents"):
            d = s.sort_values("QTE CONSO 12M", ascending=False).head(15)
            ui.graphe(charts.barres(d["PNR"], {"12 derniers mois": d["QTE CONSO 12M"].fillna(0), "12 mois précédents": d["Conso 12 mois précédents"]},
                                    {"12 derniers mois": COLORS["navy_2"], "12 mois précédents": COLORS["gris"]},
                                    ligne={"Évolution": d["Evolution 12M vs 12M précédents (%)"]}, fmt_ligne=charts.pourcent,
                                    survol=list(d["DESCRIPTION"].fillna("").astype(str)) if "DESCRIPTION" in d else None, hauteur=260))
        _conso_pn(s, annees)


@st.fragment
def _conso_pn(s, annees):
    if not annees:
        return
    with ui.section(f"{TAB_ID}_pn", "Par PN"):
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
1. **Groupe d'avions** (ex. A320 Group 1) : pour chaque PN, la quantité nécessaire par avion et le nombre d'avions du groupe.
2. **Objectif d'avance** : pouvoir équiper à tout moment un pourcentage des avions du groupe (paramètre, 10 % par défaut,
   minimum 1). Exemple : 10 avions → 1, 50 avions → 5.
3. **Stock minimum du PN** = quantité par avion × objectif d'avance, additionné sur tous les groupes qui utilisent le PN.
4. **Besoin** = stock minimum − (stock étagère + quantités déjà en commande).
5. **Commande** : au plus tard à la date de besoin moins le délai fournisseur. Si le délai ne permet pas de livrer à temps,
   la commande part maintenant et le manque avant livraison est signalé.
6. **Statuts** : « A commander » = déjà sous l'objectif ; « A planifier » = passera sous l'objectif avant la fin de
   l'horizon ; « OK » = objectif couvert.
7. **PN dormants et inactifs** : aucune commande recommandée (la quantité bloquée est indiquée à part).
8. **Fournisseur** d'un PN : celui de ses commandes habituelles ; à défaut le dernier fournisseur de l'État du stock,
   puis le code fournisseur.
"""


def _section_prevision(prev, cat, o):
    if prev is None:
        with ui.section(f"{TAB_ID}_prev_vide", "Prévision de commandes"):
            ui.empty_state(f"Importez le fichier {pv.FICHIER_PIECES}", "La prévision s'appuie sur les pièces par avion. "
                           "Les paramètres sont réglables dans « Paramètres de la prévision ».",
                           [(pv.FICHIER_PIECES, False)], icon="🧮")
        return
    pbi, res = prev
    s = pbi if cat == TOUTES else pbi[tx.categorie(pbi) == cat]
    plan = res["plan"] if cat == TOUTES else res["plan"][res["plan"]["Catégorie"] == cat]
    gs = res["gs"] if cat == TOUTES else res["gs"][res["gs"]["equipment"] == cat]
    now = s[s["Qté à commander maintenant"] > 0]
    with ui.section(f"{TAB_ID}_prev", "Prévision de commandes", "Stock minimum à tenir : avions d'avance par groupe d'avions"):
        if len(now):
            ui.callout(f"<b>{len(now)} PN à commander maintenant</b> pour {charts.euros(now['Valeur à commander maintenant (€)'].sum())}, "
                       f"chez <b>{now['Fournisseur'].nunique()} fournisseur(s)</b>.", "ko", "📌")
        ui.kpi_grid([
            ui.kpi_card("PN à commander maintenant", charts.entier(len(now)), "", "ko"),
            ui.kpi_card("Valeur à commander", charts.euros(now["Valeur à commander maintenant (€)"].sum()), "maintenant", "ko"),
            ui.kpi_card("PN à planifier", charts.entier((s["Statut prévision"] == "A planifier").sum()), "sur l'horizon", "warn"),
            ui.kpi_card("Groupes sous l'objectif", charts.entier((gs["Statut groupe"] == "Sous l'objectif").sum()), "", "accent"),
            ui.kpi_card("Dormants / inactifs", charts.entier((s["Statut prévision"] == "Dormant / inactif : pas de commande").sum()),
                        "non commandés", "violet"),
        ])
        c1, c2, c3 = st.columns(3)
        with c1.popover("ℹ️ Comment le besoin est calculé", width="stretch"):
            st.markdown(EXPLICATION)
        with c2.popover("📋 Tableaux détaillés", width="stretch"):
            _tableaux_prevision(s, plan, gs, res)
        with c3:
            ui.telecharger(_export(*st.session_state[K + "cle_export"]), sio.nom_export(TAB_ID), K + "export_prev__btn")

    fours = pv.par_fournisseur(s, plan)
    with ui.section(f"{TAB_ID}_prev_four", "Prévision par fournisseur",
                    "PN actifs rattachés à un groupe d'avions · fournisseur, ou à défaut code fournisseur", tag=str(len(fours))):
        a, b = st.columns(2, gap="large")
        with a:
            top = fours[fours["Valeur maintenant (€)"] > 0].sort_values("Valeur maintenant (€)", ascending=False).head(12)
            ui.graphe(charts.barres_h([(r["Fournisseur"], r["Valeur maintenant (€)"], charts.euros(r["Valeur maintenant (€)"]))
                                       for _, r in top.iterrows()], couleur=COLORS["ko"], titre="Valeur à commander maintenant")
                      if len(top) else charts.vide("Aucune commande à passer maintenant"))
        with b:
            top = fours[fours["Valeur sur l'horizon (€)"] > 0].sort_values("Valeur sur l'horizon (€)", ascending=False).head(12)
            ui.graphe(charts.barres_h([(r["Fournisseur"], r["Valeur sur l'horizon (€)"], charts.euros(r["Valeur sur l'horizon (€)"]))
                                       for _, r in top.iterrows()], titre="Valeur à commander sur l'horizon")
                      if len(top) else charts.vide("Aucune commande sur l'horizon"))
        ui.tableau(fours, column_config=CFG, height=min(38 + 35 * len(fours), 420))
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
                                     "Dormants / inactifs non commandés", "Groupes d'avions", "Besoin par groupe et PN"],
                         key=K + "tab_prev", persist_state="page", label_visibility="collapsed")
    if choix == "À commander maintenant":
        d = s[s["Qté à commander maintenant"] > 0].sort_values("Valeur à commander maintenant (€)", ascending=False)
        d = d[[c for c in COL_PREV if c in d.columns]].rename(columns=COL_PREV)
    elif choix == "Plan de commande":
        d = plan.sort_values(["Mois de commande", "PNR"])
    elif choix == "Manque avant livraison":
        d = s[s["Manque avant livraison possible (qté)"] > 0].sort_values("Manque avant livraison possible (qté)", ascending=False)
        d = d[[c for c in [*COL_PREV, "Manque avant livraison possible (qté)"] if c in d.columns]].rename(columns=COL_PREV)
    elif choix == "Dormants / inactifs non commandés":
        d = s[s["Dans un groupe avion"] & s["Statut activité"].isin(["Dormant", "Inactif"])]
        d = d.sort_values("Commande bloquée PN dormant/inactif (qté)", ascending=False)
        d = d[[c for c in [*COL_PREV, "Statut activité", "Commande bloquée PN dormant/inactif (qté)"] if c in d.columns]].rename(columns=COL_PREV)
    elif choix == "Groupes d'avions":
        d = gs.sort_values(["equipment", "Ecart vs objectif (avions)"])
    else:
        d = res["gp"][res["gp"]["pn"].isin(s["PNR"])]
    ui.tableau(d, column_config=CFG, width=1100, height=440)


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
        cand = s[s["Dans un groupe avion"] & (s["Statut activité"] == "Actif") & (s["Fournisseur"] == f)]
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
                                {"En stock": COLORS["navy_2"], "Déjà en commande": "#F4A259", "À commander": COLORS["ko"]},
                                empile=True, repere={"Stock minimum à tenir": g["Besoin minimum (qté)"]},
                                survol=list(g["DESCRIPTION"].fillna("").astype(str)) if "DESCRIPTION" in g else None,
                                titre="Par PN : en stock, déjà en commande, à commander", hauteur=260)
                  if len(g) else charts.vide("Aucun PN actif suivi chez ce fournisseur"))
        _ecarts_lignes(ec, lignes)
        t1, t2 = st.columns(2)
        with t1.popover(f"📋 PN du fournisseur ({len(d)})", width="stretch"):
            ui.tableau(d[[c for c in COL_PREV if c in d.columns]].rename(columns=COL_PREV), column_config=CFG, width=1100, height=420)
        with t2.popover("📦 Commandes en cours chez ce fournisseur", width="stretch"):
            if o.empty:
                st.caption("Aucun fichier de commandes chargé.")
            else:
                oc = o[((o["Fournisseur"] == f) | o["PNR"].isin(d["PNR"])) & (o["Qte restante"].fillna(0) > 0)]
                cols = {**COL_RELANCES, "Date emission commande": "Émise", "Ecart promis vs demandé (j)": "Écart (j)"}
                t = oc.sort_values("Date livraison promise")[[c for c in cols if c in oc.columns]].rename(columns=cols)
                t["Statut"] = t["Statut"].map(STATUT_ICONES)
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
