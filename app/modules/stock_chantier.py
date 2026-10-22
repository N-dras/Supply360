"""Onglet « Stock par chantier » : croisement besoins chantier (GEAV) × état du stock × commandes.

Repris de legacy/streamlit_GEAV.py. Identifie les pièces à commander et les fournisseurs
à relancer pour sécuriser les équipements avant le début du chantier.
"""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import components as ui
from core import io as sio
from core import transforms as tf
from core.style import COLORS

TAB_ID = "stock_chantier"
TAB_LABEL = "Stock par chantier"
TAB_ICON = "🛠️"
TAB_DESCRIPTION = ("Croise les besoins d'un chantier (GEAV) avec l'état du stock et les commandes "
                   "pour lister les pièces à commander et les fournisseurs à relancer avant le début du chantier.")

K = f"{TAB_ID}__"  # préfixe des clés de widgets / session

GESTIONS_DEFAUT = [245, 246, 247, 400, 401, 230]
GESTIONS_PROPOSEES = sorted(set(GESTIONS_DEFAUT) | {230, 245, 246, 247, 251, 256, 300, 375, 400, 401, 443, 487, 500})

ETUDE_CLASSIQUE = "Classique"
ETUDE_ASREQ = "ASREQ/NOREQ"

COLONNES_ATTENDUES = {
    ETUDE_CLASSIQUE: [
        ("MPN Prime", "référence pièce (clé de croisement)", True),
        ("Qty", "quantité requise", True),
        ("Task TRFX / Task Name / Task WP Line", "code TRFX", False),
        ("Description", "", False),
    ],
    ETUDE_ASREQ: [
        ("PN + infos pièce sortie", "référence pièce, feuille « Ordered »", True),
        ("Qty", "quantité requise", True),
        ("ID BARECODE", "code TRFX", False),
    ],
    "stock": [
        ("PNR", "référence pièce", True),
        ("QTE SUR ÉTAGÈRE", "stock disponible", True),
        ("QTE EN CDE", "quantité en commande", False),
        ("GESTION", "code de gestion", False),
        ("CODE AGT APPRO", "contact par défaut", False),
        ("CODE FOURNISSEUR / DERNIER FOURNISSEUR", "", False),
        ("CCN, CLASS CODE, Description", "", False),
    ],
    "commandes": [
        ("PN", "référence pièce", True),
        ("Commande", "n° de commande", False),
        ("Code acheteur", "", False),
        ("Gestion", "fait foi sur l'État du stock", False),
        ("Fournisseur / Code fournisseur", "", False),
        ("Date de livraison promise (PSD)", "à défaut : date de livraison demandée", False),
        ("Statut, Quantité restant à livrer, Class code, CCN", "", False),
    ],
}

COLONNES_TABLEAU = {
    "PN": "PN",
    "CCN": "CCN",
    "TRFX": "TRFX",
    "QTY_GEAV": "QTY GEAV",
    "QTY_STOCK": "QTY en stock",
    "QTY_CDE": "QTY en cmd",
    "Qty_a_commander": "QTY à commander",
    "STATUT": "Statut",
    "ACTION": "Action",
    "PSD": "PSD",
    "FOURNISSEUR": "Fournisseur",
    "CODE_FOURNISSEUR": "Code fournisseur",
    "CODE_ACHETEUR": "Code acheteur",
    "Commande": "N° Commande",
    "GESTION": "Gestion",
    "CLASS_CODE": "Class code",
    "GEAV_DATE": "Date chantier",
}

COLUMN_CONFIG = {
    "PSD": st.column_config.DateColumn("PSD", format="DD/MM/YYYY"),
    "Date chantier": st.column_config.DateColumn("Date chantier", format="DD/MM/YYYY"),
    "Gestion": st.column_config.NumberColumn("Gestion", format="%d"),
    "Class code": st.column_config.NumberColumn("Class code", format="%d"),
    "QTY GEAV": st.column_config.NumberColumn("QTY GEAV", format="%d"),
    "QTY en stock": st.column_config.NumberColumn("QTY en stock", format="%d"),
    "QTY en cmd": st.column_config.NumberColumn("QTY en cmd", format="%d"),
    "QTY à commander": st.column_config.NumberColumn("QTY à commander", format="%d"),
    "Action": st.column_config.TextColumn("Action", width="large"),
    "Statut": st.column_config.TextColumn("Statut", width="medium"),
}


