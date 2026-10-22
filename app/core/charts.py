"""Graphes interactifs (Altair / Vega-Lite), dans le style du prototype Supply360.

Altair est déjà chargé par stlite (dépendance de Streamlit) : aucun téléchargement en plus.
Chaque graphe propose : infobulle au survol, mise en évidence de la série survolée, plein écran,
export PNG / SVG et affichage des données (barre d'outils au survol du graphe).

Les fonctions construisent un `alt.Chart` (affiché par `components.graphe`) à partir de données
déjà agrégées. Les libellés (valeurs, € …) sont formatés en Python, au format français.
"""

import math

import altair as alt
import pandas as pd

from core.style import COLORS, FONT

PALETTE = [COLORS["navy_2"], "#2A9D8F", "#F4A259", "#BC4B51", COLORS["violet"], "#8AB17D", COLORS["gris"]]
OPACITE_FOND = 0.35  # séries non survolées


# --------------------------------------------------------------------------
# Formats
# --------------------------------------------------------------------------
def _nan(v) -> bool:
    try:
        return v is None or math.isnan(float(v))
    except (TypeError, ValueError):
        return True


def court(v) -> str:
    """1 234 → « 1,2k », 3 400 000 → « 3,4 M » (format français)."""
    if _nan(v):
        return ""
    v = float(v)
    a = abs(v)
    if a >= 1e6:
        s = f"{v / 1e6:.1f} M"
    elif a >= 1e4:
        s = f"{v / 1e3:.0f}k"
    elif a >= 1e3:
        s = f"{v / 1e3:.1f}k"
    else:
        s = f"{v:.0f}" if v.is_integer() else f"{v:.1f}"
    return s.replace(".", ",")


def euros(v) -> str:
    if _nan(v):
        return "0 €"
    v = float(v)
    a = abs(v)
    if a >= 1e6:
        return f"{v / 1e6:.1f} M€".replace(".", ",")
    if a >= 1e3:
        return f"{v / 1e3:.0f} k€"
    return f"{v:.0f} €"


def entier(v) -> str:
    return "" if _nan(v) else f"{float(v):,.0f}".replace(",", " ")


def pourcent(v) -> str:
    return "" if _nan(v) else f"{float(v):.0f} %"


# --------------------------------------------------------------------------
# Style commun
# --------------------------------------------------------------------------
def _titre(titre):
    return alt.TitleParams(titre, anchor="start", fontSize=15, fontWeight=700, color=COLORS["text"], offset=10) \
        if titre else alt.Undefined


def _config(ch, font_axes=12):
    return (ch.configure(font=FONT, background="transparent")
            .configure_view(stroke=None)
            .configure_axis(labelColor=COLORS["muted"], labelFontSize=font_axes, titleColor=COLORS["muted"], titleFontSize=12,
                            titleFontWeight=600, domain=False, tickColor=COLORS["grid"], gridColor=COLORS["grid"],
                            gridDash=[3, 3], labelLimit=180)
            .configure_legend(orient="bottom", direction="horizontal", labelColor=COLORS["text"], labelFontSize=12,
                              title=None, symbolType="circle", symbolSize=110, columnPadding=16, labelLimit=260)
            .configure_title(font=FONT))


def _style(ch, titre="", hauteur=240):
    props = {"height": hauteur, "width": "container"}
    if titre:
        props["title"] = _titre(titre)
    return _config(ch.properties(**props))


def _couleur(noms, couleurs):
    noms = list(noms)
    return alt.Scale(domain=noms, range=[(couleurs or {}).get(n, PALETTE[i % len(PALETTE)]) for i, n in enumerate(noms)])


def vide(message="Aucune donnée à afficher"):
    """Graphe vide avec un message (garde l'emplacement)."""
    ch = alt.Chart(pd.DataFrame({"t": [message]})).mark_text(fontSize=14, color=COLORS["muted"]).encode(text="t:N")
    return _style(ch, hauteur=70)


