# CLAUDE.md — Supply360 · Air France Industries

Ce fichier cadre tout le travail sur ce dépôt. Relis-le en début de session et respecte-le à chaque modification.

---

## 1. Contexte

**Supply360** est la plateforme de pilotage de la supply chain des équipements cabine d'Air France Industries. Elle relie trois domaines : **Supply Chain** (stock, commandes), **Production** (chantiers de maintenance) et **Achats** (pilotage fournisseur).

Ce dépôt contient la version opérationnelle de Supply360 : une **app tout-en-un** construite brique par brique. Chaque brique d'analyse devient un **onglet**, par exemple :

- analyse de stock par chantier de maintenance ;
- analyse stock / commandes des textiles cabine ;
- les briques suivantes, au fil de l'eau.

**Pourquoi un fichier HTML autonome ?** L'app Streamlit hébergée en interne plante souvent et doit être relancée en permanence, si bien que les collègues ne peuvent pas l'utiliser en l'absence de l'auteur. L'app est donc livrée sous forme d'**un seul fichier HTML** qui exécute Streamlit dans le navigateur grâce à **stlite / Pyodide**. Il n'y a aucun serveur à maintenir : chacun ouvre le fichier et l'utilise.

Conséquences à garder en tête :

- Les données sont traitées **localement dans le navigateur** de l'utilisateur et ne transitent par aucun serveur.
- Rafraîchir la page **réinitialise tout**. C'est voulu : chaque session repart de zéro.
- Au premier lancement, le navigateur télécharge Pyodide et les paquets depuis le CDN jsdelivr (et le paquet `protobuf` de Streamlit depuis PyPI, demandé par stlite lui-même), ce qui prend une quinzaine de secondes.

---

## 2. Règles absolues

1. **Aucune donnée réelle dans le code, le dépôt ou le HTML.** Les utilisateurs importent leurs fichiers à chaque session. Ne jamais coder en dur de valeurs issues de vraies extractions (PN, prix, fournisseurs, chantiers).
2. **Ne jamais mentionner le nom de l'outil d'optimisation du stock du groupe**, ni dans l'interface, ni dans le code, ni dans les commentaires, ni dans les noms de fichiers. Utiliser le libellé générique « État du stock ».
3. **Libellés des sources de données :**
   - « État du stock » : export Excel de l'outil d'optimisation du stock (sans le nommer) ;
   - « Commandes (SAP) » : extraction SAP des commandes ;
   - « Besoins chantier (LOGOPS) » : demandes de chantier issues de LOGOPS.
4. **Interface entièrement en français.**
5. **Aucun appel réseau dans le code Python** : pas de `requests`, `urllib`, API, base de données, ni chemin local (`C:\...`). Tout passe par `st.file_uploader`.
6. **Le HTML livré doit rester un fichier unique** qui fonctionne par double-clic.

---

## 3. Architecture