# --------------------------------------------------------------------------
# Lectures mises en cache (une fois par fichier importé)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False, max_entries=8)
def _besoins(data: bytes, etude: str):
    lignes, feuille = (sio.lire_besoins_geav if etude == ETUDE_CLASSIQUE else sio.lire_besoins_asreq)(data)
    return tf.agreger_besoins(lignes), feuille


@st.cache_data(show_spinner=False, max_entries=4)
def _stock(data: bytes):
    lignes, feuille = sio.lire_etat_stock(data)
    return tf.agreger_stock(lignes), feuille


@st.cache_data(show_spinner=False, max_entries=4)
def _commandes(data: bytes):
    lignes, feuille = sio.lire_commandes_sap(data)
    return tf.agreger_commandes(lignes), feuille


@st.cache_data(show_spinner=False, max_entries=8)
def _croiser(besoin, stock, commandes, gestion_scope: tuple, date_chantier: date):
    return tf.croiser_geav(besoin, stock, commandes, gestion_scope, pd.Timestamp(date_chantier))


def tableau(m: pd.DataFrame) -> pd.DataFrame:
    """Vue d'affichage / d'export : colonnes renommées, statut court."""
    v = m.assign(STATUT=m["ACTION_CODE"].map(tf.ACTION_LABELS))
    return v[list(COLONNES_TABLEAU)].rename(columns=COLONNES_TABLEAU)


@st.cache_data(show_spinner=False, max_entries=4)
def _export(m: pd.DataFrame, m_scope: pd.DataFrame, params: dict) -> bytes:
    s = tf.synthese_geav(m_scope)
    synthese = pd.DataFrame(
        [
            ("Type d'étude", params["etude"]),
            ("Date de début du chantier", f"{params['date']:%d/%m/%Y}"),
            ("Codes Gestion du périmètre", ", ".join(str(g) for g in params["gestions"])),
            ("Date de l'analyse", f"{date.today():%d/%m/%Y}"),
            ("Références (périmètre)", s["n_total"]),
            ("À commander (références)", s["n_commander"]),
            ("À commander (unités)", s["qty_a_commander"]),
            ("À relancer (dont urgentes)", f"{s['n_relance']} ({s['n_relance_urgente']})"),
            ("En cours de livraison", s["n_en_cours"]),
            ("Stock suffisant", s["n_ok"]),
            ("PN introuvables", s["n_inconnu"]),
            ("Références classe 8/9", s["n_risque"]),
        ],
        columns=["Indicateur", "Valeur"],
    )
    actions = tf.actions_a_lancer(m_scope)
    detail = m_scope.sort_values("Qty_a_commander", ascending=False, kind="stable")
    annexe = m.sort_values("Qty_a_commander", ascending=False, kind="stable")

    def fills(d):
        return d["ACTION_CODE"].map(tf.ACTION_FILL_HEX).tolist()

    return sio.exporter_excel(
        {"Synthèse": synthese, "Actions à lancer": tableau(actions), "Détail": tableau(detail),
         "Annexe (toutes réf.)": tableau(annexe)},
        couleurs_lignes={"Actions à lancer": fills(actions), "Détail": fills(detail),
                         "Annexe (toutes réf.)": fills(annexe)},
    )


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------
def _liste_colonnes(cle: str) -> None:
    with st.expander("Colonnes attendues"):
        lignes = []
        for nom, aide, obligatoire in COLONNES_ATTENDUES[cle]:
            tag = "**obligatoire**" if obligatoire else "facultatif"
            lignes.append(f"- `{nom}` — {tag}" + (f" · {aide}" if aide else ""))
        st.markdown("\n".join(lignes))
        st.caption("Détection automatique, insensible aux accents et majuscules : "
                   "la feuille et la ligne d'en-tête sont trouvées seules.")


