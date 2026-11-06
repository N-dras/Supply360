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
    return pv.run_policy(s, o, parts, fleet, pv.regles_pe_defaut(parts), p, TODAY)


def test_prevision_besoin_et_statuts(prevision):
    pbi, res = prevision
    r = pbi.set_index("PNR")
    # Housse Y : 30 par avion ; A320 (10 avions → 1 d'avance) + A350 (5 avions → 1 d'avance) = 60
    assert r.loc["FX-1002", "Besoin minimum (qté)"] == 60
    assert r.loc["FX-1002", "Statut prévision"] == "A commander"
    assert r.loc["FX-2001", "Statut prévision"] == "Dormant / inactif : pas de commande"
    assert r.loc["FX-1007", "Statut prévision"] in (pv.HORS, "A commander", "A planifier", "OK")  # sans flotte : conso seule
    assert set(res["gs"]["Statut groupe"]) <= set(pv.GROUP_STATUS_ORDER)


def test_prevision_par_fournisseur(prevision):
    pbi, res = prevision
    f = pv.par_fournisseur(pbi, res["plan"]).set_index("Fournisseur")
    assert "F002" in f.index                       # PN sans commande : code fournisseur de l'État du stock
    assert not any(str(x).startswith("Fournisseur ") for x in f.index)  # uniquement des codes : aucun doublon nom / code
    assert f["PN à commander"].sum() == ((pbi["Qté à commander maintenant"] > 0) & pbi["Dans la prévision"]
                                         & (pbi["Statut activité"] == "Actif")).sum()
    assert res["plan"]["Fournisseur"].notna().all()


def test_fournisseur_prevision_ordre():
    """CODE FOURNISSEUR du Résultat → code des commandes → nom des commandes → DERNIER FOURNISSEUR → non renseigné."""
    d = pd.DataFrame({"Fournisseur principal": ["F1", "Alpha", "Bravo", np.nan, np.nan, np.nan],
                      "Fournisseur principal (code)": [True, False, False, False, False, False],
                      "DERNIER FOURNISSEUR": ["Nom 1", "Nom A", np.nan, "Charlie", np.nan, np.nan],
                      "CODE FOURNISSEUR": ["F9", "F2", np.nan, np.nan, "F4", np.nan]})
    assert pv.fournisseur_prevision(d).tolist() == ["F9", "F2", "Bravo", "Charlie", "F4", pv.FOURNISSEUR_ABSENT]


def test_commandes_fournisseur_par_code():
    """Un même code écrit sous deux noms = un seul fournisseur ; ligne sans code : code du même PN, sinon le nom."""
    lignes = pd.DataFrame({"PN": ["A", "A", "B", "C"], "Code_fournisseur_cmd": ["F1", np.nan, "F1", np.nan],
                           "Fournisseur": ["ALPHA SAS", "Alpha", "ALPHA", "Delta"]})
    assert tf.fournisseur_par_code(lignes).tolist() == ["F1", "F1", "F1", "Delta"]


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


# --------------------------------------------------------------------------
# Sous-onglet Stock : couverture en mois de consommation
# --------------------------------------------------------------------------
def test_etat_des_stocks(tables):
    s, _ = tables
    e = tx.etat_stocks(s).set_index("PN")
    # consommé (4 sur 12 mois), stock à 0 → rupture, même avec des commandes en cours
    assert e.loc["FX-1004", "Statut"] == "Rupture" and e.loc["FX-1004", "Couverture avec commandes (mois)"] == 15
    # 2 en stock pour 30 consommés par an (2,5 / mois) → 0,8 mois : critique (seuil 1 mois)
    assert e.loc["FX-1003", "Statut"] == "Critique" and e.loc["FX-1003", "Couverture (mois)"] == 0.8
    assert e.loc["FX-1002", "Statut"] == "Correct"            # 3 mois
    assert e.loc["FX-1001", "Statut"] == "Couverture élevée"  # 30 mois > 24, mais consommé : pas du surstock
    assert e.loc["FX-2001", "Statut"] == tx.DORMANT           # du stock, dernière conso en 2019 : surstock
    assert list(tx.top_dormants(tx.etat_stocks(s))["PN"]) == ["FX-2001"]
    assert tx.etat_stocks(s, seuil_mois=4).set_index("PN").loc["FX-1002", "Statut"] == "Critique"  # seuil réglable
    statuts = list(tx.etat_stocks(s)["Statut"])
    assert statuts == sorted(statuts, key=tx.STOCK_STATUTS.index)  # du plus urgent au moins urgent


