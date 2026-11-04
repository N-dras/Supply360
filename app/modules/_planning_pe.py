"""Sous-onglets « Avancement PE » et « Forecast » de l'onglet PE mousses : avancement de la politique d'entretien
des mousses de sièges (fichier PE mousses mensuel) et forecast des commandes (12 / 24 / 36 mois), par PN et par
fournisseur.

Rendu seulement : les calculs sont dans core/pe.py. Fichier préfixé « _ » : ce n'est pas un onglet du registre.
"""

import re
from datetime import date

import pandas as pd
import streamlit as st

from core import charts
from core import components as ui
from core import io as sio
from core import pe
from core.style import COLORS

K = "pe_mousses__"
ELEMENTS = ["J · Assise", "J · Dossier", "W · Assise", "Y · Assise"]
COULEURS_ELEMENTS = {"J · Assise": COLORS["navy_2"], "J · Dossier": "#7FA7E0", "W · Assise": "#2A9D8F", "Y · Assise": "#F4A259"}
CFG = {
    "Dernier remplacement": st.column_config.DateColumn("Dernier remplacement", format="DD/MM/YYYY"),
    "Échéance": st.column_config.DateColumn("Échéance", format="DD/MM/YYYY"),
    "Prochaine visite": st.column_config.DateColumn("Prochaine visite", format="DD/MM/YYYY"),
    "Date prévue": st.column_config.DateColumn("Date prévue", format="MM/YYYY"),
    "Âge (mois)": st.column_config.NumberColumn("Âge (mois)", format="%d"),
    "Rupture sans commande": st.column_config.DateColumn("Rupture sans commande", format="MM/YYYY",
                                                        help="Premier mois où le stock devient négatif sans nouvelle commande"),
    "Prix (€)": st.column_config.NumberColumn("Prix (€)", format="%.0f €"),
    "Valeur (€)": st.column_config.NumberColumn("Valeur (€)", format="%.0f €"),
    "Stock": st.column_config.NumberColumn("Stock", format="%d"),
    "En commande": st.column_config.NumberColumn("En commande", format="%d"),
    "Stock de sécurité": st.column_config.NumberColumn("Stock de sécurité", format="%d",
                                                      help="% des avions de chaque flotte qui utilisent le PN (paramètre) × quantité par avion"),
    "Besoin": st.column_config.NumberColumn("Besoin", format="%d", help="Mousses à remplacer sur l'horizon"),
    "À commander": st.column_config.NumberColumn("À commander", format="%d",
                                                help="Besoin + stock de sécurité − stock − commandes en cours (toutes, déjà passées)"),
    "À avancer": st.column_config.NumberColumn("À avancer", format="%d",
                                              help="Commandes en cours promises après le mois où elles sont nécessaires : à relancer"),
    "Avant": st.column_config.DateColumn("Avant", format="MM/YYYY", help="Mois où la commande en cours est nécessaire"),
    "Total": st.column_config.NumberColumn("Total", format="%d"),
}
ICONES_STATUT = {"En retard": "🔴 En retard", "Délai toléré": "🟠 Délai toléré", "À faire < 3 mois": "🟡 À faire < 3 mois",
                 "À faire < 12 mois": "🔵 À faire < 12 mois", "OK": "🟢 OK"}


# --------------------------------------------------------------------------
# Paramètres (popover du bloc d'import)
# --------------------------------------------------------------------------
def parametres() -> pe.ParamsPE:
    """Champs des paramètres du Planning PE (placés dans le popover « Paramètres » du bloc d'import)."""
    d = pe.ParamsPE()
    st.markdown("**Cycle de remplacement (mois)** · 0 = jamais remplacé")
    cols = st.columns(3)
    cycles = []
    for i, (cl, comp, mois) in enumerate(d.cycles):
        v = cols[i % 3].number_input(f"{cl} · {comp}", 0, 240, mois, 6, key=f"{K}cycle_{cl}_{comp}", persist_state="page")
        cycles.append((cl, comp, int(v)))
    a, b, c = st.columns(3)
    tol = a.number_input("Délai toléré après l'échéance (mois)", 0, 24, d.tolerance_mois, key=K + "tol", persist_state="page",
                         help="Échéance dépassée depuis moins longtemps : « Délai toléré » ; au-delà : « En retard ».")
    ratio = b.number_input("Stock de sécurité (% des avions)", 0, 50, int(d.securite_ratio * 100), 5, key=K + "ss",
                           persist_state="page", help="Par flotte et par PN. 0 % : aucun stock de sécurité.")
    mini = c.number_input("Minimum d'avions de sécurité", 0, 10, d.securite_min, key=K + "ssmin", persist_state="page",
                          help="Par flotte, si le stock de sécurité n'est pas à 0 %.")
    return pe.ParamsPE(cycles=tuple(cycles), tolerance_mois=int(tol), securite_ratio=ratio / 100, securite_min=int(mini))


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------
def _element(classe, composant):
    return classe.astype(str) + " · " + composant.astype(str)


