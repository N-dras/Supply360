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
4. Le fichier **Commandes (SAP)** est commun : importé une fois, il sert à tous les onglets. L'**État du
   stock** est propre à chaque onglet. Changer d'onglet conserve fichiers, filtres et paramètres.
5. Rafraîchir la page **réinitialise tout** : il faut alors réimporter les fichiers.

Pendant un calcul, la barre sous le header s'anime et la pastille « Calcul en cours… » s'affiche.

## Organisation des dossiers et import

Version en ligne : **https://n-dras.github.io/Supply360/** (republiée automatiquement à chaque mise à
jour). Les fichiers importés restent dans le navigateur : rien n'est envoyé, ni à GitHub ni ailleurs.

```
SharePoint (canal Teams MS-LGT1-Analystes, bibliothèque Documents)
├── COMMANDE/          fichier Commandes (SAP) à jour (le plus récent est pris) — c'est lui qui fait foi
├── Textile/           « Résultat… » (État du stock), « textile_master_export » (Références textile),
│                      « textile_all_parts » (Pièces par avion)
│                      « PE_MOUSSE_JJMMAAAA » (âge des mousses, fichier mensuel tel quel)
│                      « Besoin_Prod… » (objectif PE mousses de l'année : avions et CCN par type d'avion)
└── R2/                un dossier par chantier : <IMMAT> - <JJMMAA>
    ├── F-XKAA - 151126/   Besoins LOGOPS (ou étude ASREQ), État du stock
    └── F-XKBB - 030227/
```

**Première utilisation (une fois par poste)** : aide « 🔗 Première utilisation » de l'onglet → ouvrir le dossier
sur SharePoint → « Ajouter un raccourci à Mon OneDrive » (idéalement la bibliothèque Documents entière). Les
dossiers apparaissent dans l'Explorateur et restent à jour ; rien n'est copié, chacun le fait avec son compte.

