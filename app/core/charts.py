"""Graphes HTML / SVG légers, dans le style du prototype Supply360.

Fonctions pures : elles renvoient du HTML affiché par `components.graphe` (st.markdown). Aucune
dépendance et aucun JavaScript : rendu instantané, rien à charger. Les positions horizontales sont
en %, les hauteurs en px : les textes gardent leur taille quelle que soit la largeur.

Survol : chaque colonne (ou ligne, ou case) porte une infobulle `data-tip` affichée en CSS
(core/theme.css) avec toutes ses valeurs.
"""

import math
from html import escape

import pandas as pd

from core.style import COLORS

PALETTE = [COLORS["navy_2"], "#2A9D8F", "#F4A259", "#BC4B51", COLORS["violet"], "#8AB17D", COLORS["gris"]]
HAUT = 20  # marge au-dessus des barres (étiquettes de valeur)


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


def jours(v) -> str:
    return "" if _nan(v) else f"{float(v):+.0f} j".replace("+0 j", "0 j")


# --------------------------------------------------------------------------
# Briques communes
# --------------------------------------------------------------------------
def _tip(lignes) -> str:
    """Attribut data-tip (une ligne par élément, vides ignorés)."""
    texte = "\n".join(str(l) for l in lignes if l not in (None, ""))
    return f' data-tip="{escape(texte, quote=True)}"'.replace("\n", "&#10;")


def _titre(t):
    return f"<h5>{escape(t)}</h5>" if t else ""


def legende(items) -> str:
    """items : [(libellé, couleur, 'barre' | 'ligne' | 'repere' | 'trait')]."""
    if not items:
        return ""
    cls = {"ligne": "ln", "repere": "rp", "trait": "tr"}
    spans = "".join(f'<span><i class="{cls.get(k, "")}" style="background:{c}"></i>{escape(str(n))}</span>' for n, c, k in items)
    return f'<div class="s360-legend">{spans}</div>'


def vide(message="Aucune donnée à afficher") -> str:
    return f'<div class="s360-chart"><p class="s360-vide">{escape(message)}</p></div>'


def _libelle(c, temporel):
    if temporel:
        return pd.Timestamp(c).strftime("%m/%y")
    return str(c)


def _etiquettes_x(cats, temporel=False):
    """Étiquettes sous les colonnes : inclinées si longues ; mois : une sur k si nombreux."""
    n = len(cats)
    if temporel:
        pas = max(1, math.ceil(n / 14))
        spans = "".join(f"<span>{escape(c) if i % pas == 0 else ''}</span>" for i, c in enumerate(cats))
        return f'<div class="s360-xl" style="grid-template-columns:repeat({n},minmax(0,1fr))">{spans}</div>', False
    long_ = max(len(c) for c in cats)
    tourner = n > 4 and (n > 12 or long_ > 9)
    spans = "".join(f'<span title="{escape(c)}">{escape(c)}</span>' for c in cats)
    cls = "s360-xl rot" if tourner else "s360-xl"
    return f'<div class="{cls}" style="grid-template-columns:repeat({n},minmax(0,1fr))">{spans}</div>', tourner


def _cote(i, n):
    """Classe d'alignement de l'infobulle : à gauche pour les premières colonnes, à droite pour les dernières."""
    if n >= 3 and i < n * 0.25:
        return " tl"
    if n >= 3 and i >= n * 0.75:
        return " tr"
    return ""