# --------------------------------------------------------------------------
# Barres verticales (groupées ou empilées) + courbe optionnelle (axe de droite)
# --------------------------------------------------------------------------
def barres(cats, series: dict, couleurs: dict | None = None, empile=False, ligne: dict | None = None,
           couleur_ligne=COLORS["text"], fmt=court, fmt_ligne=None, hauteur=260, titre="", survol=None,
           temporel=False, fenetre=None, titre_y="", repere: dict | None = None, titre_x_survol="Libellé"):
    """Barres avec valeurs affichées ; `ligne` = {nom: valeurs} sur un axe de droite ;
    `repere` = {nom: valeurs} : losanges sur la même échelle que les barres (ex. stock minimum).

    `temporel=True` : `cats` sont des dates (début de mois) → axe temporel ; `fenetre` = (début, fin)
    limite les mois affichés.
    """
    cats = list(cats)
    noms = list(series)
    valeurs = {k: list(series[k]) for k in noms}
    if temporel and fenetre:  # période affichée : on ne garde que les mois de la fenêtre
        a, b = pd.Timestamp(fenetre[0]), pd.Timestamp(fenetre[1])
        garde = [a <= pd.Timestamp(c) <= b for c in cats]
        cats = [c for c, g in zip(cats, garde) if g]
        valeurs = {k: [v for v, g in zip(valeurs[k], garde) if g] for k in noms}
        survol = [v for v, g in zip(survol, garde) if g] if survol else survol
        if ligne:
            ligne = {k: [v for v, g in zip(list(vv), garde) if g] for k, vv in ligne.items()}
    if not cats or not series:
        return vide()
    lignes = []
    for i, c in enumerate(cats):
        for k in noms:
            v = valeurs[k][i]
            v = 0.0 if _nan(v) else float(v)
            lignes.append({"cat": c if temporel else str(c), "serie": k, "valeur": v, "txt": fmt(v) if v else "",
                           "info": str(survol[i]) if survol else ""})
    df = pd.DataFrame(lignes)
    ordre = [str(c) for c in cats]
    if temporel:
        xenc = alt.X("cat:T", title=None, timeUnit="yearmonth", axis=alt.Axis(format="%m/%y", labelAngle=0, grid=False, tickCount="month"))
        xtxt = alt.X("cat:T", title=None, timeUnit="yearmonth", bandPosition=0.5)  # étiquettes au centre du mois
        tip_x = alt.Tooltip("cat:T", title="Mois", timeUnit="yearmonth", format="%m/%Y")
    else:
        incline = len(cats) > 7 or (len(cats) > 4 and max(len(str(c)) for c in cats) > 12)
        xenc = alt.X("cat:N", sort=ordre, title=None,
                     axis=alt.Axis(labelAngle=-35 if incline else 0, grid=False, labelLimit=140))
        tip_x = alt.Tooltip("cat:N", title=titre_x_survol)
        xtxt = xenc
    tooltip = [tip_x, alt.Tooltip("serie:N", title="Série"), alt.Tooltip("txt:N", title="Valeur")]
    if survol:
        tooltip.append(alt.Tooltip("info:N", title="Détail"))
    sel = alt.selection_point(fields=["serie"], on="pointerover", clear="pointerout")
    opac = alt.condition(sel, alt.value(1), alt.value(OPACITE_FOND))
    color = alt.Color("serie:N", scale=_couleur(noms, couleurs), legend=alt.Legend() if len(noms) > 1 else None, sort=noms)
    axe_y = alt.Axis(format="~s", tickCount=5)
    forme = {"cornerRadiusTopLeft": 4, "cornerRadiusTopRight": 4}
    if temporel:
        forme["width"] = {"band": 0.7}  # barres plus fines, comme sur le prototype
    if empile:
        bars = alt.Chart(df).mark_bar(**forme).encode(
            x=xenc, y=alt.Y("valeur:Q", stack="zero", title=titre_y or None, axis=axe_y),
            color=color, opacity=opac, tooltip=tooltip).add_params(sel)
        tot = df.groupby("cat", as_index=False, sort=False)["valeur"].sum()
        tot["txt"] = tot["valeur"].map(lambda v: fmt(v) if v else "")
        texte = alt.Chart(tot).mark_text(dy=-8, fontSize=12, fontWeight=800, color=COLORS["text"]).encode(
            x=xtxt, y=alt.Y("valeur:Q"), text="txt:N")
    else:
        off = alt.XOffset("serie:N", sort=noms) if len(noms) > 1 else alt.Undefined
        bars = alt.Chart(df).mark_bar(**forme).encode(
            x=xenc, xOffset=off, y=alt.Y("valeur:Q", title=titre_y or None, axis=axe_y),
            color=color, opacity=opac, tooltip=tooltip).add_params(sel)
        texte = alt.Chart(df).mark_text(dy=-8, fontSize=12, fontWeight=700, color=COLORS["text"]).encode(
            x=xtxt if len(noms) == 1 else xenc, xOffset=off, y="valeur:Q", text="txt:N", opacity=opac)
    ch = alt.layer(bars, texte)
    if repere:
        nom_r, vals_r = next(iter(repere.items()))
        dr = pd.DataFrame({"cat": cats if temporel else ordre, "v": [None if _nan(v) else float(v) for v in vals_r], "serie": nom_r})
        dr["txt"] = dr["v"].map(lambda v: "" if v is None or _nan(v) else fmt(v))
        losange = alt.Chart(dr).mark_point(shape="diamond", size=150, filled=True, stroke="white", strokeWidth=1.2).encode(
            x=xtxt, y=alt.Y("v:Q"),
            color=alt.Color("serie:N", scale=alt.Scale(domain=[nom_r], range=[COLORS["text"]]), legend=alt.Legend(symbolType="diamond")),
            tooltip=[tip_x, alt.Tooltip("txt:N", title=nom_r)])
        ch = alt.layer(ch, losange).resolve_scale(color="independent")
    if ligne:
        fmt_l = fmt_ligne or fmt
        nom_l, vals = next(iter(ligne.items()))
        dl = pd.DataFrame({"cat": cats if temporel else ordre, "v": [None if _nan(v) else float(v) for v in vals]})
        dl["serie"] = nom_l
        dl["txt"] = dl["v"].map(lambda v: "" if v is None or _nan(v) else fmt_l(v))
        hi = max([v for v in dl["v"] if v is not None and not _nan(v)] or [1])
        lo = min([v for v in dl["v"] if v is not None and not _nan(v)] or [0] + [0])
        # Échelle de droite étendue vers le bas : la courbe reste au-dessus des barres.
        ytl = alt.Y("v:Q", title=None, axis=None,
                    scale=alt.Scale(domain=[min(lo, 0) - (hi - min(lo, 0)) * 1.4, hi + (hi - min(lo, 0)) * .12]))
        bl = alt.Chart(dl).encode(x=xtxt, y=ytl)
        couleur_l = alt.Color("serie:N", scale=alt.Scale(domain=[nom_l], range=[couleur_ligne]),
                              legend=alt.Legend(symbolType="stroke", symbolStrokeWidth=3))
        trait = bl.mark_line(strokeWidth=2.5, point=alt.OverlayMarkDef(size=55, filled=True)).encode(color=couleur_l)
        lab = bl.mark_text(dy=-11, fontSize=12, fontWeight=800, color=couleur_ligne).encode(text="txt:N")
        survol_l = bl.mark_point(size=220, opacity=0).encode(tooltip=[tip_x, alt.Tooltip("txt:N", title=nom_l)])
        ch = alt.layer(ch, alt.layer(trait, lab, survol_l)).resolve_scale(y="independent", color="independent")
    return _style(ch, titre, hauteur)


