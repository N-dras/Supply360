"""Registre des onglets de Supply360, dans l'ordre d'affichage.

Ajouter un onglet = créer `app/modules/<tab_id>.py` (contrat : TAB_ID, TAB_LABEL, TAB_ICON,
TAB_DESCRIPTION, render()) puis l'ajouter à MODULES ci-dessous.
"""

from modules import stock_chantier

MODULES = [
    stock_chantier,
]