# --------------------------------------------------------------------------
# Barres verticales (groupées ou empilées) + courbe et repères optionnels
# --------------------------------------------------------------------------
def barres(cats, series: dict, couleurs: dict | None = None, empile=False, ligne: dict | None = None,
           couleur_ligne=COLORS["text"], fmt=court, fmt_ligne=None, hauteur=250, titre="", survol=None,
           temporel=False, fenetre=None, repere: dict | None = None, legende_auto=True, etiquettes=True,
           couleurs_barres=None) -> str:
    """Barres avec valeurs affichées.

    `ligne` = {nom: valeurs} : courbe tracée sur sa propre échelle, dans une bande au-dessus des barres ;
    `repere` = {nom: valeurs} : losanges sur l'échelle des barres (ex. stock minimum) ;
    `temporel` : `cats` sont des débuts de mois (étiquettes MM/AA), `fenetre` = (début, fin) limite les mois ;
    `survol` : texte en plus dans l'infobulle de chaque colonne ; `couleurs_barres` : une couleur par colonne
    (série unique).
    """
    cats = list(cats)
    noms = list(series)
    vals = {k: [0.0 if _nan(v) else float(v) for v in series[k]] for k in noms}
    lig = {k: list(v) for k, v in (ligne or {}).items()}
    rep = {k: list(v) for k, v in (repere or {}).items()}
    survol = list(survol) if survol is not None else None
    if temporel and fenetre:
        a, b = pd.Timestamp(fenetre[0]), pd.Timestamp(fenetre[1])
        garde = [a <= pd.Timestamp(c) <= b for c in cats]
        cats = [c for c, g in zip(cats, garde) if g]
        vals = {k: [x for x, g in zip(v, garde) if g] for k, v in vals.items()}
        lig = {k: [x for x, g in zip(v, garde) if g] for k, v in lig.items()}
        rep = {k: [x for x, g in zip(v, garde) if g] for k, v in rep.items()}
        survol = [x for x, g in zip(survol, garde) if g] if survol else survol
    n = len(cats)
    if n == 0 or not noms:
        return vide()
    libelles = [_libelle(c, temporel) for c in cats]
    couleurs = couleurs or {}
    coul = {k: couleurs.get(k, PALETTE[j % len(PALETTE)]) for j, k in enumerate(noms)}
    tot = [sum(vals[k][i] for k in noms) for i in range(n)]
    rep_vals = [float(x) for v in rep.values() for x in v if not _nan(x)]
    ymax = max([max(tot) if empile else max((max(v) for v in vals.values()), default=0)] + rep_vals) or 1.0
    fmt_l = fmt_ligne or fmt

    bande = 0.0
    if lig:  # la courbe occupe une bande au-dessus des barres : les étiquettes ne se chevauchent pas
        bande = (hauteur - HAUT) * 0.32
    zone = hauteur - HAUT - bande
    grp = 62 if n > 3 else 40  # largeur du groupe de barres (% de la colonne)
    montrer = etiquettes and (n * (1 if empile else len(noms)) <= 36)

    # Position verticale des points de la courbe (px depuis le haut)
    pts_l = {}
    for nom, valeurs in lig.items():
        pts = [None if _nan(v) else float(v) for v in valeurs]
        ok = [p for p in pts if p is not None]
        if ok:
            lo, hi = min(min(ok), 0), max(ok)
            ech = (hi - lo) or 1
            pts_l[nom] = (pts, [None if p is None else HAUT - 4 + (1 - (p - lo) / ech) * (bande - 16) for p in pts])

    colonnes = []
    for i in range(n):
        infos = [libelles[i], survol[i] if survol else None]
        infos += [f"{k} : {fmt(vals[k][i])}" for k in noms]
        if empile and len(noms) > 1:
            infos.append(f"Total : {fmt(tot[i])}")
        infos += [f"{k} : {fmt(v[i])}" for k, v in rep.items() if not _nan(v[i])]
        infos += [f"{k} : {fmt_l(pts[i])}" for k, (pts, _) in pts_l.items() if pts[i] is not None]
        corps = []
        if empile:
            segs = []
            plusieurs = sum(1 for k in noms if vals[k][i] > 0) > 1  # une seule part : le total suffit
            for k in noms:
                h = vals[k][i] / ymax * zone
                if h <= 0:
                    continue
                txt = fmt(vals[k][i]) if montrer and plusieurs and h >= 17 else ""
                segs.append(f'<i style="height:{h:.1f}px;background:{coul[k]}">{txt}</i>')
            haut_txt = fmt(tot[i]) if montrer and tot[i] else ""
            corps.append(f'<div class="bw"><b>{haut_txt}</b><div class="stk">{"".join(segs)}</div></div>')
        else:
            for k in noms:
                v = vals[k][i]
                h = v / ymax * zone
                c = couleurs_barres[i] if couleurs_barres is not None and len(noms) == 1 else coul[k]
                corps.append(f'<div class="bw"><b>{fmt(v) if montrer and v else ""}</b>'
                             f'<i class="b" style="height:{max(h, 0):.1f}px;background:{c}"></i></div>')
        extra = []
        for k, v in rep.items():
            if not _nan(v[i]):
                extra.append(f'<i class="rp" style="bottom:{float(v[i]) / ymax * zone:.1f}px"></i>')
        for j, (k, (pts, ys)) in enumerate(pts_l.items()):
            if ys[i] is None:
                continue
            cl = couleur_ligne if j == 0 else PALETTE[(j + 3) % len(PALETTE)]
            extra.append(f'<i class="pt" style="top:{ys[i]:.1f}px;background:{cl}"></i>')
            if montrer:
                extra.append(f'<span class="pl" style="top:{ys[i] - 19:.1f}px;color:{cl}">{fmt_l(pts[i])}</span>')
        colonnes.append(f'<div class="col{_cote(i, n)}"{_tip(infos)}>'
                        f'<div class="grp" style="width:{grp}%">{"".join(corps)}</div>{"".join(extra)}</div>')

    traces = []
    for j, (k, (pts, ys)) in enumerate(pts_l.items()):
        cl = couleur_ligne if j == 0 else PALETTE[(j + 3) % len(PALETTE)]
        p = " ".join(f"{(i + .5) / n * 100:.3f},{y:.1f}" for i, y in enumerate(ys) if y is not None)
        traces.append(f'<polyline points="{p}" fill="none" stroke="{cl}" stroke-width="2.5" stroke-linejoin="round" '
                      f'vector-effect="non-scaling-stroke"/>')
    svg = (f'<svg class="ov" viewBox="0 0 100 {hauteur}" preserveAspectRatio="none">{"".join(traces)}</svg>'
           if traces else "")
    xl, tourner = _etiquettes_x(libelles, temporel)
    plot = (f'<div class="s360-plot" style="height:{hauteur}px"><div class="cols" style="grid-template-columns:'
            f'repeat({n},minmax(0,1fr))">{"".join(colonnes)}</div>{svg}</div>{xl}')
    if tourner:  # marge à gauche : la première étiquette inclinée n'est pas coupée
        plot = f'<div class="s360-rotpad">{plot}</div>'
    leg = [(k, coul[k], "barre") for k in noms] if couleurs_barres is None else []
    leg += [(k, COLORS["text"], "repere") for k in rep]
    leg += [(k, couleur_ligne if j == 0 else PALETTE[(j + 3) % len(PALETTE)], "ligne") for j, k in enumerate(pts_l)]
    lg_html = legende(leg) if legende_auto and (len(noms) > 1 or rep or pts_l) else ""
    return f'<div class="s360-chart">{_titre(titre)}{plot}{lg_html}</div>'


