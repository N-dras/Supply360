"""Tests des lectures et croisements (sans Streamlit), sur données FICTIVES."""

import ast
import io
import sys
import types
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from openpyxl import Workbook, load_workbook

from core import io as sio
from core import transforms as tf

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(FIX))
from generer_fixtures import CAS_ATTENDUS, DATE_CHANTIER, GESTIONS  # noqa: E402


def octets(nom: str) -> bytes:
    return (FIX / nom).read_bytes()


@pytest.fixture(scope="module")
def sources():
    besoin = tf.agreger_besoins(sio.lire_besoins_geav(octets("besoins_chantier.xlsx"))[0])
    stock = tf.agreger_stock(sio.lire_etat_stock(octets("etat_stock.xlsx"))[0])
    commandes = tf.agreger_commandes(sio.lire_commandes_sap(octets("commandes_sap.xlsx"))[0])
    return besoin, stock, commandes


@pytest.fixture(scope="module")
def croise(sources):
    return tf.croiser_geav(*sources, GESTIONS, pd.Timestamp(DATE_CHANTIER))


# --------------------------------------------------------------------------
# Lecture / normalisation
# --------------------------------------------------------------------------
def test_normaliser():
    assert sio.normaliser("  QTE SUR\nÉTAGÈRE ") == "qte_sur_etagere"
    assert sio.normaliser("Date de livraison demandée") == "date_de_livraison_demandee"


def test_trouver_colonne_exacte_puis_partielle():
    df = pd.DataFrame(columns=["Code fournisseur", "Fournisseur principal", "PN"])
    assert sio.trouver_colonne(df, "pn", exact=True) == "PN"
    assert sio.trouver_colonne(df, "fournisseur", exact=True) is None
    assert sio.trouver_colonne(df, "fournisseur") == "Code fournisseur"


def test_cle_pn_texte():
    s = pd.Series([123456.0, "  ab-12 ", "000789", None, "", 42])
    assert sio.cle_pn(s).tolist()[:3] == ["123456", "AB-12", "000789"]
    assert sio.cle_pn(s).isna().tolist() == [False, False, False, True, True, False]
    assert sio.cle_pn(s).iloc[5] == "42"


def test_feuilles_et_entetes_detectees():
    assert sio.lire_besoins_geav(octets("besoins_chantier.xlsx"))[1] == "Workpages_PartRequirements"
    assert sio.lire_etat_stock(octets("etat_stock.xlsx"))[1] == "Export"
    assert sio.lire_commandes_sap(octets("commandes_sap.xlsx"))[1] == "Toutes les commandes"


def test_colonne_manquante_message_lisible():
    wb = Workbook()
    wb.active.append(["MPN Prime", "Description"])
    wb.active.append(["FX-1", "x"])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(sio.ColonneIntrouvable, match="Colonne « Qty » introuvable dans le fichier Besoins chantier"):
        sio.lire_besoins_geav(buf.getvalue())


def test_fichier_non_excel():
    with pytest.raises(sio.FichierIllisible):
        sio.lire_etat_stock(b"pas un classeur")


def test_asreq():
    lignes, feuille = sio.lire_besoins_asreq(octets("etude_asreq.xlsm"))
    besoin = tf.agreger_besoins(lignes).set_index("PN")
    assert feuille == "Ordered"
    assert besoin.loc["FX-1002", "QTY_GEAV"] == 2
    assert besoin.loc["FX-1002", "TRFX"] == "BC-0002"
    assert "Description" not in besoin.columns


# --------------------------------------------------------------------------
# Agrégations
# --------------------------------------------------------------------------
def test_besoins_sommes_par_pn(sources):
    besoin = sources[0].set_index("PN")
    assert besoin.loc["FX-1002", "QTY_GEAV"] == 5
    assert besoin.loc["FX-1002", "Nb_lignes"] == 2
    assert "FX-1013" in besoin.index  # « fx-1013 » normalisé
    assert len(besoin) == 16  # la ligne sans PN est ignorée


def test_commandes_psd_la_plus_proche(sources):
    cmd = sources[2].set_index("PN")
    assert cmd.loc["FX-1015", "PSD"] == pd.Timestamp("2026-11-25")
    assert cmd.loc["FX-1015", "Commande"] == "CMD-0152 | CMD-0151"
    assert cmd.loc["FX-1015", "Nb_commandes"] == 2
    assert bool(cmd.loc["FX-1006", "PSD_est_estimee"]) is True
    assert bool(cmd.loc["FX-1012", "Has_risk_class"]) is True


