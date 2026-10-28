"""PE mousses de l'année (core/pe2026.py) sur les fichiers fictifs besoin_prod_foam.xlsx, etat_stock.xlsx,
commandes_sap.xlsx, pe_mousse_29092026.xlsx et textile_all_parts.csv."""
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from core import io as sio  # noqa: E402
from core import pe  # noqa: E402
from core import pe2026 as p26  # noqa: E402
from core import prevision as pv  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
AUJ = date(2026, 10, 27)


@pytest.fixture(scope="module")
def bp():
    return p26.lire_besoin_prod((FIX / "besoin_prod_foam.xlsx").read_bytes())[0]


@pytest.fixture(scope="module")
def entrees(bp):
    parts = pv.preparer_pieces(pv.lire_pieces((FIX / "textile_all_parts.csv").read_bytes(), "textile_all_parts.csv"), pv.Params())[0]
    lignes, dref = pe.lire_pe_mousses((FIX / "pe_mousse_29092026.xlsx").read_bytes(), "pe_mousse_29092026.xlsx")
    cal = pe.calendrier(lignes, dref, AUJ, pe.ParamsPE())
    stock = sio.lire_etat_stock((FIX / "etat_stock.xlsx").read_bytes())[0]
    cmd = sio.lire_commandes_sap((FIX / "commandes_sap.xlsx").read_bytes())[0]
    return parts, cal, dref, stock, cmd


@pytest.fixture(scope="module")
def calcul(bp, entrees):
    parts, cal, dref, stock, cmd = entrees
    rat = p26.rattacher_avions(bp, parts)
    b = p26.avions_restants(bp, rat, p26.remplaces_depuis(cal, p26.date_debut_annee(dref)))
    m = p26.analyse_ccn(b, stock, cmd)
    blocs, detail = p26.avions_faisables(b, m)
    return rat, b, m, blocs.set_index(["Type avion", "Classe"]), detail


def test_lecture_besoin_prod(bp):
    assert len(bp) == 8 and set(bp["Type avion"]) == {"A350 34J", "B777 14J"}
    r = bp.iloc[0]
    assert (r["CCN"], r["PN"], r["Classe"], r["Composant"], r["Qté par avion"], r["NB_AC"]) == ("7101", "FM-1001", "J", "Assise", 34, 6)
    assert bp.loc[1, "Composant"] == "Dossier" and pd.isna(bp.loc[3, "Restant fichier"])   # restant vide dans le fichier


def test_fichier_reconnu_dans_le_dossier():
    data = (FIX / "besoin_prod_foam.xlsx").read_bytes()
    assert sio.detecter_source(data, "export.xlsx") == "besoin_prod"
    assert sio.reconnaitre_fichier("Besoin_Prod_Foam_v3.xlsx") == "besoin_prod"


def test_rattachement_des_avions_par_leurs_ccn(calcul):
    rat = calcul[0].set_index("Immatriculation")["Type avion"]
    assert (rat[[f"F-XM0{i}" for i in range(1, 7)]] == "A350 34J").all()
    assert (rat[[f"F-XN0{i}" for i in range(1, 5)]] == "B777 14J").all()   # FM-1004 commun, mais J et W propres au B777


def test_avions_restants_recalcules(bp, calcul):
    b = calcul[1].set_index(["Type avion", "Classe", "CCN"])
    # F-XN01 remplacé en 2026 (âge 5 mois au 29/09) : 4 − 1 = 3 ; le fichier disait 4 (pas à jour)
    x = b.loc[("B777 14J", "W", "7203")]
    assert (x["Remplacés cette année"], x["Restant calculé"], x["Avions restants"], x["Restant fichier"]) == (1, 3, 3, 4)
    assert b.loc[("A350 34J", "Y", "7104"), "Avions restants"] == 6           # restant vide dans le fichier : recalculé
    f = p26.avions_restants(bp, calcul[0], pd.DataFrame(), p26.RESTANT_FICHIER).set_index(["Type avion", "Classe", "CCN"])
    assert f.loc[("B777 14J", "W", "7203"), "Avions restants"] == 4 and f.loc[("A350 34J", "Y", "7104"), "Avions restants"] == 6


def test_analyse_par_ccn(calcul):
    m = calcul[2].set_index("CCN")
    y = m.loc["7104"]   # FM-1004 : besoin A350 (266 × 6) + B777 (300 × 3), stock 300, commande 150 (CCN de la commande)
    assert y["Besoin"] == 266 * 6 + 300 * 3 and y["Stock"] == 300 and y["En commande"] == 150
    assert y["À demander (PR)"] == y["Besoin"] - 450 and y["Action"] == p26.ACTIONS[1] and y["Nb types"] == 2
    assert m.loc["7209", "À coter"] and m.loc["7209", "Action"] == p26.ACTIONS[0]   # ni stock, ni prix
    assert m.loc["7104", "PU (€)"] == 45                                             # Dernier PU de l'État du stock


def test_repartition_du_stock_commun():
    blocs = [("A", 3, {"c": 10}), ("B", 3, {"c": 10, "d": 1})]
    assert p26.repartir(blocs, {"c": 40, "d": 5}) == {"A": 2, "B": 2}          # équilibré, sans compter deux fois le stock
    assert p26.repartir(blocs, {"c": 40, "d": 0}) == {"A": 3, "B": 0}          # B bloqué par d
    assert p26.repartir([("A", 2, {"c": 10})], {"c": 100}) == {"A": 2}         # jamais au-delà de l'objectif


def test_avions_faisables(calcul):
    blocs, d = calcul[3], calcul[4]
    # Y : FM-1004 commun (300 en stock) → 1 avion A350 (266) ; plus rien pour le B777 (300), bloqué aussi par FM-2009
    assert blocs.loc[("A350 34J", "Y"), "Complets maintenant"] == 1 and blocs.loc[("B777 14J", "Y"), "Complets maintenant"] == 0
    assert blocs.loc[("B777 14J", "Y"), "PN à coter"] == 1
    tot = blocs[["Complets maintenant", "Complets à réception", "À approvisionner"]].sum(axis=1)
    assert (tot == blocs["Objectif"]).all()
    # chaque CCN seul (sans partage) : FM-1004 suffirait pour 1 avion de chaque type → potentiels > réalité
    pot = d[d["CCN"] == "7104"].set_index("Type avion")["Avions (stock)"]
    assert pot["A350 34J"] == 1 and pot["B777 14J"] == 1
