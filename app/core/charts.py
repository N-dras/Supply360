"""Graphes SVG / HTML légers, dans le style du prototype Supply360.

Fonctions pures : elles renvoient du HTML à afficher avec `st.html`. Aucune dépendance
(plotly n'est plus chargé : le premier lancement est plus rapide). Les positions horizontales
sont en %, les textes gardent donc une taille fixe (en rem) quelle que soit la largeur.
"""

import math
from html import escape

from core.style import COLORS

PALETTE = [COLORS["navy_2"], "#2A9D8F", "#F4A259", "#BC4B51", COLORS["violet"], "#8AB17D", COLORS["gris"]]
FS = "font-size:.8125rem"


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


def _titre(t):
    return f"<h5>{escape(t)}</h5>" if t else ""


def legende(items) -> str:
    """items : [(libellé, couleur, 'barre' | 'ligne')]."""
    if not items:
        return ""
    spans = "".join(f'<span><i class="{"ln" if k == "ligne" else ""}" style="background:{c}"></i>{escape(str(n))}</span>'
                    for n, c, k in items)
    return f'<div class="s360-legend">{spans}</div>'


def vide(message="Aucune donnée à afficher") -> str:
    return f'<div class="s360-chart"><p style="color:{COLORS["muted"]};margin:.6rem 0">{escape(message)}</p></div>'


def _etiquettes_x(cats, tourner):
    cls = "s360-xl rot" if tourner else "s360-xl"
    spans = "".join(f'<span title="{escape(c)}">{escape(c)}</span>' for c in cats)
    return f'<div class="{cls}" style="grid-template-columns:repeat({len(cats)},minmax(0,1fr))">{spans}</div>'


