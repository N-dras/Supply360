"""Onglet « Stock par chantier » : besoins chantier (GEAV) × état du stock × commandes.

Repris de legacy/streamlit_GEAV.py. Identifie les pièces à commander et les fournisseurs
à relancer pour sécuriser les équipements avant le début du chantier.
"""

from datetime import date

import pandas as pd
import streamlit as st

from core import cache, charts
from core import components as ui
from core import io as sio
from core import transforms as tf
from core.style import COLORS

TAB_ID = "stock_chantier"
TAB_LABEL = "Stock par chantier"
TAB_ICON = "🛠️"
TAB_DESCRIPTION = "Pièces à commander et fournisseurs à relancer avant le début d'un chantier (GEAV)."

K = f"{TAB_ID}__"  # préfixe des clés de widgets / session

GESTIONS_DEFAUT = [245, 246, 247, 400, 401, 230]
GESTIONS_PROPOSEES = sorted(set(GESTIONS_DEFAUT) | {251, 256, 300, 375, 443, 487, 500})
ETUDE_CLASSIQUE = "Classique"
ETUDE_ASREQ = "ASREQ/NOREQ"

COLONNES_ATTENDUES = {
    ETUDE_CLASSIQUE: [("MPN Prime", "référence pièce", True), ("Qty", "quantité requise", True),
                      ("Task TRFX / Task Name", "code TRFX", False), ("Description", "", False)],
    ETUDE_ASREQ: [("PN + infos pièce sortie", "feuille « Ordered »", True), ("Qty", "", True), ("ID BARECODE", "code TRFX", False)],
    "stock": [("PNR", "", True), ("QTE SUR ÉTAGÈRE", "", True), ("QTE EN CDE", "", False), ("GESTION", "", False),
              ("CODE AGT APPRO", "contact par défaut", False), ("CODE / DERNIER FOURNISSEUR", "", False), ("CCN, CLASS CODE", "", False)],
    "commandes": [("PN", "", True), ("Commande", "", False), ("Code acheteur", "", False), ("Gestion", "fait foi", False),
                  ("Fournisseur, Code fournisseur", "le nom manquant est retrouvé par le code", False),
                  ("Date de livraison promise / demandée", "", False), ("Class code, CCN", "", False)],
}

COLONNES_TABLEAU = {
    "PN": "PN", "STATUT": "Statut", "Qty_a_commander": "À commander", "QTY_GEAV": "Besoin", "QTY_STOCK": "Stock",
    "QTY_CDE": "En cmd", "PSD": "PSD", "FOURNISSEUR": "Fournisseur", "CODE_ACHETEUR": "Acheteur", "ACTION": "Action",
    "Commande": "N° commande", "CODE_FOURNISSEUR": "Code fournisseur", "TRFX": "TRFX", "CCN": "CCN", "GESTION": "Gestion",
    "CLASS_CODE": "Class code", "GEAV_DATE": "Date chantier",
}
COLUMN_CONFIG = {
    "PSD": st.column_config.DateColumn("PSD", format="DD/MM/YYYY"),
    "Date chantier": st.column_config.DateColumn("Date chantier", format="DD/MM/YYYY"),
    "Gestion": st.column_config.NumberColumn("Gestion", format="%d"),
    "Class code": st.column_config.NumberColumn("Class code", format="%d"),
    "Besoin": st.column_config.NumberColumn("Besoin", format="%d"),
    "Stock": st.column_config.NumberColumn("Stock", format="%d"),
    "En cmd": st.column_config.NumberColumn("En cmd", format="%d"),
    "À commander": st.column_config.NumberColumn("À commander", format="%d"),
    "Action": st.column_config.TextColumn("Action", width="large"),
}
ACTION_COULEURS = {"commander": COLORS["ko"], "relancer_urgent": COLORS["accent"], "relancer": COLORS["warn"],
                   "inconnu": COLORS["muted"], "en_cours": COLORS["navy_2"], "hors_perimetre": COLORS["gris"], "ok": COLORS["ok"]}


# --------------------------------------------------------------------------
# Lectures et calculs mis en cache (une fois par fichier / jeu de paramètres)
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner=False, max_entries=4)
def _besoins(data: bytes, etude: str):
    lignes, feuille = (sio.lire_besoins_geav if etude == ETUDE_CLASSIQUE else sio.lire_besoins_asreq)(data)
    return tf.agreger_besoins(lignes), feuille


@st.cache_resource(show_spinner=False, max_entries=2)
def _stock(data: bytes):
    lignes, feuille = cache.etat_stock(data)
    return tf.agreger_stock(lignes), feuille


@st.cache_resource(show_spinner=False, max_entries=2)
def _commandes(data: bytes):
    lignes, feuille = cache.commandes(data)
    return tf.agreger_commandes(lignes), feuille