def _bloc_import():
    with ui.section(f"{TAB_ID}_import", "1 · Import des fichiers et paramètres",
                    "Importez les trois fichiers : l'analyse se lance automatiquement."):
        p1, p2, p3 = st.columns([1.1, 1, 2])
        etude = p1.radio("Type d'étude", [ETUDE_CLASSIQUE, ETUDE_ASREQ], horizontal=True, key=K + "etude",
                         help="Les fichiers État du stock et Commandes sont communs aux deux études.")
        date_chantier = p2.date_input("Date de début du chantier", value=date.today(), format="DD/MM/YYYY",
                                      key=K + "date",
                                      help="Sert à vérifier que les commandes en cours arriveront à temps.")
        gestions = p3.multiselect("Codes Gestion du périmètre", GESTIONS_PROPOSEES, default=GESTIONS_DEFAUT,
                                  key=K + "gestions", placeholder="Choisir les codes Gestion",
                                  help="Seuls ces codes entrent dans l'analyse principale ; "
                                       "les autres sont listés en annexe.")

        c1, c2, c3 = st.columns(3)
        with c1:
            if etude == ETUDE_CLASSIQUE:
                f_besoin = st.file_uploader(f"① {sio.FICHIER_BESOINS}", type=["xlsx", "xlsm"],
                                            key=K + "besoin_classique")
            else:
                f_besoin = st.file_uploader(f"① {sio.FICHIER_ASREQ} (.xlsm, feuille « Ordered »)",
                                            type=["xlsm", "xlsx"], key=K + "besoin_asreq")
            _liste_colonnes(etude)
        with c2:
            f_stock = st.file_uploader(f"② {sio.FICHIER_STOCK}", type=["xlsx", "xlsm"], key=K + "stock_file")
            _liste_colonnes("stock")
        with c3:
            f_cmd = st.file_uploader(f"③ {sio.FICHIER_COMMANDES}", type=["xlsx", "xlsm"], key=K + "cmd_file")
            _liste_colonnes("commandes")
    return etude, date_chantier, gestions, f_besoin, f_stock, f_cmd


def _figure_actions(m_scope: pd.DataFrame):
    # « Hors périmètre » est exclu : par construction il n'y en a pas dans le périmètre.
    codes = [c for c in tf.ACTION_ORDRE if c != "hors_perimetre"]
    counts = m_scope["ACTION_CODE"].value_counts().reindex(codes, fill_value=0)
    fig = go.Figure(go.Bar(
        x=counts.values,
        y=[tf.ACTION_LABELS[c].split(" ", 1)[1] for c in codes],
        orientation="h",
        marker_color=[COLORS[tf.ACTION_TONES[c]] for c in codes],
        text=counts.values,
        textposition="outside",
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x} référence(s)<extra></extra>",
    ))
    ui.style_figure(fig, height=340)
    fig.update_layout(showlegend=False, bargap=0.35)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(title_text="Nombre de références", rangemode="tozero")
    return fig


def _bouton_export(data: bytes, cle: str) -> None:
    st.download_button("⬇️ Télécharger l'analyse (Excel)", data=data, file_name=sio.nom_export(TAB_ID),
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=K + cle, width="content")


