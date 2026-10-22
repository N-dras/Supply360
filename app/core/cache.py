"""Lectures des sources communes, mises en cache et partagées entre onglets.

Un même fichier « État du stock » ou « Commandes (SAP) » importé dans un onglet est lu une seule
fois : l'autre onglet réutilise le résultat. La clé de cache est le contenu du fichier (octets).

`st.cache_resource` plutôt que `st.cache_data` : le résultat est gardé tel quel en mémoire, sans
copie par pickle. Sous Pyodide, relire par pickle un DataFrame contenant des dates échoue
(NotImplementedError) et coûte du temps à chaque interaction. Les fonctions appelantes ne
modifient jamais les tables reçues (elles travaillent sur des copies).
"""

import streamlit as st

from core import io as sio


@st.cache_resource(show_spinner="Lecture de l'État du stock…", max_entries=2)
def etat_stock(data: bytes):
    return sio.lire_etat_stock(data)


@st.cache_resource(show_spinner="Lecture des commandes…", max_entries=2)
def commandes(data: bytes):
    return sio.lire_commandes_sap(data)


@st.cache_resource(show_spinner="Lecture des références textile…", max_entries=2)
def references_textile(data: bytes):
    return sio.lire_references_textile(data)
