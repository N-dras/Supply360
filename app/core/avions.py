"""Type d'avion d'après l'immatriculation, et image associée (en-tête de Stock par chantier).

Correspondance par série d'immatriculation (3 lettres après « F- ») : un nouvel avion d'une série connue est
reconnu sans rien changer. Une image par famille : fichier `assets/avions/<famille>.webp` ; build.py et
style.css_complet en tirent une classe CSS `s360-avion t-<famille>` (aucune image : rien n'est affiché).
"""

import re

SERIES = {
    "HZU": "A220", "HPN": "A220",
    "GUG": "A318", "GRH": "A319", "GRX": "A319",
    "GKX": "A320", "HEP": "A320", "HBN": "A320", "HZF": "A320",
    "GTA": "A321", "GMZ": "A321",
    "GZC": "A330",
    "HTY": "A350", "HUV": "A350",
    "GSP": "B777-200", "GUO": "B777-200",
    "GSQ": "B777-300", "GZN": "B777-300",
    "HRB": "B787",
}

# Famille d'image de chaque type (même silhouette pour la famille A320)
FAMILLES = {"A220": "a220", "A318": "a320", "A319": "a320", "A320": "a320", "A321": "a320", "A330": "a330",
            "A350": "a350", "B777-200": "b777-200", "B777-300": "b777-300", "B787": "b787"}


def serie(immat) -> str:
    """« F-HTYA », « fhtya », « HTYA » → « HTY » (vide si illisible)."""
    s = re.sub(r"[^A-Z]", "", str(immat or "").upper())
    if len(s) == 5 and s[0] == "F":
        s = s[1:]
    return s[:3] if len(s) >= 4 else ""


def type_avion(immat) -> str | None:
    """Type d'avion (« A350 », « B777-300 »…) ou None si la série est inconnue."""
    return SERIES.get(serie(immat))


def famille(immat) -> str | None:
    """Famille d'image (« a350 », « a320 »…) ou None."""
    t = type_avion(immat)
    return FAMILLES.get(t) if t else None