def render() -> None:
    ui.page_intro(
        "Stock par chantier — GEAV",
        TAB_DESCRIPTION,
        [f"{sio.FICHIER_BESOINS} ou {sio.FICHIER_ASREQ}", sio.FICHIER_STOCK, sio.FICHIER_COMMANDES],
    )
    etude, date_chantier, gestions, f_besoin, f_stock, f_cmd = _bloc_import()

    fichiers = [(f_besoin, sio.FICHIER_BESOINS if etude == ETUDE_CLASSIQUE else sio.FICHIER_ASREQ),
                (f_stock, sio.FICHIER_STOCK), (f_cmd, sio.FICHIER_COMMANDES)]
    if not all(f for f, _ in fichiers):
        etapes = [("✅ " if f else "") + f"<b>{nom}</b>" + (f" — {f.name}" if f else " — à importer")
                  for f, nom in fichiers]
        ui.empty_state("Importez vos fichiers pour lancer l'analyse",
                       "Les trois fichiers sont nécessaires. Ils restent sur votre poste : "
                       "rien n'est envoyé sur un serveur.", etapes)
        return
    if not gestions:
        ui.callout("Sélectionnez au moins un <b>code Gestion</b> pour définir le périmètre de l'analyse.",
                   "warn", "⚠️")
        return

    try:
        with st.spinner("Lecture et croisement des fichiers…"):
            besoin, feuille_b = _besoins(f_besoin.getvalue(), etude)
            stock, feuille_s = _stock(f_stock.getvalue())
            commandes, feuille_c = _commandes(f_cmd.getvalue())
            m = _croiser(besoin, stock, commandes, tuple(sorted(gestions)), date_chantier)
    except ValueError as exc:  # ColonneIntrouvable, FichierIllisible
        ui.callout(f"<b>Import impossible.</b> {exc}", "ko", "⛔")
        return

    st.caption(f"Feuilles détectées — besoins : **{feuille_b}** · état du stock : **{feuille_s}** · "
               f"commandes : **{feuille_c}** · analyse du {date.today():%d/%m/%Y}")

    m_scope = m[m["gestion_in_scope"]].copy()
    s = tf.synthese_geav(m_scope)
    export = _export(m, m_scope, {"etude": etude, "date": date_chantier, "gestions": sorted(gestions)})

    # ---- Synthèse ----
    with ui.section(f"{TAB_ID}_synthese", "2 · Synthèse",
                    f"Étude {etude} · {len(m)} référence(s) au total, {s['n_total']} dans le périmètre"):
        j = tf.jours_avant(date_chantier, date.today())
        statut = (ui.chantier_badge("À venir", j) if j > 0
                  else ui.badge(f"Début le {date_chantier:%d/%m/%Y}" + (" (aujourd'hui)" if j == 0 else ""), "muted"))
        echeance = f"avant le {date_chantier:%d/%m/%Y}"
        if s["n_commander"] or s["n_relance"]:
            urgentes = f" dont {s['n_relance_urgente']} urgente(s)" if s["n_relance_urgente"] else ""
            ui.callout(
                f"Chantier du <b>{date_chantier:%d/%m/%Y}</b> {statut}<br>"
                f"<b>{s['n_commander']} référence(s) à commander</b> ({s['qty_a_commander']} unités) et "
                f"<b>{s['n_relance']} relance(s) fournisseur</b>{urgentes} {echeance}.",
                "ko" if s["n_commander"] else "warn", "📌")
        else:
            ui.callout(f"Chantier du <b>{date_chantier:%d/%m/%Y}</b> {statut}<br>"
                       "Aucune commande ni relance à lancer sur le périmètre.", "ok", "✅")
        if s["n_risque"]:
            risques = m_scope.loc[m_scope["RISK_CLASS"], "PN"].unique()
            extrait = ", ".join(risques[:5]) + ("…" if len(risques) > 5 else "")
            ui.callout(f"<b>{s['n_risque']} référence(s) classe 8/9</b> : pièces critiques, vérifier "
                       f"délais et stocks en priorité. {extrait}", "accent", "🚨")

        ui.kpi_grid([
            ui.kpi_card("Références (périmètre)", s["n_total"], f"{len(m) - s['n_total']} hors périmètre"),
            ui.kpi_card("À commander", s["n_commander"], f"{s['qty_a_commander']} unités", "ko"),
            ui.kpi_card("À relancer", s["n_relance"], f"dont {s['n_relance_urgente']} urgente(s)", "warn"),
            ui.kpi_card("En cours de livraison", s["n_en_cours"], "PSD avant le chantier", "info"),
            ui.kpi_card("Stock suffisant", s["n_ok"], "aucune action", "ok"),
        ])
        _bouton_export(export, "export_haut")

    # ---- Actions à lancer ----
    actions = tf.actions_a_lancer(m_scope)
    with ui.section(f"{TAB_ID}_actions", f"3 · Actions à lancer ({len(actions)})",
                    "Du plus urgent au moins urgent : classe 8/9, commandes à passer, relances, PN à vérifier."):
        if actions.empty:
            ui.callout("Aucune action à lancer : le besoin du périmètre est couvert.", "ok", "✅")
        else:
            st.dataframe(tableau(actions), hide_index=True, column_config=COLUMN_CONFIG,
                         height=min(38 + 35 * len(actions), 420), key=K + "actions_df")
        if s["n_inconnu"]:
            st.caption(f"❓ {s['n_inconnu']} PN introuvable(s) dans l'État du stock : à vérifier manuellement "
                       "(erreur de saisie, pièce obsolète ?).")

    # ---- Répartition + tableau croisé ----
    with ui.section(f"{TAB_ID}_detail", "4 · Détail du périmètre",
                    f"Codes Gestion : {', '.join(str(g) for g in sorted(gestions))}"):
        st.plotly_chart(_figure_actions(m_scope), config=ui.PLOTLY_CONFIG, key=K + "fig_actions")

        f1, f2 = st.columns([1, 2])
        recherche = f1.text_input("🔎 Rechercher un PN", key=K + "recherche")
        filtre = f2.multiselect("Filtrer par action", options=tf.ACTION_ORDRE,
                                format_func=lambda c: tf.ACTION_LABELS[c], key=K + "filtre_action",
                                placeholder="Toutes les actions")
        vue = m_scope
        if recherche:
            vue = vue[vue["PN"].str.contains(recherche.strip().upper(), na=False, regex=False)]
        if filtre:
            vue = vue[vue["ACTION_CODE"].isin(filtre)]
        vue = vue.sort_values("Qty_a_commander", ascending=False, kind="stable")
        st.markdown(f"**{len(vue)} référence(s)** correspondant aux critères")
        st.dataframe(tableau(vue), hide_index=True, column_config=COLUMN_CONFIG, height=440,
                     key=K + "detail_df")

        with st.expander(f"📎 Annexe — toutes les références ({len(m)}), y compris hors périmètre"):
            annexe = m.sort_values("Qty_a_commander", ascending=False, kind="stable")
            st.dataframe(tableau(annexe), hide_index=True, column_config=COLUMN_CONFIG,
                         key=K + "annexe_df")
        _bouton_export(export, "export_bas")
        st.caption("L'export contient les feuilles Synthèse, Actions à lancer, Détail (périmètre complet, "
                   "sans les filtres ci-dessus) et Annexe, surlignées par action.")

    _aide()


