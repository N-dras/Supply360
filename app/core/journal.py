"""Diagnostic sous stlite : les erreurs Python (avertissements Streamlit, tracebacks) sont aussi transmises à la
page, qui les garde pour le bandeau « L'application ne répond plus » (bouton « Détails techniques »).

Le moteur Python tourne dans un « worker » du navigateur : ses erreurs n'apparaissent que dans la console de
développement, invisible pour l'utilisateur. Ici, elles sont envoyées à la page par `postMessage` (message
interne au navigateur, aucun accès réseau). Sans effet en local (`streamlit run`).
"""

import logging
import sys

IGNORES = ("Failed to scan component manifests",)


def _envoyer(texte: str) -> None:
    try:
        import js
        from pyodide.ffi import to_js

        js.postMessage(to_js({"type": "s360:journal", "texte": texte[-1500:]}, dict_converter=js.Object.fromEntries))
    except Exception:  # le diagnostic ne doit jamais casser l'app
        pass


class _VersPage(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "_s360", False):  # déjà transmis par un logger enfant (même gestionnaire sur toute la lignée)
            return
        record._s360 = True
        texte = record.getMessage()
        if any(i in texte for i in IGNORES):
            return
        if record.exc_info:
            texte += " | " + logging.Formatter().formatException(record.exc_info).splitlines()[-1]
        _envoyer(f"{record.levelname} {record.name} : {texte}")


class _Sortie:
    """Copie de sys.stderr (tracebacks imprimés, ex. arrêt de la boucle du runtime Streamlit)."""

    def __init__(self, flux):
        self._flux, self._tampon = flux, ""

    def write(self, s):
        n = self._flux.write(s)
        self._tampon += s
        if "\n" in self._tampon:
            bloc, self._tampon = self._tampon.rsplit("\n", 1)
            if bloc.strip() and not any(i in bloc for i in IGNORES):
                _envoyer("stderr : " + bloc)
        return n

    def __getattr__(self, nom):
        return getattr(self._flux, nom)


def installer() -> None:
    """À appeler au démarrage (une seule installation par session du moteur)."""
    if sys.platform != "emscripten" or getattr(sys, "_s360_journal", False):
        return
    sys._s360_journal = True
    gestionnaire = _VersPage(level=logging.WARNING)
    # Les loggers de Streamlit ne remontent pas à leur parent (propagate=False) : on se branche sur chacun.
    noms = [""] + [n for n in logging.root.manager.loggerDict if n.startswith("streamlit")]
    for nom in noms:
        logging.getLogger(nom).addHandler(gestionnaire)
    sys.stderr = _Sortie(sys.stderr)