```
supply360/
├── CLAUDE.md
├── README.md                 # mode d'emploi pour les utilisateurs
├── requirements.txt          # dépendances runtime (minimales, voir §4)
├── requirements-dev.txt      # streamlit, pytest… pour le dev local
├── build.py                  # assemble app/ → dist/supply360.html
├── .github/workflows/pages.yml  # publication GitHub Pages (build.py → index.html) à chaque push sur main
├── .streamlit/
│   └── config.toml           # thème Streamlit (couleurs de la charte)
├── assets/
│   ├── logo_afi.png          # logo Air France Industries (fourni par l'auteur, ne pas redessiner ; fond transparent)
│   ├── fond_aeroport.webp    # fond d'écran (prototype v3)
│   ├── avion_a350.webp       # avion Air France (décor : titres d'onglet, écran de chargement)
│   └── fonts/                # Manrope (woff2, licence OFL), embarquée dans le thème
├── app/
│   ├── main.py               # point d'entrée : page_config, style, header, navigation
│   ├── core/
│   │   ├── theme.css         # thème (tokens, header, cartes, graphes) ; images via asset(nom)
│   │   ├── style.py          # couleurs de la charte + injection du thème (dev local uniquement)
│   │   ├── components.py     # header, section, kpi_card, fichier, tableau, graphe, sous_onglets…
│   │   ├── charts.py         # graphes HTML / SVG légers (barres, écarts, 100 %, chaleur) : infobulles au survol
│   │   ├── io.py             # lecture xlsx (calamine), normalisation et validation des colonnes, export Excel
│   │   ├── xlsx.py           # écriture .xlsx mise en forme, bibliothèque standard
│   │   ├── cache.py          # lectures communes mises en cache, partagées entre onglets
│   │   ├── transforms.py     # fonctions de croisement réutilisables (stock × besoins × commandes)
│   │   ├── dossiers.py       # import de dossier : regroupement par chantier, choix du fichier le plus récent
│   │   ├── textile.py        # calculs de l'onglet Textile cabine
│   │   ├── prevision.py      # prévision de commandes textile (stock minimum, PE, plan par fournisseur)
│   │   ├── pe.py             # Planning PE des mousses : fichier PE_MOUSSE, échéances, stock de sécurité, forecast 12/24/36 mois
│   │   ├── pe2026.py         # PE mousses de l'année : Besoin Prod × stock × commandes par CCN, avions restants, avions faisables
│   │   └── journal.py        # stlite : erreurs Python transmises au bandeau de diagnostic de la page
│   └── modules/
│       ├── __init__.py       # REGISTRE des onglets (ordre d'affichage)
│       ├── stock_chantier.py
│       ├── textiles.py
│       ├── pe_mousses.py     # PE mousses : année (Besoin Prod), avions faisables, CCN, avancement PE, forecast
│       ├── _planning_pe.py   # rendu « Avancement PE » et « Forecast » de pe_mousses (« _ » : pas un onglet du registre)
│       ├── fournisseurs.py   # en cours de développement
│       └── alertes.py        # en cours de développement
├── legacy/                   # scripts Streamlit d'origine à intégrer (référence, non buildés)
├── tests/
│   ├── fixtures/             # données FICTIVES générées par script
│   ├── test_transforms.py
│   ├── test_textile.py
│   ├── test_pe.py
│   ├── test_pe2026.py
│   └── test_app.py           # l'app démarre sur chaque onglet
└── dist/
    └── supply360.html        # livrable (généré)
```

### 3.1 Contrat d'un module (onglet)

Chaque fichier de `app/modules/` expose :

```python
TAB_ID = "textiles"                   # identifiant court, unique, sans accent
TAB_LABEL = "Textiles cabine"         # libellé affiché
TAB_ICON = "🧵"                       # icône de l'onglet
TAB_DESCRIPTION = "Stock, commandes et couverture des besoins sur les textiles cabine."

def render() -> None:
    """Dessine l'onglet complet. Aucun effet de bord hors de st.*"""
```

