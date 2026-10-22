"""Tests de l'onglet Textile, de la règle fournisseur, des graphes SVG et de l'export Excel (données FICTIVES)."""

import re
import io
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from openpyxl import load_workbook

from core import charts, xlsx
from core import prevision as pv
from core import io as sio
from core import textile as tx
from core import transforms as tf

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
TODAY = pd.Timestamp("2026-10-22")


def octets(nom):
    return (FIX / nom).read_bytes()


@pytest.fixture(scope="module")
def tables():
    stock, _ = sio.lire_etat_stock(octets("etat_stock.xlsx"))
    cmd, _ = sio.lire_commandes_sap(octets("commandes_sap.xlsx"))
    ref, feuille = sio.lire_references_textile(octets("references_textile.xlsx"))
    assert feuille == "PN Catalog"
    return tx.construire_tables(stock, cmd, ref, TODAY, True)


# --------------------------------------------------------------------------
# Règle fournisseur (demande métier : jamais « fournisseur inconnu »)
# --------------------------------------------------------------------------
def test_fournisseur_retrouve_par_le_code():
    lignes = pd.DataFrame({
        "PN": ["A", "A", "B", "C", "D", "D"],
        "Code_fournisseur_cmd": ["F1", "F1", "F2", np.nan, "F9", np.nan],
        "Fournisseur": ["Alpha", np.nan, np.nan, np.nan, np.nan, np.nan],
    })
    lignes.loc[6] = ["B", "F2", "Bravo"]
    out = tf.completer_fournisseurs(lignes).tolist()
    assert out[:3] == ["Alpha", "Alpha", "Bravo"]      # même code ailleurs dans le fichier
    assert pd.isna(out[3])                             # ni nom ni code, sur aucune ligne du PN
    assert out[4] == "Code F9" and out[5] == "Code F9" # code seul, puis code du même PN


def test_fournisseur_complete_dans_le_fichier_commandes():
    cmd, _ = sio.lire_commandes_sap(octets("commandes_sap.xlsx"))
    ligne = cmd[cmd["Commande"] == "CMD-0031"].iloc[0]
    assert ligne["Fournisseur"] == "Fournisseur Charlie"   # vide dans le fichier, code F003


def test_pn_sans_espaces():
    assert sio.cle_pn(pd.Series([" ab 12 ", "X Y"])).tolist() == ["AB12", "XY"]


# --------------------------------------------------------------------------
# Textile
# --------------------------------------------------------------------------
def test_tables_textile(tables):
    s, o = tables
    assert set(s["PNR"]) == {"FX-1001", "FX-1002", "FX-1003", "FX-1004", "FX-1005", "FX-1006", "FX-1007", "FX-1012",
                             "FX-1015", "FX-2001", "FX-2002"}          # FX-9999 : au catalogue mais pas au stock
    assert tx.annees_conso(s) == [2021, 2022, 2023, 2024, 2025]
    st = s.set_index("PNR")["Statut activité"]
    assert st["FX-2001"] == "Dormant" and st["FX-2002"] == "Inactif" and st["FX-1003"] == "Actif"
    assert s.set_index("PNR").loc["FX-2001", "Valeur stock dormant (€)"] == 720
    assert "Evolution 2025 vs 2024 (%)" in s.columns
    assert s.set_index("PNR").loc["FX-1015", "Commandes (liste)"] == "CMD-0151 ; CMD-0152"


def test_statuts_commandes(tables):
    _, o = tables
    st = o.set_index("Commande")["Statut commande"]
    assert st["CMD-0031"] == "En attente BFE"          # date promise 2049
    assert st["CMD-0007"] == "Sans date promise"       # 2031 : date fictive
    assert st["CMD-0006"] == "Sans date promise"       # vide
    assert st["CMD-0003"] == "A l'heure"               # promise 10/11 vs demandée 01/11 : 9 j ≤ 10 j de tolérance
    assert st["CMD-0005"] == "En retard"
    assert o.set_index("Commande").loc["CMD-0005", "Classe de retard"] == "51 à 150 j"


def test_relances_ordre(tables):
    _, o = tables
    rel = tx.relances(o)
    statuts = rel["Statut commande"].tolist()
    assert statuts == sorted(statuts, key=["En retard", "Sans date promise", "En attente BFE"].index)
    retards = rel.loc[rel["Statut commande"] == "En retard", "Jours de retard"].tolist()
    assert retards == sorted(retards, reverse=True)
    assert "CMD-0012" not in set(rel["Commande"])      # livrée (reste 0) : pas de relance


