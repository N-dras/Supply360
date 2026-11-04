"""Tableau standard (components.tableau_html) : valeurs brutes pour les filtres, statut, pages de 200 lignes."""
import json
import re
from html import unescape

import pandas as pd

from core import components as ui


def _rendu(monkeypatch, df, **kw):
    sortie = []
    monkeypatch.setattr(ui.st, "html", lambda h, **_: sortie.append(h))
    ui.tableau_html(df, cle="t", **kw)
    return sortie[-1]


def test_types_et_valeurs_brutes(monkeypatch):
    df = pd.DataFrame({"Statut": ["Rupture", "Correct"], "PN": ["A", "B"], "Stock": [0, 12.5], "Valeur (€)": [1500, 20000],
                       "Date": pd.to_datetime(["2026-03-01", None])})
    h = _rendu(monkeypatch, df, statut="Statut", couleurs={"Rupture": "#A61B1B"})
    assert 'data-type="num"' in h and 'data-type="euros"' in h and 'data-type="date"' in h
    assert 'data-v="12.5"' in h and 'data-v="2026-03-01"' in h          # tri et filtres sur la valeur brute
    assert 'data-statut="Rupture"' in h and "s360-filtres" in h           # pastilles par statut
    assert "20 k€" in h and "01/03/2026" in h and "data-reste" not in h


def test_pages_de_200_lignes(monkeypatch):
    df = pd.DataFrame({"PN": [f"P{i:04d}" for i in range(450)], "Qté": range(450)})
    h = _rendu(monkeypatch, df)
    corps = re.search(r"<tbody>(.*)</tbody>", h).group(1)
    assert corps.count("<tr") == 200                                      # 200 lignes dessinées
    reste = json.loads(unescape(re.search(r'data-reste="([^"]*)"', h).group(1)))
    assert len(reste) == 250 and "P0449" in reste[-1]                     # les autres attendent (filtres, « Afficher plus »)
    assert "450 lignes · 200 affichées" in h and "Afficher 200 lignes de plus" in h


def test_tableau_simple_reprend_column_config(monkeypatch):
    import streamlit as st
    df = pd.DataFrame({"Mois": pd.to_datetime(["2026-05-01"]), "Taux (%)": [42.0]})
    cfg = {"Mois": st.column_config.DateColumn("Mois", format="MM/YYYY", help="Mois de commande"),
           "Taux (%)": st.column_config.ProgressColumn("Taux (%)", min_value=0, max_value=100)}
    sortie = []
    monkeypatch.setattr(ui.st, "html", lambda h, **_: sortie.append(h))
    ui.tableau(df, column_config=cfg, height=300)
    h = sortie[-1]
    assert "05/2026" in h and 'title="Mois de commande"' in h and 'class="progres"' in h