- Le registre `app/modules/__init__.py` contient la liste ordonnée `MODULES = [stock_chantier, textiles, ...]`. **Ajouter un onglet = créer le fichier + l'ajouter au registre.** Rien d'autre ne doit changer.
- **Seul le module actif s'exécute.** La navigation passe par `st.session_state["active_tab"]` et un sélecteur horizontal stylé, pas par `st.tabs`, qui exécuterait tous les onglets à chaque interaction. Vérifier que le composant choisi existe dans la version de Streamlit embarquée par stlite.
- Toutes les clés de `st.session_state` et de widgets d'un module sont **préfixées par son `TAB_ID`** (`textiles__stock_file`…) pour éviter les collisions. Exception : l'import partagé entre onglets `commun__commandes` — le fichier « Commandes (SAP) » est le même pour tous. L'« État du stock » est propre à chaque onglet (il change d'un chantier à l'autre).
- **Import d'un dossier** : `components.import_dossier(...)` en tête du bloc d'import. Chaque fichier est reconnu par son **contenu** (`io.detecter_source` : en-têtes), à défaut par son nom (`io.reconnaitre_fichier`) ; plusieurs fichiers d'une même source → le plus récent (`dossiers.meilleur`, date dans le nom), modifiable. Stock par chantier : sélection d'un dossier (`accept_multiple_files="directory"`), fichiers regroupés par dossier « <IMMAT> - <JJMMAA> » (`core/dossiers.py`), qui donne immatriculation et date de début. stlite n'envoie que le nom des fichiers : build.py redéfinit `FormData.append` pour transmettre le chemin relatif (`webkitRelativePath`).
- **Dossier mémorisé** (JavaScript de build.py, API File System Access, Edge/Chrome) : `components.bouton_dossier(dossier, cible, mode)` affiche « 📂 Ouvrir <dossier> ». Le dossier (R2, Textile, COMMANDE) est choisi une fois puis retenu en IndexedDB ; au clic suivant, « Autoriser » suffit. Les fichiers sont lus dans le navigateur puis **déposés dans le `file_uploader` de clé `cible`** (DataTransfer + événement change) : le Python ne voit qu'un import normal. Modes : `chantier` (liste des dossiers « <IMMAT> - <JJMMAA> »), `fichiers` (tout le dossier), `dernier` (fichier le plus récemment modifié). Chemins relatifs transmis via `window.s360Chemins` (patch FormData). Les fichiers ne quittent jamais le poste. **Commandes (SAP)** : seul le dossier COMMANDE fait foi (aucune cible `commandes` dans les imports R2 / Textile ; un fichier de commandes y est ignoré et signalé). **Textile** : règles de nommage prioritaires (`NOMS_DOSSIER` : « Résultat… », textile_master_export, textile_all_parts ; `dossiers.appliquer_noms`), puis contenu. Chaque sélection **remplace** la précédente (Streamlit ajouterait les fichiers aux anciens) : fichiers gardés en mémoire, zone d'import vidée (clé versionnée) ; en mode chantier, les emplacements sans fichier dans le nouveau dossier sont vidés (`vider_emplacement`).
- **Garder l'état quand on change d'onglet** : Streamlit efface un widget non affiché. Tous les widgets d'un module prennent `persist_state="page"` ; les imports passent par `components.fichier(...)`, qui garde le fichier en mémoire.
- **Filtres** : un bloc filtrable (recherche, multisélection + tableau) est une fonction décorée `@st.fragment` — filtrer ne relance que ce bloc.
- **Sous-onglets** d'un module : `components.sous_onglets(...)` (seule la section active est calculée).
- La logique métier (croisements, calculs) va dans `core/transforms.py` ou dans des fonctions pures du module, **jamais mélangée au rendu**. Elle doit être testable sans Streamlit.
- `st.set_page_config` est appelé **uniquement** dans `main.py`.

### 3.2 Structure type d'un onglet

1. **En-tête de section** : titre, description courte, rappel des fichiers attendus.
2. **Bloc d'import** : un `file_uploader` par source, avec la liste des colonnes attendues dans un `expander`.
3. **Validation** : message d'erreur clair en français si une colonne manque (laquelle, dans quel fichier).
4. **Synthèse** : 3 à 5 cartes KPI.
5. **Actions à lancer** en premier (commandes à passer, relances fournisseurs), puis le détail.
6. **Graphiques et tableaux** filtrables.
7. **Export** : bouton de téléchargement Excel en bas et dans la synthèse.

Tant qu'aucun fichier n'est importé, afficher un **état vide soigné** (`components.empty_state`) qui explique quoi faire, jamais une erreur.

---

## 4. Contraintes stlite / Pyodide