def test_syntheses(tables):
    s, o = tables
    r = tx.synthese(s, o)
    assert r["pn"] == 11 and r["dormants"] == 1 and r["inactifs"] == 1
    assert tx.resume_categories(s, o)["Catégorie"].tolist() == ["CEINTURE", "HOUSSE", "MOUSSE", "RIDEAUX", "TOTAL"]
    poids = tx.poids_par_categorie(s, o)
    assert poids.loc["PN"].sum() == 11
    assert tx.tableau_retards(o)["Lignes"].sum() == (o["Statut commande"] == "En retard").sum()
    pl = tx.planning_livraisons(o)
    assert not pl.empty and isinstance(pl.index, pd.DatetimeIndex)
    assert pl.sum().sum() == o["Date livraison promise"].notna().sum() + (o["Date livraison promise"].isna()
                                                                           & o["Date livraison demandee"].notna()).sum()


def test_filtre_catalogue_identique():
    """Le filtre en amont sur le catalogue donne le même résultat que le filtre final d'origine."""
    stock, _ = sio.lire_etat_stock(octets("etat_stock.xlsx"))
    cmd, _ = sio.lire_commandes_sap(octets("commandes_sap.xlsx"))
    ref, _ = sio.lire_references_textile(octets("references_textile.xlsx"))
    s1, o1 = tx.construire_tables(stock, cmd, ref, TODAY, True)
    s2, o2 = tx.construire_tables(stock, cmd, ref, TODAY, False)
    s2 = s2[s2["REF_Equipement"].notna()].reset_index(drop=True)
    o2 = o2[o2["REF_Equipement"].notna()].reset_index(drop=True)
    pd.testing.assert_frame_equal(s1, s2[s1.columns])
    pd.testing.assert_frame_equal(o1, o2)


# --------------------------------------------------------------------------
# Agrégation de textes : même résultat que la version d'origine (groupby + fonction)
# --------------------------------------------------------------------------
def test_joindre_par_groupe_equivalent():
    rng = np.random.default_rng(0)
    d = pd.DataFrame({"k": rng.choice(list("abcdefg"), 400), "v": rng.choice(["x", "y", "z", " ", None, "nan", "w"], 400)})
    attendu = d.groupby("k")["v"].agg(tf.joindre_uniques).dropna()
    obtenu = tf.joindre_par_groupe(d, "k", "v").reindex(attendu.index)
    assert obtenu.tolist() == attendu.tolist()


# --------------------------------------------------------------------------
# Graphes HTML : infobulles au survol, fenêtre de mois, valeurs signées
# --------------------------------------------------------------------------
def test_graphes_html():
    h = charts.barres(["A", "B"], {"x": [3, np.nan]}, ligne={"l": [10, 20]}, fmt_ligne=charts.pourcent, survol=["desc A", "desc B"])
    assert len(re.findall(r'class="col[ "]', h)) == 2 and "data-tip=" in h and "desc A&#10;x : 3&#10;l : 10 %" in h and "<polyline" in h
    assert "\n" not in h  # une seule ligne : st.markdown garde le bloc HTML entier
    mois = pd.date_range("2026-01-01", periods=6, freq="MS")
    f = charts.barres(mois, {"x": range(6)}, temporel=True, fenetre=("2026-02-01", "2026-03-01"))
    assert len(re.findall(r'class="col[ "]', f)) == 2 and "02/26" in f and "04/26" not in f       # seuls les mois de la fenêtre
    e = charts.barres(["P1"], {"a": [2], "b": [3]}, empile=True, repere={"Minimum": [8]})
    assert "Total : 5" in e and 'class="rp"' in e and "Minimum : 8" in e
    ec = charts.ecarts(["C1", "C2", "C3"], [25, 4, -3], [["PN X"], ["PN Y"], ["PN Z"]], seuil=10)
    assert "+25 j" in ec and "-3 j" in ec and 'class="zero"' in ec and "PN Z" in ec
    for h in [charts.parts(pd.DataFrame({"a": [1, 3]}, index=["L1", "L2"]), {"a": "#000"}),
              charts.barres_h([("a", 3), ("b", 1, "1 j", "#f00")]), charts.multiples({"A": (["2021"], [1])}),
              charts.chaleur(pd.DataFrame({"01/26": [1]}, index=["F"])), charts.vide(), charts.barres([], {"x": []})]:
        assert h.startswith('<div class="s360-chart">') and "\n" not in h
    assert "<script" not in h and charts._tip(['a "b" <c>']) == ' data-tip="a &quot;b&quot; &lt;c&gt;"'
    assert charts.euros(1_234_567) == "1,2 M€" and charts.court(12_345) == "12k" and charts.entier(1234) == "1 234"


