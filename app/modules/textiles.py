"""Onglet « Textile cabine » : stock, consommation, activité et commandes des références textile.

Repris du dashboard Textile (streamlit_textile_dashboard.py + textile_analytics.py), sur trois
imports : État du stock, Commandes (SAP), Références textile.
"""

from datetime import date

import pandas as pd
import streamlit as st

from core import cache, charts
from core import components as ui
from core import io as sio
from core import textile as tx
from core.style import COLORS

TAB_ID = "textiles"
TAB_LABEL = "Textile cabine"
TAB_ICON = "🧵"
TAB_DESCRIPTION = "Stock, consommation, commandes et retards fournisseurs des ceintures, housses, mousses et rideaux."

K = f"{TAB_ID}__"
SECTIONS = ["Synthèse", "Commandes", "Fournisseurs", "Consommation"]
ICONES = {"Synthèse": "📊", "Commandes": "📦", "Fournisseurs": "🏭", "Consommation": "📈"}
TOUTES = "Toutes"

COLONNES_ATTENDUES = {
    "stock": [("PNR", "", True), ("QTE SUR ÉTAGÈRE", "", True), ("QTE EN CDE", "", False), ("DESCRIPTION, CCN", "", False),
              ("QTE CONSO 12M / 18M / 24M", "consommation glissante", False), ("QTE CONSO <année>", "ex. 2021 à 2025", False),
              ("Dernier PU (achat) Euros", "valorisation", False), ("DATE DERNIERE CONSO", "2001 = jamais consommé", False),
              ("B/O, RP, EOQ, TDD", "", False)],
    "commandes": [("PN", "", True), ("Commande", "", True), ("Fournisseur, Code fournisseur", "nom retrouvé par le code", False),
                  ("Date d'émission de la commande", "", False), ("Date de livraison demandée / promise", "2001, 2030+ : sans date ; 2049 : BFE", False),
                  ("Quantité restant à livrer", "", False)],
    "references": [("pn", "feuille « PN Catalog »", True), ("equipment", "CEINTURE, HOUSSE, MOUSSE, RIDEAUX", True),
                   ("description, ccn", "", False)],
}

COL_RELANCES = {"Statut commande": "Statut", "Fournisseur": "Fournisseur", "Commande": "Commande", "PNR": "PN",
                "REF_Equipement": "Catégorie", "Date livraison demandee": "Demandée", "Date livraison promise": "Promise",
                "Jours de retard": "Retard (j)", "Qte restante": "Reste à livrer", "Code acheteur": "Acheteur"}
