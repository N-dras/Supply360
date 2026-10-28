"""Diagnostic sous stlite : les erreurs Python (avertissements Streamlit, tracebacks) sont aussi transmises à la
page, qui les garde pour le bandeau « L'application ne répond plus » (bouton « Détails techniques »).

Le moteur Python tourne dans un « worker » du navigateur : ses erreurs n'apparaissent que dans la console de
développement, invisible pour l'utilisateur. Ici, elles sont envoyées à la page par `postMessage` (message
interne au navigateur, aucun accès réseau). Sans effet en local (`streamlit run`).
"""

import logging
import re
import sys
import traceback

IGNORES = ("Failed to scan component manifests",)


def _envoyer(texte: str, evenement: str = "") -> None:
    try:
        import js
        from pyodide.ffi import to_js

        js.postMessage(to_js({"type": "s360:journal", "texte": texte[-1500:], "evenement": evenement},
                             dict_converter=js.Object.fromEntries))
    except Exception:  # le diagnostic ne doit jamais casser l'app
        pass


def _resume_exception() -> str:
    typ, exc, tb = sys.exc_info()
    if exc is None:
        return ""
    lieu = traceback.extract_tb(tb)[-1] if tb else None
    return f"{typ.__name__}: {exc}" + (f" ({lieu.filename.rsplit('/', 1)[-1]}:{lieu.lineno})" if lieu else "")


def proteger_runtime() -> None:
    """Garde-fous sur le runtime Streamlit sous stlite (cause des pages figées sans message d'erreur).

    Sous stlite, les clics passent par une seule session « websocket » vers le moteur. Si une exception remonte
    jusqu'à elle, stlite l'avale : la session s'arrête, les clics suivants partent dans le vide et la page reste
    sur « Calcul en cours ». Idem si l'envoi d'un message à la page échoue : la boucle d'envoi de Streamlit s'arrête.
    - une erreur sur un message reçu est journalisée et ignorée, la session continue ;
    - une erreur à l'envoi d'un message est journalisée et le message sauté, la boucle d'envoi continue ;
    - si la session se ferme malgré tout, la page est prévenue tout de suite et relance le moteur.
    """
    from streamlit.runtime import Runtime
    from streamlit.runtime.session_manager import SessionClientDisconnectedError

    traiter, envoyer, deconnecter = Runtime.handle_backmsg, Runtime._send_message, Runtime.disconnect_session

    def handle_backmsg(self, *args, **kwargs):
        try:
            return traiter(self, *args, **kwargs)
        except Exception:
            _envoyer("Erreur ignorée sur un message reçu : " + _resume_exception())

    def _send_message(self, *args, **kwargs):
        try:
            return envoyer(self, *args, **kwargs)
        except SessionClientDisconnectedError:
            raise
        except Exception:
            _envoyer("Message non envoyé (erreur ignorée) : " + _resume_exception())

    def disconnect_session(self, *args, **kwargs):
        _envoyer("Session du moteur fermée" + (" : " + _resume_exception() if sys.exc_info()[1] else ""), "session_fermee")
        return deconnecter(self, *args, **kwargs)

    Runtime.handle_backmsg, Runtime._send_message, Runtime.disconnect_session = handle_backmsg, _send_message, disconnect_session


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
            # Seulement les erreurs (traceback, exception) : pas les avertissements de dépréciation de pandas.
            if bloc.strip() and not any(i in bloc for i in IGNORES) and re.search(r"Traceback|Error|Exception|report this bug", bloc) \
                    and "Warning" not in bloc:
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
    try:
        proteger_runtime()
    except Exception as exc:  # version de Streamlit différente : on garde au moins le journal
        _envoyer(f"Garde-fous du moteur non installés : {exc}")
