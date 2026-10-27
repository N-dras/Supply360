"""Planning PE des mousses (core/pe.py) sur les fichiers fictifs pe_mousse_29092026.xlsx et textile_all_parts.csv."""
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from core import io as sio  # noqa: E402
from core import pe  # noqa: E402
from core import prevision as pv  # noqa: E402
from core import textile as tx  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
AUJ = date(2026, 10, 27)


@pytest.fixture(scope="module")
def lignes():
    return pe.lire_pe_mousses((FIX / "pe_mousse_29092026.xlsx").read_bytes(), "pe_mousse_29092026.xlsx")


@pytest.fixture(scope="module")
def planning(lignes):
    l, dref = lignes
    parts, _, _ = pv.preparer_pieces(pv.lire_pieces((FIX / "textile_all_parts.csv").read_bytes(), "textile_all_parts.csv"), pv.Params())
    stock = sio.lire_etat_stock((FIX / "etat_stock.xlsx").read_bytes())[0]
    cmd = sio.lire_commandes_sap((FIX / "commandes_sap.xlsx").read_bytes())[0]
    pbi, o = tx.construire_tables(stock, cmd, pe.catalogue_mousses(parts), AUJ, True)
    return pe.planning_pe(l, dref, parts, pe.articles(pbi), o, AUJ, pe.ParamsPE())


def test_lecture_fichier_mensuel(lignes):
    l, dref = lignes
    assert dref == date(2026, 9, 29)                                  # date des âges lue dans le nom du fichier
    assert l["Immatriculation"].nunique() == 10 and l.groupby("Composant").size().to_dict() == {"Assise": 30, "Dossier": 10}
    assert l.groupby("Flotte")["Immatriculation"].nunique().to_dict() == {"A350": 6, "B777": 4}
    xm04 = l[(l["Immatriculation"] == "F-XM04") & (l["Composant"] == "Dossier")].iloc[0]
    assert xm04["Âge extraction (mois)"] == 108 and not xm04["Âge exact"]          # « > 108 » : âge minimum
    xn02 = l[l["Immatriculation"] == "F-XN02"].iloc[0]
    assert xn02["Date visite"] == date(2027, 8, 16)                    # « 16AOUT2027 » (mois en français)


def test_dates_dans_les_textes_de_visite():
    assert pe.date_texte("EO : S06 - MOD - BOD - 03-FEB-2025 [TRFX]") == date(2025, 2, 3)
    assert pe.date_texte("MRI : S37 - ORY - 07-SEPT-2026 [TR") == date(2026, 9, 7)
    assert pe.date_texte("MRI : SNT - S15 - 12APR2026 [TRFX]") == date(2026, 4, 12)
    assert pe.date_texte("MRI : EXT - S2 - 11JAN27 [TRFX]") == date(2027, 1, 11)
    assert pe.date_texte("dont 14 siège J remplacé") is None


def test_composant_et_classe_des_mousses():
    assert [pe.composant_mousse(d) for d in ["FOAM BACKREST J", "FOAM BACK Y", "FOAM BOTTOM SEAT", "FOAM BOTT W", "FOAM HEADREST"]] == \
        ["Dossier", "Dossier", "Assise", "Assise", None]
    assert [pe.classe_cabine(a) for a in ["J", "w", "Business", "Economy", "NA"]] == ["J", "W", "J", "Y", None]


def test_statuts_et_dates_prevues(planning):
    cal = planning["cal"].set_index(["Immatriculation", "Classe", "Composant"])
    assert len(planning["cal"]) == 40                                   # dossiers W / Y : jamais → exclus
    assert cal.loc[("F-XM03", "Y", "Assise"), "Statut"] == "En retard"          # 41 mois > 36 + 3 de tolérance
    assert cal.loc[("F-XM06", "J", "Assise"), "Statut"] == "Délai toléré"       # 38 mois
    assert cal.loc[("F-XM02", "J", "Assise"), "Statut"] == "À faire < 3 mois"   # échéance 29/11/2026
    assert cal.loc[("F-XM02", "J", "Dossier"), "Échéance"] == pd.Timestamp(2026, 11, 29)  # 70 mois + 2 → cycle 72
    x = cal.loc[("F-XN02", "J", "Assise")]                              # prochaine visite après l'échéance : signalée
    assert x["Date prévue"] == pd.Timestamp(2027, 8, 16) and x["Visite après l'échéance"]
    assert cal.loc[("F-XM03", "J", "Assise"), "Date prévue"] == pd.Timestamp(2026, 10, 1)  # retard → mois en cours


def test_stock_de_securite_10_pct_par_flotte(planning):
    ss = planning["synth"].set_index("PN")["Stock de sécurité"]
    assert ss["FM-1004"] == 266 + 300          # Y : 1 avion A350 (6 avions) + 1 avion B777 (4 avions)
    assert ss["FM-1001"] == 34                 # J assise A350 : ceil(10 % × 6) = 1 avion × 34


def test_forecast_mois_par_mois(planning):
    long = planning["long"].set_index(["PN", "Mois"])
    oct_, jan = pd.Timestamp(2026, 10, 1), pd.Timestamp(2027, 1, 1)
    assert long.loc[("FM-1004", oct_), "Besoin"] == 1398                       # retard rattrapé dès ce mois-ci
    assert long.loc[("FM-1004", oct_), "À livrer"] == 1398 - 300 + 566         # stock 300, sécurité 566
    assert long.loc[("FM-1004", jan), "Arrivées commandes"] == 150 and long.loc[("FM-1004", jan), "À livrer"] == 266 - 150
    s = planning["synth"].set_index("PN")
    assert s.loc["FM-1004", "À commander 12 mois"] == pytest.approx(planning["long"].query("PN == 'FM-1004'")["À livrer"].head(12).sum())
    assert s.loc["FM-1004", "Fournisseur"] == "Fournisseur Tango" and s.loc["FM-1004", "Prix unitaire (€)"] == 45
    assert s.loc["FM-1004", "Valeur 12 mois (€)"] == s.loc["FM-1004", "À commander 12 mois"] * 45


def test_controles(planning):
    assert set(planning["non_reconnues"]["description"]) >= {"FOAM HEADREST J"}
    assert planning["sans_pn"].empty and planning["pn_absents_stock"] == []


def test_fichier_pe_reconnu_dans_un_dossier():
    data = (FIX / "pe_mousse_29092026.xlsx").read_bytes()
    assert sio.detecter_source(data, "export.xlsx") == "pe" and sio.reconnaitre_fichier("PE_MOUSSE_29092026_F.xlsx") == "pe"
