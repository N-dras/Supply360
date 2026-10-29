"""Composants visuels réutilisables (charte Supply360, prototype v3).

Les fonctions qui renvoient du HTML (`kpi_card`, `badge`…) sont pures ; celles qui
dessinent (`header`, `section`, `kpi_grid`…) appellent Streamlit.
"""

from contextlib import contextmanager, nullcontext
from datetime import date
from html import escape

import numpy as np
import pandas as pd
import streamlit as st

from core import dossiers
from core import io as sio
from core.icones import ICONES, ic
from core.style import ONGLETS, teinte

# Tons : (couleur du trait / de l'icône, couleur du chiffre, fond teinté) — palette de core/style.py
TONES = {
    "navy": ("#1F4E9C", "#002157", "#EAF0FA"), "info": ("#2B6CB0", "#2B6CB0", "#E9F1FA"),
    "accent": ("#E4002B", "#C1002A", "#FDE8EC"), "ok": ("#1E8E5A", "#17784B", "#E6F4EC"),
    "warn": ("#DBA100", "#A36F00", "#FDF6DD"), "orange": ("#E8590C", "#C2410C", "#FDF0E7"),
    "ko": ("#A61B1B", "#A61B1B", "#FBECEC"), "muted": ("#8A94A6", "#5B6478", "#EEF1F5"),
    "violet": ("#7B61C9", "#6247B3", "#F1EDFB"), "teal": ("#2A9D8F", "#1F7A6F", "#E5F4F2"),
}
ICONE_TON = {"navy": "layers", "info": "info", "accent": "flag", "ok": "check-circle", "warn": "clock", "orange": "send",
             "ko": "alert", "muted": "help", "violet": "pause", "teal": "package"}
# Emojis encore passés par les modules → icônes vectorielles
EMOJIS = {"📌": "flag", "🚨": "flag", "💤": "moon", "✅": "check-circle", "⚠️": "alert", "ℹ️": "info", "⛔": "x", "🔴": "alert",
          "📦": "package", "🏭": "factory", "🐢": "clock", "🧮": "grid", "📥": "inbox", "✈️": "plane", "📅": "calendar",
          "🛠️": "wrench", "🧵": "scissors", "🪑": "armchair", "🔔": "bell", "📈": "trend", "📊": "grid"}
CHANTIER_STATUTS = {"Terminé": "muted", "En cours": "info", "À venir": "ok"}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _tone(tone: str) -> tuple[str, str, str]:
    return TONES.get(tone, TONES["navy"])


def _vars(tone: str) -> str:
    c, t, f = _tone(tone)
    return f"--c:{c};--t:{t};--f:{f}"


def _icone(icone: str) -> str:
    """SVG d'une icône (nom du jeu core/icones, ou emoji connu) ; à défaut, le texte tel quel."""
    nom = EMOJIS.get(icone, icone)
    return ic(nom) if nom in ICONES else f"<span>{escape(icone)}</span>"


# --------------------------------------------------------------------------
# Structure de page
# --------------------------------------------------------------------------
def header() -> None:
    """Header fixe : logo AFI (fond clair : le logo est transparent), Supply360, état du moteur, date du jour.

    La navigation entre onglets (main.py) est positionnée dans ce header par le CSS.
    """
    j = date.today()
    st.html(
        '<div class="s360-header"><div class="s360-logo" role="img" '
        'aria-label="Air France Industries KLM Engineering &amp; Maintenance"></div><span class="s360-sep"></span>'
        '<div class="s360-brand">Supply<span>360</span></div>'
        f'<div class="s360-today"><span class="s360-moteur"><i></i>Prêt</span>{ic("calendar")}{JOURS[j.weekday()]} {j:%d/%m/%Y}</div></div>'
        '<div class="s360-busy">Calcul en cours…</div>'
    )


def contexte(*blocs: tuple[str, str, str]) -> str:
    """Encadré de contexte de l'en-tête de page : (libellé, valeur, badge facultatif) par bloc."""
    html = ""
    for lbl, val, extra in blocs:
        html += (f'<div class="bloc"><span class="lbl">{escape(lbl)}</span><span class="val">{escape(val)}</span>'
                 f'{extra}</div>')
    return f'<div class="s360-contexte">{html}</div>'