def test_stock_classe_risque_prioritaire():
    lignes = pd.DataFrame({"PN": ["A", "A", "B", "B", "C"], "CLASS_CODE_STOCK": [1.0, 9.0, np.nan, 2.0, np.nan]})
    r = tf._premier_prioritaire(lignes, "PN", "CLASS_CODE_STOCK", tf.CLASSES_RISQUE)
    assert r["A"] == 9.0 and r["B"] == 2.0 and np.isnan(r["C"])


# --------------------------------------------------------------------------
# Croisement
# --------------------------------------------------------------------------
@pytest.mark.parametrize("pn,code", sorted(CAS_ATTENDUS.items()))
def test_action_par_cas(croise, pn, code):
    assert croise.set_index("PN").loc[pn, "ACTION_CODE"] == code


def test_quantites(croise):
    m = croise.set_index("PN")
    assert (m.loc["FX-1003", "Deficit"], m.loc["FX-1003", "Qty_a_commander"]) == (4, 2)
    assert "Commander le complément (2) + relancer Fournisseur Charlie (contact: AC03)" in m.loc["FX-1003", "ACTION"]
    assert m.loc["FX-1008", "ACTION"].startswith("🟠 Relancer Fournisseur Hotel")


def test_gestion_commandes_fait_foi(croise):
    m = croise.set_index("PN")
    assert m.loc["FX-1014", "GESTION"] == 245 and bool(m.loc["FX-1014", "gestion_in_scope"])


def test_classe_risque_prefixe(croise):
    m = croise.set_index("PN")
    assert m.loc["FX-1012", "ACTION"].startswith("🚨 CLASSE 8/9 — PRIORITÉ : 🔴 Commander 2")
    assert not m.loc["FX-1010", "ACTION"].startswith("🚨")


def test_synthese_et_priorisation(croise):
    scope = croise[croise["gestion_in_scope"]]
    s = tf.synthese_geav(scope)
    assert s["n_total"] == 14
    assert (s["n_commander"], s["qty_a_commander"]) == (3, 8)
    assert (s["n_relance"], s["n_relance_urgente"]) == (3, 1)
    actions = tf.actions_a_lancer(scope)
    assert actions["PN"].iloc[0] == "FX-1012"  # classe 9 en tête
    assert actions["ACTION_CODE"].tolist()[1:] == ["commander", "commander", "relancer_urgent",
                                                    "relancer", "relancer", "inconnu"]


def test_jours_avant():
    assert tf.jours_avant(date(2026, 12, 1), date(2026, 11, 1)) == 30


# --------------------------------------------------------------------------
# Non-régression : même résultat que le script d'origine (legacy/streamlit_GEAV.py)
# --------------------------------------------------------------------------
def _legacy():
    """Charge les fonctions du script d'origine sans exécuter son interface Streamlit."""
    source = (ROOT / "legacy" / "streamlit_GEAV.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    arbre.body = [n for n in arbre.body if isinstance(n, (ast.FunctionDef, ast.Import, ast.ImportFrom))
                  and not (isinstance(n, ast.Import) and n.names[0].name == "streamlit")
                  and not (isinstance(n, ast.ImportFrom) and n.module and "plotly" in n.module)
                  and not (isinstance(n, ast.Import) and "plotly" in n.names[0].name)]
    st = types.SimpleNamespace(cache_data=lambda **kw: (lambda f: f))
    ns = {"st": st}
    exec(compile(arbre, "legacy", "exec"), ns)
    return ns


def _comparer(attendu: pd.DataFrame, obtenu: pd.DataFrame):
    a = attendu.set_index("PN").sort_index()
    o = obtenu.set_index("PN").sort_index()
    a_msg = a["ACTION"].str.replace("fichier Stock", "fichier État du stock")
    pd.testing.assert_series_equal(a["ACTION_CODE"], o["ACTION_CODE"], check_dtype=False)
    pd.testing.assert_series_equal(a_msg, o["ACTION"], check_dtype=False, check_names=False)
    for col in ["Deficit", "Qty_a_commander", "QTY_STOCK", "QTY_CDE", "GESTION", "RISK_CLASS"]:
        pd.testing.assert_series_equal(a[col], o[col], check_dtype=False, check_names=False)


def test_identique_au_script_origine_sur_fixtures(croise):
    lg = _legacy()
    besoin, _ = lg["load_besoin"](octets("besoins_chantier.xlsx"))
    stock, _ = lg["load_stock"](octets("etat_stock.xlsx"))
    cmd, _ = lg["load_commandes"](octets("commandes_sap.xlsx"))
    attendu = lg["build_cross"](besoin, stock, cmd, GESTIONS, pd.Timestamp(DATE_CHANTIER))
    _comparer(attendu, croise)