@st.cache_resource(show_spinner=False, max_entries=4)
def _analyse(b_besoin: bytes, etude: str, b_stock: bytes, b_cmd: bytes, gestions: tuple, date_chantier: date):
    """(m, m_scope) : clé de cache = contenu des fichiers + paramètres (pas de hachage de tables)."""
    besoin, _ = _besoins(b_besoin, etude)
    stock, _ = _stock(b_stock)
    commandes, _ = _commandes(b_cmd)
    m = tf.croiser_geav(besoin, stock, commandes, gestions, pd.Timestamp(date_chantier))
    return m, m[m["gestion_in_scope"]].copy()


def tableau(m: pd.DataFrame) -> pd.DataFrame:
    """Vue d'affichage / d'export : colonnes renommées, statut court."""
    v = m.assign(STATUT=m["ACTION_CODE"].map(tf.ACTION_LABELS))
    return v[list(COLONNES_TABLEAU)].rename(columns=COLONNES_TABLEAU)


@st.cache_resource(show_spinner=False, max_entries=2)
def _export(b_besoin: bytes, etude: str, b_stock: bytes, b_cmd: bytes, gestions: tuple, date_chantier: date) -> bytes:
    m, m_scope = _analyse(b_besoin, etude, b_stock, b_cmd, gestions, date_chantier)
    params = {"etude": etude, "date": date_chantier, "gestions": list(gestions)}
    s = tf.synthese_geav(m_scope)
    synthese = pd.DataFrame([
        ("Type d'étude", params["etude"]), ("Date de début du chantier", f"{params['date']:%d/%m/%Y}"),
        ("Codes Gestion du périmètre", ", ".join(str(g) for g in params["gestions"])),
        ("Date de l'analyse", f"{date.today():%d/%m/%Y}"), ("Références (périmètre)", s["n_total"]),
        ("À commander (références)", s["n_commander"]), ("À commander (unités)", s["qty_a_commander"]),
        ("À relancer (dont urgentes)", f"{s['n_relance']} ({s['n_relance_urgente']})"),
        ("En cours de livraison", s["n_en_cours"]), ("Stock suffisant", s["n_ok"]),
        ("PN introuvables", s["n_inconnu"]), ("Références classe 8/9", s["n_risque"]),
    ], columns=["Indicateur", "Valeur"])
    actions = tf.actions_a_lancer(m_scope)
    detail = m_scope.sort_values("Qty_a_commander", ascending=False, kind="stable")
    annexe = m.sort_values("Qty_a_commander", ascending=False, kind="stable")

    def fills(d):
        return d["ACTION_CODE"].map(tf.ACTION_FILL_HEX).tolist()

    return sio.exporter_excel(
        {"Synthèse": synthese, "Actions à lancer": tableau(actions), "Détail": tableau(detail), "Annexe (toutes réf.)": tableau(annexe)},
        couleurs_lignes={"Actions à lancer": fills(actions), "Détail": fills(detail), "Annexe (toutes réf.)": fills(annexe)},
    )


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------
# Dossier R2 du canal Teams des analystes : un sous-dossier « <IMMAT> - <JJMMAA> » par chantier.
SHAREPOINT_R2 = ("https://afkl.sharepoint.com/:f:/r/teams/MS-LGT1-Analystes/Shared%20Documents/R2"
                 "?d=we883c34cf267439f900715f00b63339a&csf=1&web=1&e=sss8GM")
NOMMAGE = ("Choisissez dans R2 le dossier « <IMMAT> - <JJMMAA> » du chantier (ou R2 entier, puis le chantier dans la liste). "
           "Les fichiers sont reconnus par leur contenu, quel que soit leur nom ; l'immatriculation et la date de début "
           "viennent du nom du dossier.")


def _infos_chantier(nom: str) -> None:
    """Callback d'import : « <IMMAT> - <JJMMAA> » dans le nom du fichier → immatriculation et date de début."""
    info = sio.chantier_depuis_nom(nom)
    if info:
        st.session_state[K + "immat"], st.session_state[K + "date"] = info


def _choix_chantier(dossier: str, par_source: dict) -> None:
    """Callback de l'import de dossier : immatriculation et date (nom du dossier), type d'étude (fichiers trouvés)."""
    if "besoins" in par_source or "asreq" in par_source:
        st.session_state[K + "etude"] = ETUDE_CLASSIQUE if "besoins" in par_source else ETUDE_ASREQ
    _infos_chantier(dossier or next(iter(par_source.get("besoins") or par_source.get("asreq") or [""])))


