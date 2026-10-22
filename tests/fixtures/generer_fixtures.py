"""Génère les fichiers FICTIFS de tests/fixtures/ (aucune donnée réelle).

Usage : python tests/fixtures/generer_fixtures.py
Les PN, fournisseurs et codes sont inventés. Chaque PN illustre un cas de la règle
d'action (voir CAS_ATTENDUS, avec une date de début de chantier au DATE_CHANTIER).
"""

from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

ICI = Path(__file__).resolve().parent
DATE_CHANTIER = datetime(2026, 12, 1)
GESTIONS = [245, 246, 247, 400, 401, 230]

# PN → code action attendu (périmètre = GESTIONS, chantier au 01/12/2026)
CAS_ATTENDUS = {
    "FX-1001": "ok",               # stock suffisant
    "FX-1002": "commander",        # aucune commande en cours (2 lignes besoin : 2 + 3)
    "FX-1003": "commander",        # complément à commander + relance
    "FX-1004": "en_cours",         # PSD avant le chantier
    "FX-1005": "relancer_urgent",  # PSD après le chantier
    "FX-1006": "en_cours",         # pas de PSD, date demandée avant le chantier
    "FX-1007": "relancer",         # PSD 2031 = non fournie
    "FX-1008": "relancer",         # QTE EN CDE sans ligne de commande
    "FX-1009": "hors_perimetre",   # gestion 300
    "FX-1010": "inconnu",          # absent de l'état du stock, gestion via commandes
    "FX-1011": "inconnu",          # absent partout (hors périmètre → annexe)
    "FX-1012": "commander",        # classe 9 → préfixe priorité
    "FX-1013": "ok",               # PN saisi en minuscules avec espaces dans les besoins
    "123456": "ok",                # PN numérique
    "FX-1014": "en_cours",         # gestion 300 au stock mais 245 aux commandes (fait foi)
    "FX-1015": "en_cours",         # 2 commandes : la PSD la plus proche est retenue
}


def _feuille(wb, titre, entete, lignes, prefixe=()):
    ws = wb.create_sheet(titre)
    for ligne in prefixe:
        ws.append(list(ligne))
    ws.append(entete)
    for ligne in lignes:
        ws.append(list(ligne))
    return ws


def besoins():
    wb = Workbook()
    wb.remove(wb.active)
    _feuille(wb, "Lisez-moi", ["Info"], [["Export fictif pour les tests"]])
    _feuille(
        wb, "Workpages_PartRequirements",
        ["Task TRFX", "Task Name", "MPN Prime", "Description", "Qty"],
        [
            ["TRFX-01", "Dépose sièges", "FX-1001", "Coussin assise", 4],
            ["TRFX-02", "Housses", "FX-1002", "Housse dossier", 2],
            ["TRFX-02", "Housses", "FX-1002", "Housse dossier", 3],
            ["TRFX-03", "Tablettes", "FX-1003", "Tablette", 6],
            ["TRFX-04", "Rideaux", "FX-1004", "Rideau galley", 3],
            ["TRFX-05", "Moquette", "FX-1005", "Moquette allée", 3],
            ["TRFX-06", "Accoudoirs", "FX-1006", "Accoudoir", 2],
            ["TRFX-07", "Liseuses", "FX-1007", "Liseuse LED", 2],
            ["TRFX-08", "Ceintures", "FX-1008", "Boucle ceinture", 2],
            ["TRFX-09", "Divers", "FX-1009", "Pièce hors périmètre", 1],
            ["TRFX-10", "Divers", "FX-1010", "Pièce non référencée", 1],
            ["TRFX-11", "Divers", "FX-1011", "Pièce inconnue", 1],
            ["TRFX-12", "Sécurité", "FX-1012", "Pièce classe 9", 2],
            ["TRFX-13", "Divers", "  fx-1013 ", "Saisie en minuscules", 1],
            ["TRFX-14", "Divers", 123456, "PN numérique", 1],
            ["TRFX-15", "Divers", "FX-1014", "Gestion corrigée", 2],
            ["TRFX-16", "Divers", "FX-1015", "Deux commandes", 2],
            ["TRFX-17", "Divers", None, "Ligne sans PN (ignorée)", 9],
        ],
        prefixe=[["Besoins chantier — fichier fictif"], []],
    )
    wb.save(ICI / "besoins_chantier.xlsx")