# --------------------------------------------------------------------------
# Barres verticales (groupées ou empilées) + courbe optionnelle
# --------------------------------------------------------------------------
def barres(cats, series: dict, couleurs: dict | None = None, empile=False, ligne: dict | None = None,
           couleur_ligne=COLORS["text"], fmt=court, fmt_ligne=None, hauteur=230, titre="", survol=None,
           legende_auto=True, etiquettes=True) -> str:
    """Barres avec valeurs affichées ; `ligne` = {nom: valeurs} tracée sur sa propre échelle."""
    cats = [str(c) for c in cats]
    n = len(cats)
    if n == 0 or not series:
        return vide()
    couleurs = couleurs or {}
    noms = list(series)
    vals = {k: [0.0 if _nan(v) else float(v) for v in series[k]] for k in noms}
    tot = [sum(vals[k][i] for k in noms) for i in range(n)]
    ymax = max(tot) if empile else max((max(v) for v in vals.values()), default=0)
    ymax = ymax or 1.0
    haut, bas = 22, 2
    zone = hauteur - haut - bas
    bande = 0.0
    if ligne:  # la courbe occupe une bande au-dessus des barres : les étiquettes ne se chevauchent plus
        bande = zone * 0.36
        zone -= bande
    slot = 100 / n
    largeur_groupe = slot * (0.62 if n > 3 else 0.42)
    lg = largeur_groupe if empile else largeur_groupe / len(noms)
    opacite = ".5" if ligne else "1"
    els = [f'<line x1="0" x2="100%" y1="{hauteur - bas}" y2="{hauteur - bas}" stroke="{COLORS["grid"]}"/>']
    for i, cat in enumerate(cats):
        x0 = slot * i + (slot - largeur_groupe) / 2
        y_cumul = hauteur - bas
        for j, k in enumerate(noms):
            v = vals[k][i]
            h = v / ymax * zone
            coul = couleurs.get(k, PALETTE[j % len(PALETTE)])
            x = x0 if empile else x0 + j * lg
            y = y_cumul - h if empile else hauteur - bas - h
            info = escape(f"{cat} · {k} : {fmt(v)}" + (f" — {survol[i]}" if survol else ""))
            els.append(f'<rect x="{x:.3f}%" y="{y:.1f}" width="{max(lg - .25, .2):.3f}%" height="{max(h, 0):.1f}" rx="3" '
                       f'fill="{coul}" opacity="{opacite}"><title>{info}</title></rect>')
            if etiquettes and v:
                cx = x + lg / 2
                if empile:
                    if h >= 15:
                        els.append(f'<text x="{cx:.3f}%" y="{y + h / 2 + 4:.1f}" text-anchor="middle" fill="#fff" '
                                   f'style="{FS};font-weight:700">{fmt(v)}</text>')
                else:
                    els.append(f'<text x="{cx:.3f}%" y="{y - 5:.1f}" text-anchor="middle" fill="{COLORS["text"]}" '
                               f'style="{FS};font-weight:700">{fmt(v)}</text>')
            if empile:
                y_cumul -= h
        if empile and etiquettes and len(noms) > 1 and tot[i]:
            els.append(f'<text x="{x0 + largeur_groupe / 2:.3f}%" y="{y_cumul - 5:.1f}" text-anchor="middle" '
                       f'fill="{COLORS["text"]}" style="{FS};font-weight:800">{fmt(tot[i])}</text>')
    leg = [(k, couleurs.get(k, PALETTE[j % len(PALETTE)]), "barre") for j, k in enumerate(noms)]
    if ligne:
        fmt_l = fmt_ligne or fmt
        for j, (nom, valeurs) in enumerate(ligne.items()):
            coul = couleur_ligne if j == 0 else PALETTE[(j + 3) % len(PALETTE)]
            pts = [None if _nan(v) else float(v) for v in valeurs]
            ok = [p for p in pts if p is not None]
            if not ok:
                continue
            lo, hi = min(min(ok), 0), max(ok)
            ech = (hi - lo) or 1
            ypos = [None if p is None else haut + 6 + (1 - (p - lo) / ech) * (bande - 14) for p in pts]
            for i in range(n - 1):
                if ypos[i] is not None and ypos[i + 1] is not None:
                    els.append(f'<line x1="{slot * (i + .5):.3f}%" x2="{slot * (i + 1.5):.3f}%" y1="{ypos[i]:.1f}" '
                               f'y2="{ypos[i + 1]:.1f}" stroke="{coul}" stroke-width="2.5" stroke-linecap="round"/>')
            for i, yp in enumerate(ypos):
                if yp is None:
                    continue
                els.append(f'<circle cx="{slot * (i + .5):.3f}%" cy="{yp:.1f}" r="3.5" fill="{coul}">'
                           f'<title>{escape(f"{cats[i]} · {nom} : {fmt_l(pts[i])}")}</title></circle>')
                els.append(f'<text x="{slot * (i + .5):.3f}%" y="{yp - 8:.1f}" text-anchor="middle" fill="{coul}" '
                           f'style="{FS};font-weight:800">{fmt_l(pts[i])}</text>')
            leg.append((nom, coul, "ligne"))
    tourner = n > 7 or max(len(c) for c in cats) > 12
    svg = f'<svg height="{hauteur}" role="img">{"".join(els)}</svg>'
    lg_html = legende(leg) if legende_auto and (len(noms) > 1 or ligne) else ""
    corps = f"{svg}{_etiquettes_x(cats, tourner)}"
    if tourner:  # marge à gauche : la première étiquette inclinée n'est pas coupée
        corps = f'<div class="s360-rotpad">{corps}</div>'
    return f'<div class="s360-chart">{_titre(titre)}{corps}{lg_html}</div>'


def multiples(panneaux: dict, couleurs: dict | None = None, hauteur=170, fmt=court, titre="") -> str:
    """Petits multiples : {titre: (catégories, valeurs)}, une mini-série de barres par panneau."""
    if not panneaux:
        return vide()
    couleurs = couleurs or {}
    cartes = []
    for i, (t, (cats, vals)) in enumerate(panneaux.items()):
        coul = couleurs.get(t, PALETTE[i % len(PALETTE)])
        cartes.append(f'<div class="s360-mini"><b>{escape(str(t))}</b>'
                      f'{barres(cats, {str(t): vals}, {str(t): coul}, hauteur=hauteur, fmt=fmt, legende_auto=False)}</div>')
    return f'<div class="s360-chart">{_titre(titre)}<div class="s360-minis">{"".join(cartes)}</div></div>'


