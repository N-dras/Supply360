"""Registre des onglets de Supply360, dans l'ordre d'affichage.

Ajouter un onglet = créer `app/modules/<tab_id>.py` (contrat : TAB_ID, TAB_LABEL, TAB_ICON,
TAB_DESCRIPTION, render()) puis l'ajouter à MODULES.
"""

from modules import alertes, fournisseurs, pe_mousses, stock_chantier, textiles

MODULES = [
    stock_chantier,
    textiles,
    pe_mousses,
    fournisseurs,   # en cours de développement
    alertes,        # en cours de développement
]