def _mois_label(m) -> str:
    return pd.Timestamp(m).strftime("%m/%y")


CLASSES_LIBELLES = {"J": "J · Business", "W": "W · Premium", "Y": "Y · Économie"}


def _filtres(cal: pd.DataFrame) -> tuple[list, list, list]:
    """Barre « Périmètre » : flotte, classe et élément (assise / dossier) à afficher."""
    with ui.barre_perimetre("pe"):
        a, b, c = st.columns([1.5, 1.2, 0.9], gap="medium")
        flottes = sorted(cal["Flotte"].dropna().unique())
        f = ui.choix_multiple(a, "Flotte", flottes, K + "flottes_v2", "Toutes")
        cl = ui.choix_multiple(b, "Classe", pe.CLASSES, K + "classes_v2", "Toutes", CLASSES_LIBELLES)
        co = ui.choix_multiple(c, "Assise / dossier", pe.COMPOSANTS, K + "composants_v2", "Tous")
    return f, cl, co


def render(res: dict, today: date, avec_pieces: bool, partie: str = "avancement") -> None:
    """`partie` : « avancement » (KPI, calendrier par avion) ou « forecast » (mousses à commander, fournisseurs)."""
    cal = res["cal"]
    flottes, classes, composants = _filtres(cal)
    c = cal[cal["Flotte"].isin(flottes) & cal["Classe"].isin(classes) & cal["Composant"].isin(composants)]
    if partie == "avancement":
        _avancement(c, res["date_ref"], today)
        with st.popover("Règles de calcul"):
            st.markdown(REGLES_PE)
        _calendrier(c, today)
        return
    if not avec_pieces or res["ev"].empty:
        ui.callout("Ajoutez <b>textile_all_parts</b> (Pièces par avion) pour la prévision des mousses à commander.", "info", "📦")
        return
    ev = res["ev"]
    ev = ev[ev["Flotte"].isin(flottes) & ev["Classe"].isin(classes) & ev["Composant"].isin(composants)]
    pns = set(ev["PN"])
    synth, long = res["synth"][res["synth"]["PN"].isin(pns)], res["long"][res["long"]["PN"].isin(pns)]
    horizon = _forecast(ev, synth, long, today)
    _forecast_fournisseur(ev, synth, long, today, horizon)
    _exports_controles(res, c, ev, synth, long, horizon)


CLASSE_INFO = ("Une classe = les mousses d'une classe (J, W ou Y) d'un avion, assise ou dossier. Exemple : l'A350 F-HTYA compte "
               "4 classes suivies (assise J, dossier J, assise W, assise Y). Les dossiers W et Y ne sont jamais remplacés.")


def _nom_element(classe, composant) -> pd.Series:
    """« Assise J », « Dossier J »… (libellé lisible d'une classe d'un avion)."""
    return composant.astype(str) + " " + classe.astype(str)


