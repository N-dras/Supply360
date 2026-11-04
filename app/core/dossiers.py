"""Dossiers importés d'un coup (dossier SharePoint synchronisé) : regroupement par chantier, choix des fichiers.

Fonctions pures, testables sans Streamlit. Les fichiers arrivent avec leur chemin relatif
(« R2/F-XKAA - 151126/extraction.xlsx ») grâce au correctif FormData de build.py ; en développement
local (`streamlit run`), seul le nom est connu et tout est rangé dans un même dossier.
"""

import re
from datetime import date, datetime

from core import io as sio

# Dates dans un nom de fichier : AAAAMMJJ (20261020, 2026-10-20) ou JJMMAAAA / JJ.MM.AA.
DATE_ISO = re.compile(r"(?<!\d)(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)")
DATE_FR = re.compile(r"(?<!\d)(0[1-9]|[12]\d|3[01])[-_./]?(0[1-9]|1[0-2])[-_./]?(20\d{2}|\d{2})(?!\d)")
HORS_CHANTIER = ""
# Date de modification du fichier (ms), ajoutée devant le chemin par build.py (« @1730650000000@/Textile/x.xlsx ») :
# sert à retenir le fichier le plus récent quand aucune date n'est écrite dans son nom.
MARQUE_MODIF = re.compile(r"@(\d{10,})@/")
# Fichiers « Résultat » du dossier Textile (nom normalisé : minuscules, sans accents, espaces → _) :
# « Résultat … ALL TEXTILE … » pour l'onglet Textile cabine, « Résultat … PE … » pour l'onglet PE mousses.
RESULTAT_ALL_TEXTILE = r"^resultat.*all[_\-.]*textile"
RESULTAT_PE = r"^resultat.*(?<![a-z])pe(?![a-z])"


def nom_court(chemin: str) -> str:
    return chemin.replace("\\", "/").rsplit("/", 1)[-1]


def date_modif(chemin: str) -> int:
    """Date de modification du fichier en millisecondes (0 si inconnue, ex. en développement local)."""
    m = MARQUE_MODIF.search(chemin.replace("\\", "/"))
    return int(m.group(1)) if m else 0


def sans_marque(chemin: str) -> str:
    """Chemin sans la date de modification ajoutée par build.py."""
    return MARQUE_MODIF.sub("", chemin)


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


def _recence(chemin: str) -> tuple:
    ms = date_modif(chemin)
    jour = date_dans_nom(chemin) or (datetime.fromtimestamp(ms / 1000).date() if ms else date.min)
    return jour, ms, nom_court(chemin).lower()


def meilleur(chemins: list[str]) -> str:
    """Parmi plusieurs fichiers d'une même source, le plus récent : date écrite dans le nom, à défaut date de
    modification du fichier ; à égalité, le dernier modifié, puis le dernier par nom."""
    return max(chemins, key=_recence)


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


def appliquer_noms(sources: dict[str, str | None], regles: dict) -> dict[str, str | None]:
    """Règles de nommage propres à un dossier ({source: motif regex, ou liste de motifs par ordre de préférence}, sur le
    nom normalisé, sans accents ni majuscules), appliquées dans l'ordre.

    Si au moins un fichier correspond au motif d'une source, il fait foi : il prend cette source et les autres
    fichiers reconnus comme cette source par leur contenu sont écartés. Avec une liste, le premier motif qui trouve un
    fichier l'emporte (ex. « Résultat ALL TEXTILE », à défaut tout « Résultat »). Un fichier pris par une règle ne
    peut plus l'être par une règle suivante. Sans fichier correspondant, la détection par contenu s'applique.
    """
    sources = dict(sources)
    pris: set[str] = set()
    for source, motifs in regles.items():
        retenus = []
        for motif in [motifs] if isinstance(motifs, str) else motifs:
            retenus = [c for c in sources if c not in pris and re.search(motif, sio.normaliser(nom_court(c)))]
            if retenus:
                break
        if not retenus:
            continue
        pris.update(retenus)
        for c in sources:
            if c in retenus:
                sources[c] = source
            elif sources[c] == source and c not in pris:
                sources[c] = None
    return sources
