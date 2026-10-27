"""Dossiers importés d'un coup (dossier SharePoint synchronisé) : regroupement par chantier, choix des fichiers.

Fonctions pures, testables sans Streamlit. Les fichiers arrivent avec leur chemin relatif
(« R2/F-HRBA - 151126/extraction.xlsx ») grâce au correctif FormData de build.py ; en développement
local (`streamlit run`), seul le nom est connu et tout est rangé dans un même dossier.
"""

import re
from datetime import date

from core import io as sio

# Dates dans un nom de fichier : AAAAMMJJ (20261020, 2026-10-20) ou JJMMAAAA / JJ.MM.AA.
DATE_ISO = re.compile(r"(?<!\d)(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)")
DATE_FR = re.compile(r"(?<!\d)(0[1-9]|[12]\d|3[01])[-_./]?(0[1-9]|1[0-2])[-_./]?(20\d{2}|\d{2})(?!\d)")
HORS_CHANTIER = ""


def nom_court(chemin: str) -> str:
    return chemin.replace("\\", "/").rsplit("/", 1)[-1]


def date_dans_nom(nom: str) -> date | None:
    """Date d'extraction lue dans le nom du fichier (sans le dossier), ou None."""
    nom = nom_court(nom)
    for motif, ordre in ((DATE_ISO, (0, 1, 2)), (DATE_FR, (2, 1, 0))):
        for m in motif.finditer(nom):
            a, mo, j = (m.group(i + 1) for i in ordre)
            try:
                return date(int(a) if len(a) == 4 else 2000 + int(a), int(mo), int(j))
            except ValueError:
                continue
    return None


def dossier_chantier(chemin: str) -> str:
    """Dossier « <IMMAT> - <JJMMAA> » qui contient le fichier (le plus proche), ou HORS_CHANTIER."""
    parties = chemin.replace("\\", "/").split("/")[:-1]
    for partie in reversed(parties):
        if sio.chantier_depuis_nom(partie):
            return partie
    return HORS_CHANTIER


def regrouper(chemins: list[str]) -> dict[str, list[str]]:
    """{dossier chantier: [chemins]} ; les fichiers hors dossier chantier vont sous HORS_CHANTIER."""
    groupes: dict[str, list[str]] = {}
    for c in chemins:
        groupes.setdefault(dossier_chantier(c), []).append(c)
    return groupes


def chantiers_tries(groupes: dict[str, list[str]]) -> list[str]:
    """Dossiers chantier triés par date de début (les plus proches d'abord), puis par nom."""
    noms = [g for g in groupes if g != HORS_CHANTIER]
    return sorted(noms, key=lambda g: (sio.chantier_depuis_nom(g)[1], g))


def meilleur(chemins: list[str]) -> str:
    """Parmi plusieurs fichiers d'une même source, le plus récent (date dans le nom), sinon le dernier par nom."""
    return max(chemins, key=lambda c: (date_dans_nom(c) or date.min, nom_court(c).lower()))


def repartir(sources: dict[str, str | None]) -> tuple[dict[str, list[str]], list[str]]:
    """{chemin: source} → ({source: [chemins, le retenu en premier]}, [chemins non reconnus])."""
    par_source: dict[str, list[str]] = {}
    inconnus = []
    for chemin, source in sources.items():
        if source is None:
            inconnus.append(chemin)
        else:
            par_source.setdefault(source, []).append(chemin)
    for source, liste in par_source.items():
        retenu = meilleur(liste)
        par_source[source] = [retenu] + sorted((c for c in liste if c != retenu), key=nom_court)
    return par_source, inconnus
