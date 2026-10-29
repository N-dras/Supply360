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

# Couleurs de la charte, réutilisées côté Python (graphes, export Excel). Statuts et catégories : palette vérifiée
# (couleurs distinctes, y compris pour les daltoniens) ; toujours accompagnées d'un libellé, jamais seules.
COLORS = {
    "navy": "#002157",
    "navy_2": "#1F4E9C",
    "accent": "#E4002B",
    "bg": "#F5F7FA",
    "surface": "#FFFFFF",
    "tile": "#F5F7FA",
    "text": "#1A1F36",
    "muted": "#5B6478",
    "border": "#E3E8EF",
    "grid": "#E3E9F1",
    # statuts : rouge = à commander / en retard, orange = urgent, ambre = à relancer, bleu = en cours, vert = OK
    "ko": "#A61B1B",
    "orange": "#E8590C",
    "warn": "#DBA100",
    "bleu": "#2B6CB0",
    "ok": "#1E8E5A",
    "violet": "#7B61C9",
    "gris": "#9AA5B1",
    "gris_clair": "#B5BDCB",
}
# Catégories (identité), ordre fixe : bleu, sarcelle, orange, brique, violet, ocre
CATEGORIES = ["#1F4E9C", "#2A9D8F", "#E8833A", "#B83D4B", "#7B61C9", "#C99A06"]
# Fonds teintés des badges et des cellules de statut (interface et export Excel)
TEINTES = {"#A61B1B": "FBECEC", "#E8590C": "FDF0E7", "#DBA100": "FDF6DD", "#2B6CB0": "E9F1FA", "#1E8E5A": "E6F4EC",
           "#7B61C9": "F1EDFB", "#9AA5B1": "EEF1F5", "#B5BDCB": "F3F5F8", "#1F4E9C": "EAF0FA", "#2A9D8F": "E5F4F2"}
# Couleur d'accent de chaque onglet (en-tête de page, onglet actif) et icône
ONGLETS = {"stock_chantier": ("#1F4E9C", "wrench"), "textiles": ("#2A9D8F", "scissors"), "pe_mousses": ("#7B61C9", "armchair"),
           "fournisseurs": ("#E8833A", "factory"), "alertes": ("#B83D4B", "bell")}


def teinte(couleur: str) -> str:
    """Fond teinté (hexa sans #) associé à une couleur de statut."""
    return TEINTES.get(couleur, "EEF1F5")


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
