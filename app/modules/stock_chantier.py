"""Onglet « Stock par chantier » : besoins chantier (GEAV) × état du stock × commandes.

Repris de legacy/streamlit_GEAV.py. Identifie les pièces à commander et les fournisseurs
à relancer pour sécuriser les équipements avant le début du chantier.
"""

import re
from datetime import date

import pandas as pd
import streamlit as st

from core import cache
from core import components as ui
from core import io as sio
from core import transforms as tf

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
                      ("Task TRFX / Task Name", "code TRFX", False), ("Requestid", "affiché « RRS »", False),
                      ("Description", "", False)],
    ETUDE_ASREQ: [("PN + infos pièce sortie", "feuille « Ordered »", True), ("Qty", "", True), ("ID BARECODE", "code TRFX", False)],
    "stock": [("PNR", "", True), ("QTE SUR ÉTAGÈRE", "", True), ("QTE EN CDE", "", False), ("GESTION", "", False),
              ("CODE AGT APPRO", "affiché « Code agent », contact des actions", False), ("QTE SAR, Purchase Req.", "affichés « SAR », « PR »", False),
              ("CODE / DERNIER FOURNISSEUR", "", False), ("CCN, CLASS CODE, TRACKING LEVEL", "", False)],
    "commandes": [("PN", "", True), ("Commande", "", False), ("Gestion", "fait foi", False),
                  ("Fournisseur, Code fournisseur", "le nom manquant est retrouvé par le code", False),
                  ("Date de livraison promise / demandée", "", False), ("Class code, CCN", "", False)],
}

# Ordre demandé par l'auteur ; TRFX et Class code (non cités) gardés en fin de tableau. Même ordre dans l'export.
COLONNES_TABLEAU = {
    "STATUT": "Statut", "PN": "PN", "CCN": "CCN", "RRS": "RRS", "Qty_a_commander": "À commander", "QTY_GEAV": "Besoin",
    "QTY_STOCK": "Stock", "QTY_CDE": "En cmd", "QTE_SAR": "SAR", "QTE_PR": "PR", "Commande": "N° commande", "PSD": "PSD",
    "FOURNISSEUR": "Fournisseur", "CODE_FOURNISSEUR": "Code fournisseur", "ACTION": "Action", "CODE_AGENT": "Code agent",
    "GESTION": "Gestion", "TL": "TL", "GEAV_DATE": "Date chantier", "TRFX": "TRFX", "CLASS_CODE": "Class code",
}
GROUPES = [("Pièce", 4), ("Quantités", 6), ("Commande", 2), ("Fournisseur", 2), ("Suivi", 5), ("Autres", 2)]
COLUMN_CONFIG = {
    "PSD": st.column_config.DateColumn("PSD", format="DD/MM/YYYY"),
    "Date chantier": st.column_config.DateColumn("Date chantier", format="DD/MM/YYYY"),
    "Gestion": st.column_config.NumberColumn("Gestion", format="%d"),
    "Class code": st.column_config.NumberColumn("Class code", format="%d"),
    "Besoin": st.column_config.NumberColumn("Besoin", format="%d"),
    "Stock": st.column_config.NumberColumn("Stock", format="%d"),
    "En cmd": st.column_config.NumberColumn("En cmd", format="%d"),
    "À commander": st.column_config.NumberColumn("À commander", format="%d"),
    "SAR": st.column_config.NumberColumn("SAR", format="%d", help="QTE SAR de l'État du stock"),
    "PR": st.column_config.NumberColumn("PR", format="%d", help="Purchase Req. de l'État du stock (quantité en demande d'achat)"),
    "RRS": st.column_config.TextColumn("RRS", help="Requestid du fichier LOGOPS (plusieurs RRS pour un même PN : besoins additionnés)"),
    "Code agent": st.column_config.TextColumn("Code agent", help="CODE AGT APPRO de l'État du stock"),
    "Action": st.column_config.TextColumn("Action", width="large"),
    "TL": st.column_config.TextColumn("TL", help="Tracking level (État du stock) : 0 = consommable (TL0), 1 = réparable (TL1)",
                                      width="small"),
}


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


EMOJIS = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B55\uFE0F]\\s*")
COULEURS_STATUT = {tf.ACTION_LABELS[c]: couleur for c, couleur in tf.ACTION_COULEURS.items()}


def tableau(m: pd.DataFrame) -> pd.DataFrame:
    """Vue d'affichage et d'export (mêmes colonnes, même ordre) : colonnes renommées, statut en clair, action sans emoji."""
    v = m.assign(STATUT=m["ACTION_CODE"].map(tf.ACTION_LABELS), ACTION=m["ACTION"].astype(str).str.replace(EMOJIS, "", regex=True))
    return v[list(COLONNES_TABLEAU)].rename(columns=COLONNES_TABLEAU)


