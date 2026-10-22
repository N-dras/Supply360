# Supply360 · Air France Industries

Plateforme de pilotage de la supply chain des équipements cabine, livrée sous forme d'**un seul
fichier HTML** : `dist/supply360.html`.

## Utilisation

1. Ouvrir `supply360.html` par **double-clic** (Edge ou Chrome). Aucun serveur, aucune installation.
2. Au premier lancement, le navigateur télécharge son moteur Python (environ 15 s) depuis
   `cdn.jsdelivr.net`, plus un petit paquet depuis `pypi.org` / `files.pythonhosted.org`. Ces adresses
   doivent être accessibles via le proxy. Les lancements suivants profitent du cache du navigateur.
3. Importer les fichiers dans l'onglet voulu. Ils sont **traités localement dans le navigateur** et
   ne sont envoyés nulle part.
4. Les fichiers **État du stock** et **Commandes (SAP)** sont communs : importés une fois, ils servent
   à tous les onglets. Changer d'onglet conserve fichiers, filtres et paramètres.
5. Rafraîchir la page **réinitialise tout** : il faut alors réimporter les fichiers.

Pendant un calcul, la barre sous le header s'anime et la pastille « Calcul en cours… » s'affiche.

## Onglets

### 🛠️ Stock par chantier (GEAV)

Pièces à **commander** et fournisseurs à **relancer** avant le début d'un chantier.

**Paramètres** : type d'étude (Classique ou ASREQ/NOREQ), date de début du chantier, codes Gestion du
périmètre (par défaut 245, 246, 247, 400, 401, 230).

| Fichier | Colonnes obligatoires | Colonnes facultatives |
|---|---|---|
| Besoins chantier (LOGOPS) — étude Classique | `MPN Prime`, `Qty` | `Task TRFX` / `Task Name` / `Task WP Line`, `Description` |
| Étude ASREQ/NOREQ — `.xlsm`, feuille `Ordered`, en-tête en ligne 6 | `PN + infos pièce sortie`, `Qty` | `ID BARECODE` |
| État du stock | `PNR`, `QTE SUR ÉTAGÈRE` | `QTE EN CDE`, `GESTION`, `CODE AGT APPRO`, `CODE FOURNISSEUR`, `DERNIER FOURNISSEUR`, `CCN`, `CLASS CODE` |
| Commandes (SAP) — feuille « Toutes les commandes » de préférence | `PN` | `Commande`, `Code acheteur`, `Gestion`, `Code fournisseur`, `Fournisseur`, `Date de livraison promise`, `Date de livraison demandée`, `Class code`, `CCN` |

**Résultat** : synthèse, actions à lancer (classe 8/9 en tête), répartition des actions, tableau
filtrable, toutes les références, export `Supply360_stock_chantier_AAAAMMJJ.xlsx`.

### 🧵 Textile cabine

Stock, consommation, commandes et retards fournisseurs des ceintures, housses, mousses et rideaux.

| Fichier | Colonnes obligatoires | Colonnes facultatives |
|---|---|---|
| État du stock | `PNR`, `QTE SUR ÉTAGÈRE` | `QTE EN CDE`, `DESCRIPTION`, `QTE CONSO 12M / 18M / 24M`, `QTE CONSO <année>`, `Dernier PU (achat) Euros`, `DATE DERNIERE CONSO`, `B/O`, `RP`, `EOQ`, `TDD` |
| Commandes (SAP) | `PN`, `Commande` | `Fournisseur`, `Code fournisseur`, `Date d'émission de la commande`, `Date de livraison demandée / promise`, `Quantité restant à livrer` |
| Références textile — feuille « PN Catalog » | `pn`, `equipment` | `description`, `ccn` |

Seul l'État du stock est indispensable ; les deux autres fichiers complètent l'analyse.

**Sous-onglets** : Synthèse (relances fournisseurs, valeur et activité du stock par catégorie),
Commandes (statuts, livraisons, profondeur des retards, toutes les lignes), Fournisseurs (Pareto,
retards, délais promis, BFE, vue par fournisseur), Consommation (par année, 12/18/24 mois, top PN, par PN).
Un filtre par catégorie s'applique à toutes les vues. Export `Supply360_textiles_AAAAMMJJ.xlsx`.

**Règles** : retard = date promise − date demandée au-delà de 10 jours de tolérance ; date promise 2001,
2030 ou plus (ou vide) = sans date promise ; 2049 = en attente de BFE. PN **dormant** = du stock mais
aucune consommation sur 3 ans ; **inactif** = ni stock, ni consommation, ni commande.

### Fournisseur manquant (tous les onglets)

Quand la colonne `Fournisseur` est vide dans les Commandes (SAP), le nom est retrouvé grâce au
`Code fournisseur` (autres lignes du même code), puis grâce aux autres lignes du même PN ; à défaut, le
code lui-même est affiché (« Code F123 »).

### 🏭 Fournisseurs · 🔔 Alertes

En cours de développement.

## Développement

```bash
pip install -r requirements-dev.txt     # dev local
streamlit run app/main.py               # tester en local (serveur)
pytest                                  # tests des lectures, croisements, exports
python build.py                         # générer dist/supply360.html
python tests/fixtures/generer_fixtures.py   # régénérer les fichiers fictifs de test
```

Les fichiers de `tests/fixtures/` sont **fictifs** : ils permettent d'essayer l'application sans
données réelles. Voir `CLAUDE.md` pour l'architecture et les règles du projet.