CFG = {
    "Demandée": st.column_config.DateColumn("Demandée", format="DD/MM/YYYY"),
    "Promise": st.column_config.DateColumn("Promise", format="DD/MM/YYYY"),
    "Émise": st.column_config.DateColumn("Émise", format="DD/MM/YYYY"),
    "Retard (j)": st.column_config.NumberColumn("Retard (j)", format="%d"),
    "Reste à livrer": st.column_config.NumberColumn("Reste à livrer", format="%d"),
    "Valeur stock (€)": st.column_config.NumberColumn("Valeur stock (€)", format="%.0f €"),
    "Valeur en commande (€)": st.column_config.NumberColumn("Valeur en commande (€)", format="%.0f €"),
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


def _filtrer(s_all, o_all, cat):
    s = s_all if cat == TOUTES else s_all[tx.categorie(s_all) == cat]
    o = o_all if cat == TOUTES or o_all.empty else o_all[tx.categorie(o_all) == cat]
    return s, o


@st.cache_resource(show_spinner=False, max_entries=4)
def _export(stock: bytes, cmd: bytes | None, ref: bytes | None, today: date, seulement_textile: bool, cat: str) -> bytes:
    s, o = _filtrer(*_tables(stock, cmd, ref, today, seulement_textile), cat)
    rel = tx.relances(o) if len(o) else o
    return sio.exporter_excel({
        "Synthèse catégories": tx.resume_categories(s, o),
        "Relances fournisseurs": rel,
        "Stock": s,
        "Commandes": o,
        "Retards": tx.tableau_retards(o),
        "Conso catégories": tx.conso_par_categorie(s),
        "Délais fournisseurs": tx.delais_fournisseurs(o),
    }, couleurs_lignes={"Relances fournisseurs": rel["Statut commande"].map(
        {"En retard": "F8D7DA", "Sans date promise": "FCE4D6", "En attente BFE": "E9DDF8"}).tolist()})


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------
def _bloc_import():
    with ui.section(f"{TAB_ID}_import", "Import et paramètres"):
        c1, c2, c3 = st.columns(3)
        with c1:
            f_stock = ui.fichier(sio.FICHIER_STOCK, "commun__stock", ["xlsx", "xlsm"], COLONNES_ATTENDUES["stock"])
        with c2:
            f_cmd = ui.fichier(sio.FICHIER_COMMANDES, "commun__commandes", ["xlsx", "xlsm"], COLONNES_ATTENDUES["commandes"])
        with c3:
            f_ref = ui.fichier(sio.FICHIER_REFERENCES, K + "references", ["xlsx", "xlsm"], COLONNES_ATTENDUES["references"])
        p1, p2, _ = st.columns([1, 1.4, 1.6])
        today = p1.date_input("Date de référence", value=date.today(), format="DD/MM/YYYY", key=K + "date", persist_state="page",
                              help="Date des données : âge des commandes, retards, mois du planning.")
        p2.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
        seul = p2.toggle("Uniquement les PN du catalogue textile", value=True, key=K + "seul", persist_state="page")
    return f_stock, f_cmd, f_ref, today, seul


def render() -> None:
    ui.hero(TAB_ICON, "Textile cabine", TAB_DESCRIPTION)
    f_stock, f_cmd, f_ref, today, seul = _bloc_import()
    if not f_stock:
        with ui.section(f"{TAB_ID}_vide", "Analyse"):
            ui.empty_state("Importez l'État du stock", "Les commandes et les références textile enrichissent ensuite l'analyse.",
                           [(sio.FICHIER_STOCK, bool(f_stock)), (sio.FICHIER_COMMANDES, bool(f_cmd)), (sio.FICHIER_REFERENCES, bool(f_ref))])
        return
    cle = (f_stock[1], f_cmd[1] if f_cmd else None, f_ref[1] if f_ref else None, today, seul)
    try:
        s_all, o_all = _tables(*cle)
    except ValueError as exc:
        ui.callout(f"<b>Import impossible.</b> {exc}", "ko", "⛔")
        return
    if not f_ref or not f_cmd:
        manquants = " et ".join(n for f, n in [(f_cmd, sio.FICHIER_COMMANDES), (f_ref, sio.FICHIER_REFERENCES)] if not f)
        ui.callout(f"Analyse partielle : ajoutez <b>{manquants}</b> pour la compléter.", "warn", "⚠️")
    if s_all.empty:
        ui.callout("Aucun PN du catalogue textile dans l'État du stock. Vérifiez les fichiers ou désactivez le filtre catalogue.", "warn", "⚠️")
        return


    # Sous-onglets + filtre catégorie : seule la section choisie est calculée et affichée.
    n1, n2 = st.columns([2.2, 1.6], vertical_alignment="bottom")
    with n1:
        section = ui.sous_onglets(K + "section", SECTIONS, ICONES)
    with n2, st.container(key="s360pills_" + K + "cat"):
        cats = [TOUTES] + tx.categories(s_all)
        cat = st.pills("Catégorie", cats, default=TOUTES, key=K + "cat", label_visibility="collapsed", persist_state="page") or TOUTES
    s, o = _filtrer(s_all, o_all, cat)
    st.session_state[K + "cle_export"] = (*cle, cat)

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
            ui.graphe(charts.parts(poids, tx.CATEGORY_COLORS, "Poids de chaque catégorie", afficher="pourcent"))
        with b:
            cats = tx.categories(s)
            g = s.assign(c=tx.categorie(s)).groupby("c")[["Valeur stock (€)", "Valeur en commande (€)", "Valeur stock dormant (€)"]].sum().reindex(cats)
            part = (g["Valeur stock dormant (€)"] / g["Valeur stock (€)"].where(g["Valeur stock (€)"] > 0) * 100)
            ui.graphe(charts.barres(cats, {"Valeur du stock": g["Valeur stock (€)"], "Valeur en commande": g["Valeur en commande (€)"]},
                                    {"Valeur du stock": COLORS["navy_2"], "Valeur en commande": "#F4A259"},
                                    ligne={"Part dormante": part}, fmt=charts.euros, fmt_ligne=charts.pourcent,
                                    titre="Valeur du stock et part dormante", hauteur=250))
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
                                    titre="Stock, commandes et back-orders (qté)", hauteur=230))
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
            em = tx.commandes_emises_par_mois(o, today)
            ui.graphe(charts.barres(em.index, {c: em[c] for c in em.columns}, tx.CATEGORY_COLORS, empile=True,
                                    titre="Lignes émises par mois", hauteur=230) if len(em) else charts.vide())
    with ui.section(f"{TAB_ID}_liv", "Livraisons et retards"):
        pl = tx.planning_livraisons(o, today)
        ui.graphe(charts.barres(pl.index, {c: pl[c] for c in pl.columns},
                                {"Avec date promise": COLORS["navy_2"], "Sans date promise (date demandée)": COLORS["warn"]},
                                empile=True, titre="Planning des livraisons (lignes par mois)", hauteur=230))
        a, b = st.columns([1.4, 1], gap="large")
        with a:
            pr = tx.profondeur_retards(o)
            ui.graphe(charts.barres(pr.index, {c: pr[c] for c in pr.columns}, tx.CATEGORY_COLORS, empile=True,
                                    titre="Profondeur des retards (lignes)", hauteur=230) if len(pr.columns) else charts.vide("Aucune commande en retard"))
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
                                    ligne={"% cumulé": cum.values}, fmt_ligne=charts.pourcent, titre="Volume de lignes (Pareto)", hauteur=240))
        with b:
            late = o[o["Statut commande"] == "En retard"]
            if late.empty:
                ui.graphe(charts.vide("Aucune commande en retard"))
            else:
                g = late.groupby("Fournisseur").agg(n=("PNR", "size"), j=("Jours de retard", "mean")).sort_values("n", ascending=False).head(12)
                ui.graphe(charts.barres(g.index, {"Lignes en retard": g["n"]}, {"Lignes en retard": COLORS["ko"]},
                                        ligne={"Retard moyen (j)": g["j"]}, fmt_ligne=lambda v: f"{v:.0f} j",
                                        titre="Fournisseurs avec le plus de retards", hauteur=240))
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
                                    for _, r in sel.iterrows()}, {}, hauteur=150))

