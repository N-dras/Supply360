# Supply360 · Air France Industries

Plateforme de pilotage de la supply chain des équipements cabine, livrée sous forme d'**un seul
fichier HTML** : `dist/supply360.html`.

## Utilisation

1. Ouvrir `supply360.html` par **double-clic** (Edge ou Chrome). Aucun serveur, aucune installation.
2. Au premier lancement, le navigateur télécharge son moteur Python depuis `cdn.jsdelivr.net` et
   `pypi.org` : comptez jusqu'à une minute. Les lancements suivants sont plus rapides (cache).
3. Importer les fichiers demandés dans l'onglet. Ils sont **traités localement dans le navigateur**
   et ne sont envoyés nulle part.
4. Rafraîchir la page **réinitialise tout** : il faut alors réimporter les fichiers.

## Onglets

### 🛠️ Stock par chantier (GEAV)

Croise les besoins d'un chantier avec l'état du stock et les commandes pour lister les **pièces à
commander** et les **fournisseurs à relancer** avant la date de début du chantier.

**Paramètres** : type d'étude (Classique ou ASREQ/NOREQ), date de début du chantier, codes Gestion du
périmètre (par défaut 245, 246, 247, 400, 401, 230).

**Fichiers attendus** (feuille et ligne d'en-tête détectées automatiquement, noms de colonnes
insensibles aux accents et aux majuscules) :

| Fichier | Colonnes obligatoires | Colonnes facultatives |
|---|---|---|
| ① Besoins chantier (LOGOPS) — étude Classique | `MPN Prime`, `Qty` | `Task TRFX` / `Task Name` / `Task WP Line`, `Description` |
| ① Étude ASREQ/NOREQ — `.xlsm`, feuille `Ordered`, en-tête en ligne 6 | `PN + infos pièce sortie`, `Qty` | `ID BARECODE` |
| ② État du stock | `PNR`, `QTE SUR ÉTAGÈRE` | `QTE EN CDE`, `GESTION`, `CODE AGT APPRO`, `CODE FOURNISSEUR`, `DERNIER FOURNISSEUR`, `CCN`, `CLASS CODE`, `Description` |
| ③ Commandes (SAP) — feuille « Toutes les commandes » de préférence | `PN` | `Commande`, `Code acheteur`, `Gestion`, `Code fournisseur`, `Fournisseur`, `Date de livraison promise`, `Date de livraison demandée`, `Statut de la commande`, `Quantité restant à livrer`, `Class code`, `CCN` |

**Résultat** : synthèse (KPI et message d'action), **actions à lancer** triées du plus urgent au
moins urgent (classe 8/9 en tête), graphique de répartition, tableau filtrable du périmètre, annexe
avec toutes les références, et export Excel `Supply360_stock_chantier_AAAAMMJJ.xlsx` (feuilles
Synthèse, Actions à lancer, Détail, Annexe ; lignes surlignées par action).

Les règles de calcul sont détaillées dans l'onglet (« Règles de calcul et légende des actions »).

## Développement

```bash
pip install -r requirements-dev.txt     # dev local
streamlit run app/main.py               # tester en local (serveur)
pytest                                  # tests des lectures et croisements
python build.py                         # générer dist/supply360.html
python tests/fixtures/generer_fixtures.py   # régénérer les fichiers fictifs de test
```

Les fichiers de `tests/fixtures/` sont **fictifs** : ils permettent d'essayer l'application sans
données réelles. Voir `CLAUDE.md` pour l'architecture et les règles du projet (ajout d'un onglet :
créer `app/modules/<tab_id>.py` et l'ajouter au registre `app/modules/__init__.py`).