def _bloc_import():
    with ui.section(f"{TAB_ID}_import", "Import et paramètres"):
        d1, d2, d3 = st.columns([1.1, 1.1, 1], vertical_alignment="center")
        with d1:
            ui.bouton_dossier("R2", K + "dossier__upload", mode="chantier")
        with d2:
            ui.bouton_commandes()
        with d3:
            ui.lien_sharepoint(SHAREPOINT_R2, "R2")
        ui.import_dossier(K + "dossier", {"besoins": K + "besoin_classique", "asreq": K + "besoin_asreq", "stock": K + "stock",
                                          "commandes": "commun__commandes"}, dossier=True, on_choix=_choix_chantier,
                          label="… ou choisir le dossier du chantier avec Parcourir", aide=NOMMAGE)
        p1, p2, p3 = st.columns([1.1, 1, 2.2])
        etude = p1.radio("Type d'étude", [ETUDE_CLASSIQUE, ETUDE_ASREQ], horizontal=True, key=K + "etude", persist_state="page")
        date_chantier = p2.date_input("Début du chantier", value=date.today(), format="DD/MM/YYYY", key=K + "date",
                                      persist_state="page")
        gestions = p3.multiselect("Codes Gestion du périmètre", GESTIONS_PROPOSEES, default=GESTIONS_DEFAUT, key=K + "gestions",
                                  placeholder="Choisir les codes Gestion", persist_state="page")
        c1, c2, c3 = st.columns(3)
        with c1:
            if etude == ETUDE_CLASSIQUE:
                f_besoin = ui.fichier(sio.FICHIER_BESOINS, K + "besoin_classique", ["xlsx", "xlsm"], COLONNES_ATTENDUES[etude],
                                      on_import=_infos_chantier)
            else:
                f_besoin = ui.fichier(f"{sio.FICHIER_ASREQ} (.xlsm)", K + "besoin_asreq", ["xlsm", "xlsx"], COLONNES_ATTENDUES[etude],
                                      on_import=_infos_chantier)
        with c2:
            f_stock = ui.fichier(sio.FICHIER_STOCK, K + "stock", ["xlsx", "xlsm"], COLONNES_ATTENDUES["stock"])
        with c3:
            f_cmd = ui.import_commandes(COLONNES_ATTENDUES["commandes"])
    return etude, date_chantier, gestions, f_besoin, f_stock, f_cmd


def _statut_chantier(date_chantier) -> str:
    j = tf.jours_avant(date_chantier, date.today())
    return f"À venir · J-{j}" if j > 0 else ("Début aujourd'hui" if j == 0 else f"Démarré depuis {-j} j")


def render() -> None:
    ui.hero(TAB_ICON, "Stock par chantier — GEAV", TAB_DESCRIPTION)
    etude, date_chantier, gestions, f_besoin, f_stock, f_cmd = _bloc_import()

    nom_besoin = sio.FICHIER_BESOINS if etude == ETUDE_CLASSIQUE else sio.FICHIER_ASREQ
    if not (f_besoin and f_stock and f_cmd):
        with ui.section(f"{TAB_ID}_vide", "Analyse"):
            ui.empty_state("Importez les trois fichiers", "L'analyse se lance automatiquement. Les fichiers restent sur votre poste.",
                           [(nom_besoin, bool(f_besoin)), (sio.FICHIER_STOCK, bool(f_stock)), (sio.FICHIER_COMMANDES, bool(f_cmd))])
        return
    if not gestions:
        ui.callout("Sélectionnez au moins un <b>code Gestion</b>.", "warn", "⚠️")
        return

    cle = (f_besoin[1], etude, f_stock[1], f_cmd[1], tuple(sorted(gestions)), date_chantier)
    try:
        with st.spinner("Lecture et croisement des fichiers…"):
            m, m_scope = _analyse(*cle)
            export = _export(*cle)
    except ValueError as exc:  # ColonneIntrouvable, FichierIllisible
        ui.callout(f"<b>Import impossible.</b> {exc}", "ko", "⛔")
        return

    s = tf.synthese_geav(m_scope)
    immat = st.session_state.get(K + "immat", "")
    statut = _statut_chantier(date_chantier)

    # ---- Synthèse ----
    with ui.section(f"{TAB_ID}_synthese", "Synthèse", f"Chantier {immat + ' ' if immat else ''}du {date_chantier:%d/%m/%Y} · étude {etude}", tag=statut):
        if s["n_commander"] or s["n_relance"]:
            ui.callout(f"<b>{s['n_commander']} référence(s) à commander</b> ({s['qty_a_commander']} unités) et "
                       f"<b>{s['n_relance']} relance(s) fournisseur</b> avant le {date_chantier:%d/%m/%Y}.",
                       "ko" if s["n_commander"] else "warn", "📌")
        else:
            ui.callout("Besoin couvert : aucune commande ni relance à lancer.", "ok", "✅")
        if s["n_risque"]:
            ui.callout(f"<b>{s['n_risque']} référence(s) classe 8/9</b> à traiter en priorité.", "accent", "🚨")
        ui.kpi_grid([
            ui.kpi_card("Références du périmètre", s["n_total"], f"{len(m) - s['n_total']} hors périmètre"),
            ui.kpi_card("À commander", s["n_commander"], f"{s['qty_a_commander']} unités", "ko"),
            ui.kpi_card("À relancer", s["n_relance"], f"dont {s['n_relance_urgente']} urgente(s)", "warn"),
            ui.kpi_card("En cours de livraison", s["n_en_cours"], "à temps", "info"),
            ui.kpi_card("Stock suffisant", s["n_ok"], "", "ok"),
        ])
        ui.telecharger(export, sio.nom_export(TAB_ID), K + "export_haut__btn")

    # ---- Actions à lancer ----
    actions = tf.actions_a_lancer(m_scope)
    with ui.section(f"{TAB_ID}_actions", "Actions à lancer", tag=str(len(actions))):
        if actions.empty:
            ui.callout("Aucune action à lancer.", "ok", "✅")
        else:
            ui.tableau(tableau(actions), column_config=COLUMN_CONFIG,
                         height=min(38 + 35 * len(actions), 420))

    _detail(m, m_scope, export, gestions)