def hero(icone: str, titre: str, sous_titre: str = "", surtitre: str = "", contexte_html: str = "") -> None:
    """En-tête de page : bandeau léger à la couleur de l'onglet, icône, titre, et à droite un encadré de contexte
    (chantier, date des données…). Couleur et icône : core/style.ONGLETS (onglet actif)."""
    couleur, nom_icone = ONGLETS.get(st.session_state.get("active_tab", ""), ("#1F4E9C", ""))
    sub = f'<p class="sous">{escape(sous_titre)}</p>' if sous_titre else ""
    sur = f'<p class="surtitre">{escape(surtitre)}</p>' if surtitre else ""
    st.markdown(f'<div class="s360-hero" style="--onglet:{couleur}"><div class="gauche"><div class="ico">{_icone(nom_icone or icone)}</div>'
                f'<div>{sur}<h1>{escape(titre)}</h1>{sub}</div></div>{contexte_html}</div>', unsafe_allow_html=True)


def _tete(title: str, subtitle: str, tag: str) -> str:
    sub = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    tg = f'<span class="tag">{escape(tag)}</span>' if tag else ""
    return f'<div class="s360-section-head"><div><h3>{escape(title)}{tg}</h3>{sub}</div></div>'


@contextmanager
def section(key: str, title: str, subtitle: str = "", tag: str = "", export=None, carte: bool = True):
    """Bloc : titre, sous-titre et compteur (`tag`) ; carte blanche, ou bloc sans fond (`carte=False`, ex. tuiles).
    `export` = (fonction, nom de fichier, clé) : bouton « Exporter (Excel) » à droite du titre. `key` unique (TAB_ID)."""
    box = st.container(key=f"{'s360sec' if carte else 's360bloc'}_{key}")
    with box:
        if export:
            with st.container(key=f"s360tete_{key}"):
                a, b = st.columns([5, 1.3], vertical_alignment="bottom")
                a.html(_tete(title, subtitle, tag))
                with b:
                    telecharger(*export)
        elif title or subtitle:
            st.html(_tete(title, subtitle, tag))
        yield box


def footer() -> None:
    st.html('<div class="s360-footer">Supply360 · Air France Industries — fichiers traités localement dans votre navigateur, '
            "rien n'est envoyé. Rafraîchir la page réinitialise la session.</div>")


