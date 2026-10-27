"""Point d'entrée Supply360 : configuration de page, thème, header et navigation.

Fonctionne à l'identique avec `streamlit run app/main.py` et dans le HTML stlite.
"""

import sys
from pathlib import Path

# Rend `core` et `modules` importables, que l'app tourne sous Streamlit ou stlite.
_APP_DIR = str(Path(__file__).resolve().parent)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Supply360 · Air France Industries", page_icon="✈️",
                   layout="wide", initial_sidebar_state="collapsed")

from core import components as ui  # noqa: E402
from core import journal  # noqa: E402
from core import style  # noqa: E402
from modules import MODULES  # noqa: E402

journal.installer()  # stlite : erreurs Python transmises au bandeau de diagnostic de la page

PAR_ID = {m.TAB_ID: m for m in MODULES}
assert len(PAR_ID) == len(MODULES), "TAB_ID en double dans le registre des modules"

# L'onglet actif est porté par le sélecteur de navigation (clé s360_nav).
if st.session_state.get("s360_nav") not in PAR_ID:
    st.session_state["s360_nav"] = MODULES[0].TAB_ID

style.inject()
ui.header()
st.segmented_control(
    "Onglet",
    options=list(PAR_ID),
    format_func=lambda tab_id: f"{PAR_ID[tab_id].TAB_ICON} {PAR_ID[tab_id].TAB_LABEL}",
    required=True,
    key="s360_nav",
    label_visibility="collapsed",
)
st.session_state["active_tab"] = st.session_state["s360_nav"]

# Seul l'onglet actif est exécuté (contrairement à st.tabs).
PAR_ID[st.session_state["active_tab"]].render()
ui.footer()
