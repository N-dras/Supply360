"""Composants visuels réutilisables (charte Supply360, prototype v3).

Les fonctions qui renvoient du HTML (`kpi_card`, `badge`…) sont pures ; celles qui
dessinent (`header`, `section`, `kpi_grid`…) appellent Streamlit.
"""

from contextlib import contextmanager
from datetime import date
from html import escape

import streamlit as st

TONES = {
    "navy": "var(--navy)", "info": "var(--navy-2)", "accent": "var(--accent)", "ok": "var(--ok)",
    "warn": "var(--warn)", "ko": "var(--ko)", "muted": "var(--muted)", "violet": "#6D28D9",
}
CHANTIER_STATUTS = {"Terminé": "muted", "En cours": "info", "À venir": "ok"}
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _tone(tone: str) -> str:
    return TONES.get(tone, TONES["navy"])


# --------------------------------------------------------------------------
# Structure de page
# --------------------------------------------------------------------------
def header() -> None:
    """Header fixe : logo AFI (fond clair : le logo est transparent), Supply360, date du jour.

    La navigation entre onglets (main.py) est positionnée dans ce header par le CSS.
    """
    j = date.today()
    st.html(
        '<div class="s360-header"><div class="s360-logo" role="img" '
        'aria-label="Air France Industries KLM Engineering &amp; Maintenance"></div><span class="s360-sep"></span>'
        '<div class="s360-brand">Supply<span>360</span></div>'
        f'<div class="s360-today">{JOURS[j.weekday()]} {j:%d/%m/%Y}</div></div>'
        '<div class="s360-busy">⏳ Calcul en cours…</div>'
    )


def hero(icone: str, titre: str, sous_titre: str = "") -> None:
    """Titre d'onglet : carte translucide posée sur le fond."""
    sub = f"<p>{escape(sous_titre)}</p>" if sous_titre else ""
    st.html(f'<div class="s360-hero"><div class="ico">{icone}</div><div><h1>{escape(titre)}</h1>{sub}</div></div>')


@contextmanager
def section(key: str, title: str, subtitle: str = "", tag: str = ""):
    """Bloc carte translucide à en-tête dégradé. `key` doit être unique (préfixé par le TAB_ID)."""
    box = st.container(key=f"s360sec_{key}")
    with box:
        sub = f"<p>{escape(subtitle)}</p>" if subtitle else ""
        tg = f'<span class="tag">{escape(tag)}</span>' if tag else ""
        st.html(f'<div class="s360-section-head"><div><h3>{escape(title)}</h3>{sub}</div>{tg}</div>')
        yield box


def footer() -> None:
    st.html('<div class="s360-footer">Supply360 · Air France Industries — fichiers traités localement dans votre navigateur, '
            "rien n'est envoyé. Rafraîchir la page réinitialise la session.</div>")


def en_developpement(icone: str, titre: str, points: list[str]) -> None:
    """Page d'un onglet prévu mais pas encore développé."""
    items = "".join(f"<li>{escape(p)}</li>" for p in points)
    st.html(f'<div class="s360-wip"><div class="plane"></div><div class="ico">{icone}</div><h2>{escape(titre)}</h2>'
            f'<span class="s360-badge" style="--tone:var(--warn)">En cours de développement</span>'
            f"<p>Cette fonctionnalité arrive dans une prochaine version de Supply360.</p><ul>{items}</ul></div>")


# --------------------------------------------------------------------------
# Indicateurs
# --------------------------------------------------------------------------
def kpi_card(label: str, value, sub: str = "", tone: str = "navy") -> str:
    """HTML d'une tuile KPI (à passer à `kpi_grid`)."""
    sub_html = f'<div class="sub">{escape(str(sub))}</div>' if sub else ""
    return (f'<div class="s360-kpi" style="--tone:{_tone(tone)}"><div class="val">{escape(str(value))}</div>'
            f'<div class="lbl">{escape(str(label))}</div>{sub_html}</div>')


def kpi_grid(cards: list[str]) -> None:
    st.html(f'<div class="s360-kpis">{"".join(cards)}</div>')


def badge(text: str, tone: str = "navy") -> str:
    return f'<span class="s360-badge" style="--tone:{_tone(tone)}">{escape(text)}</span>'


