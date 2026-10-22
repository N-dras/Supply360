"""CSS global de Supply360 (charte Air France Industries) et injection dans la page."""

import streamlit as st

# Couleurs de la charte, réutilisées côté Python (Plotly, export Excel).
COLORS = {
    "navy": "#002157",
    "navy_2": "#1F4E9C",
    "accent": "#E4002B",
    "bg": "#F4F6FA",
    "surface": "#FFFFFF",
    "text": "#1A1F36",
    "muted": "#5B6478",
    "border": "#DDE3EE",
    "ok": "#1E8E5A",
    "warn": "#E8A317",
    "ko": "#C62828",
}

FONT_STACK = '"Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif'

HEADER_HEIGHT = "4.5rem"

CSS = f"""
:root {{
  --navy: {COLORS["navy"]};
  --navy-2: {COLORS["navy_2"]};
  --accent: {COLORS["accent"]};
  --bg: {COLORS["bg"]};
  --surface: {COLORS["surface"]};
  --text: {COLORS["text"]};
  --muted: {COLORS["muted"]};
  --border: {COLORS["border"]};
  --ok: {COLORS["ok"]};
  --warn: {COLORS["warn"]};
  --ko: {COLORS["ko"]};
  --radius: 12px;
  --shadow: 0 1px 2px rgba(0, 33, 87, .06), 0 4px 14px rgba(0, 33, 87, .06);
  --header-h: {HEADER_HEIGHT};
}}

html, body, .stApp, [data-testid="stAppViewContainer"] {{
  background: var(--bg);
  color: var(--text);
  font-family: {FONT_STACK};
}}
/* Pas de règle sur span/div : les icônes Streamlit utilisent leur propre police. */
.stApp :is(p, li, label, input, textarea, button, td, th, h1, h2, h3, h4) {{
  font-family: {FONT_STACK};
}}

/* ---- Habillage Streamlit masqué ---- */
header[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stMainMenu"],
[data-testid="stAppDeployButton"],
#MainMenu, footer {{
  display: none !important;
}}

[data-testid="stMainBlockContainer"], .block-container {{
  max-width: 1500px;
  padding: calc(var(--header-h) + 1.25rem) 1.5rem 3rem;
}}
@media (max-width: 640px) {{
  [data-testid="stMainBlockContainer"], .block-container {{
    padding-left: 1rem;
    padding-right: 1rem;
  }}
}}

/* ---- Header fixe ---- */
.s360-header {{
  position: fixed;
  inset: 0 0 auto 0;
  z-index: 999990;
  height: var(--header-h);
  display: flex;
  align-items: center;
  gap: 1.25rem;
  padding: 0 1.5rem;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 2px 10px rgba(0, 33, 87, .06);
}}
.s360-header::after {{
  content: "";
  position: absolute;
  inset: auto 0 -3px 0;
  height: 3px;
  background: linear-gradient(90deg, var(--navy), var(--navy-2));
}}
/* Le logo est sur fond transparent avec un texte bleu marine :
   il doit toujours être posé sur un fond clair. */
.s360-header img {{
  height: 2.75rem;
  width: auto;
  display: block;
}}
.s360-header .s360-sep {{
  width: 1px;
  align-self: stretch;
  margin: 1rem 0;
  background: var(--border);
}}
.s360-brand {{
  display: flex;
  flex-direction: column;
  line-height: 1.15;
}}
.s360-brand b {{
  color: var(--navy);
  font-size: 1.375rem;
  font-weight: 700;
  letter-spacing: .01em;
}}
.s360-brand small {{
  color: var(--muted);
  font-size: .875rem;
}}
.s360-header .s360-current {{
  margin-left: auto;
  padding: .4rem .9rem;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--navy), var(--navy-2));
  color: #fff;
  font-size: .9375rem;
  font-weight: 600;
  white-space: nowrap;
}}
@media (max-width: 760px) {{
  .s360-header {{ gap: .75rem; padding: 0 1rem; }}
  .s360-header img {{ height: 2rem; }}
  .s360-brand small, .s360-header .s360-sep {{ display: none; }}
  .s360-header .s360-current {{ font-size: .875rem; padding: .3rem .7rem; }}
}}
@media (max-width: 560px) {{
  .s360-header .s360-current {{ display: none; }}
}}

/* ---- Navigation entre onglets ---- */
.st-key-s360_nav [data-testid="stButtonGroup"] {{
  flex-wrap: wrap;
}}
.st-key-s360_nav button {{
  min-height: 2.6rem;
  padding: .45rem 1.1rem;
  color: var(--navy);
  background: var(--surface);
  border-color: var(--border);
}}
.st-key-s360_nav button p {{
  font-size: 1rem;
  font-weight: 600;
  color: inherit;
}}
.st-key-s360_nav button[aria-checked="true"] {{
  background: linear-gradient(90deg, var(--navy), var(--navy-2));
  border-color: var(--navy);
}}
.st-key-s360_nav button[aria-checked="true"] p {{ color: #fff; }}

/* ---- Intro d'onglet ---- */
.s360-intro h1 {{
  margin: 0 0 .25rem;
  padding: 0;
  color: var(--navy);
  font-size: 1.75rem;
  font-weight: 700;
}}
.s360-intro p {{
  margin: 0 0 .6rem;
  color: var(--muted);
  font-size: 1rem;
  max-width: 70rem;
}}
.s360-chips {{ display: flex; flex-wrap: wrap; gap: .4rem; }}
.s360-chip {{
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  padding: .2rem .7rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--navy);
  font-size: .875rem;
  font-weight: 600;
}}

/* ---- Sections (cartes à en-tête dégradé) ---- */
[class*="st-key-s360sec_"] {{
  background: var(--surface);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  border: 1px solid var(--border);
  padding: 0 1.25rem 1.25rem;
  overflow: hidden;
}}
.s360-section-head {{
  margin: 0 -1.25rem .25rem;
  padding: .8rem 1.25rem;
  background: linear-gradient(90deg, var(--navy), var(--navy-2));
  color: #fff;
}}
.s360-section-head h3 {{
  margin: 0;
  padding: 0;
  color: #fff;
  font-size: 1.125rem;
  font-weight: 650;
}}
.s360-section-head p {{
  margin: .15rem 0 0;
  color: rgba(255, 255, 255, .85);
  font-size: .875rem;
}}

/* ---- Cartes KPI ---- */
.s360-kpis {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: .9rem;
}}
.s360-kpi {{
  position: relative;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: .9rem 1rem .85rem;
  box-shadow: var(--shadow);
  overflow: hidden;
}}
.s360-kpi::before {{
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 4px;
  background: var(--tone, var(--navy));
}}
.s360-kpi .lbl {{
  color: var(--muted);
  font-size: .875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .03em;
}}
.s360-kpi .val {{
  margin: .3rem 0 .15rem;
  color: var(--tone, var(--navy));
  font-size: 2rem;
  font-weight: 700;
  line-height: 1.1;
}}
.s360-kpi .sub {{ color: var(--muted); font-size: .875rem; }}

/* ---- Badges ---- */
.s360-badge {{
  display: inline-block;
  padding: .15rem .6rem;
  border-radius: 999px;
  font-size: .875rem;
  font-weight: 600;
  color: var(--tone, var(--navy));
  background: color-mix(in srgb, var(--tone, var(--navy)) 12%, white);
  border: 1px solid color-mix(in srgb, var(--tone, var(--navy)) 35%, white);
  white-space: nowrap;
}}

/* ---- Bandeaux d'alerte / message d'action ---- */
.s360-callout {{
  display: flex;
  gap: .75rem;
  align-items: flex-start;
  padding: .85rem 1rem;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--tone, var(--navy)) 35%, white);
  border-left: 5px solid var(--tone, var(--navy));
  background: color-mix(in srgb, var(--tone, var(--navy)) 7%, white);
  color: var(--text);
  font-size: 1rem;
}}
.s360-callout .ico {{ font-size: 1.25rem; line-height: 1.3; }}
.s360-callout b {{ color: var(--tone, var(--navy)); }}

/* ---- État vide ---- */
.s360-empty {{
  text-align: center;
  padding: 2.5rem 1.5rem;
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}}
.s360-empty .ico {{ font-size: 2.5rem; }}
.s360-empty h4 {{ margin: .5rem 0 .35rem; color: var(--navy); font-size: 1.25rem; }}
.s360-empty p {{ margin: 0 auto .75rem; color: var(--muted); max-width: 40rem; }}
.s360-empty ol {{
  display: inline-block;
  text-align: left;
  margin: 0;
  color: var(--text);
}}
.s360-empty li {{ margin: .2rem 0; }}

/* ---- Boutons (style unique) ---- */
.stButton > button, .stDownloadButton > button {{
  min-height: 2.6rem;
  border-radius: 8px;
  font-weight: 600;
  font-size: 1rem;
  color: #fff;
  background: linear-gradient(90deg, var(--navy), var(--navy-2));
  border: 1px solid var(--navy);
  transition: filter .15s ease, box-shadow .15s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
  color: #fff;
  border-color: var(--navy);
  filter: brightness(1.12);
  box-shadow: 0 3px 10px rgba(0, 33, 87, .25);
}}
.stButton > button:focus-visible, .stDownloadButton > button:focus-visible {{
  outline: 3px solid color-mix(in srgb, var(--navy-2) 45%, white);
  color: #fff;
}}

/* ---- Imports, tableaux, expanders ---- */
[data-testid="stFileUploaderDropzone"] {{
  border: 1.5px dashed color-mix(in srgb, var(--navy-2) 45%, white);
  background: #F8FAFD;
  border-radius: 10px;
}}
/* Textes du composant d'import traduits (Streamlit ne les localise pas). */
[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] p {{ font-size: 0; }}
[data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] p::after {{
  content: "Parcourir";
  font-size: 1rem;
}}
[data-testid="stFileUploaderDropzoneInstructions"] span {{ font-size: 0; }}
[data-testid="stFileUploaderDropzoneInstructions"] span::after {{
  content: "ou glisser-déposer le fichier ici";
  font-size: .875rem;
}}
[data-testid="stDataFrame"] {{
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}}
[data-testid="stExpander"] details {{
  border-color: var(--border);
  border-radius: 10px;
  background: var(--surface);
}}
[data-testid="stCaptionContainer"] {{ color: var(--muted); font-size: .875rem; }}

.s360-footer {{
  margin-top: 1rem;
  text-align: center;
  color: var(--muted);
  font-size: .875rem;
}}
"""


def inject() -> None:
    """Injecte le CSS global (à appeler une fois par exécution, depuis main.py)."""
    st.html(f"<style>{CSS}</style>")
