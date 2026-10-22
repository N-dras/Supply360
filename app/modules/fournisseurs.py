"""Onglet « Fournisseurs » : en cours de développement."""

from core import components as ui

TAB_ID = "fournisseurs"
TAB_LABEL = "Fournisseurs"
TAB_ICON = "🏭"
TAB_DESCRIPTION = "Performance fournisseurs : OTD / OTIF, retards et commandes en cours."


def render() -> None:
    ui.en_developpement(TAB_ICON, TAB_LABEL, ["OTD / OTIF et score par fournisseur",
                                             "Commandes en cours classées du pire au meilleur statut"])
