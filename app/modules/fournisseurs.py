"""Onglet « Fournisseurs » : en cours de développement.

En attendant le calcul, la page présente ce que l'onglet contiendra : score fournisseur pondéré, indicateurs,
fiche fournisseur, relances. Aucune donnée : texte et exemple fictif seulement.
"""

import streamlit as st

from core import components as ui
from core.style import ONGLETS

TAB_ID = "fournisseurs"
TAB_LABEL = "Fournisseurs"
TAB_ICON = "🏭"
TAB_DESCRIPTION = "Performance fournisseurs : score pondéré, OTD / OTIF, retards et relances."

CARTES = [
    {"icone": "gauge", "titre": "Score fournisseur",
     "texte": "Une note sur 100 par fournisseur pour savoir qui suivre en priorité.",
     "points": ["Classe A / B / C, du plus fiable au moins fiable", "Poids des critères réglables dans Paramètres",
                "Évolution mois par mois sur un an"]},
    {"icone": "target", "titre": "Indicateurs clés",
     "texte": "Les mêmes chiffres pour tous les fournisseurs, désignés par leur code.",
     "points": ["OTD : livré à la date demandée (10 jours de tolérance)", "OTIF : à l'heure et en quantité complète",
                "Retard moyen et retard maximal, en jours", "Lignes sans date promise, lignes en attente BFE",
                "Délai moyen promis (commande → livraison)", "Valeur et nombre de lignes en commande"]},
    {"icone": "file", "titre": "Fiche fournisseur",
     "texte": "Tout sur un fournisseur, sur une seule page.",
     "points": ["Commandes ouvertes, de la pire à la meilleure", "PN les plus en retard",
                "Écart promis − demandé, ligne par ligne", "Chantiers touchés par ses retards (Stock par chantier)"]},
    {"icone": "send", "titre": "Relances",
     "texte": "La liste à envoyer, prête à l'emploi.",
     "points": ["Par fournisseur : commande, PN, date demandée, date promise",
                "D'abord ce qui bloque un chantier ou un PN en rupture", "Export Excel par fournisseur, à joindre au mail"]},
    {"icone": "trend", "titre": "Comparaisons",
     "texte": "Situer chaque fournisseur par rapport aux autres.",
     "points": ["Par famille : ceintures, housses, mousses, rideaux", "Fournisseurs qui s'améliorent ou se dégradent",
                "Poids des 5 premiers fournisseurs dans la valeur commandée"]},
    {"icone": "alert", "titre": "Risques fournisseur",
     "texte": "Repérer les dépendances avant qu'elles ne coûtent un siège.",
     "points": ["PN critique avec un seul fournisseur", "Délais promis qui s'allongent d'un mois sur l'autre",
                "Beaucoup de lignes sans date promise"]},
]

CRITERES = [
    ("Ponctualité (OTD)", 30, "Lignes livrées au plus tard 10 jours après la date demandée"),
    ("Livraison complète (OTIF)", 20, "À l'heure ET toute la quantité commandée"),
    ("Promesses tenues", 15, "La date promise par le fournisseur est respectée"),
    ("Retards en cours", 15, "Part des commandes ouvertes déjà en retard, selon leur valeur"),
    ("Confirmation", 10, "Part des lignes avec une vraie date promise (ni vide, ni 2001, ni 2030 et après)"),
    ("Délai d'approvisionnement", 10, "Délai promis comparé aux autres fournisseurs de la même famille"),
]


def render() -> None:
    couleur = ONGLETS[TAB_ID][0]
    ui.hero(TAB_ICON, "Fournisseurs", "Performance, fiabilité et relances de chaque fournisseur, identifié par son code.",
            "Achats · Pilotage fournisseur",
            ui.contexte(("Statut", "Bientôt", ui.badge("En développement", "warn")), ("Source", "Commandes (SAP)", "")))

    with ui.section(f"{TAB_ID}_quoi", "Ce que vous trouverez", "Six vues pour piloter les fournisseurs", carte=False):
        ui.cartes_fonctions(CARTES, couleur)

    with ui.section(f"{TAB_ID}_score", "Score fournisseur pondéré", "Une note sur 100, six critères",
                    info="Chaque critère est noté de 0 à 100, puis compte selon son poids. Les poids sont réglables."):
        ui.ponderation(CRITERES, couleur)
        st.markdown("")
        a, b = st.columns([1.1, 1], gap="large")
        with a:
            ui.tableau_simple(["Classe", "Ce que ça veut dire", "Que faire"], [
                [ui.badge("A · 80 et plus", "ok"), "Fournisseur fiable", "Suivi normal"],
                [ui.badge("B · 60 à 79", "warn"), "Quelques retards ou promesses non tenues", "Point mensuel, relances ciblées"],
                [ui.badge("C · moins de 60", "ko"), "Retards fréquents, dates souvent absentes", "Plan d'action avec les Achats"],
            ])
        with b:
            ui.callout("<b>Exemple (fictif)</b> : ponctualité 85, livraison complète 70, promesses tenues 90, retards en "
                       "cours 80, confirmation 100, délai 60. Chaque note compte selon son poids : "
                       "<b>81 / 100 → classe A</b>.", "info", "ℹ️")

    ui.callout("<b>À valider ensemble</b> : l'OTD et l'OTIF réels demandent la <b>date de réception effective</b>. "
               "Si l'extraction SAP ne la contient pas, le calcul se fera sur la date promise. Les poids proposés "
               "ci-dessus sont modifiables.", "warn", "⚠️")