@pytest.mark.parametrize("graine", range(5))
def test_identique_au_script_origine_aleatoire(graine):
    """Croisement sur des données aléatoires : les deux implémentations doivent concorder."""
    rng = np.random.default_rng(graine)
    n = 300
    pns = [f"P{i:04d}" for i in range(n)]
    besoin = pd.DataFrame({"PN": pns, "QTY_GEAV": rng.integers(0, 6, n), "Nb_lignes": 1,
                           "Description": "x", "TRFX": rng.choice(["T1", None], n)})
    dans_stock = rng.random(n) < 0.85
    stock = pd.DataFrame({
        "PN": np.array(pns)[dans_stock],
        "QTY_STOCK": rng.integers(0, 6, dans_stock.sum()).astype(float),
        "QTY_CDE": rng.integers(0, 4, dans_stock.sum()).astype(float),
        "GESTION": rng.choice([245.0, 300.0, np.nan], dans_stock.sum()),
        "CODE_AGENT": rng.choice(["AG1", None], dans_stock.sum()),
        "CODE_FOURNISSEUR": rng.choice(["F1", None], dans_stock.sum()),
        "DERNIER_FOURNISSEUR": rng.choice(["Dernier", None], dans_stock.sum()),
        "Description_stock": "y",
        "CCN": rng.choice(["1", None], dans_stock.sum()),
        "CLASS_CODE_STOCK": rng.choice([1.0, 8.0, np.nan], dans_stock.sum()),
    })
    a_cmd = rng.random(n) < 0.6
    k = a_cmd.sum()
    psd = pd.Series(pd.to_datetime("2026-11-01") + pd.to_timedelta(rng.integers(0, 120, k), "D"))
    psd[rng.random(k) < 0.15] = pd.Timestamp("2031-12-31")
    psd[rng.random(k) < 0.15] = pd.NaT
    commandes = pd.DataFrame({
        "PN": np.array(pns)[a_cmd], "Commande": "C", "Code_acheteur": rng.choice(["AC", None], k),
        "Gestion_cmd": rng.choice([245.0, 246.0, 300.0, np.nan], k),
        "Code_fournisseur_cmd": rng.choice(["FC", None], k), "Fournisseur": rng.choice(["Fourn", None], k),
        "PSD": psd.values, "PSD_est_estimee": False, "Statut": "En cours", "Qty_restant_cmd": 1.0,
        "Nb_commandes": 1, "Class_code": rng.choice([1.0, 9.0, np.nan], k),
        "Has_risk_class": rng.choice([True, False], k), "CCN_cmd": "2",
    })
    date_chantier = pd.Timestamp("2026-12-15")
    attendu = _legacy()["build_cross"](besoin, stock, commandes, [245, 246], date_chantier)
    obtenu = tf.croiser_geav(besoin, stock, commandes, [245, 246], date_chantier)
    assert set(obtenu["ACTION_CODE"]) >= {"ok", "commander", "relancer", "relancer_urgent", "en_cours",
                                          "hors_perimetre", "inconnu"}
    _comparer(attendu, obtenu)


# --------------------------------------------------------------------------
# Export Excel
# --------------------------------------------------------------------------
def test_export_excel_mis_en_forme(croise):
    df = croise[["PN", "QTY_GEAV", "PSD", "ACTION_CODE"]]
    data = sio.exporter_excel({"Synthèse": pd.DataFrame({"Indicateur": ["a"], "Valeur": [1]}), "Détail": df},
                              couleurs_lignes={"Détail": df["ACTION_CODE"].map(tf.ACTION_FILL_HEX).tolist()})
    wb = load_workbook(io.BytesIO(data))
    assert wb.sheetnames == ["Synthèse", "Détail"]
    ws = wb["Détail"]
    assert ws["A1"].font.bold and ws["A1"].fill.start_color.rgb.endswith("002157")
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == f"A1:D{len(df) + 1}"
    assert ws["C2"].number_format == "DD/MM/YYYY"
    assert ws["A2"].fill.start_color.rgb.endswith(tf.ACTION_FILL_HEX[df["ACTION_CODE"].iloc[0]])


def test_nom_export():
    assert sio.nom_export("stock_chantier", date(2026, 10, 22)) == "Supply360_stock_chantier_20261022.xlsx"
