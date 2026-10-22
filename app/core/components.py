"""Composants visuels réutilisables (charte Supply360).

Les fonctions qui renvoient du HTML (`kpi_card`, `badge`…) sont pures ; celles qui
dessinent (`header`, `section`, `kpi_grid`…) appellent Streamlit.
"""

from contextlib import contextmanager
from html import escape

import streamlit as st

from core.style import COLORS, FONT_STACK

try:
    from core._logo import LOGO_B64
except ImportError:  # _logo.py pas encore généré : lancer `python build.py`
    LOGO_B64 = ""

TONES = {
    "navy": "var(--navy)",
    "info": "var(--navy-2)",
    "accent": "var(--accent)",
    "ok": "var(--ok)",
    "warn": "var(--warn)",
    "ko": "var(--ko)",
    "muted": "var(--muted)",
}

CHANTIER_STATUTS = {"Terminé": "muted", "En cours": "info", "À venir": "ok"}


def _tone(tone: str) -> str:
    return TONES.get(tone, TONES["navy"])


def header(tab_label: str = "") -> None:
    """Header fixe : logo AFI (sur fond clair, le logo est transparent) + Supply360 + onglet actif."""
    logo = (
        f'<img src="data:image/png;base64,{LOGO_B64}" alt="Air France Industries KLM Engineering &amp; Maintenance">'
        if LOGO_B64 else ""
    )
    current = f'<span class="s360-current">{escape(tab_label)}</span>' if tab_label else ""
    st.html(
        f'<div class="s360-header">{logo}<span class="s360-sep"></span>'
        f'<div class="s360-brand"><b>Supply360</b>'
        f"<small>Pilotage supply chain · équipements cabine</small></div>{current}</div>"
    )


def page_intro(title: str, description: str, fichiers: list[str] | None = None) -> None:
    """En-tête d'onglet : titre, description courte et rappel des fichiers attendus."""
    chips = "".join(f'<span class="s360-chip">📄 {escape(f)}</span>' for f in fichiers or [])
    st.html(
        f'<div class="s360-intro"><h1>{escape(title)}</h1><p>{escape(description)}</p>'
        f'<div class="s360-chips">{chips}</div></div>'
    )


@contextmanager
def section(key: str, title: str, subtitle: str = ""):
    """Bloc carte blanche à en-tête dégradé. `key` doit être unique (préfixé par le TAB_ID)."""
    box = st.container(key=f"s360sec_{key}")
    with box:
        sub = f"<p>{escape(subtitle)}</p>" if subtitle else ""
        st.html(f'<div class="s360-section-head"><h3>{escape(title)}</h3>{sub}</div>')
        yield box


def kpi_card(label: str, value, sub: str = "", tone: str = "navy") -> str:
    """HTML d'une carte KPI (à passer à `kpi_grid`)."""
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    return (
        f'<div class="s360-kpi" style="--tone:{_tone(tone)}">'
        f'<div class="lbl">{escape(str(label))}</div>'
        f'<div class="val">{escape(str(value))}</div>{sub_html}</div>'
    )


def kpi_grid(cards: list[str]) -> None:
    """Grille responsive de cartes KPI (passe à la ligne sur écran étroit)."""
    st.html(f'<div class="s360-kpis">{"".join(cards)}</div>')


def badge(text: str, tone: str = "navy") -> str:
    return f'<span class="s360-badge" style="--tone:{_tone(tone)}">{escape(text)}</span>'


def chantier_badge(statut: str, jours_avant_debut: int | None = None) -> str:
    """Badge de statut chantier : uniquement Terminé / En cours / À venir."""
    if statut not in CHANTIER_STATUTS:
        raise ValueError(f"Statut de chantier inconnu : {statut}")
    text = statut
    if statut == "À venir" and jours_avant_debut is not None:
        text += f" · J-{jours_avant_debut}"
    return badge(text, CHANTIER_STATUTS[statut])


def callout(message_html: str, tone: str = "navy", icon: str = "ℹ️") -> None:
    """Bandeau de message (action à mener, alerte). `message_html` est du HTML de confiance."""
    st.html(
        f'<div class="s360-callout" style="--tone:{_tone(tone)}">'
        f'<span class="ico">{icon}</span><div>{message_html}</div></div>'
    )


def empty_state(title: str, message: str, steps: list[str] | None = None, icon: str = "📥") -> None:
    """État vide soigné, affiché tant que les fichiers ne sont pas importés."""
    steps_html = "".join(f"<li>{s}</li>" for s in steps or [])
    st.html(
        f'<div class="s360-empty"><div class="ico">{icon}</div><h4>{escape(title)}</h4>'
        f"<p>{escape(message)}</p>{f'<ol>{steps_html}</ol>' if steps_html else ''}</div>"
    )


def footer() -> None:
    st.html(
        '<div class="s360-footer">Supply360 · Air France Industries — les fichiers sont traités '
        "localement dans votre navigateur et ne sont envoyés nulle part. "
        "Rafraîchir la page réinitialise la session.</div>"
    )


def style_figure(fig, height: int = 380):
    """Applique la charte à une figure Plotly : fond transparent, police, légende en bas."""
    fig.update_layout(
        height=height,
        font=dict(family=FONT_STACK, size=14, color=COLORS["text"]),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=30, t=30, b=10),
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5),
        hoverlabel=dict(font_family=FONT_STACK),
    )
    fig.update_xaxes(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"])
    fig.update_yaxes(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"])
    return fig


PLOTLY_CONFIG = {"displaylogo": False, "locale": "fr"}