def _avancement(c: pd.DataFrame, date_ref, today):
    auj = pd.Timestamp(today)
    n = len(c)
    st_ = c["Statut"].astype(str)
    retard, tolere, trois = (st_ == "En retard").sum(), (st_ == "Délai toléré").sum(), (st_ == "À faire < 3 mois").sum()
    nb_avions = c["Immatriculation"].nunique()
    avions_retard = c.loc[st_ == "En retard", "Immatriculation"].nunique()
    visites = c.loc[c["Prochaine visite"] <= auj + pd.DateOffset(months=3), "Immatriculation"].nunique()
    conformite = (1 - retard / n) * 100 if n else 100
    with ui.section("pe_mousses_pe_avancement", "Avancement de la PE mousses",
                    f"{nb_avions} avions · {n} classes suivies",
                    info=f"{CLASSE_INFO} Âges au {pd.Timestamp(date_ref):%d/%m/%Y} (fichier PE mousses), statut au {auj:%d/%m/%Y}.",
                    carte=False):
        if retard:
            ui.callout(f"<b>{retard} classes en retard</b> sur <b>{avions_retard} avions</b> : à rattraper en priorité "
                       "(prévues dès ce mois-ci dans la Prévision).", "ko", "🔴")
        ui.kpi_grid([
            ui.kpi_card("Conformité PE", f"{conformite:.0f} %", f"{n - retard} classes sur {n} à l'heure",
                        "ok" if conformite >= 90 else "warn" if conformite >= 70 else "ko"),
            ui.kpi_card("Classes en retard", charts.entier(retard), "échéance et délai toléré dépassés", "ko"),
            ui.kpi_card("Avions avec un retard", charts.entier(avions_retard), f"sur {nb_avions} avions suivis", "ko"),
            ui.kpi_card("Classes en délai toléré", charts.entier(tolere), "échéance dépassée, encore tolérée", "warn"),
            ui.kpi_card("Classes à faire < 3 mois", charts.entier(trois), "échéance dans les 3 prochains mois", "warn"),
            ui.kpi_card("Avions en visite < 3 mois", charts.entier(visites), "visite datée dans le fichier", "info"),
        ])
        a, b = st.columns(2, gap="large")
        with a:
            t = c.assign(L=c["Flotte"].astype(str) + " · " + _nom_element(c["Classe"], c["Composant"]))
            t = t.groupby(["L", "Statut"], observed=False).size().unstack(fill_value=0)
            t = t.reindex(columns=[s for s in pe.STATUTS if s in t.columns])
            t = t[t.sum(axis=1) > 0]
            ui.graphe(charts.parts(t, pe.STATUT_COULEURS, "Statut par flotte et classe"), "Nombre d'avions dans chaque statut")
        with b:
            debut = auj.to_period("M").start_time
            mois = pd.date_range(debut, periods=12, freq="MS")
            d = c.assign(E=_element(c["Classe"], c["Composant"]))
            d["Case"] = d["Date prévue"].dt.to_period("M").dt.start_time
            retard_b = d["Origine date prévue"] == "Mois en cours (retard)"
            cats = ["À rattraper"] + [_mois_label(m) for m in mois]
            series = {}
            for e in ELEMENTS:
                x = d[d["E"] == e]
                if x.empty:
                    continue
                cnt = x[~retard_b.loc[x.index]].groupby("Case").size()
                classe, comp = e.split(" · ")
                series[f"{comp} {classe}"] = [int(retard_b.loc[x.index].sum())] + [int(cnt.get(m, 0)) for m in mois]
            couleurs = {f"{e.split(' · ')[1]} {e.split(' · ')[0]}": c_ for e, c_ in COULEURS_ELEMENTS.items()}
            ui.graphe(charts.barres(cats, series, couleurs, empile=True, hauteur=260,
                                    titre="Classes à remplacer, mois par mois")
                      if series else charts.vide("Aucun remplacement prévu"))


def _calendrier(c: pd.DataFrame, today):
    auj = pd.Timestamp(today)
    with ui.section("pe_mousses_pe_calendrier", "Calendrier des remplacements",
                    "Classes à remplacer, par avion et par mois",
                    info="Survolez une case pour voir les classes concernées. « À rattraper » : échéance déjà dépassée. Sinon, le mois de la prochaine visite datée de l'avion, "
                         "à défaut celui de l'échéance PE."):
        debut = auj.to_period("M").start_time
        mois = pd.date_range(debut, periods=24, freq="MS")
        d = c.copy()
        d["Col"] = d["Date prévue"].dt.to_period("M").dt.start_time.map(_mois_label)
        d.loc[d["Origine date prévue"] == "Mois en cours (retard)", "Col"] = "À rattraper"
        d["Ligne"] = d["Immatriculation"] + " · " + d["Flotte"].astype(str)
        d["Élément"] = _nom_element(d["Classe"], d["Composant"])
        cols = ["À rattraper"] + [_mois_label(m) for m in mois]
        x = d[d["Col"].isin(cols)]
        t = x.groupby(["Ligne", "Col"]).size().unstack(fill_value=0).reindex(columns=cols, fill_value=0)
        if t.empty:
            ui.graphe(charts.vide("Aucun remplacement sur les 24 prochains mois"))
        else:
            ordre = x.groupby("Ligne")["Date prévue"].min().sort_values().index
            quoi = x.groupby(["Ligne", "Col"])["Élément"].agg(lambda s: ", ".join(sorted(s))).unstack()
            ui.graphe(charts.chaleur(t.reindex(ordre), libelle="classe(s)", hauteur_max="34rem", details=quoi))
        _detail_avions(c)


