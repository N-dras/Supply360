"""Sous-onglet « Planning PE » de l'onglet Textile cabine : avancement de la politique d'entretien des mousses
de sièges et forecast des commandes (12 / 24 / 36 mois), par PN et par fournisseur.

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

K = "textiles__pe__"
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
                                                      help="10 % des avions de chaque flotte qui utilisent le PN × quantité par avion"),
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
    d = pe.ParamsPE()
    with st.popover("⚙️ Paramètres PE (mousses)", width="stretch"):
        st.markdown("**Cycle PE (mois)** · 0 = jamais remplacé")
        cols = st.columns(3)
        cycles = []
        for i, (cl, comp, m) in enumerate(d.cycles):
            v = cols[i % 3].number_input(f"{cl} · {comp}", 0, 240, m, 6, key=f"{K}cycle_{cl}_{comp}", persist_state="page")
            cycles.append((cl, comp, int(v)))
        a, b, c = st.columns(3)
        tol = a.number_input("Délai toléré après l'échéance (mois)", 0, 24, d.tolerance_mois, key=K + "tol", persist_state="page",
                             help="Échéance dépassée depuis moins longtemps : « Délai toléré » ; au-delà : « En retard ».")
        ratio = b.slider("Stock de sécurité (% des avions de la flotte)", 0, 50, int(d.securite_ratio * 100), key=K + "ss",
                         persist_state="page")
        mini = c.number_input("Minimum d'avions de sécurité par flotte", 0, 10, d.securite_min, key=K + "ssmin", persist_state="page")
    return pe.ParamsPE(cycles=tuple(cycles), tolerance_mois=int(tol), securite_ratio=ratio / 100, securite_min=int(mini))


# --------------------------------------------------------------------------
# Rendu
# --------------------------------------------------------------------------
def _element(classe, composant):
    return classe.astype(str) + " · " + composant.astype(str)


def _mois_label(m) -> str:
    return pd.Timestamp(m).strftime("%m/%y")


def _filtres(cal: pd.DataFrame) -> tuple[list, list, list]:
    with st.container(key="s360barre_pe"):
        a, b, c = st.columns([1.3, 1, 1.1], vertical_alignment="center")
        flottes = sorted(cal["Flotte"].dropna().unique())
        f = a.pills("Flotte", flottes, selection_mode="multi", default=flottes, key=K + "flottes", persist_state="page")
        cl = b.pills("Classe", pe.CLASSES, selection_mode="multi", default=pe.CLASSES, key=K + "classes", persist_state="page")
        co = c.pills("Élément", pe.COMPOSANTS, selection_mode="multi", default=pe.COMPOSANTS, key=K + "composants",
                     persist_state="page")
    return f or flottes, cl or pe.CLASSES, co or pe.COMPOSANTS


def render(res: dict, today: date, avec_pieces: bool) -> None:
    cal = res["cal"]
    flottes, classes, composants = _filtres(cal)
    c = cal[cal["Flotte"].isin(flottes) & cal["Classe"].isin(classes) & cal["Composant"].isin(composants)]
    _avancement(c, res["date_ref"], today)
    _calendrier(c, today)
    if not avec_pieces or res["ev"].empty:
        ui.callout("Ajoutez <b>textile_all_parts</b> (Pièces par avion) pour le forecast des mousses à commander.", "info", "📦")
        return
    ev = res["ev"]
    ev = ev[ev["Flotte"].isin(flottes) & ev["Classe"].isin(classes) & ev["Composant"].isin(composants)]
    pns = set(ev["PN"])
    synth, long = res["synth"][res["synth"]["PN"].isin(pns)], res["long"][res["long"]["PN"].isin(pns)]
    horizon = _forecast(ev, synth, long, today)
    _forecast_fournisseur(ev, synth, long, today, horizon)
    _exports_controles(res, c, ev, synth, long, horizon)


def _avancement(c: pd.DataFrame, date_ref, today):
    auj = pd.Timestamp(today)
    n = len(c)
    st_ = c["Statut"].astype(str)
    retard, tolere, trois = (st_ == "En retard").sum(), (st_ == "Délai toléré").sum(), (st_ == "À faire < 3 mois").sum()
    avions_retard = c.loc[st_ == "En retard", "Immatriculation"].nunique()
    visites = c.loc[c["Prochaine visite"] <= auj + pd.DateOffset(months=3), "Immatriculation"].nunique()
    conformite = (1 - retard / n) * 100 if n else 100
    with ui.section("textiles_pe_avancement", "Avancement de la PE mousses",
                    f"Âges au {pd.Timestamp(date_ref):%d/%m/%Y} (fichier PE mousses) · statut au {auj:%d/%m/%Y}",
                    tag=f"{c['Immatriculation'].nunique()} avions"):
        if retard:
            ui.callout(f"<b>{retard} remplacements en retard</b> sur {avions_retard} avions : à rattraper en priorité "
                       f"(prévus dès ce mois-ci dans le forecast).", "ko", "🔴")
        ui.kpi_grid([
            ui.kpi_card("Conformité PE", f"{conformite:.0f} %", f"{n - retard} éléments sur {n} dans les temps",
                        "ok" if conformite >= 90 else "warn" if conformite >= 70 else "ko"),
            ui.kpi_card("En retard", charts.entier(retard), f"{avions_retard} avions", "ko"),
            ui.kpi_card("Délai toléré", charts.entier(tolere), "échéance dépassée, encore dans la tolérance", "warn"),
            ui.kpi_card("À faire < 3 mois", charts.entier(trois), "", "warn"),
            ui.kpi_card("Visites dans les 3 mois", charts.entier(visites), "avions avec une visite datée", "info"),
        ])
        a, b = st.columns(2, gap="large")
        with a:
            t = c.assign(L=c["Flotte"].astype(str) + " · " + _element(c["Classe"], c["Composant"]))
            t = t.groupby(["L", "Statut"], observed=False).size().unstack(fill_value=0)
            t = t.reindex(columns=[s for s in pe.STATUTS if s in t.columns])
            t = t[t.sum(axis=1) > 0]
            ui.graphe(charts.parts(t, pe.STATUT_COULEURS, "Avancement par flotte et élément (nombre d'avions)"))
        with b:
            debut = auj.to_period("M").start_time
            mois = pd.date_range(debut, periods=12, freq="MS")
            d = c.assign(E=_element(c["Classe"], c["Composant"]))
            d["Case"] = d["Date prévue"].dt.to_period("M").dt.start_time
            retard_b = d["Origine date prévue"] == "Mois en cours (retard)"
            cats = ["Retard"] + [_mois_label(m) for m in mois]
            series = {}
            for e in ELEMENTS:
                x = d[d["E"] == e]
                if x.empty:
                    continue
                cnt = x[~retard_b.loc[x.index]].groupby("Case").size()
                series[e] = [int(retard_b.loc[x.index].sum())] + [int(cnt.get(m, 0)) for m in mois]
            ui.graphe(charts.barres(cats, series, COULEURS_ELEMENTS, empile=True, hauteur=260,
                                    titre="Remplacements à faire : retard puis 12 prochains mois (avions)")
                      if series else charts.vide("Aucun remplacement prévu"))


def _calendrier(c: pd.DataFrame, today):
    auj = pd.Timestamp(today)
    with ui.section("textiles_pe_calendrier", "Calendrier des remplacements",
                    "Une ligne par avion : nombre d'éléments à remplacer par mois (date prévue = prochaine visite datée, sinon échéance)"):
        debut = auj.to_period("M").start_time
        mois = pd.date_range(debut, periods=24, freq="MS")
        d = c.copy()
        d["Col"] = d["Date prévue"].dt.to_period("M").dt.start_time.map(_mois_label)
        d.loc[d["Origine date prévue"] == "Mois en cours (retard)", "Col"] = "Retard"
        d["Ligne"] = d["Immatriculation"] + " · " + d["Flotte"].astype(str)
        cols = ["Retard"] + [_mois_label(m) for m in mois]
        t = d[d["Col"].isin(cols)].groupby(["Ligne", "Col"]).size().unstack(fill_value=0).reindex(columns=cols, fill_value=0)
        if t.empty:
            ui.graphe(charts.vide("Aucun remplacement sur les 24 prochains mois"))
        else:
            ordre = d[d["Col"].isin(cols)].groupby("Ligne")["Date prévue"].min().sort_values().index
            with st.container(height=min(60 + 30 * len(t), 470), border=False):
                ui.graphe(charts.chaleur(t.reindex(ordre), libelle="élément(s)", couleur=(198, 40, 40) if False else (31, 78, 156)))
        _detail_avions(c)


@st.fragment
def _detail_avions(c: pd.DataFrame):
    with st.popover(f"📋 Détail par avion et par élément ({len(c)})", width="content"):
        f1, f2 = st.columns([1, 2])
        q = f1.text_input("Immatriculation", placeholder="🔎 Immatriculation", key=K + "q", label_visibility="collapsed")
        statuts = f2.multiselect("Statut", pe.STATUTS, key=K + "statuts", placeholder="Tous les statuts", label_visibility="collapsed")
        d = c
        if q:
            d = d[d["Immatriculation"].str.contains(re.sub(r"[^A-Z0-9-]", "", q.upper()), regex=False)]
        if statuts:
            d = d[d["Statut"].astype(str).isin(statuts)]
        t = pd.DataFrame({
            "Statut": d["Statut"].astype(str).map(ICONES_STATUT), "Immatriculation": d["Immatriculation"], "Flotte": d["Flotte"],
            "Version": d["Version cabine"], "Classe": d["Classe"], "Élément": d["Composant"],
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
    debut = pd.Timestamp(today).to_period("M").start_time
    with ui.section("textiles_pe_forecast", "Forecast des mousses à commander",
                    "À commander = besoin + stock de sécurité − stock − commandes en cours (déjà passées, toujours déduites), par PN"):
        a, _ = st.columns([1, 2])
        with a:
            h = _horizon()
        fin = debut + pd.DateOffset(months=h)
        e = ev[ev["Mois"] < fin]
        lg = long[long["Mois"] < fin]
        besoin, rattrapage = e["Qté"].sum(), e.loc[e["Rattrapage du retard"], "Qté"].sum()
        a_cmd, valeur = lg["À livrer"].sum(), lg["Valeur à livrer (€)"].sum()
        fours = lg.loc[lg["À livrer"] > 0, "Fournisseur"].nunique()
        avancer = synth[synth["À avancer (commandes en cours)"] > 0]
        if len(avancer):
            ui.callout(f"<b>{charts.entier(avancer['À avancer (commandes en cours)'].sum())} pièces en commande à faire avancer</b> "
                       f"sur {len(avancer)} PN : elles sont promises après le mois où elles sont nécessaires. "
                       "Relancez les fournisseurs (colonnes « À avancer » et « Avant » du tableau par PN) plutôt que de recommander.",
                       "warn", "📌")
        ui.kpi_grid([
            ui.kpi_card(f"Mousses à remplacer ({h} mois)", charts.entier(besoin), f"dont {charts.entier(rattrapage)} de retard à rattraper", "navy"),
            ui.kpi_card("À commander", charts.entier(a_cmd), "besoin + sécurité − stock − en commande", "ko"),
            ui.kpi_card("Valeur à commander", charts.euros(valeur), f"horizon {h} mois", "ko"),
            ui.kpi_card("Stock disponible", charts.entier(synth["Stock"].sum()), f"+ {charts.entier(synth['En commande'].sum())} déjà en commande (déduits)", "info"),
            ui.kpi_card("Fournisseurs", charts.entier(fours), "à solliciter", "violet"),
        ])
        mois = pd.date_range(debut, periods=h, freq="MS")
        x = e.assign(E=_element(e["Classe"], e["Composant"])).groupby(["Mois", "E"])["Qté"].sum().unstack(fill_value=0)
        x = x.reindex(index=mois, fill_value=0)
        series = {k: x[k] for k in ELEMENTS if k in x.columns}
        ui.graphe(charts.barres(mois, series, COULEURS_ELEMENTS, empile=True, temporel=True, hauteur=260,
                                titre="Mousses à remplacer par mois (le 1er mois inclut le retard à rattraper)")
                  if series else charts.vide())
        a, b = st.columns([1.2, 1], gap="large")
        with a:
            liv = lg.groupby("Mois")["À livrer"].sum().reindex(mois, fill_value=0)
            ui.graphe(charts.barres(mois, {"À livrer": liv}, {"À livrer": COLORS["ko"]}, temporel=True, hauteur=230,
                                    titre="Livraisons à prévoir par mois (tous fournisseurs)"))
        with b:
            v = lg.groupby("Fournisseur")["Valeur à livrer (€)"].sum().sort_values(ascending=False)
            v = v[v > 0]
            ui.graphe(charts.barres_h([(f, val, charts.euros(val)) for f, val in v.items()], couleur=COLORS["navy_2"],
                                      titre="Valeur à commander par fournisseur") if len(v) else charts.vide("Rien à commander"))
        t = synth.assign(**{"Besoin": synth[f"Besoin {h} mois"], "À commander": synth[f"À commander {h} mois"],
                            "Valeur (€)": synth[f"Valeur {h} mois (€)"]})
        t = t.sort_values("Valeur (€)", ascending=False)
        cols = {"PN": "PN", "Désignation": "Désignation", "Classes": "Classe", "Composant": "Élément", "Flottes": "Flottes",
                "Fournisseur": "Fournisseur", "Prix unitaire (€)": "Prix (€)", "Stock": "Stock", "En commande": "En commande",
                "Stock de sécurité": "Stock de sécurité", "Besoin": "Besoin", "À commander": "À commander", "Valeur (€)": "Valeur (€)",
                "À avancer (commandes en cours)": "À avancer", "À avancer avant": "Avant", "Rupture sans commande": "Rupture sans commande"}
        st.markdown(f"**Par PN** · horizon {h} mois")
        ui.tableau(t[list(cols)].rename(columns=cols), column_config=CFG, height=min(38 + 35 * len(t), 420))
    return h


@st.fragment
def _forecast_fournisseur(ev, synth, long, today, h):
    debut = pd.Timestamp(today).to_period("M").start_time
    fin = debut + pd.DateOffset(months=h)
    lg = long[long["Mois"] < fin]
    v = lg.groupby("Fournisseur")["Valeur à livrer (€)"].sum().sort_values(ascending=False)
    if v.empty:
        return
    with ui.section("textiles_pe_fournisseur", "Forecast par fournisseur",
                    f"Commande globale et livraisons mois par mois sur {h} mois : à partager avec le fournisseur"):
        libelles = {f: f"{f}  ·  {charts.euros(val)}" for f, val in v.items()}
        f = st.selectbox("Fournisseur", list(libelles), format_func=libelles.get, key=K + "fournisseur", persist_state="page",
                         label_visibility="collapsed")
        d = lg[lg["Fournisseur"] == f]
        a_livrer = d[d["À livrer"] > 0]
        premier = a_livrer["Mois"].min()
        ui.kpi_grid([
            ui.kpi_card("Commande globale", charts.entier(d["À livrer"].sum()), f"mousses sur {h} mois", "ko"),
            ui.kpi_card("Valeur", charts.euros(d["Valeur à livrer (€)"].sum()), "", "ko"),
            ui.kpi_card("PN", charts.entier(a_livrer["PN"].nunique()), "à livrer", "navy"),
            ui.kpi_card("Première livraison", f"{premier:%m/%Y}" if pd.notna(premier) else "—",
                        "dès que possible" if pd.notna(premier) and premier == debut else "", "warn"),
        ])
        mois = pd.date_range(debut, periods=h, freq="MS")
        piv = d.pivot_table(index="PN", columns="Mois", values="À livrer", aggfunc="sum", fill_value=0).reindex(columns=mois, fill_value=0)
        piv = piv[piv.sum(axis=1) > 0]
        series = {pn: piv.loc[pn] for pn in piv.index[:8]}
        if len(piv) > 8:
            series["Autres PN"] = piv.iloc[8:].sum()
        ui.graphe(charts.barres(mois, series, empile=True, temporel=True, hauteur=250,
                                titre="Mousses à livrer par mois et par PN") if series else charts.vide("Rien à livrer"))
        desig = synth.set_index("PN")["Désignation"]
        tab = piv.copy()
        tab.columns = [m.strftime("%m/%Y") for m in tab.columns]
        tab.insert(0, "Total", piv.sum(axis=1))
        tab.insert(0, "Désignation", desig.reindex(tab.index))
        tab = tab.reset_index()
        ui.tableau(tab, column_config=CFG, height=min(38 + 35 * len(tab), 320))
        ui.telecharger(_export_fournisseur(f, tab, ev[ev["PN"].isin(piv.index)], synth), _nom_fichier(f"forecast_{f}"),
                       K + "export_fournisseur", label="⬇️ Forecast fournisseur (Excel)")


def _nom_fichier(base: str) -> str:
    return f"Supply360_{re.sub(r'[^A-Za-z0-9]+', '_', base).strip('_')}_{date.today():%Y%m%d}.xlsx"


def _export_fournisseur(f, tab, ev, synth) -> bytes:
    resume = synth[synth["PN"].isin(tab["PN"])][["PN", "Désignation", "Composant", "Classes", "Prix unitaire (€)"]].merge(
        tab[["PN", "Total"]], on="PN")
    resume["Valeur (€)"] = resume["Total"] * resume["Prix unitaire (€)"].fillna(0)
    avions = ev.assign(Mois=ev["Mois"].dt.strftime("%m/%Y"))[["PN", "Mois", "Immatriculation", "Flotte", "Classe", "Composant", "Qté"]]
    return sio.exporter_excel({"Commande globale": resume, "Livraisons par mois": tab, "Besoins par avion": avions})


def _exports_controles(res, c, ev, synth, long, h):
    with ui.section("textiles_pe_exports", "Exports et contrôles"):
        a, b = st.columns(2)
        with a:
            debut = long["Mois"].min()
            liv = long[(long["À livrer"] > 0) & (long["Mois"] < debut + pd.DateOffset(months=h))]
            feuilles = {
                "Avancement PE": c.drop(columns=["Âge exact"]).assign(Statut=c["Statut"].astype(str)),
                f"Forecast PN {h} mois": synth,
                "Livraisons à prévoir": liv[["Fournisseur", "PN", "Désignation", "Mois", "À livrer", "Valeur à livrer (€)"]],
                "Besoins par avion": ev,
            }
            ui.telecharger(sio.exporter_excel(feuilles), _nom_fichier("planning_PE"), K + "export_tout",
                           label="⬇️ Planning PE complet (Excel)")
        with b, st.popover("🔎 Contrôles des données", width="stretch"):
            nr, sans, absents = res["non_reconnues"], res["sans_pn"], res["pn_absents_stock"]
            age_min = int((~res["cal"]["Âge exact"]).sum())
            st.markdown(f"- **{age_min}** éléments avec un âge minimum seulement (« > 60 », « > 108 » dans le fichier PE) : "
                        "échéance calculée au plus tôt.")
            st.markdown(f"- **{len(sans)}** éléments sans PN de mousse dans textile_all_parts (immat / classe / élément) : "
                        "absents du forecast.")
            if len(sans):
                ui.tableau(sans.assign(Statut=sans["Statut"].astype(str)), height=200)
            st.markdown(f"- **{len(nr)}** lignes MOUSSE de textile_all_parts non reconnues (ni FOAM BOTTOM / BOTT, ni FOAM BACK…) "
                        "ou classe inconnue.")
            if len(nr):
                ui.tableau(nr, height=200)
            st.markdown(f"- **{len(absents)}** PN absents de l'État du stock (stock compté à 0)" + (f" : {', '.join(absents[:15])}" if absents else ""))