def chantier_badge(statut: str, jours_avant_debut: int | None = None) -> str:
    """Badge de statut chantier : uniquement Terminé / En cours / À venir."""
    if statut not in CHANTIER_STATUTS:
        raise ValueError(f"Statut de chantier inconnu : {statut}")
    text = statut + (f" · J-{jours_avant_debut}" if statut == "À venir" and jours_avant_debut is not None else "")
    return badge(text, CHANTIER_STATUTS[statut])


def callout(message_html: str, tone: str = "navy", icon: str = "ℹ️") -> None:
    """Bandeau court (action à mener, alerte). `message_html` est du HTML de confiance."""
    st.html(f'<div class="s360-callout" style="--tone:{_tone(tone)}"><span>{icon}</span><div>{message_html}</div></div>')


def empty_state(title: str, message: str, etapes: list[tuple[str, bool]] | None = None, icon: str = "📥") -> None:
    """État vide : explique quoi faire tant que les fichiers ne sont pas importés."""
    steps = "".join(f'<span class="s360-step{" ok" if ok else ""}">{"✓" if ok else "○"} {escape(lbl)}</span>'
                    for lbl, ok in etapes or [])
    st.html(f'<div class="s360-empty"><div class="ico">{icon}</div><h4>{escape(title)}</h4><p>{escape(message)}</p>'
            f'<div class="s360-steps">{steps}</div></div>')


def tableau(df, **kwargs) -> None:
    """st.dataframe avec « — » à la place des textes vides (au lieu de « None »)."""
    texte = df.select_dtypes(include=["object", "string"]).columns
    if len(texte):
        df = df.copy()
        df[texte] = df[texte].astype(object).where(df[texte].notna(), "—")
    st.dataframe(df, hide_index=True, **kwargs)


def graphe(html: str) -> None:
    """Affiche un graphe de core/charts.py. st.markdown (et non st.html, qui supprime le SVG)."""
    st.markdown(html, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Imports et téléchargements
# --------------------------------------------------------------------------
def _fichier_valide(f) -> bool:
    """Vrai pour un fichier réellement importé (Streamlit peut renvoyer un `DeletedFile` après un changement d'onglet)."""
    return f is not None and hasattr(f, "getvalue") and hasattr(f, "name")


def fichier(label: str, cle: str, types: list[str], colonnes: list[tuple[str, str, bool]] | None = None):
    """`file_uploader` dont le contenu survit au changement d'onglet. Renvoie (nom, octets) ou None.

    Streamlit efface un widget qui n'est pas affiché : sans cette mémoire, revenir sur un onglet
    obligeait à réimporter ses fichiers.
    """
    memoire, cle_up = f"{cle}__data", f"{cle}__upload"

    def _maj():
        f = st.session_state.get(cle_up)
        if f is None:
            st.session_state.pop(memoire, None)   # l'utilisateur a retiré le fichier
        elif _fichier_valide(f):
            st.session_state[memoire] = (f.name, f.getvalue(), f.file_id)

    up = st.file_uploader(label, type=types, key=cle_up, on_change=_maj)
    garde = st.session_state.get(memoire)
    if _fichier_valide(up) and (garde is None or garde[2] != up.file_id):
        garde = st.session_state[memoire] = (up.name, up.getvalue(), up.file_id)
    if not _fichier_valide(up) and garde:
        st.html(f'<div class="s360-file">✓ <span>{escape(garde[0])}</span></div>')
    if colonnes:
        with st.popover("Colonnes attendues", width="stretch"):
            st.markdown("\n".join(f"- `{nom}`{' — **obligatoire**' if obl else ''}" + (f" · {aide}" if aide else "")
                                  for nom, aide, obl in colonnes))
            st.caption("Détection automatique de la feuille et de la ligne d'en-tête, sans tenir compte des accents ni des majuscules.")
    return garde[:2] if garde else None


def telecharger(data: bytes, nom: str, cle: str, label: str = "⬇️ Télécharger (Excel)") -> None:
    """Bouton de téléchargement Excel. `on_click="ignore"` : télécharger ne relance pas les calculs."""
    st.download_button(label, data=data, file_name=nom, key=cle, on_click="ignore",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def sous_onglets(cle: str, options: list[str], icones: dict | None = None) -> str:
    """Barre de sous-onglets (style du prototype : soulignement rouge). Renvoie l'option active."""
    icones = icones or {}
    with st.container(key="s360sub_" + cle):
        choix = st.segmented_control("Section", options, default=options[0], key=cle, required=True,
                                     label_visibility="collapsed", persist_state="page",
                                     format_func=lambda o: f"{icones.get(o, '')} {o}".strip())
    return choix or options[0]