def test_top_ruptures(tables):
    s, _ = tables
    top = tx.top_ruptures(tx.etat_stocks(s), n=3)
    assert list(top["PN"])[0] == "FX-1003"                      # le plus consommé d'abord
    assert len(top) == 3 and set(top["Statut"]) <= {"Rupture", "Critique"}


def test_etat_des_stocks_classe_code_et_2001():
    import pandas as pd
    s = pd.DataFrame({
        "PNR": ["A", "B", "C", "D", "E"], "REF_Equipement": ["HOUSSE"] * 5, "CCN": ["C1", "C2", "C3", "C4", "C5"], "DESCRIPTION": ["x"] * 5,
        # A : surstock en classe 3 ; B : rupture en classe 9 ; C : classe 8 ; D : classe 1, surstock ; E : jamais consommé
        "QTE SUR ÉTAGÈRE": [500, 0, 10, 500, 7], "QTE EN CDE": [0, 0, 0, 0, 0], "QTE CONSO 12M": [12, 24, 12, 12, 0],
        "CLASS CODE": [3, 9, 8, 1, None], "Valeur stock (€)": [1000, 0, 50, 1000, 70],
        "DATE DERNIERE CONSO": pd.to_datetime(["2026-05-01", "2026-06-01", "2025-01-01", "2026-01-01", "2001-01-01"]),
    })
    e = tx.etat_stocks(s).set_index("PN")
    # classes 3 / 8 / 9 : jamais en surstock ni en rupture, comptées à part
    assert (e.loc[["A", "B", "C"], "Statut"] == "Obsolète / supprimé").all()
    assert e.loc["A", "Classe code"] == "3 · obsolète" and e.loc["B", "Classe code"] == "9 · supprimé"
    assert e.loc["C", "Classe code"] == "8 · en cours de suppression" and e.loc["D", "Classe code"] == "1"
    assert e.loc["D", "Statut"] == "Couverture élevée" and e.loc["D", "CCN"] == "C4"
    # 2001 = date fictive : jamais consommé, compté à part (pas en surstock)
    assert e.loc["E", "Dernière conso"] == "Jamais consommé" and e.loc["E", "Statut"] == "Jamais consommé"
    assert pd.Timestamp(e.loc["D", "Dernière conso"]) == pd.Timestamp("2026-01-01")
    assert "B" not in set(tx.top_ruptures(e.reset_index())["PN"])
    assert list(tx.etat_stocks(s).columns[:6]) == ["Statut", "PN", "CCN", "Description", "Catégorie", "Classe code"]


def test_prevision_sans_commande_classe_code_3_8_9(tables):
    """Un PN en classe code 3, 8 ou 9 n'est jamais proposé à la commande, même sous l'objectif."""
    s, o = tables
    s = s.copy()
    s.loc[s["PNR"] == "FX-1002", "CLASS CODE"] = 9
    p = pv.Params()
    parts, fleet, _ = pv.preparer_pieces(pv.lire_pieces(octets("pieces_par_avion.csv"), "pieces_par_avion.csv"), p)
    pbi, res = pv.run_policy(s, o, parts, fleet, pv.regles_pe_defaut(parts), p, TODAY)
    r = pbi.set_index("PNR").loc["FX-1002"]
    assert r["Statut prévision"] == pv.OBSOLETE
    assert r["Qté à commander maintenant"] == 0 and r["À commander 36 mois (qté)"] == 0
    assert r[pv.BLOQUEE] > 0 and r["Manque avant livraison possible (qté)"] == 0
    assert "FX-1002" not in set(res["plan"]["PNR"]) and "FX-1002" not in set(pv.suivis(pbi)["PNR"])