- **Paquets autorisés** : uniquement ceux de la **distribution Pyodide** (servis par jsdelivr, aucun accès PyPI à prévoir). Base : `pandas`, `numpy`, `python-calamine`.
  - Lecture Excel : moteur **calamine** (~10× plus rapide qu'openpyxl sous Pyodide).
  - Export Excel : `core/xlsx.py` (bibliothèque standard) — openpyxl et xlsxwriter ne sont pas dans Pyodide.
  - Graphes : `core/charts.py`, HTML / SVG générés en Python, sans JavaScript ni paquet — plotly (9,7 Mo) n'est pas chargé. **Pas d'Altair / Vega** : essayé puis retiré (graphes plats, plein écran et « show data » défaillants, et ~0,3 s de validation de schéma par graphe à chaque interaction — plusieurs secondes par clic sous Pyodide). Pas de zoom.
  - `st.data_editor` est **inutilisable sous stlite** (il exige pyarrow) : utiliser des `number_input` / `selectbox`.
- **Garder `requirements.txt` minimal** : chaque paquet allonge le premier chargement. Ne pas ajouter `plotly`, `openpyxl`, `scikit-learn`, `scipy`, `matplotlib`… sans vraie nécessité.
- **Interdit** : `requests` et tout accès réseau, `subprocess`, `multiprocessing`, threads, boucles avec `time.sleep`, lecture ou écriture sur le disque de l'utilisateur, connexion à une base de données.
- **Fichiers importés** : lus depuis l'objet `UploadedFile` (`pd.read_excel(uploaded, engine="openpyxl")`), jamais via un chemin.
- **Performance** : Pyodide est plus lent que Python natif. Vectoriser avec pandas (pas d'`iterrows`, pas de `groupby().agg(fonction Python)` sur de gros volumes), mettre en cache les lectures et calculs lourds, et vérifier sous stlite.
- **Cache** : `st.cache_resource` (et non `st.cache_data` : sous Pyodide, relire par pickle un DataFrame contenant des dates échoue). Clé = **contenu des fichiers (octets) + paramètres**, jamais des DataFrames (leur hachage à chaque clic coûte cher). Ne jamais modifier une table reçue du cache.
- **Téléchargements** : `components.telecharger(...)` (`on_click="ignore"` : télécharger ne relance pas les calculs).
- **Version de stlite épinglée** dans `build.py` (jamais `latest`). Toute montée de version doit être testée avant livraison.
- **Préchargement** (`PRECHARGEMENT` dans build.py) : stlite télécharge certains morceaux de l'interface (tableau, liste déroulante, téléchargement…) à leur première utilisation. Ils sont préchargés juste après le démarrage : sinon, après une inactivité (proxy expiré), leur téléchargement échoue et la page se fige. **Liste à refaire à chaque montée de version de stlite** (relever les requêtes jsdelivr pendant un parcours complet). Les requêtes de contrôle vers `stlite.invalid` reçoivent une réponse locale ; un bandeau propose de recharger si un calcul dépasse 90 s. **Surveillance du moteur** (build.py) : sonde « heartbeat » toutes les 30 s et au retour sur l'onglet, erreurs Python transmises par `core/journal.py` ; pastille « Calcul en cours » dès qu'une réponse est attendue ; si le moteur est arrêté ou muet 60 s, relance AUTOMATIQUE (une fois par 5 min, sinon bandeau « Relancer en gardant mes fichiers ») : `unmount()` + `mount()` de stlite puis réimport des fichiers gardés en mémoire de la page (`window.s360Relancer`). **Mémoire** : Pyodide ne rend jamais la mémoire ; les gros fichiers sont lus par `io.lire_colonnes` (colonnes utiles seulement) et reconnus par `io.apercu_xlsx` (début du XML seulement, sans charger la feuille).

---

## 5. `build.py` : assemblage du HTML

Script Python sans dépendance externe, qui :

1. intègre le thème `app/core/theme.css`, images de `assets/` comprises (data URI), **une seule fois en fin de `<body>`** : rien n'est renvoyé à chaque interaction, et le thème passe après les styles que Streamlit ajoute au `<head>` ;
2. lit tous les fichiers `.py` de `app/`, ainsi que `requirements.txt` et `.streamlit/config.toml` ;
3. produit `dist/supply360.html` avec l'API JavaScript `mount()` de `@stlite/browser` (version épinglée) :
   - fichiers passés dans un objet JSON (`json.dumps`), en **échappant `</` en `<\/`** pour ne pas casser le HTML ;
   - `entrypoint: "app/main.py"` ;
   - `requirements` reprises de `requirements.txt` ;
4. ajoute un **écran de chargement** aux couleurs de Supply360 (logo, « Chargement de Supply360… le premier lancement peut prendre jusqu'à une minute ») ;
5. affiche la taille du fichier généré et la liste des modules embarqués.

Le HTML doit aussi fonctionner en local avec `streamlit run app/main.py` (même code, sans stlite) pour le développement.

---

## 6. Charte graphique

Rendu attendu : **corporate, épuré, lisible**, cohérent avec le prototype Supply360. Ce doit être un outil interne Air France Industries, pas un Streamlit brut.

**Couleurs** (tokens CSS sur `:root` ; à ajuster sur la charte officielle si besoin) :

| Token | Usage | Valeur indicative |
|---|---|---|
| `--navy` | primaire, header, textes forts | `#002157` |
| `--navy-2` | fin des dégradés | `#1F4E9C` |
| `--accent` | rouge, très parcimonieux (alerte forte) | `#E4002B` |
| `--bg` | fond de page | `#F4F6FA` |
| `--surface` | fond des blocs | `#FFFFFF` |
| `--text` / `--muted` | textes | `#1A1F36` / `#5B6478` |
| `--ok` / `--warn` / `--ko` | statuts | `#1E8E5A` / `#E8A317` / `#C62828` |

**Composants** (`core/components.py`) :

- **Ambiance** du prototype v3 : fond aérien (`fond_aeroport.webp`), cartes blanches translucides.
- **Header** fixe en haut : logo Air France Industries (sur fond clair : il est transparent) + « Supply**360** » (360 en rouge) + navigation entre onglets (onglet actif surligné) + date du jour. Une barre animée et la pastille « Calcul en cours… » signalent que Python travaille.
- **Blocs / sections** : carte blanche, coins arrondis (10–12 px), ombre légère, **en-tête en dégradé bleu** (`--navy` → `--navy-2`) avec texte blanc.
- **Cartes KPI** : valeur en grand, libellé, variation ou statut coloré.
- **Badges de statut** : chantiers uniquement **Terminé / En cours / À venir**.
- **Boutons** bien visibles, style identique partout (« Voir tout », « Détail », « Télécharger »).
- **Tableaux** : `st.dataframe` avec `column_config` (formats €, dates JJ/MM/AAAA, barres de progression), en-têtes figés, actions à lancer en haut.
- **Graphiques** (`core/charts.py`, style du prototype v3) : couleurs de la charte, **valeurs affichées sur les graphes**, fond transparent, légende en bas, police cohérente. Affichage via `components.graphe` (`st.markdown`, car `st.html` supprime le SVG). **Infobulle au survol** : attribut `data-tip` (une ligne par valeur) affiché en CSS ; une colonne de barres montre toutes ses séries. Graphes hauts (300 px par défaut), deux par ligne au plus.
- **Peu de texte** : titre + une ligne de description ; les détails (colonnes attendues, règles de calcul, tableaux annexes) vont dans des `st.popover`.

**Typographie et responsive :**

- Police **Manrope** (celle du prototype), embarquée en woff2 dans le HTML (aucun appel à Google Fonts), puis pile système (`"Segoe UI", system-ui, …`).
- Tailles en `rem` (base **13 px** ≈ 80 % de 16 px, à la demande de l'auteur : `html { font-size }` + `baseFontSize` ; hauteurs des graphes réduites d'autant) pour que **le texte grossisse avec le zoom navigateur**.
- Mise en page **responsive** : colonnes qui passent à la ligne sur écran étroit, espacements constants.
- **Masquer l'habillage Streamlit** : menu, footer, bouton Deploy, barre d'outils du header.

---

## 7. Règles métier (vocabulaire commun)

- **Process cible** : la Production fournit les besoins par chantier (PN, quantités, dates) → les analystes Supply Chain croisent avec l'état du stock et les commandes → actions : passer les commandes ou relancer les fournisseurs pour livrer **avant la date de début du chantier**.
- **Statuts de chantier** : Terminé, En cours, À venir. Afficher le nombre de jours avant le début à côté de « À venir ».
- **TDD (Taux De Disponibilité)** : disponibilité des équipements par rapport à la demande de production.
- **TL0** = consommable, **TL1** = réparable (repair, TAT).
- **Commandes fournisseurs** : elles ne sont pas forcément liées à un chantier (besoins imprévus). Les classer du pire au meilleur statut.
- **Surplus / stock dormant** : équipements sans consommation depuis plus de 4 ans.
- **Enjeu cabine** : pas d'immobilisation avion pour une pièce cabine. L'enjeu est la **décommercialisation de sièges** et l'expérience client.

En cas de doute sur une règle métier, **poser la question plutôt que supposer**.

---

## 8. Lecture et export des fichiers (`core/io.py`)

- **Normaliser les en-têtes** (minuscules, sans accents, espaces → `_`) et accepter des **alias** de colonnes déclarés par module (`{"pn": ["pn", "part_number", "reference"]}`).
- **Valider** et lever une erreur métier lisible : « Colonne *Date début chantier* introuvable dans le fichier Besoins chantier. »
- **Typage explicite** : PN en texte (zéros en tête conservés), dates avec `dayfirst=True`, quantités numériques.
- **Export Excel** :
  - plusieurs feuilles (Synthèse, Actions à lancer, Détail) ;
  - en-têtes en gras sur fond bleu marine, volets figés, filtres automatiques, largeurs ajustées ;
  - nom de fichier : `Supply360_<TAB_ID>_<AAAAMMJJ>.xlsx`.

---

## 9. Intégrer un script existant (`legacy/`)

Quand l'auteur dépose un script Streamlit dans `legacy/` :

1. Lire le script en entier et identifier entrées, croisements, sorties.
2. Créer `app/modules/<tab_id>.py` selon le contrat du §3.1 :
   - supprimer `st.set_page_config` et tout chemin local ;
   - remplacer les lectures de fichiers par des `file_uploader` ;
   - extraire la logique de calcul en fonctions pures ;
   - appliquer les composants de la charte (ne pas laisser de `st.title` / `st.write` bruts).
3. Déduire les colonnes attendues et générer des **données fictives** cohérentes dans `tests/fixtures/`.
4. Écrire les tests des fonctions de croisement.
5. Ajouter le module au registre, lancer le build, vérifier le rendu.
6. Mettre à jour `requirements.txt` si nécessaire, en respectant le §4.
7. **Conserver la logique métier d'origine.** Signaler tout comportement douteux au lieu de le « corriger » en silence.

---

## 10. Commandes

```bash
pip install -r requirements-dev.txt     # dev local
streamlit run app/main.py               # tester en local (serveur)
pytest                                  # tests des croisements
python build.py                         # générer dist/supply360.html
```

Puis ouvrir `dist/supply360.html` par double-clic dans Edge ou Chrome pour vérifier le rendu stlite.

---

## 11. Définition de « terminé »

Avant d'annoncer qu'une modification est faite :

- [ ] `pytest` passe ;
- [ ] `streamlit run app/main.py` fonctionne et l'onglet s'affiche sans erreur, avec et sans fichiers importés ;
- [ ] `python build.py` génère le HTML sans erreur ;
- [ ] aucun import ou appel interdit (§4), aucune donnée réelle, aucun nom d'outil interdit (§2) ;
- [ ] le style respecte la charte (§6) et le rendu tient au zoom et sur écran étroit ;
- [ ] l'export Excel s'ouvre correctement ;
- [ ] le `README.md` est à jour si un onglet a été ajouté (fichiers attendus, usage).

---

## 12. Façon de travailler

- Avancer par **petites étapes vérifiables**, une brique à la fois.
- Expliquer brièvement les choix techniques non évidents.
- **Ne pas modifier un module existant** quand on en ajoute un nouveau, sauf pour factoriser dans `core/`, et le signaler.
- Ton des textes de l'interface : professionnel, proactif, orienté action (« 12 commandes à passer avant le 15/11 »).