def courbes(x, series: dict, couleurs: dict | None = None, hauteur=260, titre="", fmt=court, pointilles=(), escalier=()):
    """Courbes sur un axe temporel (mois), infobulle unifiée au survol."""
    if len(x) == 0 or not series:
        return vide()
    noms = list(series)
    df = pd.concat([pd.DataFrame({"x": list(x), "serie": k, "v": [None if _nan(v) else float(v) for v in series[k]]}) for k in noms])
    df["txt"] = df["v"].map(lambda v: "" if v is None or _nan(v) else fmt(v))
    color = alt.Color("serie:N", scale=_couleur(noms, couleurs), sort=noms)
    dash = alt.condition(alt.FieldOneOfPredicate(field="serie", oneOf=list(pointilles) or ["-"]), alt.value([6, 4]), alt.value([0]))
    base = alt.Chart(df).encode(x=alt.X("x:T", title=None, axis=alt.Axis(format="%m/%y", grid=False, labelAngle=0)),
                                y=alt.Y("v:Q", title=None, axis=alt.Axis(format="~s", tickCount=5)), color=color)
    trait = base.mark_line(strokeWidth=2.6, interpolate="step-after" if escalier else "linear").encode(strokeDash=dash)
    survol = alt.selection_point(fields=["x"], nearest=True, on="pointerover", clear="pointerout", empty=False)
    regle = alt.Chart(df).mark_rule(color=COLORS["gris"]).encode(
        x="x:T", opacity=alt.condition(survol, alt.value(.6), alt.value(0)),
        tooltip=[alt.Tooltip("x:T", title="Mois", format="%m/%Y")] + [alt.Tooltip(f"{k}:N", title=k) for k in noms]
    ).transform_pivot("serie", value="txt", groupby=["x"]).add_params(survol)
    points = base.mark_point(filled=True, size=40).encode(opacity=alt.condition(survol, alt.value(1), alt.value(0)))
    ch = alt.layer(trait, points, regle)
    return _style(ch, titre, hauteur)