def ecarts(cats, valeurs, infos=None, seuil=10, titre="", hauteur=250, fmt=jours) -> str:
    """Barres positives / négatives autour de zéro (ex. écart promis − demandé, en jours).

    Couleur : rouge au-delà de `seuil`, orange entre 1 et `seuil`, vert si ≤ 0.
    `infos` : lignes de détail par barre (infobulle).
    """
    cats = [str(c) for c in cats]
    vals = [0.0 if _nan(v) else float(v) for v in valeurs]
    n = len(cats)
    if n == 0:
        return vide()
    hi, lo = max(max(vals), 0), min(min(vals), 0)
    ech = (hi - lo) or 1
    zone = hauteur - HAUT - (HAUT if lo < 0 else 2)  # marge basse seulement s'il y a des valeurs négatives
    zero = HAUT + hi / ech * zone  # position de l'axe zéro (px depuis le haut)
    montrer = n <= 40
    colonnes = []
    for i, v in enumerate(vals):
        c = COLORS["ko"] if v > seuil else COLORS["warn"] if v > 0 else COLORS["ok"]
        h = abs(v) / ech * zone
        top = zero - h if v > 0 else zero
        txt = f'<span class="pv" style="top:{(top - 18 if v > 0 else zero + h + 2):.1f}px">{fmt(v)}</span>' if montrer else ""
        detail = infos[i] if infos is not None else []
        colonnes.append(f'<div class="col{_cote(i, n)}"{_tip([cats[i], *detail, f"Écart : {fmt(v)}"])}>'
                        f'<i class="bz" style="top:{top:.1f}px;height:{max(h, 1.5):.1f}px;background:{c}"></i>{txt}</div>')
    axe = f'<div class="zero" style="top:{zero:.1f}px"></div>'
    xl = ""
    if n <= 30:
        xl, tourner = _etiquettes_x(cats)
    plot = (f'<div class="s360-plot nob" style="height:{hauteur}px">{axe}<div class="cols" style="grid-template-columns:'
            f'repeat({n},minmax(0,1fr))">{"".join(colonnes)}</div></div>{xl}')
    if xl and tourner:
        plot = f'<div class="s360-rotpad">{plot}</div>'
    leg = legende([(f"Plus de {seuil} j de retard", COLORS["ko"], "barre"), (f"1 à {seuil} j", COLORS["warn"], "barre"),
                   ("À l'heure ou en avance", COLORS["ok"], "barre")])
    return f'<div class="s360-chart">{_titre(titre)}{plot}{leg}</div>'