def _afficher(m: pd.DataFrame, cle: str, filtres: bool = False, hauteur: str = "34rem") -> None:
    """Tableau de références : statut en badge, classe 8/9 signalée, colonnes regroupées (Pièce, Quantités…)."""
    ui.tableau_html(tableau(m).assign(_risque=m["RISK_CLASS"].to_numpy()), statut="Statut", couleurs=COULEURS_STATUT,
                    num=["Besoin", "Stock", "En cmd", "SAR", "PR", "Gestion", "Class code"], fort=["À commander"],
                    longs=["Action"], pn=["PN"], groupes=GROUPES, fixes=2, marque=("_risque", "Classe 8/9"), filtres=filtres,
                    cle=f"{TAB_ID}_{cle}", hauteur=hauteur, colonne_config=COLUMN_CONFIG)


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

    def statut(d):  # cellule Statut à la teinte de son badge, comme dans l'application
        return {"Statut": d["ACTION_CODE"].map(tf.ACTION_FILL_HEX).tolist()}

    return sio.exporter_excel(
        {"Synthèse": synthese, "Actions à lancer": tableau(actions), "Détail": tableau(detail), "Annexe (toutes réf.)": tableau(annexe)},
        couleurs_cellules={"Actions à lancer": statut(actions), "Détail": statut(detail), "Annexe (toutes réf.)": statut(annexe)},
    )


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------
# Dossier R2 du canal Teams des analystes : un sous-dossier « <IMMAT> - <JJMMAA> » par chantier.
SHAREPOINT_R2 = ("https://afkl.sharepoint.com/:f:/r/teams/MS-LGT1-Analystes/Shared%20Documents/R2"
                 "?d=we883c34cf267439f900715f00b63339a&csf=1&web=1&e=sss8GM")