def multiples(panneaux: dict, couleurs: dict | None = None, hauteur=140, fmt=court, titre="", colonnes=4):
    """Petits multiples : {titre: (catégories, valeurs)}, une mini-série de barres par panneau (échelle propre)."""
    if not panneaux:
        return vide()
    lignes = []
    for t, (cats, vals) in panneaux.items():
        for c, v in zip(cats, vals):
            v = 0.0 if _nan(v) else float(v)
            lignes.append({"panneau": str(t), "cat": str(c), "valeur": v, "txt": fmt(v) if v else ""})
    df = pd.DataFrame(lignes)
    noms = list(dict.fromkeys(df["panneau"]))
    ordre_x = list(dict.fromkeys(df["cat"]))
    sel = alt.selection_point(fields=["cat"], on="pointerover", clear="pointerout")
    base = alt.Chart().encode(x=alt.X("cat:N", sort=ordre_x, title=None, axis=alt.Axis(labelAngle=0, grid=False)))
    bars = base.mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        y=alt.Y("valeur:Q", title=None, axis=alt.Axis(format="~s", tickCount=3)),
        color=alt.Color("panneau:N", scale=_couleur(noms, couleurs), legend=None),
        opacity=alt.condition(sel, alt.value(1), alt.value(.7)),
        tooltip=[alt.Tooltip("panneau:N", title="Série"), alt.Tooltip("cat:N", title="Période"), alt.Tooltip("txt:N", title="Valeur")],
    ).add_params(sel)
    texte = base.mark_text(dy=-7, fontSize=11, fontWeight=700, color=COLORS["text"]).encode(y="valeur:Q", text="txt:N")
    ch = alt.layer(bars, texte, data=df).properties(height=hauteur, width=alt.Step(34)) \
        .facet(facet=alt.Facet("panneau:N", sort=noms, title=None,
                               header=alt.Header(labelFontSize=13, labelFontWeight=700, labelColor=COLORS["navy"],
                                                 labelAnchor="start", labelFont=FONT)),
               columns=colonnes, spacing=22) \
        .resolve_scale(y="independent")
    if titre:
        ch = ch.properties(title=_titre(titre))
    return _config(ch, font_axes=11)


# --------------------------------------------------------------------------
# Barres horizontales (classements)
# --------------------------------------------------------------------------
def barres_h(lignes, couleur=COLORS["navy_2"], fmt=court, titre="", max_lignes=12, titre_x=""):
    """lignes : [(libellé, valeur)], [(libellé, valeur, texte)] ou [(libellé, valeur, texte, couleur)], déjà triées."""
    lignes = list(lignes)[:max_lignes]
    if not lignes:
        return vide()
    df = pd.DataFrame({
        "nom": [str(l[0]) for l in lignes],
        "valeur": [0.0 if _nan(l[1]) else float(l[1]) for l in lignes],
        "txt": [l[2] if len(l) > 2 and l[2] is not None else fmt(l[1]) for l in lignes],
        "couleur": [l[3] if len(l) > 3 else couleur for l in lignes],
    })
    sel = alt.selection_point(fields=["nom"], on="pointerover", clear="pointerout")
    base = alt.Chart(df).encode(y=alt.Y("nom:N", sort=list(df["nom"]), title=None, axis=alt.Axis(labelLimit=220, labelFontSize=12.5)))
    bars = base.mark_bar(cornerRadiusTopRight=5, cornerRadiusBottomRight=5).encode(
        x=alt.X("valeur:Q", title=titre_x or None, axis=alt.Axis(format="~s", tickCount=4), scale=alt.Scale(nice=True)),
        color=alt.Color("couleur:N", scale=None), opacity=alt.condition(sel, alt.value(1), alt.value(.75)),
        tooltip=[alt.Tooltip("nom:N", title="Libellé"), alt.Tooltip("txt:N", title="Valeur")]).add_params(sel)
    texte = base.mark_text(align="left", dx=5, fontSize=12, fontWeight=800, color=COLORS["text"]).encode(x="valeur:Q", text="txt:N")
    return _style(alt.layer(bars, texte), titre, max(110, 34 * len(df) + 20))