@st.fragment
def _detail(m, m_scope, export, gestions):
    """Répartition + tableau filtrable. Fragment : filtrer ne relance que ce bloc."""
    with ui.section(f"{TAB_ID}_detail", "Détail du périmètre", f"Codes Gestion {', '.join(str(g) for g in sorted(gestions))}"):
        g, d = st.columns([1, 2.2], gap="large")
        with g:
            counts = m_scope["ACTION_CODE"].value_counts()
            ui.graphe(charts.barres_h(
                [(tf.ACTION_LABELS[c].split(" ", 1)[1], int(counts.get(c, 0)), None, ACTION_COULEURS[c])
                 for c in tf.ACTION_ORDRE if c != "hors_perimetre"], titre="Répartition des actions", fmt=charts.entier))
        with d:
            f1, f2 = st.columns([1, 1.6])
            recherche = f1.text_input("Rechercher un PN", key=K + "recherche", placeholder="🔎 PN…", persist_state="page")
            filtre = f2.multiselect("Filtrer par statut", options=tf.ACTION_ORDRE, format_func=lambda c: tf.ACTION_LABELS[c],
                                    key=K + "filtre_action", placeholder="Tous les statuts", persist_state="page")
            vue = m_scope
            if recherche:
                vue = vue[vue["PN"].str.contains(recherche.strip().upper().replace(" ", ""), na=False, regex=False)]
            if filtre:
                vue = vue[vue["ACTION_CODE"].isin(filtre)]
            vue = vue.sort_values("Qty_a_commander", ascending=False, kind="stable")
            ui.tableau(tableau(vue), column_config=COLUMN_CONFIG, height=400)
        b1, b2, b3 = st.columns([1.3, 1.3, 3])
        with b1:
            ui.telecharger(export, sio.nom_export(TAB_ID), K + "export_bas__btn")
        with b2.popover(f"📎 Toutes les références ({len(m)})", width="stretch"):
            st.caption("Y compris codes Gestion hors périmètre et PN sans code Gestion.")
            ui.tableau(tableau(m.sort_values("Qty_a_commander", ascending=False, kind="stable")),
                         column_config=COLUMN_CONFIG, height=420, width=1100)
        with b3.popover("ℹ️ Règles de calcul"):
            _aide()


def _aide() -> None:
    st.markdown(f"""
**Croisement** par PN (majuscules, sans espaces). La gestion du fichier Commandes fait foi ; la PSD retenue est
la plus proche (à défaut, date de livraison demandée). Les besoins d'un même PN sont additionnés.

- **Déficit** = max(0, besoin − stock) · **À commander** = max(0, déficit − en commande)

| Statut | Condition (la première vérifiée l'emporte) |
|---|---|
| {tf.ACTION_LABELS['inconnu']} | PN absent de l'État du stock |
| {tf.ACTION_LABELS['hors_perimetre']} | code Gestion hors périmètre |
| {tf.ACTION_LABELS['commander']} | à commander > 0 |
| {tf.ACTION_LABELS['ok']} | déficit nul |
| {tf.ACTION_LABELS['relancer']} | déficit couvert, PSD absente ou {tf.ANNEE_PSD_NON_FOURNIE} |
| {tf.ACTION_LABELS['relancer_urgent']} | PSD après le début du chantier |
| {tf.ACTION_LABELS['en_cours']} | PSD avant le début du chantier |

Classe 8/9 : préfixe « 🚨 PRIORITÉ », en tête des actions. Fournisseur manquant : retrouvé par le code fournisseur.
""")