def test_surstock_dormant_3_ans():
    s = pd.DataFrame({
        "PNR": ["F", "G", "H", "I"], "REF_Equipement": ["HOUSSE"] * 4, "DESCRIPTION": ["x"] * 4,
        "QTE SUR ÉTAGÈRE": [5, 5, 0, 5], "QTE EN CDE": [0, 0, 0, 3], "QTE CONSO 12M": [0, 0, 0, 0], "QTE CONSO 24M": [0, 0, 0, 0],
        "QTE CONSO 2022": [9, 0, 0, 0], "QTE CONSO 2023": [0, 4, 0, 0], "QTE CONSO 2024": [0, 0, 0, 0], "QTE CONSO 2025": [0, 0, 0, 0],
        "DATE DERNIERE CONSO": pd.to_datetime(["2022-03-01", "2023-06-01", "2020-01-01", "2018-01-01"]),
    })
    e = tx.etat_stocks(s).set_index("PN")["Statut"]
    assert e["F"] == tx.DORMANT                # dernière conso en 2022 : plus de 3 ans
    assert e["G"] == "Sans conso"              # consommé en 2023 : dans les 3 dernières années civiles
    assert e["H"] == "Sans conso"              # dormant mais sans stock : rien à écouler
    assert e["I"] == tx.DORMANT                # surstock même avec une commande en cours


def test_croisement_par_ccn():
    """Une pièce peut avoir un PN différent d'un fichier à l'autre : le CCN fait le lien (catalogue, commandes)."""
    s_l, _ = sio.lire_etat_stock(octets("etat_stock.xlsx"))
    c_l, _ = sio.lire_commandes_sap(octets("commandes_sap.xlsx"))
    cat, _ = sio.lire_references_textile(octets("references_textile.xlsx"))
    # catalogue : FX-1003 écrit autrement, mais même CCN que dans l'État du stock
    ccn_1003 = s_l.loc[s_l["PN"] == "FX-1003", "CCN"].iloc[0]
    cat = cat[cat["PN"] != "FX-1003"]
    cat = pd.concat([cat, pd.DataFrame({"PN": ["FX1003-ALT"], "Equipement": ["HOUSSE"], "Description": ["Tablette"], "CCN": [ccn_1003]})])
    # commande : la ligne de FX-1004 porte un autre PN, avec le CCN de FX-1004
    i = c_l.index[c_l["PN"] == "FX-1004"][0]
    c_l.loc[i, "PN"] = "PN-FOURNISSEUR-1004"
    pbi, o = tx.construire_tables(s_l, c_l, cat, TODAY, True)
    assert "FX-1003" in set(pbi["PNR"])                                   # reconnu textile par son CCN
    assert pbi.set_index("PNR").loc["FX-1003", "REF_Equipement"] == "HOUSSE"
    ligne = o[o["PN commandé"] == "PN-FOURNISSEUR-1004"]
    assert len(ligne) == 1 and ligne["PNR"].iloc[0] == "FX-1004"          # rattachée au PN du stock par le CCN
    assert tx.cle_ccn(pd.Series([12.0, " ab 1", None, "nan"])).tolist()[:2] == ["12", "AB1"]


def test_perimetre_flotte_et_equipement(tables):
    """Barre « Périmètre » : flotte (PN ou CCN montés sur ces avions, textile_all_parts) et équipement."""
    from modules import textiles as T
    s, o = tables
    parts = pd.DataFrame({"aircraft_type": ["A320", "A350"], "pn": ["FX-1002", "AUTRE-PN"],
                          "ccn": ["", str(s.loc[s["PNR"] == "FX-1003", "CCN"].iloc[0])]})
    cles = T._cles_flottes(parts, ("A350",))
    s2, _ = T._filtrer(s, o, ((), cles))
    assert set(s2["PNR"]) == {"FX-1003"}                         # retrouvé par le CCN monté sur A350
    s3, _ = T._filtrer(s, o, (("HOUSSE",), None))
    assert set(tx.categorie(s3)) == {"HOUSSE"}
    assert T._cles_flottes(parts, ()) is None                    # aucune flotte choisie : tout