def asreq():
    wb = Workbook()
    wb.remove(wb.active)
    _feuille(
        wb, "Ordered",
        ["N°", "ID BARECODE", "PN + infos pièce sortie", "Qty"],
        [
            [1, "BC-0001", "FX-1001", 2],
            [2, "BC-0002", "FX-1002", 1],
            [3, "BC-0003", "FX-1002", 1],
            [4, "BC-0004", "FX-1009", 1],
        ],
        prefixe=[["Étude ASREQ/NOREQ — fichier fictif"], [], [], [], []],
    )
    wb.save(ICI / "etude_asreq.xlsm")


# PN → [12M, 18M, 24M, 2021…2025, PU, B/O, dernière conso]
CONSO = {
    "FX-2001": [0, 0, 0, 2, 1, 0, 0, 0, 120.0, 0, datetime(2019, 5, 1)],   # dormant : stock, aucune conso sur 3 ans
    "FX-2002": [0, 0, 0, 0, 0, 0, 0, 0, 80.0, 0, datetime(2001, 1, 1)],    # inactif : ni stock, ni conso, ni commande
    "FX-1003": [30, 40, 50, 20, 25, 30, 35, 45, 60.0, 2, datetime(2026, 10, 1)],
}

# Références textile (feuille « PN Catalog ») : PN → catégorie
REFERENCES = {"FX-1001": "CEINTURE", "FX-1002": "HOUSSE", "FX-1003": "HOUSSE", "FX-1004": "RIDEAUX", "FX-1005": "MOUSSE",
              "FX-1006": "MOUSSE", "FX-1007": "CEINTURE", "FX-1012": "HOUSSE", "FX-1015": "RIDEAUX", "FX-2001": "HOUSSE",
              "FX-2002": "RIDEAUX", "FX-9999": "CEINTURE"}


def references():
    wb = Workbook()
    wb.remove(wb.active)
    _feuille(wb, "PN Catalog", ["pn", "equipment", "description", "ccn"],
             [[pn, eq, f"Textile {pn}", 40] for pn, eq in REFERENCES.items()])
    wb.save(ICI / "references_textile.xlsx")


def stock():
    wb = Workbook()
    wb.remove(wb.active)
    _feuille(wb, "Paramètres", ["Clé", "Valeur"], [["version", "fictive"]])
    entete = ["PNR", "DESCRIPTION", "QTE SUR\nÉTAGÈRE", "QTE EN CDE", "GESTION", "CODE AGT APPRO",
              "CODE FOURNISSEUR", "DERNIER FOURNISSEUR", "CCN", "CLASS CODE",
              "QTE CONSO 12M", "QTE CONSO 18M", "QTE CONSO 24M", "QTE CONSO 2021", "QTE CONSO 2022", "QTE CONSO 2023",
              "QTE CONSO 2024", "QTE CONSO 2025", "Dernier PU (achat) Euros", "B/O", "DATE DERNIERE CONSO"]
    lignes = [
            ["FX-1001", "Coussin assise", 10, 0, 245, "AG01", "F001", "Fournisseur Alpha", 11, 1],
            ["FX-1002", "Housse dossier", 1, 0, 245, "AG01", "F002", "Fournisseur Bravo", 12, 1],
            ["FX-1003", "Tablette", 2, 2, 246, "AG02", "F003", "Fournisseur Charlie", 13, 1],
            ["FX-1004", "Rideau galley", 0, 5, 247, "AG02", "F004", "Fournisseur Delta", 14, 1],
            ["FX-1005", "Moquette allée", 1, 3, 400, "AG03", "F005", "Fournisseur Echo", 15, 1],
            ["FX-1006", "Accoudoir", 0, 2, 401, "AG03", "F006", "Fournisseur Foxtrot", 16, 1],
            ["FX-1007", "Liseuse LED", 0, 2, 230, "AG01", "F007", "Fournisseur Golf", 17, 1],
            ["FX-1008", "Boucle ceinture", 0, 2, 245, "AG01", None, "Fournisseur Hotel", 18, 1],
            ["FX-1009", "Pièce hors périmètre", 0, 0, 300, "AG04", "F009", "Fournisseur India", 19, 1],
            ["FX-1012", "Pièce classe 9", 0, 0, 245, "AG01", "F012", "Fournisseur Juliett", 20, 1],
            ["FX-1013", "Saisie en minuscules", 5, 0, 245, "AG01", "F013", "Fournisseur Kilo", 21, 1],
            [123456, "PN numérique", 3, 0, 245, "AG01", "F014", "Fournisseur Lima", 22, 1],
            ["FX-1014", "Gestion corrigée", 0, 2, 300, "AG04", "F015", "Fournisseur Mike", 23, 1],
            ["FX-1015", "Deux commandes", 0, 2, 245, "AG01", "F016", "Fournisseur November", 24, 1],
            ["FX-2001", "Housse dormante", 6, 0, 245, "AG05", "F020", "Fournisseur Papa", 30, 1],
            ["FX-2002", "Rideau inactif", 0, 0, 245, "AG05", "F021", "Fournisseur Quebec", 31, 1],
        ]
    for ligne in lignes:  # consommation et valorisation (fictives), pour l'onglet Textile
        ligne += CONSO.get(ligne[0], [4, 6, 9, 10, 8, 7, 6, 5, 25.0, 0, datetime(2026, 9, 1)])
    _feuille(wb, "Export", entete, lignes)
    wb.save(ICI / "etat_stock.xlsx")


