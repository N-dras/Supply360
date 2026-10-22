"""Thème Supply360 : couleurs de la charte, CSS global (core/theme.css) et injection.

Dans le HTML livré, build.py place le CSS (images comprises) une seule fois dans le <head> :
rien n'est renvoyé au navigateur à chaque interaction. En développement local
(`streamlit run`), `inject()` l'ajoute à la page.
"""

import base64
import re
import sys
from functools import lru_cache
from pathlib import Path

# Couleurs de la charte, réutilisées côté Python (graphes Altair, export Excel).
COLORS = {
    "navy": "#002157",
    "navy_2": "#1F4E9C",
    "accent": "#E4002B",
    "bg": "#F4F6FA",
    "surface": "#FFFFFF",
    "tile": "#F1F5FA",
    "text": "#1A1F36",
    "muted": "#5B6478",
    "border": "#DDE3EE",
    "grid": "#E3E9F1",
    "ok": "#1E8E5A",
    "warn": "#E8A317",
    "ko": "#C62828",
    "violet": "#6D28D9",
    "gris": "#9AA5B1",
}

# Manrope (police du prototype) est embarquée dans le thème : aucun appel à Google Fonts.
FONT = "Manrope"
FONT_STACK = '"Manrope", "Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif'

THEME = Path(__file__).with_name("theme.css")
MIME = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
        ".woff2": "font/woff2"}


@lru_cache(maxsize=2)
def css_complet(dossier_assets: Path) -> str:
    """CSS du thème avec les images `asset(nom)` remplacées par des data URI."""
    def data_uri(m):
        f = Path(dossier_assets) / m.group(1)
        b64 = base64.b64encode(f.read_bytes()).decode("ascii")
        return f'url("data:{MIME[f.suffix.lower()]};base64,{b64}")'

    return re.sub(r"asset\(([^)]+)\)", data_uri, THEME.read_text(encoding="utf-8"))


def dans_le_navigateur() -> bool:
    """True sous stlite / Pyodide (HTML livré), False avec `streamlit run`."""
    return sys.platform == "emscripten"


def inject() -> None:
    """Injecte le thème en développement local (dans le HTML, il est déjà dans le <head>)."""
    if dans_le_navigateur():
        return
    import streamlit as st

    assets = Path(__file__).resolve().parents[2] / "assets"
    st.html(f"<style>{css_complet(assets)}</style>")