@st.fragment
def _detail_avions(c: pd.DataFrame):
    with st.popover(f"Détail par avion et par classe ({len(c)})", width="content"):
        d = c
        t = pd.DataFrame({
            "Statut": d["Statut"].astype(str).map(ICONES_STATUT), "Immatriculation": d["Immatriculation"], "Flotte": d["Flotte"],
            "Version": d["Version cabine"], "Classe": d["Classe"], "Assise / dossier": d["Composant"],
            "Âge (mois)": d["Âge aujourd'hui (mois)"].round(0), "Âge minimum ?": d["Âge"].map(lambda v: "oui" if v else ""),
            "Dernier remplacement": d["Dernier remplacement"], "Échéance": d["Échéance"], "Prochaine visite": d["Prochaine visite"],
            "Date prévue": d["Date prévue"], "Origine": d["Origine date prévue"], "Visite liée": d["Visite liée"],
        })
        ui.tableau(t, column_config=CFG, width=1250, height=440)


def _horizon() -> int:
    h = st.segmented_control("Horizon", [f"{h} mois" for h in pe.HORIZONS], default="12 mois", key=K + "horizon",
                             required=True, persist_state="page", label_visibility="collapsed")
    return int((h or "12 mois").split()[0])


def _forecast(ev, synth, long, today) -> int:
    """Prévision des mousses à commander : chiffres clés, quand (par mois), puis le détail par PN."""
    debut = pd.Timestamp(today).to_period("M").start_time
    with ui.section("pe_mousses_pe_forecast", "Prévision des mousses à commander", carte=False,
                    info="À commander = mousses à remplacer + stock de sécurité − stock − commandes déjà passées. "
                         "Les commandes en cours sont toujours déduites."):
        a, _ = st.columns([1, 2])
        with a:
            h = _horizon()
        fin = debut + pd.DateOffset(months=h)
        periode = f"{_mois_label(debut)} → {_mois_label(fin - pd.DateOffset(months=1))}"
        e = ev[ev["Mois"] < fin]
        lg = long[long["Mois"] < fin]
        besoin, rattrapage = e["Qté"].sum(), e.loc[e["Rattrapage du retard"], "Qté"].sum()
        a_cmd, valeur = lg["À livrer"].sum(), lg["Valeur à livrer (€)"].sum()
        fours = lg.loc[lg["À livrer"] > 0, "Fournisseur"].nunique()
        ui.kpi_grid([
            ui.kpi_card("Mousses à remplacer", charts.entier(besoin), f"{periode}, dont {charts.entier(rattrapage)} en retard", "navy", "layers"),
            ui.kpi_card("À commander", charts.entier(a_cmd), "en plus du stock et des commandes en cours", "ko", "cart"),
            ui.kpi_card("Valeur à commander", charts.euros(valeur), periode, "ko", "euro"),
            ui.kpi_card("Déjà disponibles", charts.entier(synth["Stock"].sum() + synth["En commande"].sum()),
                        f"{charts.entier(synth['Stock'].sum())} en stock + {charts.entier(synth['En commande'].sum())} en commande", "ok", "package"),
            ui.kpi_card("Fournisseurs", charts.entier(fours), "à qui commander", "violet", "truck"),
        ])
        avancer = synth[synth["À avancer (commandes en cours)"] > 0]
        if len(avancer):
            ui.callout(f"<b>{charts.entier(avancer['À avancer (commandes en cours)'].sum())} mousses déjà commandées arriveront trop tard</b> "
                       f"({len(avancer)} PN) : relancez le fournisseur plutôt que de recommander (colonne « À avancer » du tableau par PN).",
                       "warn", "📌")
    mois = pd.date_range(debut, periods=h, freq="MS")
    with ui.section("pe_mousses_pe_quand", "Mois par mois", periode, carte=False,
                    info="Le premier mois inclut les remplacements en retard."):
        g1, g2 = st.columns(2, gap="medium")
        with g1:
            x = e.assign(E=_element(e["Classe"], e["Composant"])).groupby(["Mois", "E"])["Qté"].sum().unstack(fill_value=0)
            x = x.reindex(index=mois, fill_value=0)
            series = {f"{k.split(' · ')[1]} {k.split(' · ')[0]}": x[k] for k in ELEMENTS if k in x.columns}
            couleurs = {f"{k.split(' · ')[1]} {k.split(' · ')[0]}": c_ for k, c_ in COULEURS_ELEMENTS.items()}
            ui.graphe(charts.barres(mois, series, couleurs, empile=True, temporel=True, hauteur=240, titre="Mousses à remplacer")
                      if series else charts.vide(), "Nombre de mousses à poser sur les avions, par classe")
        with g2:
            liv = lg.groupby("Mois")["À livrer"].sum().reindex(mois, fill_value=0)
            ui.graphe(charts.barres(mois, {"À recevoir": liv}, {"À recevoir": COLORS["ko"]}, temporel=True, hauteur=240,
                                    titre="Mousses à recevoir des fournisseurs"),
                      "Quantités à commander, au mois où elles doivent arriver (tous fournisseurs)")
    with ui.section("pe_mousses_pe_pn", "Par PN", "La plus grosse valeur à commander en premier",
                    info="Stock de sécurité : de quoi équiper 10 % des avions de chaque flotte (réglable dans Paramètres). "
                         "« À avancer » : mousses déjà commandées mais promises après le mois où elles sont nécessaires."):
        t = synth.assign(**{"Besoin": synth[f"Besoin {h} mois"], "À commander": synth[f"À commander {h} mois"],
                            "Valeur (€)": synth[f"Valeur {h} mois (€)"]})
        t = t.sort_values("Valeur (€)", ascending=False)
        cols = {"PN": "PN", "CCN": "CCN", "Désignation": "Désignation", "Classes": "Classe", "Composant": "Assise / dossier", "Flottes": "Flottes",
                "Fournisseur": "Fournisseur", "Prix unitaire (€)": "Prix (€)", "Stock": "Stock", "En commande": "En commande",
                "Stock de sécurité": "Stock de sécurité", "Besoin": "À remplacer", "À commander": "À commander", "Valeur (€)": "Valeur (€)",
                "À avancer (commandes en cours)": "À avancer", "À avancer avant": "Avant", "Rupture sans commande": "Rupture sans commande"}
        ui.tableau(t[[c for c in cols if c in t]].rename(columns=cols), column_config=CFG, height=min(38 + 35 * len(t), 420))
    return h


