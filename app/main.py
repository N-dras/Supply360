"""Point d'entrée Supply360 : configuration de page, style, header et navigation.

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
from core import style  # noqa: E402
from modules import MODULES  # noqa: E402

PAR_ID = {m.TAB_ID: m for m in MODULES}
assert len(PAR_ID) == len(MODULES), "TAB_ID en double dans le registre des modules"

if st.session_state.get("active_tab") not in PAR_ID:
    st.session_state["active_tab"] = MODULES[0].TAB_ID


def _changer_onglet() -> None:
    st.session_state["active_tab"] = st.session_state["s360_nav"]


style.inject()
actif = PAR_ID[st.session_state["active_tab"]]
ui.header(f"{actif.TAB_ICON} {actif.TAB_LABEL}")

# Sélecteur horizontal : seul l'onglet actif est exécuté (contrairement à st.tabs).
st.segmented_control(
    "Onglet",
    options=list(PAR_ID),
    format_func=lambda tab_id: f"{PAR_ID[tab_id].TAB_ICON} {PAR_ID[tab_id].TAB_LABEL}",
    default=st.session_state["active_tab"],
    required=True,
    key="s360_nav",
    on_change=_changer_onglet,
    label_visibility="collapsed",
)

actif.render()
ui.footer()