# Règle de nommage du dossier chantier : le fichier « Résultat… » EST l'État du stock (le nom fait foi, quel que soit
# son contenu : sans cette règle, un export dont les en-têtes ressemblent à un autre fichier était écarté).
NOMS_DOSSIER = {"stock": r"^resultat"}
NOMMAGE = ("Choisissez dans R2 le dossier « <IMMAT> - <JJMMAA> » du chantier (ou R2 entier, puis le chantier dans la liste). "
           "Le fichier « Résultat… » est l'État du stock ; les autres sont reconnus par leur contenu. L'immatriculation et la date de début "
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
    """Bloc compact : dossiers mémorisés, état des fichiers, paramètres (popover) ; import manuel replié."""
    # Valeurs initiales par le Session State (pas de `value=`) : date et étude sont aussi écrites par l'import du dossier
    # chantier, et Streamlit avertit quand un widget a les deux.
    st.session_state.setdefault(K + "date", date.today())
    st.session_state.setdefault(K + "etude", ETUDE_CLASSIQUE)
    with ui.section(f"{TAB_ID}_import", ""):
        a, b, c = st.columns([2.25, 3.1, 1.15], vertical_alignment="center")
        with a:
            ui.boutons_dossiers("R2", K + "dossier__upload", mode="chantier")
        puces = b.container()
        n = len(st.session_state.get(K + "gestions", GESTIONS_DEFAUT))
        with c.popover(f"Paramètres · {n} code{'s' if n > 1 else ''} Gestion", width="stretch"):
            date_chantier = st.date_input("Début du chantier", format="DD/MM/YYYY", key=K + "date", persist_state="page",
                                          help="Lue dans le nom du dossier « <IMMAT> - <JJMMAA> ».")
            etude = st.segmented_control("Type d'étude", [ETUDE_CLASSIQUE, ETUDE_ASREQ], key=K + "etude",
                                         required=True, persist_state="page") or ETUDE_CLASSIQUE
            gestions = st.multiselect("Codes Gestion du périmètre", GESTIONS_PROPOSEES, default=GESTIONS_DEFAUT, key=K + "gestions",
                                      placeholder="Choisir les codes Gestion", persist_state="page")
        bilan = st.container()
        with ui.zone_repliable(K + "manuel", "Import manuel (Parcourir) et colonnes attendues"):
            zone_dossier = st.container()
            c1, c2, c3 = st.columns(3)
            with c1:
                if etude == ETUDE_CLASSIQUE:
                    f_besoin = ui.fichier(sio.FICHIER_BESOINS, K + "besoin_classique", ["xlsx", "xlsm"], COLONNES_ATTENDUES[etude],
                                          on_import=_infos_chantier)
                else:
                    f_besoin = ui.fichier(f"{sio.FICHIER_ASREQ} (.xlsm)", K + "besoin_asreq", ["xlsm", "xlsx"],
                                          COLONNES_ATTENDUES[etude], on_import=_infos_chantier)
            with c2:
                f_stock = ui.fichier(sio.FICHIER_STOCK, K + "stock", ["xlsx", "xlsm"], COLONNES_ATTENDUES["stock"])
            with c3:
                f_cmd = ui.import_commandes(COLONNES_ATTENDUES["commandes"])
            ui.lien_sharepoint(SHAREPOINT_R2, "R2")
        with bilan:
            # Pas de cible « commandes » : seul le fichier du dossier COMMANDE fait foi.
            ui.import_dossier(K + "dossier", {"besoins": K + "besoin_classique", "asreq": K + "besoin_asreq", "stock": K + "stock"},
                              dossier=True, on_choix=_choix_chantier, label="Dossier du chantier (ou R2 entier)", aide=NOMMAGE,
                              noms=NOMS_DOSSIER,
                              zone=zone_dossier)
        with puces:
            besoin = (sio.FICHIER_BESOINS, K + "besoin_classique") if etude == ETUDE_CLASSIQUE else (sio.FICHIER_ASREQ, K + "besoin_asreq")
            ui.etat_fichiers([(*besoin, True), (sio.FICHIER_STOCK, K + "stock", True), (sio.FICHIER_COMMANDES, "commun__commandes", True)])
    return etude, date_chantier, gestions, f_besoin, f_stock, f_cmd


def _statut_chantier(date_chantier) -> str:
    j = tf.jours_avant(date_chantier, date.today())
    return f"À venir · J-{j}" if j > 0 else ("Début aujourd'hui" if j == 0 else f"Démarré depuis {-j} j")


def _contexte() -> str:
    """Encadré de l'en-tête : immatriculation, début du chantier et statut (J-x), type d'étude."""
    d = st.session_state.get(K + "date", date.today())
    j = tf.jours_avant(d, date.today())
    statut = ui.badge(_statut_chantier(d), "info" if j > 0 else ("ok" if j == 0 else "muted"))
    blocs = [("Chantier", st.session_state[K + "immat"], "")] if st.session_state.get(K + "immat") else []
    blocs += [("Début du chantier", f"{d:%d/%m/%Y}", statut), ("Étude", st.session_state.get(K + "etude", ETUDE_CLASSIQUE), "")]
    return ui.contexte(*blocs)


def render() -> None:
    entete = st.container()
    etude, date_chantier, gestions, f_besoin, f_stock, f_cmd = _bloc_import()
    with entete:  # dessiné au-dessus de l'import, mais après lui : le contexte reflète le dossier qui vient d'être choisi
        ui.hero(TAB_ICON, "Stock par chantier", "Pièces à commander et fournisseurs à relancer avant le début du chantier (GEAV).",
                "Supply Chain · Production", _contexte())

    nom_besoin = sio.FICHIER_BESOINS if etude == ETUDE_CLASSIQUE else sio.FICHIER_ASREQ
    if not (f_besoin and f_stock and f_cmd):
        with ui.section(f"{TAB_ID}_vide", "Analyse"):
            ui.empty_state("Importez les trois fichiers", "Ouvrez le dossier du chantier dans R2 (et le dossier COMMANDE) : "
                           "l'analyse se lance automatiquement. Les fichiers restent sur votre poste.",
                           [(nom_besoin, bool(f_besoin)), (sio.FICHIER_STOCK, bool(f_stock)), (sio.FICHIER_COMMANDES, bool(f_cmd))])
        return
    if not gestions:
        ui.callout("Sélectionnez au moins un <b>code Gestion</b> (Paramètres).", "warn", "alert")
        return

    cle = (f_besoin[1], etude, f_stock[1], f_cmd[1], tuple(sorted(gestions)), date_chantier)
    try:
        with st.spinner("Lecture et croisement des fichiers…"):
            m, m_scope = _analyse(*cle)
        export = lambda: _export(*cle)  # noqa: E731 — fabriqué au clic seulement
    except ValueError as exc:  # ColonneIntrouvable, FichierIllisible
        ui.callout(f"<b>Import impossible.</b> {exc}", "ko", "x")
        return

    s = tf.synthese_geav(m_scope)
    nom = sio.nom_export(TAB_ID)

    # ---- Synthèse ----
    resume = (f"{s['n_commander']} référence(s) à commander ({s['qty_a_commander']} unités) et {s['n_relance']} relance(s) "
              f"fournisseur avant le {date_chantier:%d/%m/%Y}" if s["n_commander"] or s["n_relance"]
              else "Besoin couvert : aucune commande ni relance à lancer")
    with ui.section(f"{TAB_ID}_synthese", "Synthèse", resume, export=(export, nom, K + "export_haut__btn"), carte=False):
        compte = m_scope["ACTION_CODE"].value_counts()
        ordre = ["commander", "relancer_urgent", "relancer", "inconnu", "en_cours", "ok"]
        u = s["n_relance_urgente"]
        ui.kpi_grid([
            ui.kpi_repartition("Périmètre du chantier", s["n_total"], "références",
                               [(tf.ACTION_LABELS[c], int(compte.get(c, 0)), tf.ACTION_COULEURS[c]) for c in ordre],
                               note=f"+ {len(m) - s['n_total']} hors périmètre Gestion"),
            ui.kpi_card("À commander", s["n_commander"], f"{s['qty_a_commander']} unités au total", "ko", "cart"),
            ui.kpi_card("Relances fournisseur", s["n_relance"], f"dont {u} urgente{'s' if u > 1 else ''} (PSD après le début)",
                        "orange", "send"),
            ui.kpi_card("En cours de livraison", s["n_en_cours"], "livrées avant le début", "info", "truck"),
            ui.kpi_card("Stock suffisant", s["n_ok"], "aucune action", "ok", "package"),
        ])
        if s["n_risque"]:
            risque = m_scope[m_scope["RISK_CLASS"]]
            ui.callout(f"<b>{s['n_risque']} référence(s) classe 8/9 à traiter en priorité</b> : "
                       f"{', '.join(risque['PN'].astype(str).head(8))}{' …' if len(risque) > 8 else ''} — en tête des actions.",
                       "ko", "flag")

    # ---- Actions à lancer ----
    actions = tf.actions_a_lancer(m_scope)
    with ui.section(f"{TAB_ID}_actions", "Actions à lancer", f"Du plus urgent au moins urgent · à faire avant le {date_chantier:%d/%m/%Y}",
                    tag=str(len(actions)), export=(export, nom, K + "export_actions__btn")):
        if actions.empty:
            ui.callout("Aucune action à lancer.", "ok", "check-circle")
        else:
            _afficher(actions, "actions", filtres=True)

    _detail(m, m_scope, export, gestions)


@st.fragment
def _detail(m, m_scope, export, gestions):
    """Tableau filtrable du périmètre. Fragment : filtrer ne relance que ce bloc."""
    with ui.section(f"{TAB_ID}_detail", "Détail du périmètre", f"Toutes les références des codes Gestion "
                    f"{', '.join(str(g) for g in sorted(gestions))}", export=(export, sio.nom_export(TAB_ID), K + "export_bas__btn")):
        f1, f2 = st.columns([1, 1.6])
        recherche = f1.text_input("Rechercher un PN", key=K + "recherche", placeholder="PN…", persist_state="page")
        filtre = f2.multiselect("Filtrer par statut", options=tf.ACTION_ORDRE, format_func=lambda c: tf.ACTION_LABELS[c],
                                key=K + "filtre_action", placeholder="Tous les statuts", persist_state="page")
        vue = m_scope
        if recherche:
            vue = vue[vue["PN"].str.contains(recherche.strip().upper().replace(" ", ""), na=False, regex=False)]
        if filtre:
            vue = vue[vue["ACTION_CODE"].isin(filtre)]
        _afficher(vue.sort_values("Qty_a_commander", ascending=False, kind="stable"), "detail", hauteur="30rem")
        b2, b3, _ = st.columns([1.3, 1, 3])
        with b2.popover(f"Toutes les références ({len(m)})", width="stretch"):
            st.caption("Y compris codes Gestion hors périmètre et PN sans code Gestion.")
            ui.tableau(tableau(m.sort_values("Qty_a_commander", ascending=False, kind="stable")),
                       column_config=COLUMN_CONFIG, height=420, width=1100)
        with b3.popover("Règles de calcul", width="stretch"):
            _aide()


def _aide() -> None:
    st.markdown(f"""
**Croisement** par PN (majuscules, sans espaces). La gestion du fichier Commandes fait foi ; la PSD retenue est
la plus proche (à défaut, date de livraison demandée). Les besoins d'un même PN sont **additionnés**, même
s'ils viennent de plusieurs TRFX / RRS (colonnes TRFX et RRS : « A | B »). Contact des actions : **Code agent**
(CODE AGT APPRO de l'État du stock).

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

Classe 8/9 : étiquette « Classe 8/9 » et mention « PRIORITÉ » dans l'action, en tête des actions. Fournisseur manquant : retrouvé par le code fournisseur.
""")