def _aide() -> None:
    with st.expander("📖 Règles de calcul et légende des actions"):
        st.markdown(f"""
**Croisement** (clé : PN en majuscules, espaces de début et de fin retirés)

1. Besoins chantier + État du stock → stock sur étagère, quantité en commande, gestion, agent appro.
2. + Commandes (SAP) → n° de commande, acheteur, fournisseur, **PSD la plus proche** (à défaut : date de
   livraison demandée). La gestion du fichier Commandes fait foi sur celle de l'État du stock.
3. Les doublons du fichier besoins sont **additionnés** par PN.

**Quantités**

| Variable | Formule |
|---|---|
| Déficit | max(0, QTY GEAV − QTY en stock) |
| QTY à commander | max(0, Déficit − QTY en cmd) |

**Action recommandée** (la première règle vérifiée l'emporte)

| Statut | Condition |
|---|---|
| {tf.ACTION_LABELS['inconnu']} | PN absent de l'État du stock |
| {tf.ACTION_LABELS['hors_perimetre']} | code Gestion hors du périmètre sélectionné (annexe) |
| {tf.ACTION_LABELS['commander']} | QTY à commander > 0 (avec relance si une commande existe déjà) |
| {tf.ACTION_LABELS['ok']} | Déficit = 0 |
| {tf.ACTION_LABELS['relancer']} | déficit couvert par une commande sans PSD (ou PSD {tf.ANNEE_PSD_NON_FOURNIE} = non fournie) |
| {tf.ACTION_LABELS['relancer_urgent']} | PSD postérieure à la date de début du chantier |
| {tf.ACTION_LABELS['en_cours']} | PSD avant ou le jour du début du chantier |

Les références **classe 8 ou 9** (fichier Commandes ou État du stock) sont préfixées
« 🚨 CLASSE 8/9 — PRIORITÉ » et remontent en tête des actions.
""")