# --------------------------------------------------------------------------
# Barres 100 % (répartition par ligne)
# --------------------------------------------------------------------------
def parts(tableau, couleurs: dict, titre="", afficher="nombre", noms=("Catégorie", "Statut")):
    """`tableau` : DataFrame (lignes = catégories, colonnes = statuts) de comptages ou de valeurs."""
    if tableau is None or tableau.empty or float(tableau.to_numpy().sum()) == 0:
        return vide()
    lignes = []
    for idx, r in tableau.iterrows():
        total = float(r.sum())
        debut = 0.0
        for col, v in r.items():
            v = float(v)
            p = v / total * 100 if total else 0
            lignes.append({"ligne": str(idx), "statut": str(col), "p0": debut, "p1": debut + p, "pm": debut + p / 2,
                           "pct": f"{p:.0f} %", "vtxt": court(v),
                           "txt": (f"{p:.0f} %" if afficher == "pourcent" else court(v)) if p >= 7 else ""})
            debut += p
    df = pd.DataFrame(lignes)
    cols = [str(c) for c in tableau.columns]
    sel = alt.selection_point(fields=["statut"], on="pointerover", clear="pointerout")
    base = alt.Chart(df).encode(y=alt.Y("ligne:N", sort=[str(i) for i in tableau.index], title=None,
                                        axis=alt.Axis(labelLimit=200, labelFontSize=12.5)))
    bars = base.mark_bar(cornerRadius=3).encode(
        x=alt.X("p0:Q", title=None, scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(labelExpr="datum.value + ' %'", tickCount=5)),
        x2="p1:Q", color=alt.Color("statut:N", scale=_couleur(cols, couleurs), sort=cols),
        opacity=alt.condition(sel, alt.value(1), alt.value(.45)),
        tooltip=[alt.Tooltip("ligne:N", title=noms[0]), alt.Tooltip("statut:N", title=noms[1]), alt.Tooltip("vtxt:N", title="Valeur"),
                 alt.Tooltip("pct:N", title="Part")]).add_params(sel)
    texte = base.mark_text(fontSize=12, fontWeight=700, color="white").encode(x="pm:Q", text="txt:N")
    return _style(alt.layer(bars, texte), titre, max(110, 42 * len(tableau) + 20))


# --------------------------------------------------------------------------
# Carte de chaleur
# --------------------------------------------------------------------------
def chaleur(tableau, titre="", couleur=COLORS["navy_2"], libelle="Valeur"):
    """Lignes × colonnes, intensité proportionnelle à la valeur."""
    if tableau is None or tableau.empty:
        return vide()
    df = tableau.copy()
    df.index = [str(i) for i in df.index]
    df.columns = [str(c) for c in df.columns]
    df = df.reset_index(names="ligne").melt(id_vars="ligne", var_name="col", value_name="v")
    df["txt"] = df["v"].map(lambda v: court(v) if v else "")
    vmax = float(df["v"].max()) or 1
    base = alt.Chart(df).encode(
        x=alt.X("col:N", sort=[str(c) for c in tableau.columns], title=None, axis=alt.Axis(orient="top", labelAngle=0, grid=False)),
        y=alt.Y("ligne:N", sort=[str(i) for i in tableau.index], title=None, axis=alt.Axis(labelLimit=200, grid=False)))
    rect = base.mark_rect(cornerRadius=4, stroke="white", strokeWidth=2).encode(
        color=alt.condition("datum.v > 0", alt.Color("v:Q", scale=alt.Scale(range=["#DCE6F6", couleur], domain=[0, vmax]), legend=None),
                            alt.value("#F3F6FA")),
        tooltip=[alt.Tooltip("ligne:N", title="Fournisseur"), alt.Tooltip("col:N", title="Mois"), alt.Tooltip("txt:N", title=libelle)])
    texte = base.mark_text(fontSize=12, fontWeight=700).encode(
        text="txt:N", color=alt.condition(f"datum.v > {vmax * .55}", alt.value("white"), alt.value(COLORS["text"])))
    return _style(alt.layer(rect, texte), titre, max(120, 30 * len(tableau) + 40))