@st.fragment
def _forecast_fournisseur(ev, synth, long, today, h):
    debut = pd.Timestamp(today).to_period("M").start_time
    mois = pd.date_range(debut, periods=h, freq="MS")
    lg = long[long["Mois"].isin(mois)]
    v = lg.groupby("Fournisseur")["Valeur à livrer (€)"].sum().sort_values(ascending=False)
    if v.empty:
        return
    with ui.section("pe_mousses_pe_fournisseur", "Par fournisseur",
                    f"Commande sur {h} mois, à partager avec chaque fournisseur"):
        # Vue d'ensemble : tous les fournisseurs, par année
        qte_an = pe.par_annee(lg, mois, "Fournisseur").reindex(v.index)
        val_an = pe.par_annee(lg, mois, "Fournisseur", "Valeur à livrer (€)").reindex(v.index)
        annees = list(qte_an.columns)
        vue = pd.DataFrame(index=v.index)
        for an in annees:
            vue[f"{an} · qté"] = qte_an[an]
            vue[f"{an} · €"] = val_an[an]
        vue["Total · qté"], vue["Total · €"] = qte_an.sum(axis=1), val_an.sum(axis=1)
        cfg = {c: st.column_config.NumberColumn(c, format="%.0f €" if c.endswith("€") else "%d") for c in vue.columns}
        a, b = st.columns([1, 1.5], gap="large")
        with a:
            ui.graphe(charts.barres(annees, {"Valeur (€)": val_an.sum()}, {"Valeur (€)": COLORS["navy_2"]}, fmt=charts.euros,
                                    hauteur=220, titre="Valeur à commander par année (tous fournisseurs)",
                                    survol=[f"{charts.entier(q)} mousses" for q in qte_an.sum()]))
        with b:
            st.markdown("**Par fournisseur et par année**")
            ui.tableau(vue.reset_index(), column_config=cfg, height="content" if len(vue) <= 6 else 260)

        # Détail du fournisseur choisi
        libelles = {f: f"{f}  ·  {charts.euros(val)}" for f, val in v.items()}
        c1, c2 = st.columns([1.4, 1], vertical_alignment="center")
        f = c1.selectbox("Fournisseur", list(libelles), format_func=libelles.get, key=K + "fournisseur", persist_state="page",
                         label_visibility="collapsed")
        with c2:
            pas = st.segmented_control("Vue", ["Par année", "Par mois"], default="Par année", key=K + "vue_fournisseur",
                                       required=True, persist_state="page", label_visibility="collapsed") or "Par année"
        d = lg[lg["Fournisseur"] == f]
        a_livrer = d[d["À livrer"] > 0]
        premier = a_livrer["Mois"].min()
        ui.kpi_grid([
            ui.kpi_card("À commander", charts.entier(d["À livrer"].sum()), f"mousses sur {h} mois", "ko"),
            ui.kpi_card("Valeur", charts.euros(d["Valeur à livrer (€)"].sum()), "", "ko"),
            ui.kpi_card("PN", charts.entier(a_livrer["PN"].nunique()), "à livrer", "navy"),
            ui.kpi_card("Première livraison", f"{premier:%m/%Y}" if pd.notna(premier) else "—",
                        "dès que possible" if pd.notna(premier) and premier == debut else "", "warn"),
        ])
        piv = d.pivot_table(index="PN", columns="Mois", values="À livrer", aggfunc="sum", fill_value=0).reindex(columns=mois, fill_value=0)
        piv = piv[piv.sum(axis=1) > 0]
        an = pe.par_annee(d, mois).reindex(piv.index)
        top = list(piv.sum(axis=1).sort_values(ascending=False).index[:8])
        def _series(t):
            s = {pn: t.loc[pn] for pn in top}
            if len(t) > 8:
                s["Autres PN"] = t.drop(index=top).sum()
            return s
        if pas == "Par année":
            graphe = charts.barres(annees, _series(an), empile=True, hauteur=240, titre="Mousses à livrer par année et par PN")
            tab = an.copy()
        else:
            graphe = charts.barres(mois, _series(piv), empile=True, temporel=True, hauteur=240,
                                   titre="Mousses à livrer par mois et par PN")
            tab = piv.copy()
            tab.columns = [m_.strftime("%m/%Y") for m_ in tab.columns]
        ui.graphe(graphe if len(piv) else charts.vide("Rien à livrer"))
        prix = synth.set_index("PN")["Prix unitaire (€)"].reindex(tab.index).fillna(0)
        tab.insert(0, "Valeur (€)", piv.sum(axis=1) * prix)
        tab.insert(0, "Total", piv.sum(axis=1))
        tab.insert(0, "Désignation", synth.set_index("PN")["Désignation"].reindex(tab.index))
        tab = tab.reset_index()
        ui.tableau(tab, column_config=CFG, height="content" if len(tab) <= 8 else 320)
        par_mois = piv.copy()
        par_mois.columns = [m_.strftime("%m/%Y") for m_ in par_mois.columns]
        ui.telecharger(lambda: _export_fournisseur(f, an, par_mois, ev[ev["PN"].isin(piv.index)], synth), _nom_fichier(f"prevision_{f}"),
                       K + "export_fournisseur", label="Exporter la prévision du fournisseur (Excel)")