# --------------------------------------------------------------------------
# Prévision de commandes (portage de textile_policy.py)
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def prevision(tables):
    s, o = tables
    p = pv.Params()
    parts, fleet, sans_pn = pv.preparer_pieces(pv.lire_pieces(octets("pieces_par_avion.csv"), "pieces_par_avion.csv"), p)
    plan = pv.lire_planning(octets("planning_pe.xlsx"), "planning_pe.xlsx")
    return pv.run_policy(s, o, parts, fleet, plan, pv.regles_pe_defaut(parts), p, TODAY)


def test_prevision_besoin_et_statuts(prevision):
    pbi, res = prevision
    r = pbi.set_index("PNR")
    # Housse Y : 30 par avion ; A320 (10 avions → 1 d'avance) + A350 (5 avions → 1 d'avance) = 60
    assert r.loc["FX-1002", "Besoin minimum (qté)"] == 60
    assert r.loc["FX-1002", "Statut prévision"] == "A commander"
    assert r.loc["FX-2001", "Statut prévision"] == "Dormant / inactif : pas de commande"
    assert r.loc["FX-1007", "Statut prévision"] == "Hors groupe avion"
    assert res["events"]["registration"].nunique() == 3
    assert set(res["gs"]["Statut groupe"]) <= set(pv.GROUP_STATUS_ORDER)


def test_prevision_par_fournisseur(prevision):
    pbi, res = prevision
    f = pv.par_fournisseur(pbi, res["plan"]).set_index("Fournisseur")
    assert "Fournisseur Bravo" in f.index          # PN sans commande : dernier fournisseur de l'État du stock
    assert f["PN à commander"].sum() == ((pbi["Qté à commander maintenant"] > 0) & pbi["Dans un groupe avion"]
                                         & (pbi["Statut activité"] == "Actif")).sum()
    assert res["plan"]["Fournisseur"].notna().all()


def test_fournisseur_prevision_ordre():
    d = pd.DataFrame({"Fournisseur principal": ["Alpha", "Code F9", np.nan, np.nan, np.nan],
                      "DERNIER FOURNISSEUR": [np.nan, "Bravo", "Charlie", np.nan, np.nan],
                      "CODE FOURNISSEUR": ["F1", "F9", "F3", "F4", np.nan]})
    assert pv.fournisseur_prevision(d).tolist() == ["Alpha", "Bravo", "Charlie", "Code F4", pv.FOURNISSEUR_ABSENT]


# --------------------------------------------------------------------------
# Export Excel (écrivain maison, bibliothèque standard)
# --------------------------------------------------------------------------
def _classeur_test():
    df = pd.DataFrame({"PN": ["A1", "B<&>", None], "Qté": [1, 2.5, np.nan],
                       "Date": pd.to_datetime(["2026-11-15", None, "2027-01-02"]), "Texte": ["é — ü", "", "x"]})
    return xlsx.classeur({"Synthèse": pd.DataFrame({"Indicateur": ["a"], "Valeur": [3]}), "Détail": df},
                         {"Détail": ["F8D7DA", None, "D9F2E6"]}), df


def test_xlsx_relu_par_openpyxl():
    data, df = _classeur_test()
    wb = load_workbook(io.BytesIO(data))
    ws = wb["Détail"]
    assert ws.freeze_panes == "A2" and ws.auto_filter.ref == "A1:D4"
    assert ws["A1"].font.b and ws["A1"].fill.fgColor.rgb.endswith("002157")
    assert ws["C2"].number_format.lower() == "dd/mm/yyyy" and ws["C2"].value.date().isoformat() == "2026-11-15"
    assert ws["A3"].value == "B<&>" and ws["D2"].value == "é — ü" and ws["B3"].value == 2.5
    assert ws["A2"].fill.fgColor.rgb.endswith("F8D7DA")


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice absent")
def test_xlsx_ouvert_par_libreoffice(tmp_path):
    data, _ = _classeur_test()
    f = tmp_path / "test.xlsx"
    f.write_bytes(data)
    subprocess.run(["soffice", "--headless", "--convert-to", "csv", "--outdir", str(tmp_path), str(f)],
                   check=True, capture_output=True, timeout=120)
    csv = (tmp_path / "test.csv").read_text(encoding="utf-8", errors="replace")
    assert "Indicateur" in csv  # première feuille relue par un vrai tableur