# --------------------------------------------------------------------------
# Barres horizontales simples (classements)
# --------------------------------------------------------------------------
def barres_h(lignes, couleur=COLORS["navy_2"], fmt=court, titre="", max_lignes=12) -> str:
    """lignes : [(libellé, valeur)], [(libellé, valeur, texte affiché)] ou [(libellé, valeur, texte, couleur)]."""
    lignes = list(lignes)[:max_lignes]
    if not lignes:
        return vide()
    vmax = max((float(l[1]) for l in lignes if not _nan(l[1])), default=0) or 1
    rows = []
    for l in lignes:
        nom, v = l[0], l[1]
        txt = l[2] if len(l) > 2 and l[2] is not None else fmt(v)
        coul = l[3] if len(l) > 3 else couleur
        pct = 0 if _nan(v) or not float(v) else max(float(v) / vmax * 100, 1.5)
        rows.append(f'<div class="rw"><span class="nm" title="{escape(str(nom))}">{escape(str(nom))}</span>'
                    f'<div class="bar"><i style="width:{pct:.1f}%;--tone:{coul}"></i></div><b>{escape(str(txt))}</b></div>')
    return f'<div class="s360-chart">{_titre(titre)}<div class="s360-rows">{"".join(rows)}</div></div>'


# --------------------------------------------------------------------------
# Barres 100 % (répartition par ligne)
# --------------------------------------------------------------------------
def parts(tableau, couleurs: dict, titre="", afficher="nombre") -> str:
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
            info = escape(f"{idx} · {col} : {court(v)} ({p:.0f} %)")
            segs.append(f'<span style="width:{p:.2f}%;background:{couleurs.get(col, COLORS["gris"])}" title="{info}">{txt}</span>')
        rows.append(f'<div class="rw"><span class="nm" title="{escape(str(idx))}">{escape(str(idx))}</span>'
                    f'<div class="s360-stack">{"".join(segs)}</div></div>')
    leg = legende([(c, couleurs.get(c, COLORS["gris"]), "barre") for c in tableau.columns])
    return f'<div class="s360-chart">{_titre(titre)}<div class="s360-share">{"".join(rows)}</div>{leg}</div>'


# --------------------------------------------------------------------------
# Anneaux de progression et carte de chaleur
# --------------------------------------------------------------------------
def anneau(valeur, libelle, couleur=None, taille=76, suffixe="%") -> str:
    v = 0 if _nan(valeur) else max(0.0, min(float(valeur), 100.0))
    couleur = couleur or (COLORS["ok"] if v >= 93 else COLORS["warn"] if v >= 80 else COLORS["ko"])
    return (f'<div class="s360-ring"><svg width="{taille}" height="{taille}" viewBox="0 0 36 36">'
            f'<circle cx="18" cy="18" r="15.9" fill="none" stroke="{COLORS["grid"]}" stroke-width="3.5"/>'
            f'<circle cx="18" cy="18" r="15.9" fill="none" stroke="{couleur}" stroke-width="3.5" stroke-linecap="round" '
            f'stroke-dasharray="{v:.1f} 100" transform="rotate(-90 18 18)"/>'
            f'<text x="18" y="21" text-anchor="middle" style="font-size:8.5px;font-weight:800" fill="{COLORS["text"]}">'
            f'{v:.0f}{suffixe}</text></svg><div>{escape(libelle)}</div></div>')


def anneaux(items) -> str:
    return f'<div class="s360-rings">{"".join(items)}</div>'


def chaleur(tableau, titre="", couleur=(31, 78, 156)) -> str:
    """Carte de chaleur HTML : lignes × colonnes, intensité proportionnelle à la valeur."""
    if tableau is None or tableau.empty:
        return vide()
    vmax = float(tableau.to_numpy().max()) or 1
    r, g, b = couleur
    tete = "".join(f"<th>{escape(str(c))}</th>" for c in tableau.columns)
    lignes = []
    for idx, row in tableau.iterrows():
        cells = []
        for v in row:
            v = float(v)
            a = 0 if v <= 0 else .15 + .85 * v / vmax
            fg = "#fff" if a > .55 else COLORS["text"]
            cells.append(f'<td style="background:rgba({r},{g},{b},{a:.2f});color:{fg}">{court(v) if v else ""}</td>')
        lignes.append(f'<tr><th class="f" title="{escape(str(idx))}">{escape(str(idx))}</th>{"".join(cells)}</tr>')
    return (f'<div class="s360-chart">{_titre(titre)}<div class="s360-scroll"><table class="s360-heat">'
            f'<tr><th></th>{tete}</tr>{"".join(lignes)}</table></div></div>')