def _nom_fichier(base: str) -> str:
    return f"Supply360_{re.sub(r'[^A-Za-z0-9]+', '_', base).strip('_')}_{date.today():%Y%m%d}.xlsx"


def _export_fournisseur(f, an, par_mois, ev, synth) -> bytes:
    resume = synth[synth["PN"].isin(an.index)][["PN", "Désignation", "Composant", "Classes", "Prix unitaire (€)"]]
    resume = resume.assign(Total=resume["PN"].map(an.sum(axis=1)))
    resume["Valeur (€)"] = resume["Total"] * resume["Prix unitaire (€)"].fillna(0)
    avions = ev.assign(Mois=ev["Mois"].dt.strftime("%m/%Y"))[["PN", "Mois", "Immatriculation", "Flotte", "Classe", "Composant", "Qté"]]
    return sio.exporter_excel({"Commande globale": resume, "Par année": an.reset_index(), "Par mois": par_mois.reset_index(),
                               "Besoins par avion": avions})


REGLES_PE = """
**Échéance d'une mousse** = date du dernier remplacement + cycle de remplacement (Paramètres).
Exemple : remplacée en janvier 2024, cycle de 36 mois → à remplacer en janvier 2027.
Quand le fichier PE indique seulement « > 60 » mois, on prend 60 : l'échéance est la plus proche possible.

**Ce que veut dire chaque statut (aujourd'hui)**

| Statut | Ce que ça veut dire |
|---|---|
| **En retard** | Échéance dépassée de plus que le délai toléré (Paramètres) |
| **Délai toléré** | Échéance dépassée, mais encore dans le délai toléré |
| **À faire < 3 mois** | Échéance dans les 3 prochains mois |
| **À faire < 12 mois** | Échéance dans l'année |
| **OK** | Rien avant 12 mois |

**Date prévue du remplacement** : la prochaine visite connue de l'avion ; sinon l'échéance (ce mois-ci si elle est
dépassée). Ensuite, un remplacement à chaque cycle jusqu'à la fin de la période.

**Stock de sécurité d'une mousse** : de quoi équiper 10 % des avions de chaque flotte qui l'utilisent (au moins 1
avion ; réglable dans Paramètres). Exemple : 20 avions, 30 mousses par avion → 2 avions × 30 = **60 mousses**.

**À livrer chaque mois** : la quantité qui manque pour que le stock (stock + commandes en cours − remplacements
prévus) ne descende jamais sous le stock de sécurité.
"""