**Ensuite (Edge ou Chrome)** : boutons **📂 Ouvrir R2**, **📂 Ouvrir Textile**, **📂 Ouvrir COMMANDE**. La première
fois, choisissez le dossier ; le navigateur le retient (« dossier mémorisé »). Les fois suivantes, même après
actualisation : clic sur le bouton → **Autoriser** →
- **R2** : liste des chantiers (à venir d'abord, avec J-x), recherche par immatriculation ; seuls les fichiers du
  chantier choisi sont lus ;
- **Textile** : tous les fichiers du dossier ;
- **COMMANDE** : le fichier le plus récemment modifié, commun à tous les onglets.

« Changer de dossier » pour en choisir un autre. Sans Edge/Chrome : « Parcourir » (import manuel), toujours disponible.

**Commandes (SAP)** : seul le fichier du dossier COMMANDE fait foi ; un fichier de commandes trouvé dans un dossier
R2 ou Textile est ignoré (c'est signalé).

**Textile** : le nom fait foi — « Résultat… », « textile_master_export », « textile_all_parts ». Si aucun fichier ne
porte ce nom, la reconnaissance par le contenu prend le relais.

Sinon, les fichiers sont reconnus par leur **contenu** (en-têtes de colonnes), quel que soit leur nom ; à défaut
par un mot du nom (`logops`, `asreq`, `stock`, `commande`/`sap`, `reference`, `piece`). Si un dossier
contient plusieurs fichiers du même type, le plus récent (date dans le nom, ex. `20261020`) est retenu et
peut être changé dans la liste. Les fichiers non reconnus sont ignorés et signalés. Tout est lu localement :
rien n'est envoyé.

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
filtrable, toutes les références, export `Supply360_stock_chantier_AAAAMMJJ.xlsx`. Colonne **TL** (tracking
level, colonne `TRACKING LEVEL` de l'État du stock) : 0 = consommable, 1 = réparable.

### 🧵 Textile cabine

Stock, consommation, commandes et retards fournisseurs des ceintures, housses, mousses et rideaux.

| Fichier | Colonnes obligatoires | Colonnes facultatives |
|---|---|---|
| État du stock | `PNR`, `QTE SUR ÉTAGÈRE` | `QTE EN CDE`, `DESCRIPTION`, `QTE CONSO 12M / 18M / 24M`, `QTE CONSO <année>`, `Dernier PU (achat) Euros`, `DATE DERNIERE CONSO`, `B/O`, `RP`, `EOQ`, `TDD` |
| Commandes (SAP) | `PN`, `Commande` | `Fournisseur`, `Code fournisseur`, `Date d'émission de la commande`, `Date de livraison demandée / promise`, `Quantité restant à livrer` |
| Références textile — feuille « PN Catalog » | `pn`, `equipment` | `description`, `ccn` |
| Pièces par avion (textile_all_parts) — CSV ou Excel | `equipment`, `aircraft_type`, `group`, `registration`, `area`, `ccn`, `pn`, `description`, `qty_per_ac` | |

Seul l'État du stock est indispensable ; les autres fichiers complètent l'analyse. La Prévision
demande en plus le fichier Pièces par avion.

**Sous-onglets** : Synthèse (relances fournisseurs, valeur et activité du stock par catégorie),
Commandes (statuts, livraisons, profondeur des retards, toutes les lignes avec la qté sur étagère),
Fournisseurs (Pareto, retards, délais promis, BFE, vue par fournisseur avec la qté sur étagère),
Consommation (par année, 12/18/24 mois, top PN, par PN), Prévision (commandes à passer, par fournisseur). Un filtre par catégorie s'applique à toutes
les vues. Export `Supply360_textiles_AAAAMMJJ.xlsx` (avec les feuilles de prévision si elle est calculée).

**Règles** : retard = date promise − date demandée au-delà de 10 jours de tolérance ; date promise 2001,
2030 ou plus (ou vide) = sans date promise ; 2049 = en attente de BFE. PN **dormant** = du stock mais
aucune consommation sur 3 ans ; **inactif** = ni stock, ni consommation, ni commande.

**Prévision de commandes** (détail dans « Comment le besoin est calculé ») :

- **stock minimum** d'un PN = quantité par avion × objectif d'avance (10 % des avions du groupe, au
  moins 1), additionné sur les groupes d'avions qui l'utilisent ;
- **commande** au plus tard à la date de besoin moins le délai fournisseur ; si le délai est trop long,
  la commande part maintenant ;
- les PN dormants ou inactifs ne sont jamais recommandés ;
- vue **par fournisseur** : PN à commander, valeur maintenant et sur l'horizon, détail d'un fournisseur
  (stock / en commande / à commander par PN, **écart promis − demandé par ligne de commande**).
  Fournisseur d'un PN : celui de ses commandes, à défaut le dernier fournisseur de l'État du stock, puis
  le code fournisseur.

Les paramètres (objectif d'avance, horizon, délai par défaut…) sont dans « ⚙️ Paramètres de la prévision ».
Le planning des PE mousses est dans l'onglet **PE mousses**.

### 🛠️ PE mousses

Politique d'entretien des mousses de sièges : ce que l'on peut faire cette année avec le stock, ce qu'il faut commander,
l'avancement avion par avion et le forecast des années suivantes. Tous les fichiers sont lus dans le dossier **Textile**
(📂 Ouvrir Textile) ; les commandes dans le dossier COMMANDE.

| Fichier | Colonnes obligatoires | Colonnes facultatives |
|---|---|---|
| Besoin Prod mousses (« Besoin_Prod… », annuel) — feuille « QUOTE en euro » | `A/C` (type d'avion), `Area` (classe), `CCN`, `Qty per A/C`, `NB_AC` | `Flotte`, `NB_AC PE RESTANT`, `P/N OEM Seat Supplier`, `Seat Supplier`, `Description`, `P.U forecast PE` |
| État du stock | `PNR`, `QTE SUR ÉTAGÈRE`, `CCN` | `QTE EN CDE`, `Dernier PU (achat) Euros` |
| Commandes (SAP) | `PN`, `Commande` | `CCN` (sinon retrouvé par le PN), `Quantité restant à livrer`, `Date de livraison promise` |
| PE mousses (PE_MOUSSE_JJMMAAAA, mensuel) | feuilles « … BOTTOM FOAM … » et « … BACKREST FOAM … » : FLEET, AIRCRAFT, AGE (month) par classe, PAST / NEXT EXECUTION | |
| Pièces par avion (textile_all_parts) | `equipment`, `registration`, `area`, `ccn`, `pn`, `description`, `qty_per_ac` | |

**Sous-onglets** :

- **Synthèse** : objectif de l'année, avions complets maintenant / à réception / à approvisionner, valeurs (stock,
  en commande, à commander, besoin), CCN à coter, CCN par action, avancement par type × classe, **actions à lancer**
  (PR à émettre), export Excel complet et contrôles des données.
- **Avions faisables** : par type d'avion × classe, avions complets avec le stock, à réception des commandes, à
  approvisionner, CCN limitant, CCN communs ; détail d'un type d'avion : avions couvrables par chaque CCN (stock, + commandes,
  trait = objectif de la classe). **Code couleur commun à tous les graphes** : 🟢 couvert par le stock, 🔵 couvert à
  réception des commandes en cours, 🟠 à coter (CCN sans prix), 🔴 à approvisionner (à commander), gris : au-delà de
  l'objectif. Jamais de rouge sur ce que le stock couvre : 26 avions couverts sur un objectif de 28 = 26 en vert + 2 en
  rouge. Un CCN commun à plusieurs types est partagé selon la répartition des avions complets (le détail par CCN
  concorde avec l'avancement par classe).
- **CCN et commandes** : une barre par CCN = 100 % de son besoin de l'année, découpée en part couverte par le stock,
  par les commandes en cours et manque à commander (les moins couverts en haut) ; recherche, filtre par action, CCN à coter.
- **Avancement PE** et **Forecast** : voir ci-dessous (ex-sous-onglet « Planning PE » du Textile).

Règles de l'année (reprises du Streamlit « Pilotage Politique d'entretien Mousse ») :

- **avions restants** (objectif) : par défaut **recalculés** = NB_AC − avions du type dont la mousse (même classe,
  assise ou dossier) a été remplacée depuis le 1er janvier d'après le fichier PE mousses. Le type de chaque avion
  (A350 AFR01, B777-300 14J…) est retrouvé par ses CCN de mousses dans textile_all_parts (type qui en partage le plus).
  Sans ces fichiers, ou pour une classe non reconnue : colonne `NB_AC PE RESTANT`, à défaut `NB_AC`. Choix dans
  « ⚙️ Paramètres » › Année ; comparaison fichier / calcul dans « ℹ️ Règles de calcul et avions restants » ;
- NB_AC compté une fois par type d'avion × classe (pas une fois par ligne) ; l'objectif et les avions faisables sont
  comptés **par classe** (un avion à traiter en J, W et Y compte 3 fois), l'équivalent en avions est indiqué sous l'objectif ;
- besoin d'un CCN = qté par avion × avions restants, additionné sur les types d'avion ;
- stock d'un CCN = QTE SUR ÉTAGÈRE de l'État du stock (maximum des lignes du CCN) ; en commande = reste à livrer des
  commandes SAP du CCN (sans fichier Commandes : QTE EN CDE) ;
- à demander (PR) = besoin − stock − en commande (si positif). Action : PR à émettre (aucune commande), PR
  complémentaire (commandes insuffisantes), à réceptionner (couvert avec les commandes), couvert par le stock ;
- prix = Dernier PU de l'État du stock, à défaut le prix du devis ; sans prix : CCN « à coter » ;
- **avions faisables** : un avion d'une classe est complet si tous ses CCN sont disponibles. Le stock d'un CCN commun
  à plusieurs types d'avion est **réparti** (l'avion suivant va au type le moins avancé) : le total ne compte jamais
  deux fois le même stock. Les colonnes MRI, PSD et capa du Besoin Prod ne sont pas utilisées.

**Avancement PE et Forecast** — à partir du fichier mensuel PE_MOUSSE déposé tel quel dans le dossier Textile (date des
âges lue dans son nom) et de textile_all_parts :

- **Avancement** : conformité PE, éléments en retard, dans le délai toléré, à faire sous 3 mois, visites à venir ;
  avancement par flotte × élément (J assise, J dossier, W assise, Y assise) ; remplacements à faire par mois.
- **Calendrier** : une ligne par avion, le nombre d'éléments à remplacer par mois (24 mois) ; détail par avion.
- **Forecast des mousses** (12 / 24 / 36 mois) : mousses à remplacer (dont retard à rattraper), quantité et valeur
  à commander, livraisons à prévoir par mois, valeur par fournisseur, tableau par PN.
- **Forecast par fournisseur** : commande globale et livraisons mois par mois par PN, export Excel à lui envoyer.
- **Filtres** : flotte, classe, élément. **Exports** : planning complet ; **contrôles** des données.

Règles (paramètres dans « ⚙️ Paramètres » › Planning PE ; stock de sécurité réglable de 0 à 50 %) :
- cycles : J / W / Y assise 36 mois, J dossier 72 mois, dossiers W / Y jamais ;
- échéance = date des âges − âge + cycle (âge « > 60 » : 60 pris comme minimum, échéance au plus tôt) ;
- statut : En retard (échéance + délai toléré dépassés, 3 mois par défaut), Délai toléré, À faire < 3 mois,
  À faire < 12 mois, OK ;
- date prévue : la prochaine visite datée (PAST / NEXT EXECUTION), sinon l'échéance ; un retard est à rattraper
  le mois en cours ; une visite postérieure à l'échéance est signalée ;
- mousses : lignes `equipment` = MOUSSE de textile_all_parts, classe = `area`, assise = « FOAM BOTTOM / BOTT… »,
  dossier = « FOAM BACKREST / BACK… » ;
- stock de sécurité par PN : pour chaque flotte, 10 % des avions qui l'utilisent (arrondi au-dessus, au moins 1)
  × quantité par avion ;
- à commander, par PN = besoin + stock de sécurité − stock − commandes en cours (déjà passées : toujours déduites,
  quelle que soit leur date promise), livré le mois où il en faut ; une commande en cours promise après le mois où elle
  est nécessaire est signalée « à avancer » (relance fournisseur) au lieu d'être commandée deux fois. Le fichier étant
  régénéré chaque mois, un remplacement fait remet l'âge à zéro : rien à saisir.

### Graphiques

Chaque graphe a deux boutons en haut à droite (visibles au survol) : **⛶ Agrandir** ouvre le graphe en grand, en
entier, sans barre de défilement (un très grand graphe est affiché à la largeur de l'écran et défile verticalement) ;
**⤓** (ou **Enregistrer en PNG** dans la vue agrandie) télécharge une image identique au graphe du site (police,
couleurs, graphe complet même s'il défile à l'écran), à partager par mail ou dans une présentation.

Survol d'une colonne, d'une barre ou d'une case : infobulle avec toutes ses valeurs.

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

### Imports et page qui ne répond plus

- **📂 Ouvrir** : une barre de progression suit la lecture des fichiers, leur envoi puis l'analyse.
- Pendant un calcul (y compris le traitement d'un import), la pastille « Calcul en cours… » s'affiche aussitôt.
- **Relance automatique du moteur** : si la session du moteur se ferme ou ne répond plus aux clics alors que Python
  est disponible, il est relancé **tout de suite** ; si Python ne répond plus du tout, au bout de 30 s. Un écran
  Supply360 (logo, barre d'avancement) suit la relance, puis **tous les fichiers sont réimportés**, onglet par onglet
  (relus dans le dossier mémorisé quand ils en viennent ; gardés en mémoire de la page, jamais écrits sur le disque).
  Une seconde fois en moins de 5 minutes : bandeau **Relancer en gardant mes fichiers** / **Recharger la page** ;
  **Détails techniques › Copier** donne le diagnostic à transmettre à l'auteur.
- **Exports Excel** : bouton **Exporter** → le fichier est fabriqué à ce moment-là, puis téléchargé automatiquement
  (il n'est plus fabriqué à chaque affichage d'onglet, ce qui ralentissait et chargeait la mémoire).
- Mémoire : les gros fichiers (État du stock, Commandes) sont lus en ne gardant que les colonnes utiles ; les fichiers
  sont reconnus en ne lisant que leurs en-têtes ; chaque fichier n'est gardé qu'une fois (format Excel compressé).
Conseil Edge : *Paramètres › Système et performances › Ne jamais mettre en veille ces sites* → ajouter l'adresse de Supply360.