def multiples(panneaux: dict, couleurs: dict | None = None, hauteur=140, fmt=court, titre="") -> str:
    """Petits multiples : {titre: (catégories, valeurs)}, une mini-série de barres par panneau."""
    if not panneaux:
        return vide()
    couleurs = couleurs or {}
    cartes = []
    for i, (t, (cats, vals)) in enumerate(panneaux.items()):
        c = couleurs.get(t, PALETTE[i % len(PALETTE)])
        cartes.append(f'<div class="s360-mini"><b>{escape(str(t))}</b>'
                      f'{barres(cats, {str(t): vals}, {str(t): c}, hauteur=hauteur, fmt=fmt, legende_auto=False)}</div>')
    return f'<div class="s360-chart">{_titre(titre)}<div class="s360-minis">{"".join(cartes)}</div></div>'


# --------------------------------------------------------------------------
# Barres horizontales simples (classements)
# --------------------------------------------------------------------------
def barres_h(lignes, couleur=COLORS["navy_2"], fmt=court, titre="", max_lignes=12, **_) -> str:
    """lignes : [(libellé, valeur)], [(libellé, valeur, texte affiché)] ou [(libellé, valeur, texte, couleur)]."""
    lignes = list(lignes)[:max_lignes]
    if not lignes:
        return vide()
    vmax = max((float(l[1]) for l in lignes if not _nan(l[1])), default=0) or 1
    rows = []
    for l in lignes:
        nom, v = l[0], l[1]
        txt = l[2] if len(l) > 2 and l[2] is not None else fmt(v)
        c = l[3] if len(l) > 3 else couleur
        pct = 0 if _nan(v) or not float(v) else max(float(v) / vmax * 100, 1.5)
        rows.append(f'<div class="rw"{_tip([nom, txt])}><span class="nm">{escape(str(nom))}</span>'
                    f'<div class="bar"><i style="width:{pct:.1f}%;--tone:{c}"></i></div><b>{escape(str(txt))}</b></div>')
    return f'<div class="s360-chart">{_titre(titre)}<div class="s360-rows">{"".join(rows)}</div></div>'


# --------------------------------------------------------------------------
# Barres 100 % (répartition par ligne)
# --------------------------------------------------------------------------
def parts(tableau, couleurs: dict, titre="", afficher="nombre", **_) -> str:
    """`tableau` : DataFrame (lignes = catégories, colonnes = statuts) de comptages ou de valeurs."""
    if tableau is None or tableau.empty or float(tableau.to_numpy().sum()) == 0:
        return vide()
    rows = []
    for idx, r in tableau.iterrows():
        total = float(r.sum())
        segs = []
        for col, v in r.items():
            v = float(v)
            if v <= 0 or total <= 0:
                continue
            p = v / total * 100
            txt = (f"{p:.0f} %" if afficher == "pourcent" else court(v)) if p >= 7 else ""
            segs.append(f'<span style="width:{p:.2f}%;background:{couleurs.get(col, COLORS["gris"])}"'
                        f'{_tip([f"{idx} · {col}", f"{court(v)} ({p:.0f} %)"])}>{txt}</span>')
        rows.append(f'<div class="rw"><span class="nm" title="{escape(str(idx))}">{escape(str(idx))}</span>'
                    f'<div class="s360-stack">{"".join(segs)}</div></div>')
    leg = legende([(c, couleurs.get(c, COLORS["gris"]), "barre") for c in tableau.columns])
    return f'<div class="s360-chart">{_titre(titre)}<div class="s360-share">{"".join(rows)}</div>{leg}</div>'


