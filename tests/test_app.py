"""Test de fumée : l'app démarre sans erreur (sans fichier importé), sur chaque onglet."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"


def test_app_demarre_sur_chaque_onglet():
    at = AppTest.from_file(str(MAIN), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    from modules import MODULES  # importable une fois l'app lancée (app/ dans sys.path)
    for m in MODULES:
        at.session_state["s360_nav"] = m.TAB_ID
        at.run()
        assert not at.exception, (m.TAB_ID, [e.value for e in at.exception])