def commandes():
    wb = Workbook()
    # Date d'émission (dernière colonne) : 60 jours avant la date demandée

    wb.remove(wb.active)
    _feuille(wb, "Synthèse", ["Indicateur", "Valeur"], [["Commandes", 9]])
    d = datetime
    _feuille(
        wb, "Toutes les commandes",
        ["PN", "Commande", "Code acheteur", "Gestion", "Code fournisseur", "Fournisseur",
         "Date de livraison demandée", "Date de livraison promise", "Statut de la commande",
         "Quantité restant à livrer", "Class code", "CCN", "Date d'émission de la commande"],
        [
            ["FX-1003", "CMD-0003", "AC03", 246, "F003", "Fournisseur Charlie", d(2026, 11, 1), d(2026, 11, 10), "En cours", 2, 1, 13],
            ["FX-1004", "CMD-0004", "AC04", 247, "F004", "Fournisseur Delta", d(2026, 11, 1), d(2026, 11, 15), "En cours", 5, 1, 14],
            ["FX-1005", "CMD-0005", "AC05", 400, "F005", "Fournisseur Echo", d(2026, 11, 1), d(2027, 1, 10), "En cours", 3, 1, 15],
            ["FX-1006", "CMD-0006", "AC06", 401, "F006", "Fournisseur Foxtrot", d(2026, 11, 20), None, "En cours", 2, 1, 16],
            ["FX-1007", "CMD-0007", "AC07", 230, "F007", "Fournisseur Golf", d(2026, 11, 1), d(2031, 12, 31), "En cours", 2, 1, 17],
            ["FX-1010", "CMD-0010", "AC10", 245, "F010", "Fournisseur Oscar", d(2026, 11, 1), d(2026, 11, 5), "En cours", 1, 1, 25],
            ["FX-1012", "CMD-0012", "AC12", 245, "F012", "Fournisseur Juliett", d(2026, 10, 1), d(2026, 10, 15), "Livrée", 0, 9, 20],
            ["FX-1014", "CMD-0014", "AC14", 245, "F015", "Fournisseur Mike", d(2026, 11, 1), d(2026, 11, 20), "En cours", 2, 1, 23],
            ["FX-1015", "CMD-0151", "AC15", 245, "F016", "Fournisseur November", d(2026, 12, 1), d(2026, 12, 20), "En cours", 1, 1, 24],
            ["FX-1015", "CMD-0152", "AC15", 245, "F016", "Fournisseur November", d(2026, 11, 1), d(2026, 11, 25), "En cours", 1, 1, 24],
            # Sans nom de fournisseur : retrouvé grâce au code F003 (Fournisseur Charlie)
            ["FX-1003", "CMD-0031", "AC03", 246, "F003", None, d(2026, 6, 1), d(2049, 1, 1), "En cours", 1, 1, 13],
        ],
        prefixe=[["Tableau de bord commandes — fichier fictif"], [], ["Mise à jour : fictive"]],
    )
    ws = wb["Toutes les commandes"]
    for row in ws.iter_rows(min_row=5):
        if row[6].value:
            row[12].value = row[6].value - timedelta(days=60)
    wb.save(ICI / "commandes_sap.xlsx")


if __name__ == "__main__":
    besoins()
    asreq()
    stock()
    commandes()
    references()
    print("Fixtures générées dans", ICI)