def _exports_controles(res, c, ev, synth, long, h):
    with ui.section("pe_mousses_pe_exports", "Exports et contrôles"):
        a, b = st.columns(2)
        with a:
            debut = long["Mois"].min()
            liv = long[(long["À livrer"] > 0) & (long["Mois"] < debut + pd.DateOffset(months=h))]
            feuilles = {
                "Avancement PE": c.drop(columns=["Âge exact"]).assign(Statut=c["Statut"].astype(str)),
                f"Prévision PN {h} mois": synth,
                "Livraisons à prévoir": liv[["Fournisseur", "PN", "Désignation", "Mois", "À livrer", "Valeur à livrer (€)"]],
                "Besoins par avion": ev,
            }
            ui.telecharger(lambda: sio.exporter_excel(feuilles), _nom_fichier("planning_PE"), K + "export_tout",
                           label="Exporter le planning PE complet (Excel)")
        with b, st.popover("Règles de calcul", width="stretch"):
            st.markdown(REGLES_PE)
        with b, st.popover("Contrôles des données", width="stretch"):
            nr, sans, absents = res["non_reconnues"], res["sans_pn"], res["pn_absents_stock"]
            age_min = int((~res["cal"]["Âge exact"]).sum())
            st.caption("Points à vérifier dans les fichiers importés.")
            st.markdown(f"- **{age_min}** classes dont l'âge n'est connu qu'en minimum (« > 60 », « > 108 » dans le fichier PE) : "
                        "leur échéance est calculée au plus tôt.")
            st.markdown(f"- **{len(sans)}** classes sans référence de mousse dans textile_all_parts (immatriculation, classe ou "
                        "introuvable) : elles ne sont pas dans la prévision.")
            if len(sans):
                ui.tableau(sans.assign(Statut=sans["Statut"].astype(str)), height=200)
            st.markdown(f"- **{len(nr)}** lignes MOUSSE de textile_all_parts non reconnues (ni assise « FOAM BOTTOM / BOTT », "
                        "ni dossier « FOAM BACK… ») ou de classe inconnue.")
            if len(nr):
                ui.tableau(nr, height=200)
            st.markdown(f"- **{len(absents)}** PN introuvables dans l'État du stock : leur stock est compté à 0"
                        + (f" ({', '.join(absents[:15])})" if absents else "") + ".")
