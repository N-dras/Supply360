"""Onglet « Alertes » : en cours de développement."""

from core import components as ui

TAB_ID = "alertes"
TAB_LABEL = "Alertes"
TAB_ICON = "🔔"
TAB_DESCRIPTION = "Alertes regroupées : ruptures, retards fournisseurs, chantiers à risque."


def render() -> None:
    ui.en_developpement(TAB_ICON, TAB_LABEL, ["Ruptures et équipements critiques",
                                             "Retards fournisseurs avant le début des chantiers"])