def test_tendance_conso():
    """Rythme pondéré 12 / 18 / 24 mois (50 / 30 / 20 %) et tendance des 12 derniers mois contre les 12 d'avant."""
    d = pd.DataFrame({"QTE CONSO 12M": [120, 50, 0, 30, 0], "QTE CONSO 18M": [162, 90, 0, 30, 10],
                      "QTE CONSO 24M": [192, 130, 0, 30, 40], "QTE CONSO 2024": [90, 80, 0, 0, 30], "QTE CONSO 2025": [110, 60, 0, 30, 10]})
    t = pv.tendance_conso(d, pv.Params(), pd.Timestamp("2026-11-04"))
    assert t["Conso prévue / mois"].round(1).tolist()[0] == 9.3            # 0,5 × 10 + 0,3 × 9 + 0,2 × 8
    assert t["Tendance conso"].tolist() == ["En hausse", "En baisse", "Sans conso", "Nouveau", "En baisse"]
    assert t["Évolution conso (%)"].iloc[0] == 67                          # 120 contre 72
    assert t["Irrégularité (pièces / mois)"].iloc[2] == 0                  # pas de conso : pas d'irrégularité


def test_stock_securite():
    """Stock de sécurité = coefficient (95 % → 1,65) × irrégularité × racine du délai ; 0 sans conso prévue."""
    ss = pv.stock_securite([10, 0], [4, 4], [4, 4], 0.95)
    assert ss.tolist() == [14.0, 0.0]                                      # 1,65 × 4 × 2 = 13,2 → 14


def test_prevision_suit_la_conso(prevision):
    """La demande prévue est la consommation : commandes sur la période ≥ conso prévue − stock − commandes en cours."""
    pbi, _ = prevision
    r = pbi[pbi["Dans la prévision"] & (pbi["Statut activité"] == "Actif") & ~tx.fin_de_vie(pbi)]
    assert (r["Stock à tenir (qté)"] >= r["Besoin minimum (qté)"]).all()
    assert (r["Stock à tenir (qté)"] >= r["Stock de sécurité (qté)"]).all()
    manque = r["Stock à tenir (qté)"] + r["Conso prévue sur la période (qté)"] - r["QTE SUR ÉTAGÈRE"].fillna(0) - r["QTE EN CDE"].fillna(0)
    assert (r["À commander 36 mois (qté)"] + 1 >= manque.clip(lower=0)).all()


def test_flottes_pn():
    """PN commun à deux flottes : il apparaît sous chacune ; part des pièces installées sur la flotte filtrée."""
    gp = pd.DataFrame({"pn": ["P1", "P1", "P2"], "aircraft_type": ["A320", "A220", "A350"], "qty_per_ac": [10, 10, 4],
                       "avions_avec_pn": [3, 1, 2]})
    f = pv.flottes_pn(gp, ["A320"])
    assert f.loc["P1", "Flottes"] == "A220 · A320" and f.loc["P1", "Part des flottes choisies (%)"] == 75
    assert f.loc["P2", "Part des flottes choisies (%)"] == 0


def test_delai_pn_avant_fournisseur():
    """Délai : celui du PN d'abord, la moyenne de son fournisseur (CODE FOURNISSEUR du Résultat, 3 PN au moins) ensuite,
    le défaut en dernier ; arrondi au mois supérieur."""
    d = pd.DataFrame({"PNR": ["A", "B", "C", "D", "E"], "CODE FOURNISSEUR": ["F1", "F1", "F1", "F1", "F2"],
                      "LT observé moyen sur 2 ans": [120, 30, 45, np.nan, np.nan]})
    x = pv.ajouter_delais(d, None, pv.Params())
    mois, jours, src = pv.lead_time_months(x, pv.Params())
    assert list(jours) == [120, 30, 45, 65, 60] and list(mois) == [4, 1, 2, 3, 2]
    assert list(src) == ["PN", "PN", "PN", "Fournisseur (moyenne)", "Défaut"]