def en_developpement(icone: str, titre: str, points: list[str]) -> None:
    """Page d'un onglet prévu mais pas encore développé."""
    items = "".join(f"<li>{escape(p)}</li>" for p in points)
    st.markdown(f'<div class="s360-wip"><div class="plane"></div><div class="ico">{_icone(icone)}</div><h2>{escape(titre)}</h2>'
                f'{badge("En cours de développement", "warn")}'
                f"<p>Cette fonctionnalité arrive dans une prochaine version de Supply360.</p><ul>{items}</ul></div>",
                unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Indicateurs
# --------------------------------------------------------------------------
def kpi_card(label: str, value, sub: str = "", tone: str = "navy", icone: str | None = None, note: str = "") -> str:
    """HTML d'une tuile KPI (à passer à `kpi_grid`) : icône teintée, libellé, chiffre coloré, précision."""
    sub_html = f'<div class="sub">{escape(str(sub))}</div>' if sub else ""
    note_html = f'<span class="note">{escape(note)}</span>' if note else ""
    return (f'<div class="s360-kpi" style="{_vars(tone)}"><div class="t"><span class="pastille">{_icone(icone or ICONE_TON.get(tone, "layers"))}'
            f'</span><span>{escape(str(label))}</span>{note_html}</div><div class="val">{escape(str(value))}</div>{sub_html}</div>')


def kpi_repartition(label: str, total, unite: str, segments: list[tuple[str, float, str]], note: str = "",
                    icone: str = "layers", tone: str = "navy") -> str:
    """Grande tuile (2 colonnes) : total, barre de répartition (segments (libellé, valeur, couleur)) et légende chiffrée."""
    somme = sum(v for _, v, _ in segments) or 1
    barre = "".join(f'<span style="flex:{v};background:{c}" data-tip="{escape(lib)} : {_nombre(v)} ({v / somme:.0%})"></span>'
                    for lib, v, c in segments if v)
    leg = "".join(f'<li><i style="background:{c}"></i>{escape(lib)} <b>{_nombre(v)}</b></li>' for lib, v, c in segments)
    note_html = f'<span class="note">{escape(note)}</span>' if note else ""
    return (f'<div class="s360-kpi large" style="{_vars(tone)}"><div class="t"><span class="pastille">{_icone(icone)}</span>'
            f'<span>{escape(label)}</span>{note_html}</div><div class="val">{escape(str(total))} <small>{escape(unite)}</small></div>'
            f'<div class="s360-repart" role="img" aria-label="Répartition">{barre}</div><ul class="s360-leg">{leg}</ul></div>')


def kpi_grid(cards: list[str]) -> None:
    st.markdown(f'<div class="s360-kpis">{"".join(cards)}</div>', unsafe_allow_html=True)


def valeurs(items: list[tuple[str, str, str]]) -> None:
    """Bandeau de chiffres côte à côte : (libellé, valeur, précision)."""
    st.html('<div class="s360-valeurs">' + "".join(f"<div><span>{escape(a)}</span><b>{escape(b)}</b><small>{escape(c)}</small></div>"
                                                   for a, b, c in items) + "</div>")


def badge(text: str, tone: str = "navy", couleur: str | None = None) -> str:
    """Badge de statut : pastille de couleur + libellé (la couleur n'est jamais seule)."""
    c, _, f = _tone(tone)
    if couleur:
        c, f = couleur, "#" + teinte(couleur)
    return f'<span class="s360-badge" style="--c:{c};--f:{f}"><i></i>{escape(text)}</span>'


def chantier_badge(statut: str, jours_avant_debut: int | None = None) -> str:
    """Badge de statut chantier : uniquement Terminé / En cours / À venir."""
    if statut not in CHANTIER_STATUTS:
        raise ValueError(f"Statut de chantier inconnu : {statut}")
    text = statut + (f" · J-{jours_avant_debut}" if statut == "À venir" and jours_avant_debut is not None else "")
    return badge(text, CHANTIER_STATUTS[statut])


def callout(message_html: str, tone: str = "navy", icon: str = "ℹ️") -> None:
    """Bandeau court (action à mener, alerte). `message_html` est du HTML de confiance."""
    st.markdown(f'<div class="s360-callout" style="{_vars(tone)}">{_icone(icon)}<div>{message_html}</div></div>',
                unsafe_allow_html=True)


def empty_state(title: str, message: str, etapes: list[tuple[str, bool]] | None = None, icon: str = "inbox") -> None:
    """État vide : explique quoi faire tant que les fichiers ne sont pas importés."""
    steps = "".join(f'<span class="s360-step{" ok" if ok else ""}">{ic("check") if ok else ic("plus")} {escape(lbl)}</span>'
                    for lbl, ok in etapes or [])
    st.markdown(f'<div class="s360-empty"><div class="ico">{_icone(icon)}</div><h4>{escape(title)}</h4><p>{escape(message)}</p>'
                f'<div class="s360-steps">{steps}</div></div>', unsafe_allow_html=True)


def tableau(df, **kwargs) -> None:
    """st.dataframe avec « — » à la place des textes vides (au lieu de « None »)."""
    texte = df.select_dtypes(include=["object", "string"]).columns
    if len(texte):
        df = df.copy()
        df[texte] = df[texte].astype(object).where(df[texte].notna(), "—")
    st.dataframe(df, hide_index=True, **kwargs)


def graphe(html: str, sous: str = "") -> None:
    """Graphe de core/charts.py dans sa carte (titre, sous-titre, boutons Agrandir / PNG ajoutés par build.py).
    st.markdown (et non st.html, qui supprime le SVG)."""
    if sous:
        html = html.replace("</h5>", f'</h5><p class="g-sous">{escape(sous)}</p>', 1)
    st.markdown(f'<div class="s360-graphe">{html}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Tableaux HTML (badges de statut, colonnes fixes, filtres dans la page)
# --------------------------------------------------------------------------
def _nombre(v) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return escape(str(v))
    if f != f:  # NaN
        return "—"
    return f"{f:,.0f}".replace(",", " ") if abs(f) >= 1000 or f.is_integer() else f"{f:,.1f}".replace(",", " ").replace(".", ",")


def _cellule(v, col: str, fort: set, euros: set) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return '<span class="vide">—</span>'
    if isinstance(v, (pd.Timestamp, date)):
        return f"{pd.Timestamp(v):%d/%m/%Y}"
    if isinstance(v, (bool, np.bool_)):
        return "Oui" if v else "Non"
    if isinstance(v, (int, float, np.integer, np.floating)):
        if col in euros:
            return escape(_euros(v))
        if float(v) == 0:
            return '<span class="zero">0</span>'
        txt = _nombre(v)
        return f'<span class="fort">{txt}</span>' if col in fort and float(v) > 0 else txt
    txt = str(v)
    return escape(txt) if txt.strip() else '<span class="vide">—</span>'


def _euros(v) -> str:
    f = float(v)
    return f"{f / 1e6:.1f} M€".replace(".", ",") if abs(f) >= 1e6 else (f"{f / 1e3:.0f} k€" if abs(f) >= 1e4 else f"{f:,.0f} €".replace(",", " "))


def tableau_html(df: pd.DataFrame, statut: str | None = None, couleurs: dict | None = None, num=(), fort=(), euros=(),
                 longs=(), pn=(), groupes=None, fixes: int = 0, marque: tuple[str, str] | None = None, filtres: bool = False,
                 cle: str = "", hauteur: str = "34rem", max_lignes: int = 400, colonne_config=None) -> None:
    """Tableau HTML lisible : statut en badge coloré (`statut`, `couleurs` = {valeur: couleur}), nombres alignés, zéros
    atténués, `fort` = quantités à traiter (rouge si > 0), `longs` = textes sur plusieurs lignes, `pn` = colonnes en
    gras, `fixes` = colonnes figées à gauche, `groupes` = [(titre, nb colonnes)] au-dessus des en-têtes, `marque` =
    (colonne booléenne, libellé) : étiquette rouge sous le statut. `filtres` : pastilles par statut au-dessus,
    filtrage dans la page (sans recalcul, JavaScript de build.py). Au-delà de `max_lignes`, st.dataframe."""
    if len(df) > max_lignes:
        tableau(df.drop(columns=[c for c in [marque[0] if marque else None] if c and c in df.columns]),
                column_config=colonne_config, height=440)
        return
    couleurs = couleurs or {}
    num, fort, euros, longs, pn = set(num) | set(fort) | set(euros), set(fort), set(euros), set(longs), set(pn)
    cols = [c for c in df.columns if not (marque and c == marque[0])]
    gauche, fixe_css = 0.0, []
    for i in range(fixes):  # largeur des colonnes figées : d'après le texte le plus long (badge du statut compris)
        textes = df[cols[i]].astype(str).str.len()
        w = min(22.0, max(6.0, 0.62 * max(int(textes.max() if len(textes) else 0), len(str(cols[i]))) + (3.2 if cols[i] == statut else 1.8)))
        fixe_css.append((f"left:{gauche}rem;min-width:{w}rem;max-width:{w}rem", i == fixes - 1))
        gauche += w
    def classe(i, c):
        k = ["num"] if c in num else []
        if i < fixes:
            k += ["fixe"] + (["dernier"] if fixe_css[i][1] else [])
        return " ".join(k)
    def style(i):
        return f' style="{fixe_css[i][0]}"' if i < fixes else ""
    tete = "".join(f'<th class="{classe(i, c)}{" cle" if c in fort else ""}"{style(i)}>{escape(str(c))}</th>' for i, c in enumerate(cols))
    grp = ""
    if groupes:
        grp = '<tr class="grp">' + "".join(f'<th colspan="{n}">{escape(g)}</th>' for g, n in groupes) + "</tr>"
    lignes = []
    for rec in df.itertuples(index=False):
        r = dict(zip(df.columns, rec))
        cellules = []
        for i, c in enumerate(cols):
            v = r[c]
            if c == statut:
                txt = "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)
                h = badge(txt, couleur=couleurs.get(txt, "#9AA5B1")) if txt else '<span class="vide">—</span>'
                if marque and bool(r.get(marque[0])):
                    h += f'<br><span class="s360-tag rouge">{ic("flag")}{escape(marque[1])}</span>'
            elif c in longs:
                h = f'<span class="long">{_cellule(v, c, fort, euros)}</span>'
            elif c in pn:
                h = f'<span class="pn">{_cellule(v, c, fort, euros)}</span>'
            else:
                h = _cellule(v, c, fort, euros)
            cellules.append(f'<td class="{classe(i, c)}"{style(i)}>{h}</td>')
        attrs = f' data-statut="{escape(str(r.get(statut, "")))}"' if statut else ""
        if marque and bool(r.get(marque[0])):
            attrs += ' class="marque"'
        lignes.append(f"<tr{attrs}>{''.join(cellules)}</tr>")
    barre = ""
    if filtres and statut:
        compte = df[statut].value_counts()
        compte = compte.reindex([v for v in couleurs if v in compte.index] + [v for v in compte.index if v not in couleurs])
        barre = (f'<div class="s360-filtres" data-table="s360t_{cle}"><button class="actif" data-f="">Tous <b>{len(df)}</b></button>'
                 + "".join(f'<button data-f="{escape(str(v))}" style="--c:{couleurs.get(v, "#9AA5B1")}"><i></i>{escape(str(v))} <b>{n}</b></button>'
                           for v, n in compte.items()) + "</div>")
    st.markdown(f'{barre}<div class="s360-tableau{" groupes" if groupes else ""}" style="--h:{hauteur}"><table id="s360t_{cle}">'
                f"<thead>{grp}<tr>{tete}</tr></thead><tbody>{''.join(lignes)}</tbody></table></div>", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Imports et téléchargements
# --------------------------------------------------------------------------
def _fichier_valide(f) -> bool:
    """Vrai pour un fichier réellement importé (Streamlit peut renvoyer un `DeletedFile` après un changement d'onglet)."""
    return f is not None and hasattr(f, "getvalue") and hasattr(f, "name")


def fichier(label: str, cle: str, types: list[str], colonnes: list[tuple[str, str, bool]] | None = None, on_import=None):
    """`file_uploader` dont le contenu survit au changement d'onglet. Renvoie (nom, octets) ou None.

    Streamlit efface un widget qui n'est pas affiché : sans cette mémoire, revenir sur un onglet
    obligeait à réimporter ses fichiers. La mémoire peut aussi être remplie par `import_groupe`.
    `on_import(nom)` est appelé (en callback) quand un nouveau fichier est importé ici.
    """
    # La clé du widget porte un numéro de version : vider_emplacement() l'incrémente pour effacer le fichier affiché.
    version = st.session_state.get(f"{cle}__v", 0)
    memoire, cle_up, vu = f"{cle}__data", f"{cle}__upload" + (str(version) if version else ""), f"{cle}__vu"

    def _maj():
        f = st.session_state.get(cle_up)
        if f is None:
            st.session_state.pop(memoire, None)   # l'utilisateur a retiré le fichier
        elif _fichier_valide(f):
            st.session_state[memoire] = (f.name, f.getvalue(), f.file_id)
            st.session_state[vu] = f.file_id
            # Zone d'import vidée (nouvelle version du widget) : Streamlit libère sa propre copie du fichier, seule
            # la mémoire ci-dessus reste (le fichier n'est plus gardé deux fois).
            vider_emplacement(cle, garder_donnees=True)
            if on_import:
                on_import(f.name)

    up = st.file_uploader(label, type=types, key=cle_up, on_change=_maj)
    garde = st.session_state.get(memoire)
    if _fichier_valide(up) and st.session_state.get(vu) != up.file_id:
        garde = st.session_state[memoire] = (up.name, up.getvalue(), up.file_id)
        st.session_state[vu] = up.file_id
    if garde and not (_fichier_valide(up) and up.file_id == garde[2]):
        st.markdown(f'<div class="s360-file">{ic("check")}<span>{escape(garde[0])}</span></div>', unsafe_allow_html=True)
    if colonnes:
        with st.popover("Colonnes attendues", width="stretch"):
            st.markdown("\n".join(f"- `{nom}`{' — **obligatoire**' if obl else ''}" + (f" · {aide}" if aide else "")
                                  for nom, aide, obl in colonnes))
            st.caption("Détection automatique de la feuille et de la ligne d'en-tête, sans tenir compte des accents ni des majuscules.")
    return garde[:2] if garde else None


def vider_emplacement(cle: str, garder_donnees: bool = False) -> None:
    """Efface le fichier affiché dans l'import `fichier(cle)` (nouvelle version du widget) et, sauf
    `garder_donnees`, le fichier gardé en mémoire. À appeler dans un callback."""
    st.session_state[f"{cle}__v"] = st.session_state.get(f"{cle}__v", 0) + 1
    if not garder_donnees:
        st.session_state.pop(f"{cle}__data", None)


LIBELLES_SOURCES = {"besoins": sio.FICHIER_BESOINS, "asreq": sio.FICHIER_ASREQ, "stock": sio.FICHIER_STOCK,
                    "commandes": sio.FICHIER_COMMANDES, "references": sio.FICHIER_REFERENCES, "pieces": "Pièces par avion",
                    "pe": "PE mousses", "besoin_prod": "Besoin Prod mousses"}


@st.cache_resource(show_spinner=False, max_entries=256)
def _source_fichier(data: bytes, nom: str):
    """Source d'un fichier (contenu, puis nom), mise en cache : chaque fichier n'est analysé qu'une fois."""
    return sio.identifier_fichier(data, nom)


def _boutons_dossier(dossier: str, cible: str, mode: str) -> str:
    attrs = f'data-dossier="{escape(dossier)}" data-cible="{escape(cible)}" data-mode="{escape(mode)}"'
    return (f'<span class="s360-dossier-grp"><button type="button" class="s360-dossier-btn" {attrs}>{ic("folder")}Ouvrir {escape(dossier)}</button>'
            f'<button type="button" class="s360-dossier-btn autre" {attrs} data-changer="1" '
            f'title="Choisir un autre dossier {escape(dossier)}">Changer</button></span>')


def boutons_dossiers(dossier: str, cible: str, mode: str = "fichiers", commandes: bool = True) -> None:
    """Barre « 📂 Ouvrir <dossier> » (+ « 📂 Ouvrir COMMANDE ») : dossiers mémorisés, gérés en JavaScript par build.py.

    Le dossier choisi une fois est retenu par le navigateur. Selon `mode`, on dépose dans le `file_uploader` de
    clé `cible` : tous ses fichiers (« fichiers »), ceux du chantier choisi dans la liste (« chantier ») ou le
    fichier le plus récemment modifié (« dernier »). « Changer » choisit un autre dossier. Sans effet en local.
    COMMANDE : fichier Commandes (SAP) le plus récent, rangé dans l'import commun `commun__commandes`.
    """
    html = _boutons_dossier(dossier, cible, mode)
    if commandes:
        html += _boutons_dossier("COMMANDE", "commun__dossier_commande__upload", "dernier")
    st.markdown(f'<div class="s360-dossiers">{html}</div>', unsafe_allow_html=True)
    if commandes:
        with st.container(key="s360cache_commande"):  # zone de dépôt du bouton COMMANDE, masquée (CSS)
            import_dossier("commun__dossier_commande", {"commandes": "commun__commandes"}, resume=False)


@contextmanager
def zone_repliable(cle: str, libelle: str):
    """Zone repliée derrière un interrupteur. Contrairement à `st.expander` (dont le contenu replié n'est pas
    dans la page), les widgets restent présents, masqués en CSS : les boutons « 📂 Ouvrir » peuvent y déposer
    des fichiers même quand la zone est fermée."""
    ouvert = st.toggle(libelle, key=cle, persist_state="page")
    with st.container(key=f"s360pli_{'ouvert' if ouvert else 'ferme'}_{cle}"):
        yield


def etat_fichiers(fichiers: list[tuple[str, str, bool]]) -> None:
    """Pastilles d'état des imports : (libellé, clé de `fichier`, obligatoire) → ✓ nom du fichier, ou « à importer »."""
    puces = []
    for libelle, cle, obligatoire in fichiers:
        garde = st.session_state.get(f"{cle}__data")
        if garde:
            puces.append(f'<span class="s360-puce ok" title="{escape(garde[0])}">{ic("check")}<span><b>{escape(libelle)}</b>'
                         f'<em>{escape(garde[0])}</em></span></span>')
        else:
            ton = "ko" if obligatoire else ""
            puces.append(f'<span class="s360-puce {ton}">{ic("plus")}<span><b>{escape(libelle)}</b>'
                         f'<em>{"à importer" if obligatoire else "facultatif"}</em></span></span>')
    st.markdown(f'<div class="s360-puces">{"".join(puces)}</div>', unsafe_allow_html=True)


def import_commandes(colonnes) -> tuple[str, bytes] | None:
    """Import manuel du fichier Commandes (SAP), commun à tous les onglets. Renvoie (nom, octets) ou None."""
    return fichier(sio.FICHIER_COMMANDES, "commun__commandes", ["xlsx", "xlsm"], colonnes)


def lien_sharepoint(url: str, dossier: str) -> None:
    """Aide « première utilisation » : synchroniser le dossier Teams avec OneDrive pour le voir dans « Parcourir »."""
    with st.popover(f"Première utilisation : synchroniser le dossier {dossier}"):
        st.markdown(
            f"Le bouton **Parcourir** ouvre l'Explorateur Windows : le dossier Teams **{dossier}** doit y apparaître. "
            "À faire **une seule fois par poste** :\n\n"
            f"1. [Ouvrir le dossier {dossier} sur SharePoint]({url}) (nouvel onglet).\n"
            "2. En haut de la page, cliquer sur **« Ajouter un raccourci à Mon OneDrive »** (ou **« Synchroniser »**).\n"
            f"3. Le dossier apparaît dans l'Explorateur sous **OneDrive – Air France-KLM › {dossier}**, et reste à jour tout seul.\n\n"
            "Ensuite, dans Supply360 : **Ouvrir** puis **Autoriser** (le dossier est choisi une seule fois, puis retenu "
            "par le navigateur ; Edge ou Chrome). Rien à télécharger à la main.\n\n"
            "Astuce : ajoutez en raccourci la bibliothèque **Documents** entière du canal : R2, Textile et COMMANDE "
            "seront tous disponibles d'un coup.")


def import_dossier(cle: str, cibles: dict[str, str], dossier: bool = False, on_choix=None, label: str = "", aide: str = "",
                   noms: dict[str, str] | None = None, resume: bool = True, zone=None, autres: tuple = ()) -> None:
    """Import de tout un dossier : chaque fichier est reconnu par son contenu (à défaut son nom) et rangé
    dans l'emplacement `fichier` correspondant (`cibles` = {source: clé du fichier}).

    `dossier=True` : sélection d'un dossier entier (R2 ou un dossier « <IMMAT> - <JJMMAA> ») ; les fichiers
    sont regroupés par dossier chantier et, s'il y en a plusieurs, on choisit le chantier à analyser.
    Si une source a plusieurs fichiers, le plus récent (date dans le nom) est retenu et peut être changé.
    `on_choix(dossier_chantier, {source: [chemins]})` est appelé après chaque répartition.
    `noms` = {source: motif} : règles de nommage prioritaires (voir dossiers.appliquer_noms).
    Un fichier Commandes (SAP) trouvé ici est ignoré si `commandes` n'est pas une cible : seul le dossier COMMANDE fait foi.
    `autres` : sources lues par un autre onglet (même dossier) : ni utilisées ni signalées comme ignorées.
    `zone` : conteneur où placer la zone d'import (ex. l'expander « Import manuel ») ; le choix du chantier et le
    bilan restent à l'emplacement courant.
    """
    version = st.session_state.get(f"{cle}__v", 0)
    cle_up, cle_idx, cle_ch, cle_bilan = f"{cle}__upload{version}", f"{cle}__index", f"{cle}__chantier", f"{cle}__bilan"

    def _ranger(source, chemin):
        nom, data, fid = st.session_state[cle_idx][chemin]
        vider_emplacement(cibles[source])  # efface un ancien fichier importé à la main dans cet emplacement
        st.session_state[f"{cibles[source]}__data"] = (dossiers.nom_court(nom), data, fid)

    def _appliquer():
        index = st.session_state.get(cle_idx, {})
        groupes = dossiers.regrouper(list(index))
        ch = st.session_state.get(cle_ch, dossiers.HORS_CHANTIER)
        chemins = groupes.get(ch, []) + (groupes.get(dossiers.HORS_CHANTIER, []) if ch != dossiers.HORS_CHANTIER else [])
        sources = {c: _source_fichier(index[c][1], c) for c in chemins}
        par_source, inconnus = dossiers.repartir(dossiers.appliquer_noms(sources, noms) if noms else sources)
        for source, liste in par_source.items():
            if source in cibles:
                _ranger(source, liste[0])
                st.session_state[f"{cle}__alt__{source}"] = liste[0]
        if dossier:  # nouveau chantier : aucun fichier de l'ancien ne doit rester
            for source in cibles:
                if source not in par_source:
                    vider_emplacement(cibles[source])
        st.session_state[cle_bilan] = (par_source, inconnus)
        if on_choix:
            on_choix(ch, par_source)

    def _charger():
        # Chaque sélection REMPLACE la précédente (Streamlit, lui, ajouterait les fichiers aux anciens) : on garde
        # les fichiers en mémoire et on vide la zone d'import (nouvelle version du widget).
        fs = [f for f in st.session_state.get(cle_up) or [] if _fichier_valide(f)]
        if not fs:
            return
        st.session_state[cle_idx] = {f.name: (f.name, f.getvalue(), f.file_id) for f in fs}
        st.session_state[f"{cle}__v"] = version + 1
        chantiers = dossiers.chantiers_tries(dossiers.regrouper(list(st.session_state[cle_idx])))
        if st.session_state.get(cle_ch) not in chantiers:
            st.session_state[cle_ch] = chantiers[0] if chantiers else dossiers.HORS_CHANTIER
        _appliquer()

    with zone if zone is not None else nullcontext():
        st.file_uploader(label or "Importer les fichiers du dossier (Ctrl+A pour tout sélectionner)", type=["xlsx", "xlsm", "csv"],
                         accept_multiple_files="directory" if dossier else True, key=cle_up, on_change=_charger, help=aide or None)
    index = st.session_state.get(cle_idx, {})
    if not index:
        return
    taille = sum(len(v[1]) for v in index.values()) / 1e6
    if taille > 250:
        callout(f"{taille:.0f} Mo importés : pour aller plus vite, choisissez directement le dossier du chantier.", "warn", "🐢")
    chantiers = dossiers.chantiers_tries(dossiers.regrouper(list(index)))
    par_source, inconnus = st.session_state.get(cle_bilan, ({}, []))
    doubles = {s: l for s, l in par_source.items() if s in cibles and len(l) > 1}
    choix_chantier = dossier and len(chantiers) > 1
    if choix_chantier or doubles:
        cols = iter(st.columns(int(choix_chantier) + len(doubles)))
        if choix_chantier:
            def _libelle(g):
                immat, debut = sio.chantier_depuis_nom(g)
                return f"{immat} · début {debut:%d/%m/%Y}"
            next(cols).selectbox(f"Chantier à analyser ({len(chantiers)} dossiers)", chantiers, key=cle_ch, format_func=_libelle,
                                 on_change=_appliquer, persist_state="page")
        for source, liste in doubles.items():
            next(cols).selectbox(f"{LIBELLES_SOURCES[source]} : {len(liste)} fichiers, le plus récent est retenu", liste,
                                 key=f"{cle}__alt__{source}", format_func=dossiers.nom_court, persist_state="page",
                                 on_change=lambda s=source: _ranger(s, st.session_state[f"{cle}__alt__{s}"]))
    manquants = [LIBELLES_SOURCES[s] for s in cibles if s not in par_source and s not in ("asreq", "commandes")
                 and not (s == "besoins" and "asreq" in par_source)]
    notes = []
    ch = st.session_state.get(cle_ch, dossiers.HORS_CHANTIER)
    nb = sum(len(l) for l in par_source.values()) + len(inconnus)
    if resume:
        notes.append(f"Dossier importé : <b>{escape(ch)}</b> ({nb} fichier(s))" if ch else f"Dossier importé : {nb} fichier(s)")
    if manquants:
        notes.append("absent(s) du dossier : <b>" + ", ".join(escape(m) for m in manquants) + "</b>")
    if "commandes" in par_source and "commandes" not in cibles:
        notes.append(f"Commandes (SAP) du dossier non utilisé ({escape(dossiers.nom_court(par_source['commandes'][0]))}) : "
                     "le fichier du dossier <b>COMMANDE</b> fait foi")
    # Raison de chaque fichier écarté : non reconnu, ou reconnu comme une source que cet onglet n'utilise pas
    hors = [f"{escape(dossiers.nom_court(c))} (non reconnu)" for c in inconnus] + [
        f"{escape(dossiers.nom_court(c))} (reconnu comme {escape(LIBELLES_SOURCES.get(s, s))})" for s, l in par_source.items()
        if s not in cibles and s != "commandes" and s not in autres for c in l]
    if hors:
        notes.append("Ignoré(s) : " + ", ".join(hors))
    if notes:
        st.html('<div class="s360-note">' + " · ".join(notes) + "</div>")


def telecharger(data, nom: str, cle: str, label: str = "Exporter (Excel)") -> None:
    """Bouton de téléchargement Excel. `on_click="ignore"` : télécharger ne relance pas les calculs.

    `data` : octets, ou de préférence une FONCTION sans argument qui les produit. Le fichier n'est alors fabriqué
    qu'au clic, et non à chaque affichage de l'onglet (plusieurs secondes sur de gros fichiers, page figée) :
    « Exporter » fabrique le fichier, puis le téléchargement part tout seul (JavaScript de build.py, clé « __auto »).
    """
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if not callable(data):
        st.download_button(label, data=data, file_name=nom, key=cle, on_click="ignore", mime=mime)
        return
    if st.session_state.pop(f"{cle}__pret", False):  # fabriqué pour cette exécution seulement
        with st.spinner("Préparation du fichier Excel…"):
            octets = data()
        st.download_button(label, data=octets, file_name=nom, key=f"{cle}__auto", on_click="ignore", mime=mime)
    else:
        st.button(label, key=f"{cle}__prep", on_click=lambda: st.session_state.__setitem__(f"{cle}__pret", True))


def sous_onglets(cle: str, options: list[str], icones: dict | None = None) -> str:
    """Barre de sous-onglets (pastilles, l'active en bleu marine). Renvoie l'option active. `icones` : ignoré (libellés seuls)."""
    with st.container(key="s360sub_" + cle):
        choix = st.segmented_control("Section", options, default=options[0], key=cle, required=True,
                                     label_visibility="collapsed", persist_state="page",
                                     format_func=str)
    return choix or options[0]