# --------------------------------------------------------------------------
# Jauges horizontales : segments empilés + repère (objectif), même échelle pour toutes les lignes
# --------------------------------------------------------------------------
def jauges(lignes, titre="", legende_items=None, repere_nom="Objectif", fmt=court, hauteur_max: str | None = None) -> str:
    """lignes : [(libellé, [(nom, valeur, couleur)], repère ou None, texte à droite[, lignes d'infobulle en plus])].

    Les segments sont empilés de gauche à droite ; le repère est un trait vertical (ex. objectif d'avions).
    `hauteur_max` : zone défilante (beaucoup de lignes).
    """
    lignes = list(lignes)
    if not lignes:
        return vide()
    vmax = max(max(sum(max(float(v), 0) for _, v, _ in l[1]), float(l[2]) if not _nan(l[2]) else 0) for l in lignes) or 1
    rows = []
    for nom, segs, rep, txt, *plus in lignes:
        parts_ = []
        tip = [nom]
        for n, v, c in segs:
            v = max(float(v), 0)
            tip.append(f"{n} : {fmt(v)}")
            if v <= 0:
                continue
            w = v / vmax * 100
            parts_.append(f'<span style="width:{w:.2f}%;background:{c}">{fmt(v) if w >= 6 else ""}</span>')
        marque = ""
        if not _nan(rep):
            tip.append(f"{repere_nom} : {fmt(rep)}")
            marque = f'<i class="rp" style="left:{float(rep) / vmax * 100:.2f}%"></i>'
        tip += list(plus[0]) if plus else []
        rows.append(f'<div class="rw"{_tip(tip)}><span class="nm" title="{escape(str(nom))}">{escape(str(nom))}</span>'
                    f'<div class="trk">{"".join(parts_)}{marque}</div><b>{escape(str(txt))}</b></div>')
    corps = f'<div class="s360-jauge">{"".join(rows)}</div>'
    if hauteur_max:
        corps = f'<div class="s360-jauge-scroll" style="max-height:{hauteur_max}">{corps}</div>'
    items = list(legende_items or [])
    return f'<div class="s360-chart">{_titre(titre)}{corps}{legende(items)}</div>'


# --------------------------------------------------------------------------
# Carte de chaleur
# --------------------------------------------------------------------------
def chaleur(tableau, titre="", couleur=(31, 78, 156), libelle="lignes", hauteur_max: str | None = None) -> str:
    """Carte de chaleur HTML : lignes × colonnes, intensité proportionnelle à la valeur.

    `hauteur_max` (ex. "30rem") : zone défilante dont la ligne d'en-tête (colonnes) reste figée en haut.
    """
    if tableau is None or tableau.empty:
        return vide()
    vmax = float(tableau.to_numpy().max()) or 1
    r, g, b = couleur
    tete = "".join(f"<th>{escape(str(c))}</th>" for c in tableau.columns)
    lignes = []
    for idx, row in tableau.iterrows():
        cells = []
        for col, v in row.items():
            v = float(v)
            a = 0 if v <= 0 else .15 + .85 * v / vmax
            fg = "#fff" if a > .55 else COLORS["text"]
            cells.append(f'<td style="background:rgba({r},{g},{b},{a:.2f});color:{fg}"'
                         f'{_tip([idx, f"{col} : {entier(v)} {libelle}"])}>{court(v) if v else ""}</td>')
        lignes.append(f'<tr><th class="f" title="{escape(str(idx))}">{escape(str(idx))}</th>{"".join(cells)}</tr>')
    table = f'<table class="s360-heat"><thead><tr><th></th>{tete}</tr></thead><tbody>{"".join(lignes)}</tbody></table>'
    if hauteur_max:
        table = f'<div class="s360-heat-scroll" style="max-height:{hauteur_max}">{table}</div>'
    return f'<div class="s360-chart">{_titre(titre)}{table}</div>'

