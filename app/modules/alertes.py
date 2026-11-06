"""Onglet « Alertes » : en cours de développement.

En attendant le calcul, la page présente ce que l'onglet contiendra : alertes par gestionnaire, infos urgentes,
actions à lancer, ruptures, chantiers à risque, retards fournisseurs. Aucune donnée : texte et aperçu fictif.
"""

from core import components as ui
from core.style import ONGLETS

TAB_ID = "alertes"
TAB_LABEL = "Alertes"
TAB_ICON = "🔔"
TAB_DESCRIPTION = "Alertes par gestionnaire : urgences, actions à lancer, ruptures, chantiers à risque, retards."

CARTES = [
    {"icone": "users", "titre": "Mes alertes",
     "texte": "Chaque gestionnaire ne voit que ce qui le concerne.",
     "points": ["Choix du gestionnaire : code agent appro, code Gestion ou acheteur",
                "Seuils personnels : couverture minimale, jours avant chantier, retard toléré",
                "Réglages retenus sur le poste, d'une session à l'autre"]},
    {"icone": "alert", "titre": "Infos urgentes du jour",
     "texte": "L'essentiel en une ligne, dès l'ouverture.",
     "points": ["Bandeau en tête : « 2 chantiers démarrent cette semaine avec des pièces manquantes »",
                "Nombre d'urgences affiché sur l'onglet Alertes, dans le menu", "Ce qui a changé depuis le dernier import"]},
    {"icone": "check-circle", "titre": "Actions à lancer",
     "texte": "Une seule liste, de la plus urgente à la moins urgente : qui, quoi, avant quand.",
     "points": ["Commandes à passer : chantiers, prévision textile, mousses PE", "Relances fournisseurs à envoyer",
                "Suivi : à faire, en cours, fait", "Export Excel ou texte prêt à coller dans un mail"]},
    {"icone": "box-off", "titre": "Ruptures",
     "texte": "Les pièces qui manquent ou vont manquer.",
     "points": ["PN à stock nul avec un besoin chantier ou une consommation",
                "PN critiques : moins de 1 mois de couverture (seuil réglable)", "Pièces de classe 8 / 9 demandées par un chantier"]},
    {"icone": "calendar", "titre": "Chantiers à risque",
     "texte": "Les chantiers qui risquent de démarrer sans leurs pièces.",
     "points": ["Début dans 14 jours ou moins avec des pièces non couvertes",
                "Livraison promise après le début du chantier", "PN demandé introuvable dans l'État du stock"]},
    {"icone": "truck", "titre": "Retards fournisseurs",
     "texte": "Les commandes qui dérapent.",
     "points": ["Commandes en retard de plus de 30 jours", "Sans date promise, ou en attente de BFE",
                "Commandes ouvertes chez un fournisseur classé C"]},
    {"icone": "armchair", "titre": "PE mousses",
     "texte": "La politique d'entretien des mousses, sous contrôle.",
     "points": ["Classes en retard d'échéance", "Avions qui ne pourront pas être faits faute de mousses",
                "Commandes de mousses à avancer"]},
    {"icone": "file", "titre": "Qualité des données",
     "texte": "Pour se fier aux chiffres.",
     "points": ["Fichier importé trop ancien (plus de 7 jours)", "PN sans fournisseur ni prix",
                "Pour info : stock dormant, aucune sortie depuis 3 ans"]},
]

NIVEAUX = [
    [ui.badge("Urgent", "ko"), "Bloque un chantier ou crée une rupture dans les 14 jours", "Agir aujourd'hui"],
    [ui.badge("À traiter", "orange"), "Risque dans le mois : commande à passer, relance à faire", "Planifier cette semaine"],
    [ui.badge("À surveiller", "warn"), "Signal faible : date promise absente, couverture qui baisse", "Vérifier au prochain point"],
    [ui.badge("Info", "info"), "Pour information : stock dormant, données à mettre à jour", "Rien d'urgent"],
]

APERCU = [
    ("ko", "Urgent", "Chantier A350, début dans 5 jours : 3 pièces non couvertes, dont 1 de classe 8", "Commander ou relancer"),
    ("ko", "Urgent", "2 PN en rupture avec un besoin cette semaine", "Voir les PN"),
    ("orange", "À traiter", "Fournisseur classé C : 6 commandes en retard de plus de 30 jours", "Relancer"),
    ("orange", "À traiter", "Mousses PE : 120 assises à commander avant fin janvier", "Passer la commande"),
    ("warn", "À surveiller", "12 lignes de commande sans date promise", "Demander une date"),
    ("info", "Info", "Le fichier Commandes (SAP) date de 9 jours", "Mettre à jour"),
]


def render() -> None:
    couleur = ONGLETS[TAB_ID][0]
    ui.hero(TAB_ICON, "Alertes", "Tout ce qui demande une action, au même endroit, filtré pour chaque gestionnaire.",
            "Supply Chain · Production · Achats",
            ui.contexte(("Statut", "Bientôt", ui.badge("En développement", "warn")),
                        ("Sources", "Fichiers déjà importés", "")))

    with ui.section(f"{TAB_ID}_quoi", "Ce que vous trouverez", "Huit familles d'alertes", carte=False):
        ui.cartes_fonctions(CARTES, couleur, 4)

    with ui.section(f"{TAB_ID}_niveaux", "Quatre niveaux d'alerte", "Du plus urgent au simple signal",
                    info="Chaque alerte reçoit un niveau selon ce qu'elle bloque et dans combien de temps."):
        ui.tableau_simple(["Niveau", "Ce que ça veut dire", "Que faire"], NIVEAUX)

    with ui.section(f"{TAB_ID}_apercu", "Aperçu", "Exemple fictif du fil d'alertes"):
        ui.apercu_alertes(APERCU)

    ui.callout("<b>Aucun nouvel import</b> : les alertes reprendront les fichiers déjà chargés dans Stock par chantier, "
               "Textile cabine et PE mousses. Les seuils proposés ici sont modifiables.", "info", "ℹ️")
