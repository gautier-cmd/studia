# Studia

Bibliothèque personnelle et plateforme d'apprentissage multi-supports,
dérivée d'OfflineU (MIT, WhiskeyCoder).

## Avec qui tu travailles

Gautier, graphiste, pas administrateur système. Il comprend les concepts
mais n'écrit pas de code et ne corrige pas une commande lui-même.

- Réponds en français.
- Explique ce que fait chaque changement et pourquoi, avant de l'appliquer.
- Définis les termes techniques au passage, sans qu'il ait à demander.
- Une chose à la fois. Pas de « il faudrait aussi » qui ouvre trois chantiers.
- Pas de félicitations ni d'enthousiasme de façade.
- Ne suppose rien sur la machine : vérifie, ou demande.

## Interdits absolus

1. Ne jamais modifier l'OfflineU de production.
2. Ne jamais écrire dans /srv/disk1/Media/Formations (serveur maisonsrv,
   192.168.31.33). Cette bibliothèque sert uniquement de source de copie.
3. Ne jamais modifier ni renommer les fichiers médias de l'utilisateur,
   en particulier pas pour contourner un problème d'Unicode.
4. Ne jamais rendre le projet dépendant de Calibre. Les fichiers Calibre
   existants servent au plus de référence pour vérifier un résultat.
5. Ne rien documenter qui n'existe pas encore : ça va dans le backlog.
6. Ne jamais écrire une clé API (GOOGLE_BOOKS_API_KEY ou une autre) dans
   le code, un fichier du dépôt ou un message de commit. Elle vient
   uniquement de la variable d'environnement, propre à chaque
   installation ; l'application doit fonctionner sans (la source
   correspondante devient juste indisponible, pas une erreur).

## Environnement

    Poste          gautier@gautierPC, développement exclusivement local
    Dépôt          /home/gautier/dev/offlineu-lab
    Branche        offlineu-lab
    Remote origin  github.com/gautier-cmd/studia (le sien)
    Remote upstream github.com/WhiskeyCoder/OfflineU (projet d'origine, lecture seule)
    Venv           .venv (à activer : source .venv/bin/activate)
    Bibliothèque   /home/gautier/offlineu-test-library
    Données        /home/gautier/offlineu-test-data/studia.db
    Flask          3.1.1
    ffprobe        /usr/bin/ffprobe
    GOOGLE_BOOKS_API_KEY   variable d'environnement, propre à chaque
                           installation (jamais dans le dépôt, voir
                           interdit n°6). Absente ici en développement :
                           Google Books est alors simplement ignoré.

## État actuel

### Fichiers

    offlineu_core.py    application OfflineU d'origine, 1003 lignes, INTACTE
    library_index.py    scanner SQLite de Studia
    studia.py           application web de consultation (Flask) : grille,
                        fiche d'item, lecteur vidéo
    presentation.py     extrait couverture/fiche technique/texte des pages
                        "000 - Presentation....html" (BeautifulSoup) pour
                        les réafficher avec le gabarit de Studia
                        plutôt que telles quelles
    book_metadata.py    recherche de métadonnées de livres sur Google
                        Books et Open Library, détection d'ISBN
    covers.py           extraction des couvertures (PDF, M4B, vidéo),
                        cache à côté de la base — jamais écrit dans la
                        bibliothèque, voir "Tranche 3"
    tests/              test_library_index.py, test_studia.py,
                        test_presentation.py, test_book_metadata.py,
                        test_notes.py, test_covers.py — 70 tests pytest
    templates/          course_dashboard, lesson_view, select_course
                        (OfflineU, CSS repris comme point de départ) +
                        _base.html, library_grid, item_detail,
                        video_player, orphan_notes, _note_widget
                        (Studia — héritent de _base.html)
    static/tokens.css   seul endroit où sont déclarés couleurs,
                        typographie, espacements, rayons, transitions,
                        breakpoints (voir "Refonte visuelle")
    static/style.css    styles des composants, consomme uniquement
                        tokens.css — pas de :root propre à part
                        quelques compléments sans équivalent officiel
                        (danger, fond sélectionné), clairement isolés
                        en tête de fichier
    static/fonts/       Inter, deux variable fonts (romain, italique)
                        au format woff2 — jamais Google Fonts, jamais
                        de .ttf dans le dépôt (2 à 2,5x plus lourd)
    static/images/      copies de travail des logos (logo.png,
                        logo-picto.png), servies par Flask — design/
                        garde les fichiers d'origine de Gautier
    design/             specification.md (spec de la refonte, source de
                        vérité — voir ci-dessous), 3 maquettes PNG,
                        2 logos (LOGO.png, LOGO-Picto.png)

### Modèle de données

Item (un dossier de premier niveau) contient des Media et des Resources.
Le concept Lesson d'OfflineU est abandonné.

Tables SQLite, schéma version 4 :
schema_info, users, items, media, resources, progress, book_search,
book_candidates, notes.

    media       item_id, relative_path, parent_path, sort_order,
                media_type, extension, size_bytes,
                duration_seconds, probed_at, created_at
                UNIQUE(item_id, relative_path)
    resources   mêmes colonnes sans durée
    progress    UNIQUE(user_id, media_id) — jamais media_id seul

    book_search      item_id (clé), query, searched_at — dernière
                     recherche lancée pour un item livre
    book_candidates  item_id, source ('google_books'|'open_library'
                     |'manual'), source_id, champs bibliographiques,
                     decision ('proposed'|'accepted'|'rejected')
                     UNIQUE(item_id, source, source_id)

book_search et book_candidates ne sont jamais touchées par scan_library :
un rescan ne peut donc pas défaire une métadonnée validée ni faire
réapparaître un candidat rejeté.

    notes   library_path (clé), text, updated_at — pas de clé
            étrangère du tout vers items

notes est rattachée au chemin de bibliothèque, pas à item_id, et le
scanner n'est pas modifié : quand un dossier disparaît, scan_library
supprime l'item comme avant, la note reste simplement en base, non
liée à rien. Si le même chemin revient, elle se retrouve automatiquement.
Si le dossier a été renommé (chemin différent), la note devient
orpheline — visible et récupérable sur /notes-orphelines (voir
"Bloc-notes" ci-dessous), jamais perdue.

parent_path est le sous-dossier du fichier, vide à la racine : c'est ce
qui représente les chapitres. sort_order est le rang dans l'item, calculé
par tri naturel (10 après 9).

### Garanties du scanner, protégées par les tests

- Les ids de media sont stables entre deux scans : upsert sur
  (item_id, relative_path), jamais DELETE puis INSERT. C'est ce qui
  empêche ON DELETE CASCADE d'effacer la progression.
- Seules les lignes dont le fichier a réellement disparu sont supprimées.
- La durée est conservée tant que size_bytes ne change pas, remise à NULL
  sinon.
- Une base au schéma v1 est migrée sur place par ALTER TABLE, sans perdre
  d'id.
- Unicode, accents et apostrophes typographiques traités sans renommage.

### Classification actuelle (heuristique, à améliorer)

    contient vidéo         -> course
    contient audio         -> audiobook
    livre sans audio       -> book
    sinon                  -> document

    PDF dans un course     -> resource
    PDF dans un audiobook  -> resource
    PDF dans un book       -> media

### Bibliothèque de test

    Adobe Illustrator CS6 (Adobe Press)    book,  1 média, 2 ressources
    Devenez Copywriter avec les IA         course, 49 médias, 5h44
    Motion Design - la formation complete  course, 258 médias, 27 chapitres, 55h10
    S organiser pour reussir (David Allen) audiobook, 1 M4B, 3h05

### Application web (studia.py)

    /                       grille des items (type, durée, nb de médias)
    /item/<id>              fiche : présentation extraite (si le fichier
                            existe), chapitres/médias, ressources
    /watch/<media_id>       lecteur vidéo : playlist par chapitre,
                            précédent/suivant, enchaînement automatique
    /listen/<media_id>      lecteur audio (M4B) : fichier unique, pas de
                            playlist ni de précédent/suivant
    /media/<media_id>/file  sert le fichier vidéo ou audio (Range HTTP
                            géré par Flask, permet d'avancer/reculer)

    POST /media/<media_id>/progress                     enregistre la position
                                                         de lecture (vidéo ou audio)

    POST /item/<id>/book-search                        lance une recherche
    POST /item/<id>/book-candidate/<id>/accept          valide un candidat
    POST /item/<id>/book-candidate/<id>/reject          rejette un candidat
    POST /item/<id>/book-candidate/<id>/unreject        annule un rejet
    POST /item/<id>/book-manual                         saisie manuelle

    POST /item/<id>/note                    enregistre la note (JSON)
    GET  /notes-orphelines                  notes dont le dossier a disparu
    POST /notes-orphelines/reattach         rattache une note à un autre item

    GET /cover/<item_id>                    sert la couverture en cache (404 sinon)

Chaque page de présentation a sa propre mise en page HTML (tableau, ou
lignes en div avec couverture) selon l'item : presentation.py ne dépend
d'aucune des deux en particulier, il repère les libellés de fiche
technique par leur classe CSS commune ("k") et les blocs de texte par
leur position dans le corps de page.

### Métadonnées de livres (book_metadata.py)

Sur la fiche d'un item de type book/audiobook, une carte
"Métadonnées" propose une recherche sur Google Books (avec
GOOGLE_BOOKS_API_KEY) et Open Library, en priorisant un ISBN détecté
dans les noms de fichiers/dossier (somme de contrôle vérifiée) sur une
requête par titre (nettoyée du suffixe entre parenthèses, modifiable
avant de lancer la recherche).

Ni fusion ni tri par confiance entre les deux sources : les candidats
sont montrés côte à côte, à valider ou rejeter à la main. Rien n'est
jamais rempli automatiquement — une fiche vide vaut mieux qu'une fiche
fausse. Un candidat rejeté reste mémorisé (consultable, réversible) et
n'est jamais re-proposé. La saisie manuelle est traitée comme une
source de plus, immédiatement validée.

Cette tranche couvre les livres. Les formations restent couvertes par
la page de présentation locale (ci-dessus) : les deux mécanismes
coexistent, aucun n'est un repli pour l'autre.

### Bloc-notes (une note par item)

Un seul champ texte par item, affiché à deux endroits qui pointent
vers la même donnée : en bas de la fiche (/item/<id>, pour tous les
types) et en bas du lecteur vidéo (/watch/<media_id>, pour les
courses). Modifier la note d'un côté la met à jour de l'autre au
prochain chargement de page.

- Enregistrement automatique après une pause de frappe (900 ms), et
  immédiatement si l'onglet est masqué ou fermé (navigator.sendBeacon,
  pensé pour aboutir même pendant un déchargement de page). Un filet
  local (localStorage) garde aussi chaque frappe : si une version plus
  récente que celle du serveur est retrouvée au chargement (crash juste
  avant l'envoi différé), la page propose de la restaurer.
- Le bouton "Insérer un repère" (uniquement sur le lecteur, dans la
  barre d'outils depuis la tranche 8) écrit une ligne texte au format
  "Vidéo N — titre — mm:ss (/watch/id?t=secondes)" à la position du
  curseur. Ces lignes sont aussi détectées par une expression
  régulière côté navigateur et affichées comme une liste cliquable
  sous le champ, chacune avec une croix qui retire seulement cette
  ligne du texte — pas de zone de texte enrichi, juste un motif
  reconnu dans le texte brut.
- La reprise de position (?t=secondes) se fait par script sur
  l'évènement loadedmetadata du lecteur, pas par le fragment d'URL
  #t=secondes : ce fragment (pourtant standard, "Media Fragments URI")
  s'est révélé peu fiable ici pour positionner une vidéo servie
  localement — vérifié en pratique, currentTime restait à 0.
- Impression (accessible depuis le menu ⋮ du bloc depuis la tranche 8,
  plus un bouton dédié) : une feuille de style @media print masque
  tout sauf le titre de l'item, la date du jour et le rendu de la
  note — le même rendu Markdown que l'aperçu, pas le texte brut.

Pas encore fait : sauvegarde de la position de lecture (progress),
lecteur audio/PDF.

### CSS et gabarits

Toutes les pages de Studia héritent de templates/_base.html (squelette
HTML, `<link>` vers tokens.css puis style.css, blocs title/body_class/
active_nav/header/content/print/scripts) plutôt que de recopier
`<html><head>...` et leur propre `<style>`.

Certaines pages ont de vraies différences (largeur de `.container`,
taille du `<h1>` d'en-tête, marge du `.card` sur le lecteur, taille des
boutons sur la page des notes orphelines) : plutôt que de les fondre en
une seule règle au risque de changer un peu chacune, chaque `<body>`
porte une classe (page-grid, page-item, page-player, page-orphans) et
le fichier CSS a une règle scopée par page pour chaque différence
réelle — repérable en cherchant "body.page-" dans static/style.css.

Le bloc `print` (pas `content`) est le seul endroit où appeler
`render_print_block(...)` : il doit rester un enfant direct de
`<body>`, en dehors de `.app-shell`, sinon l'impression (qui masque
tout sauf `#print-only`) ne peut plus l'atteindre — un ancêtre caché
cache aussi ses enfants, même ceux qu'on voudrait montrer.

## Refonte visuelle

Source de vérité : `design/specification.md`. En cas de doute sur une
question de design, la relire plutôt que deviner. Deux écarts assumés
par rapport à ce document :

- Section 34 (notes individuelles avec timestamp, éditer/supprimer)
  est obsolète — on garde une seule note Markdown par formation (voir
  "Bloc-notes" ci-dessus et "Format des notes" ci-dessous).
- Les breakpoints (section 8) ne sont pas dans la spec : dérivés
  ci-dessous, voir "Tranche 1".

### Contraintes absolues de la refonte

- **Logos** : utiliser `design/LOGO.png` et `design/LOGO-Picto.png` tels
  quels. Ne jamais les redessiner, ni les recréer en CSS ou en SVG
  inline. Le wordmark a "Stud" en blanc : si un fond clair apparaît
  quelque part sous le logo, le signaler à Gautier plutôt que modifier
  le fichier.
- **Aucune donnée fictive.** Ce qui existe réellement en base : titre
  (= nom de dossier), item_type, médias (chemin/type/extension/taille/
  durée), ressources, chapitres (parent_path/sort_order), notes,
  progression. Les maquettes montrent en plus : couvertures,
  formateurs, année, tags, descriptions, libellés de chapitres
  nettoyés, pourcentages de progression, favoris, notifications, avatar,
  compteurs par type — rien de tout ça n'existe aujourd'hui. Si une
  donnée manque, appliquer l'état vide prévu par la spec (section 49)
  ou retirer l'élément, jamais la remplir avec un exemple ou un chiffre
  inventé.
- **Libellés de chapitre.** Les vrais dossiers s'appellent
  "0100 - Introduction au Motion Design", pas "01 - ...". Nettoyage à
  l'affichage uniquement (ex. retirer le préfixe numérique technique,
  reformater) — ne jamais renommer les dossiers ou fichiers réels
  (interdit n°3).
- **Pas de compte utilisateur en V1.** Favoris, cloche de notifications,
  avatar : retirés des écrans plutôt que simulés, jusqu'à un vrai compte
  (V2, déjà au backlog).
- **Polices hors-ligne.** Inter est servie depuis `static/fonts/`
  (@font-face), jamais depuis Google Fonts — l'appli doit fonctionner
  sans connexion internet.

### Format des notes

Markdown, stocké brut (colonne `notes.text` inchangée). V1 : champ
texte simple (pas d'éditeur visuel) avec une barre d'outils qui insère
la syntaxe — gras, italique, titres 1 à 3, liste, bloc de code, plus le
bouton "Insérer un repère" déjà en place — et une bascule aperçu qui
rend le Markdown. Pas de bouton souligné : ça n'existe pas en Markdown
standard, et pas de HTML dans les notes. Les repères horodatés restent
cliquables dans l'aperçu et à l'impression.

V2 (backlog) : éditeur enrichi (le gras et les titres s'affichent
directement), toujours sur le même Markdown stocké — le stockage brut
dès la V1 est justement ce qui permet ce changement plus tard sans nouvelle
migration.

### Ordre de travail (une tranche à la fois, arrêt entre chaque)

1. Design tokens — fait, voir ci-dessous.
2. Layout global et sidebar — fait, voir ci-dessous.
3. Extraction des couvertures (PDF, M4B, vidéo), cache hors bibliothèque,
   jamais écrites dedans ; placeholder par type sinon — fait, voir
   ci-dessous.
4. Écran Bibliothèque : recherche, filtres, grille, cartes — fait,
   voir ci-dessous.
5. Responsive — fait, voir ci-dessous.
6. Fiche de contenu — fait, voir ci-dessous.
7. Lecteur vidéo et programme — fait, voir ci-dessous.
8. Notes — fait, voir ci-dessous.
9. États vides et erreurs — fait, voir ci-dessous.

### Tranche 1 — design tokens (fait)

`static/tokens.css`, chargé avant `static/style.css` dans
`templates/_base.html`. Couleurs : palette officielle de la spec
(section 4), recopiée sans ré-estimation. Typographie : Inter en
`@font-face` (variable font, une seule plage de graisse 100–900 par
style plutôt qu'un fichier par graisse), échelle et graisses de la
section 6 avec le point choisi dans chaque plage documenté en
commentaire. Espacements et rayons : aucune valeur n'est imposée par la
spec (elle demande seulement qu'ils soient centralisés) — échelle de 4px
et trois rayons choisis, à ajuster librement. Transitions : valeurs
sobres par défaut, marquées "à ajuster" dans le fichier — rien à cet
égard dans la spec.

**Breakpoints**, dérivés (spec section 8 : pas de valeurs arbitraires,
doivent venir du moment où le contenu se comprime) — raisonnement :
largeur minimale de carte choisie à 260px (vignette 16:9 + 2 lignes de
titre + une ligne de métadonnées, section 13/14), espacement de grille
24px, empreinte de sidebar estimée à chaque palier (240px complète,
200px réduite, 72px icônes seules, 0 en drawer), plus le remplissage de
page. Seuil = empreinte sidebar + remplissage + N×260 + (N-1)×24,
arrondi :

    720px   -> 2 colonnes devient confortable (tablette)
    1120px  -> 3 colonnes devient confortable (desktop intermédiaire)
    1440px  -> 4 colonnes devient confortable (desktop large)

Le CSS ne permet pas d'utiliser une variable dans une condition
`@media` : ces tokens documentent et justifient les valeurs, mais les
futures règles `@media` devront répéter ces mêmes nombres en dur — à
garder synchronisés à la main si on retouche le raisonnement.

### Tranche 2 — layout global et sidebar (fait)

Avant de commencer, deux nettoyages demandés par Gautier :

- **Une seule feuille de style.** `static/style.css` avait son propre
  `:root` (ancienne palette bleue d'OfflineU) qui l'emportait sur
  `tokens.css` pour les noms en commun — deux sources pour la même
  valeur, source de confusion dès qu'on toucherait à la mise en page.
  Supprimé : `style.css` ne déclare plus que les quelques compléments
  sans équivalent officiel (voir "Fichiers"), tout le reste vient de
  `tokens.css`. Résultat direct et voulu : les pages existantes ont
  changé de couleurs et de police d'un coup (thème bleu -> palette
  officielle) avant même que leur mise en page soit reconstruite —
  normal, ce sont deux choses différentes qui se font l'une après
  l'autre, pas un rendu à moitié fini.
- **Polices en woff2.** Les .ttf déposés par Gautier ont été convertis
  (fonttools) puis retirés du dépôt ; `tokens.css` charge les .woff2
  (2 à 2,5 fois plus légers, format standard du web).

**Sidebar**, dans `_base.html`, identique sur toutes les pages :
- Logo (`static/images/logo.png`) en haut.
- Navigation (section 7.1, Favoris et Notifications retirés — pas de
  compte utilisateur en V1, voir "Contraintes absolues"). Seule
  "Bibliothèque" a une vraie destination aujourd'hui ; Continuer,
  Formations, Livres, Audiobooks, Notes, Paramètres s'affichent mais
  sont désactivés (`.disabled`, sans lien) tant que leur écran n'existe
  pas — pas de lien qui mène nulle part, pas de fonctionnalité simulée.
  Notes existe déjà comme page séparée (/notes-orphelines) mais n'est
  pas la même chose qu'"toutes mes notes" : pas relié pour ne pas
  créer une confusion entre les deux.
- Item actif marqué via `{% block active_nav %}` (une chaîne : library,
  notes...), lu dans `_base.html` avec `self.active_nav()` et comparé
  au `key` de chaque item de nav.
- Signature en bas ("Apprendre / Explorer / Progresser / Pour un
  meilleur / Demain") : texte de la maquette, repris tel quel — c'est
  une signature de marque, pas une donnée fabriquée.

Icônes de nav : SVG simples écrites à la main (pas de librairie
d'icônes, pas de CDN — cohérent avec l'appli hors-ligne). Ce n'est pas
le logo, donc pas concerné par l'interdiction de recréer le logo en SVG.

Contenu de chaque page (grille, fiche, lecteur, notes orphelines) :
inchangé dans cette tranche, simplement replacé à côté de la sidebar
dans `.app-main`. Leur reconstruction vient avec les tranches 4, 6 et 7.

### Tranche 3 — extraction des couvertures (fait)

`covers.py`, aucune nouvelle dépendance : `ffmpeg` et `pdftoppm`
(poppler-utils) étaient déjà installés sur la machine, appelés en
sous-processus comme `ffprobe` l'est déjà dans library_index.py.

Cache dans `<dossier de la base>/covers/<item_id>.jpg` — jamais dans la
bibliothèque, jamais suivi par git (déjà hors du dépôt de toute façon,
entrée `.gitignore` ajoutée par précaution). Ordre de priorité par
item :

1. Une image déjà présente dans le dossier de l'item (`resources` avec
   `resource_type = 'image'`) — recopiée en JPEG à taille plafonnée
   (480px) plutôt qu'utilisée telle quelle, pour un format uniforme.
2. book : première page du PDF (`pdftoppm -singlefile`, évite le
   suffixe de page qu'il ajoute sinon).
3. audiobook : pochette intégrée au M4B (`ffmpeg`, réencodée en JPEG —
   le flux copié tel quel donnerait un format variable selon le
   fichier).
4. course : une frame de la première vidéo, à 10% de sa durée (plafond
   15s, jamais avant 1s) — jamais la première seconde, souvent un écran
   noir ou un générique.

Si rien de tout ça n'aboutit (pas de média du bon type, outil en échec,
fichier illisible) : aucune erreur, aucun fichier en cache, l'item
reste dans la grille avec le badge de couleur par type déjà existant —
vérifié avec le livre audio de test, qui n'a pas de pochette intégrée.

Ni le scan ni la web app ne déclenchent d'extraction : c'est un choix
explicite, `library_index.py --covers` (manquantes) ou `--recovers`
(tout, même déjà en cache) — mêmes noms de logique que `--probe`/
`--reprobe`. L'app web se contente de lire le cache (`GET /cover/<id>`,
404 si absent) ; `library_grid.html` affiche l'image si elle existe,
sinon retombe sur l'emoji par type comme avant.

Non testé en pytest (nécessiterait des fichiers M4B/vidéo valides
synthétisés) : l'extraction M4B et vidéo, vérifiées à la main sur la
vraie bibliothèque de test à la place. Testé en pytest : l'extraction
PDF (avec un PDF minimal écrit à la main, `pdftoppm` s'en accommode
sans xref complet), et toute la logique de cache/priorité/repli avec
des extracteurs remplacés.

À ce stade, la carte de la grille n'était pas encore celle de la spec
(16:9, badge, auteur...) — seul le remplacement emoji -> image avait
été branché pour vérifier le mécanisme. La vraie carte est venue avec
la tranche 4 (ci-dessous).

### Tranche 4 — écran Bibliothèque (fait)

Reprise de `templates/library_grid.html` selon les points 12, 13, 31
et 32 de la revue (`design/revue-ui.md`) :

- **Auteur/formateur sur la carte.** `fetch_item_author()` (studia.py)
  réutilise exactement la même résolution que la fiche
  (`resolve_metadata_fields()` puis `extract_hero_fields()`), pas un
  second chemin qui risquerait de diverger. Titre limité à 2 lignes,
  auteur à 1 ligne, hauteur de carte uniforme pour que les cartes ne
  varient plus avec la longueur du contenu.
- **Recherche, filtres, tri.** Recherche instantanée (débattue à
  150 ms) sur titre et auteur, chips de filtre par type avec les vrais
  effectifs, tri (titre / récemment ajoutés) — tout côté client,
  puisque toute la bibliothèque tient déjà sur une seule page sans
  pagination. Recherche, filtre actif et tri restent mémorisés d'une
  navigation à l'autre (`sessionStorage`).
- **Couleurs et icônes de couverture.** Les couleurs de repli
  `.cover.*` (restées de l'ancien thème bleu, jamais migrées vers les
  tokens) reprennent les mêmes `--color-badge-*` que les badges de
  type ; les émojis colorés sont remplacés par les mêmes icônes SVG
  dessinées à la main que le repli de la fiche, factorisées dans une
  macro partagée (`_type_icon.html`) plutôt que dupliquées dans les
  deux gabarits.
- **Correctif :** le passage de `.card-body` en colonne flexible (pour
  un espacement homogène) étirait tous ses enfants directs en pleine
  largeur par défaut (`align-items: stretch`), y compris le badge —
  qui doit épouser son propre texte, comme sur la fiche. Correctif
  scopé au badge seul plutôt que de changer `align-items` du
  conteneur, dont les autres enfants ont besoin pour se tronquer
  correctement.

Écarté à cette étape, sur demande de Gautier : la progression sur la
carte et l'écran « Continuer » (tant que `progress` n'est pas
alimenté, ce serait simuler une fonctionnalité) ; les états vides
(couverts en tranche 9) ; le menu ⋮ toujours visible sur la carte,
réservé à une tranche commune avec celui de la fiche — fait depuis sur
la fiche, pas encore sur la carte.

Deux coûts mesurés et consignés au backlog plutôt qu'optimisés
immédiatement : `fetch_item_author()` reparse la présentation de
chaque item à chaque chargement de la grille ; le tri « Récemment
ajoutés » ne reflète la vraie date de premier scan qu'une fois la base
déjà peuplée (voir backlog pour le détail des deux).

Vérifié à l'œil sur les 4 items de la bibliothèque de test, `pytest
tests/` (73 tests) au vert.

### Tranche 5 — responsive (fait)

Adaptation de l'ensemble de l'application à quatre tailles, en
réutilisant les seuils déjà dérivés en tranche 1 (720/1120/1440,
tokens.css) plutôt que d'en réinventer — écran par écran, un commit
par écran :

- **Sidebar**, traitée en premier car la plus structurante. Quatre
  états : desktop large (≥1440, inchangé, 240px) ; desktop
  intermédiaire (1120–1439, réduite à 200px, même contenu) ; tablette
  (720–1119, icônes seules à 72px, pictogramme `logo-picto.png` — déjà
  fourni, jamais utilisé jusque-là — à la place du mot-symbole,
  libellés en infobulle) ; smartphone (<720, tiroir fermé par défaut,
  ouvert par un bouton hamburger).
- **Grille.** Colonnes explicites par palier (1/2/3/4) à la place d'un
  `auto-fill` qui n'utilisait pas du tout les seuils officiels et
  sautait de 2 à 4 colonnes sans jamais passer par 3 sur le palier
  intermédiaire. Chips de filtre qui débordaient à 375px (pas de
  `flex-wrap`) corrigées.
- **Fiche.** L'unique seuil existant (700px, non officiel) traitait
  tablette et smartphone pareil ; séparé en deux — tablette garde
  l'image à côté du texte (réduite), smartphone l'empile au-dessus.
- **Lecteur vidéo.** Seuil existant (900px, non officiel) réaligné sur
  719px. Tablette garde vidéo et programme côte à côte (chapitres
  toujours repliables comme sur desktop), programme rétréci à 240px
  plutôt qu'empilé.
- **Notes et modales** : déjà responsives sans y toucher — la barre
  d'outils avait son `flex-wrap` depuis la tranche 8, et `dialog.modal`
  sa largeur/hauteur bornées au viewport depuis la correction du
  centrage.

Deux corrections après un premier retour à 375px : le bouton hamburger
était en position fixe, donc gardé plaqué à l'écran pendant le
défilement — il finissait par recouvrir la couverture d'une fiche ou
le titre d'une vidéo. Déplacé dans une barre en flux normal (collante,
pas fixe), qui occupe sa propre place plutôt que de se superposer.
Les trois contrôles du hero (CTA principal, CTA secondaire, menu ⋮) ne
tenaient pas sur une ligne à cette largeur, forçant certains libellés
à se couper en deux lignes ; le CTA principal et le menu restent
ensemble sur la première ligne, le CTA secondaire passe seul en
pleine largeur en dessous.

Vérifié à chaque étape que le rendu desktop large (≥1440) reste
identique. `pytest tests/` (74 tests) au vert tout du long — CSS et
gabarits uniquement, aucun test à écrire pour cette tranche.

### Tranche 6 — fiche de contenu (fait)

Reprise de la fiche (`templates/item_detail.html`) selon les sections
20 à 28 de la spec : elle s'était éloignée en pile verticale de cartes.
Nouvelle structure : hero horizontal (couverture ~30-35% à gauche ;
badge, titre, auteur/formateur, durée, nombre de médias, chapitres,
année, boutons d'action à droite — `extract_hero_fields()` dans
studia.py, qui choisit auteur/année parmi la présentation locale puis
les métadonnées de livre validées), suivi de trois onglets À propos /
Programme / Ressources (bascule en JS pur, `data-tab-target` /
`data-panel`, pas de bibliothèque).

Cinq corrections demandées par Gautier :

1. **Logo.** La fenêtre principale (grille) affichait `<h1>Studia</h1>` ;
   remplacé par `static/images/logo.png` (picto + texte), comme la
   sidebar.
2. **Redondances supprimées :**
   - La table des matières que certaines présentations répètent en fin
     de texte (ex. Copywriter : "Table des matières" ; Motion Design :
     "Les vingt-sept chapitres", sans le mot "sommaire") duplique le
     programme réel tiré du scan. `presentation.py` la coupe désormais
     à l'affichage (`_drop_table_of_contents`, repérage par mot-clé de
     titre — "table des matières", "sommaire", "chapitre", "programme"
     — jamais par position, donc un contenu qui n'a pas ce genre de
     titre n'est jamais tronqué). Le programme réel reste seul, dans
     l'onglet Programme, en accordéon (`<details>`) replié par défaut.
   - Sur Adobe Illustrator, Auteur/Éditeur apparaissaient à la fois
     dans les faits extraits de la présentation et dans la carte
     Métadonnées validée — corrigé sur le moment par un masquage
     provisoire des libellés en double (`filter_duplicated_presentation_facts()`).
     Ce correctif a depuis disparu : `resolve_metadata_fields()` (voir
     « Traçabilité des métadonnées » ci-dessous) résout un seul champ
     par concept bibliographique avec une vraie priorité de source —
     la présentation locale ne s'affiche plus jamais à côté d'une
     valeur de fiche livre validée pour le même concept.
3. **Bouton d'action principal** du hero : lien direct vers la première
   vidéo (`first_video_id`) si l'item en a une, sinon un bouton désactivé
   pour livre/audiobook (pas encore de lecteur audio/PDF).
   Un second libellé pour une progression déjà enregistrée suppose une
   progression enregistrée : pas encore le cas (voir backlog "sauvegarde
   de la position de lecture"), donc un seul libellé est atteignable
   pour l'instant — pas un bug, une conséquence attendue. (Devenu
   depuis un choix à trois états neutres — Commencer / Continuer /
   Revoir, identiques pour une formation et un audiobook — voir la
   tranche du lecteur audio M4B.)
4. **Lecteur vidéo** (`templates/video_player.html`) : la note
   (`render_note`) est remontée juste sous les boutons précédent/
   suivant, dans la même colonne que la vidéo, au lieu d'une ligne
   pleine largeur séparée en dessous. La playlist (`.playlist`) était
   calée sur la hauteur de cette colonne par un script
   (`ResizeObserver` sur `.main`, hauteur recopiée sur `.playlist`) —
   préféré à l'époque à un `align-items: stretch` en CSS, dont le
   comportement avec une liste très longue (258 vidéos sur Motion
   Design) et un `overflow-y: auto` était incertain sans test réel.
   **Remplacé depuis** (tranche "Progression visible et liste de
   lecture" ci-dessous) par `position: sticky` : le `ResizeObserver`
   recopiait la hauteur totale de `.main` (vidéo + notes), qui pouvait
   largement dépasser la hauteur de l'écran sur une note longue — d'où
   un double défilement, et un centrage automatique faussé (calculé
   sur cette hauteur périmée). Le CSS seul borne désormais `.playlist`
   à la hauteur visible du viewport, sans dépendre d'un script ni de
   son minutage.
5. **Badges en français** : BOOK/COURSE/AUDIOBOOK → LIVRE/FORMATION/
   AUDIOBOOK (`BADGE_LABELS` dans studia.py, fonction `badge_label()`).

Vérifié à l'œil sur les 4 items de la bibliothèque de test (grille et
fiches), `pytest tests/` (73 tests) au vert.

### Tranche 7 — lecteur vidéo et programme (fait)

Reprise de `templates/video_player.html` selon les points 18 et 19 de
la revue :

- **Extensions masquées.** Titre de page, `<h1>` et chaque ligne de la
  playlist passent par `clean_file_title()`, comme partout ailleurs —
  plus de `.mp4` visible.
- **Playlist par chapitre.** Elle reflète maintenant les chapitres
  réels, en accordéon (`<details>`), au lieu d'une liste plate — même
  structure que l'onglet Programme de la fiche. Quand un item n'a
  qu'un seul groupe et qu'il correspond à la racine (pas de
  sous-dossier, ex. Copywriter et ses 49 vidéos), l'en-tête « Racine »
  n'est pas affiché : il ne coifferait qu'un unique groupe contenant
  tout le contenu, sans rien distinguer. Le total (nombre de vidéos,
  durée) reste visible dans le hero de la fiche, qui couvre déjà tout
  l'item dans ce cas.
- **Chapitre courant et état conservé.** Le chapitre qui contient la
  vidéo en cours s'ouvre toujours automatiquement ; l'état ouvert/fermé
  de chaque autre chapitre est mémorisé par item (`localStorage`) et
  survit à la navigation d'une vidéo à l'autre (point 32, persistance
  d'état, pour ce panneau spécifiquement).
- **Leçon en cours plus visible.** Fond teinté et liseré orange sur la
  ligne active (point 19), volontairement restreint à ces deux
  éléments — pas d'icône lecture ni de coche « terminé », qui
  supposerait une progression enregistrée, hors périmètre tant que
  `progress` n'est pas alimenté.
- **Colonne de durée stable.** La playlist reprend le motif de
  l'onglet Programme (titre tronqué sur une ligne, durée figée à
  droite) : un titre long ne pousse plus la durée hors de vue.

Hors périmètre, sur demande de Gautier : la progression et les états
de leçon ; le responsive (tranche 5, pas commencée).

Vérifié à l'œil sur Copywriter (49 vidéos, pas de sous-dossier) et
Motion Design (27 chapitres), `pytest tests/` (73 tests) au vert.

### Tranche 8 — notes (fait)

Complète le « Format des notes » décrit plus haut, jusque-là non
implémenté malgré le stockage Markdown déjà en place depuis le
Bloc-notes initial :

- **Barre d'outils.** Gras, italique, titres 1 à 3, liste, bloc de
  code. Chaque bouton est un véritable interrupteur plutôt qu'un
  simple ajout : recliquer sur un format déjà appliqué le retire, au
  lieu d'empiler les marqueurs (`****texte****`). Détection : pour
  gras/italique, soit la sélection inclut déjà les marqueurs, soit ils
  se trouvent juste à l'extérieur de la sélection ; pour l'italique
  spécifiquement, un seul `*` adjacent ne suffit pas à conclure (une
  paire de gras et un triple gras+italique partagent le même caractère
  immédiat) — la détection compte la série complète d'astérisques de
  chaque côté, un compte impair signalant une couche italique
  isolable, un compte pair son absence. Pour les titres et la liste,
  la détection se fait ligne par ligne ; pour le bloc de code, sur les
  clôtures ``` immédiatement à l'extérieur de la sélection ou incluses
  dedans. Pas de bouton souligné : absent du Markdown standard, et les
  notes ne doivent contenir aucun HTML. Le bouton « Insérer un repère »
  (déjà existant) rejoint cette barre, sur le lecteur uniquement.
- **Aperçu, par défaut sur la fiche.** Un moteur Markdown minimal,
  écrit à la main (aucune bibliothèque externe — l'appli doit rester
  utilisable hors connexion), limité exactement à ce que la barre
  d'outils peut produire, plus les repères horodatés rendus en lien
  cliquable. Le texte est échappé avant toute mise en forme. Sur la
  fiche, l'aperçu est l'état par défaut à l'ouverture (une note se lit
  plus souvent qu'elle ne s'édite) ; « Éditer » fait apparaître le
  champ et la barre d'outils, et quitter le champ (perte de focus)
  sauvegarde immédiatement et repasse en aperçu — déclenché sur la
  perte de focus elle-même, mesuré à moins d'une milliseconde après le
  clic, plutôt qu'à la fin des 900 ms de la sauvegarde différée, qui
  aurait pu laisser la note en édition un moment après un clic
  ailleurs, ou ne jamais revenir en aperçu si la dernière frappe datait
  déjà de plus de 900 ms. Le bouton Aperçu/Éditer capture son intention
  dès l'appui (`mousedown`), avant cette même perte de focus, pour ne
  pas s'annuler lui-même. Sur le lecteur, l'édition reste l'état par
  défaut : la note s'écrit en regardant la vidéo, un aller-retour
  supplémentaire serait pénible. Une fiche sans note affiche un état
  vide court (« Pas encore de note. ») avec son propre bouton Éditer,
  plutôt qu'un rectangle vide.
- **Impression.** Passe par le même moteur que l'aperçu au lieu d'un
  texte brut : les repères s'y affichent comme des liens propres, sans
  leur fragment technique (`/watch/id?t=secondes`).
- **Imprimer déplacé.** Sort de la barre pour rejoindre un menu ⋮ à
  côté du titre « Notes », qui réutilise le motif du menu ⋮ du hero
  (`.hero-menu`) plutôt que d'en recréer un.

Hors périmètre, sur demande de Gautier : tout changement de stockage
(reste le même Markdown brut, une note par contenu) ; l'éditeur
enrichi (WYSIWYG), toujours au backlog en V2 pour la même raison
qu'avant — le stockage Markdown brut permet de le greffer plus tard
sans migration.

Vérifié à l'œil sur la fiche (avec et sans note) et le lecteur,
`pytest tests/` (74 tests) au vert.

### Tranche 9 — états vides et erreurs (fait)

Revue des six états demandés (aucun résultat, aucune ressource, aucune
note, aucun média, bibliothèque vide, contenu introuvable) — point 33
de la revue. Quatre existaient déjà, posés dans des tranches
précédentes, vérifiés puis laissés tels quels : aucun résultat
(« Aucun résultat. » sous la grille), aucune ressource (« Aucune
ressource. » dans l'onglet Ressources), aucune note (aperçu Markdown
d'une note vide : « Pas encore de note. »), aucun média (« Aucun
média. » dans l'onglet Programme). Deux manquaient :

- **Bibliothèque vide.** La barre recherche/filtres/tri s'affichait
  même sans aucun contenu, et le message « Aucun résultat. » — pensé
  pour une recherche infructueuse — s'affichait à tort pour une
  bibliothèque jamais scannée. Toolbar et grille masquées entièrement
  quand `items` est vide, remplacées par une phrase dédiée
  (« Bibliothèque vide — aucun contenu n'a encore été scanné. »).
- **Contenu introuvable.** Les 404 (fiche, vidéo, fichier inconnu)
  renvoyaient la page Flask brute, hors de l'habillage de l'appli. Un
  gestionnaire d'erreur global (`@app.errorhandler(404)`) rend
  désormais `templates/not_found.html` (sidebar incluse) avec un lien
  de retour vers la bibliothèque, pour toute 404 de l'appli.

Deux tests ajoutés (bibliothèque vide, contenu de la page 404) —
comportements nouveaux, non couverts par la suite existante.

Vérifié à l'œil, `pytest tests/` (74 tests) au vert.

### Accessibilité et finitions (fait)

Dernière tranche de la refonte visuelle, hors de la liste numérotée
ci-dessus (comme « Traçabilité des métadonnées » et « Priorité des
couvertures ») : accessibilité clavier et finitions, selon le point 34
de la revue.

- **Contraste**, mesuré (formule WCAG), pas jugé à l'œil. Toute la
  palette officielle passe le seuil AA (4,5:1) sur les fonds où elle
  est réellement utilisée : texte secondaire 9,3–10,4:1, texte
  tertiaire 5,4–6,0:1, accent en texte 5,97–6,69:1, les trois paires
  de badges 5,52–6,40:1 — rien à changer dans la charte. Deux réglages
  qui n'en faisaient pas partie ont été corrigés : le compteur des
  chips de filtre perdait du contraste avec une opacité réduite
  (3,51:1 sur une chip active, sous le seuil) ; les champs de
  recherche et de note n'avaient pas de couleur de placeholder
  explicite (valeur du navigateur, non garantie) — fixée à
  `text-tertiary`.
- **Focus clavier**, rendu visible partout via un contour générique
  (le même accent que la sidebar) sur tous les éléments interactifs
  natifs. Deux endroits masquaient ce contour sans le vouloir : les
  cartes de la grille et les chapitres du Programme coupent tout
  dépassement pour leurs coins arrondis, un contour classique y aurait
  été invisible — contour rentrant à la place ; le menu ⋮ supprimait
  carrément son contour au clavier, ne laissant qu'un fond à peine
  visible — corrigé.
- **Modales.** Le piège de focus natif de `<dialog>` et la
  restauration du focus à la fermeture ne se sont pas montrés fiables
  à l'usage (vérifié au clavier réel, pas supposé) : refaits à la
  main — Tab/Shift+Tab bouclent dans la modale, Échap est intercepté
  directement, et les trois façons de fermer (croix, clic dehors,
  Échap) rendent le focus au bouton ⋮ d'origine.
- **Tiroir de la sidebar.** Une translation CSS ne retire rien de
  l'ordre de tabulation : fermé, ses liens restaient atteignables au
  Tab tout en étant invisibles ; ouvert, le Tab pouvait continuer dans
  le contenu masqué par le fond d'estompage. Rendu inerte (`inert`
  natif) selon l'état, uniquement au palier smartphone. Correction
  après premier retour : rendre tout `.app-main` inerte à l'ouverture
  emportait le bouton hamburger lui-même, qui ne refermait plus le
  tiroir — le contenu de page est maintenant dans son propre conteneur
  (`#app-content`), seul rendu inerte ; le bouton reste toujours
  cliquable.
- **Infobulles** ajoutées partout où un texte est coupé par une
  ellipse (carte, chapitre, playlist du lecteur — ce dernier avait été
  oublié à la tranche 7).
- **Boutons à icône seule** (hamburger, menu ⋮, croix de fermeture,
  croix de suppression d'un repère) : déjà tous étiquetés depuis les
  tranches précédentes, vérifié plutôt que refait.
- **Menus ⋮ : pas de navigation aux flèches.** Le rôle ARIA « menu »
  utilisé pour ces menus implique normalement une navigation complète
  aux flèches ; pour 1 à 3 actions, l'effort de l'implémenter aurait
  été disproportionné par rapport à Tab + Entrée, qui fonctionne déjà.
  Tranché de ce côté-ci (pas une demande de Gautier), signalé dans le
  compte-rendu de la tranche, validé sans changement.
- **Cas extrêmes** (titre et auteur très longs, 124 chapitres, durée
  de plusieurs jours, 40 ressources, aucune métadonnée, aucune
  couverture) construits dans une bibliothèque et une base jetables,
  jamais la bibliothèque réelle — deux tests pytest permanents plutôt
  qu'une vérification à usage unique.

Limite de vérification levée : le franchissement des seuils par un
vrai redimensionnement de fenêtre (tiroir ouvert qui doit se refermer
tout seul en élargissant au-delà de 720px, page qui doit rester
utilisable en rétrécissant sans toucher au tiroir) n'avait pas pu être
observé dans l'environnement de développement — une iframe de test
redimensionnée ne déclenche ni `resize` ni le `change` de `matchMedia`
sur son propre contenu. Vérifié depuis par Gautier dans une vraie
fenêtre : les deux cas passent.

Vérifié à l'œil sur les quatre écrans et à la souris comme au clavier,
`pytest tests/` (76 tests) au vert.

### Traçabilité des métadonnées — partiellement implémentée

Décidé avec Gautier au moment de la tranche 6 : **aucun champ de
métadonnée sans source identifiée.** Une partie est faite, dans une
tranche à part (entre la tranche 6 et la tranche 7, pas numérotée dans
l'ordre de travail ci-dessus) :

- `resolve_metadata_fields()` (studia.py) résout un seul champ par
  concept bibliographique (Auteur/Formateur(s), Éditeur, Date de
  publication, ISBN), avec une priorité claire : une fiche livre
  validée l'emporte toujours sur la présentation locale, jamais
  l'inverse. Chaque champ résolu porte une clé stable (`key`) en plus
  de son libellé affiché — `extract_hero_fields()` s'appuie sur cette
  clé plutôt que sur le texte du libellé, qui peut changer sans que le
  hero s'en trouve affecté.
- La provenance de chaque champ résolu est connue en interne
  (`field["source"]`), mais n'est plus affichée dans la vue normale de
  la fiche — jugée comme du bruit répété à côté de chaque fait. Elle
  reste visible dans l'interface d'édition : « Provenance actuelle »
  dans le modal « Modifier les métadonnées », « Provenance des
  métadonnées » dans « Voir les informations techniques » —
  uniquement pour un livre ou un audiobook avec une fiche validée. Une
  formation n'affiche cette information nulle part aujourd'hui : sa
  seule source possible est la présentation locale, implicite tant que
  le moissonnage de plateformes n'existe pas.
- Sources autorisées pour les livres et audiobooks : Google Books et
  Open Library, uniquement après validation d'un candidat par Gautier
  — déjà le cas depuis « Métadonnées de livres » ci-dessus.
- Un rescan ne remplace jamais un champ dont la source n'est pas le
  scanner : vrai par construction plutôt que par un mécanisme dédié —
  `book_search`/`book_candidates` ne sont jamais touchées par
  `scan_library` (voir plus haut), et les faits de présentation sont
  relus depuis le fichier HTML à chaque affichage, jamais stockés donc
  jamais écrasés.
- Le correctif provisoire de la Tranche 6
  (`filter_duplicated_presentation_facts()`) a disparu comme prévu,
  remplacé par la résolution ci-dessus plutôt que par un masquage de
  libellés.

Reste au backlog, non commencé :
- Sources pour les formations vidéo (tuto.com, Elephorm, Udemy,
  LinkedIn Learning...) par moissonnage des plateformes commerciales.
- Saisie manuelle générique pour les formations — aujourd'hui réservée
  aux livres/audiobooks via le workflow `book_manual`, pas de
  mécanisme équivalent pour un contenu de Gautier lui-même sans fiche
  livre.

### Priorité des couvertures — ordre acté, pas encore implémenté

Décidé avec Gautier, remplace l'ordre de la Tranche 3 ci-dessus le jour
où l'import manuel et la couverture Google Books seront ajoutés (tranche
séparée, pas commencée) :

1. image importée manuellement — priorité absolue, jamais écrasée par
   un rescan ni par `--recovers`.
2. image déjà présente dans le dossier de l'item.
3. première page du PDF ou de l'ebook (EPUB : couverture généralement
   intégrée au fichier ; si extraite, même rang que le PDF).
4. pochette intégrée du M4B.
5. couverture Google Books, si des métadonnées ont été validées.
6. image extraite de la vidéo.
7. placeholder par type.

Raison donnée par Gautier pour placer le PDF/l'ebook avant Google
Books : la première page vient de l'exemplaire qu'il possède
réellement, pas d'une autre édition que Google Books pourrait renvoyer.

L'import manuel lui-même (bouton sur la fiche, chargement depuis le
disque ou collage presse-papiers, stocké dans le cache des couvertures
— jamais dans la bibliothèque —, suppression possible pour revenir à
l'extraction automatique) n'est pas encore implémenté.

## Objectif suivant

Une application web locale mono-utilisateur lisant SQLite :
grille de couvertures -> fiche d'un item -> lecteurs -> progression.

Décision prise : écrire une nouvelle application (studia.py) à côté
d'OfflineU plutôt que de modifier offlineu_core.py, dont les 154
occurrences de « lesson » et l'état global current_course sont
incompatibles avec le modèle. Le CSS des templates existants est
réutilisable comme point de départ.

Lecteurs prévus, dans cet ordre : vidéo (fait), sauvegarde de la
position de lecture (fait, voir ci-dessous), audio/M4B (fait, voir
ci-dessous), PDF (PDF.js), EPUB. La
progression vient juste après la vidéo parce qu'elle ne se pose
qu'une fois et sert ensuite à tous les lecteurs suivants, plutôt que
d'être refaite à chacun. Le M4B reste avant le PDF : il partage la
même mécanique de position (en secondes) que la vidéo, déjà posée,
alors que le PDF progresse par page et suppose d'abord de connaître
le nombre de pages — pas encore lu au scan (voir backlog).

Les chapitres internes du M4B (repères ffprobe -show_chapters à
l'intérieur du fichier, distincts des chapitres par sous-dossier) ne
font pas partie de cette tranche : décidé avec Gautier, pour ne pas
mêler un chantier de lecteur à un chantier de scanner qui demanderait
une nouvelle table. Ligne de backlog inchangée, tranche suivante une
fois celle-ci validée.

Progression selon le type : secondes pour vidéo et audio, page pour PDF,
position pour EPUB.

### Sauvegarde de la position de lecture (vidéo, fait)

Écriture seule à ce stade de cette tranche : l'affichage est venu
ensuite, dans une tranche séparée — cartes de la grille, états de
leçon (Programme, playlist) et bouton principal du hero montrent
désormais la progression. Seule la section « Continuer » de la grille
reste au backlog, non construite. La table `progress` existait déjà au
schéma (v4, jamais utilisée jusqu'ici) : rien à migrer, uniquement des
requêtes et une route.

- **Écriture**, plusieurs déclencheurs combinés (`video_player.html`) :
  toutes les 30 secondes pendant la lecture (filet contre un plantage
  seulement — la pause, la fermeture et la fin couvrent déjà les cas
  réels, ce qui explique l'intervalle large plutôt que quelques
  secondes) ; à la pause ; à la fin de la vidéo (`ended`) ; à la
  fermeture ou au changement d'onglet, sur `visibilitychange` **et**
  `pagehide` combinés (selon le navigateur, l'un des deux peut ne pas
  se déclencher), via `navigator.sendBeacon` comme pour la note.
- **Seuil du « terminé »** (`is_video_completed`) : position à moins
  de 5 % de la durée totale de la fin, plafonnés à 15 secondes — le
  plafond évite qu'une formation de plusieurs heures exige d'atteindre
  sa toute dernière seconde (un générique de 10 minutes ne devrait pas
  empêcher indéfiniment le « terminé »), les 5 % s'appliquent tels
  quels sous ce plafond pour une vidéo courte.
- **Coche définitive.** Une fois vraie, `completed` ne redescend
  jamais automatiquement — revenir en arrière dans une vidéo déjà
  terminée continue de mettre à jour la position, mais ne retire pas
  la coche. « Terminé » veut dire « déjà vu en entier au moins une
  fois », pas « actuellement positionné à la fin ». Porté par un
  `MAX()` dans la requête d'upsert, pas par du code applicatif. Seule
  une remise à zéro explicite (backlog, tranche d'affichage) peut la
  défaire.
- **Agrégation média -> item** (`aggregate_item_progress`) :
  « jamais ouvert » si aucun média principal n'a de ligne de
  progression, « terminé » si tous l'ont avec `completed`, « en
  cours » sinon. Un item sans aucun média principal (item classé
  « document », ou un livre dont le PDF n'est qu'une ressource) reçoit
  explicitement « jamais ouvert » — jamais « terminé » par vacuité
  (une liste vide validerait trivialement `all()`).
- **Reprise exacte.** À l'ouverture du lecteur, la position enregistrée
  est reprise telle quelle, sans recul artificiel — sauf si la vidéo
  est déjà `completed` : dans ce cas elle repart du début, pas de sa
  position de fin enregistrée. Rouvrir une vidéo déjà terminée, c'est
  vouloir la revoir. Un repère explicite (`?t=`, cliqué depuis une
  note) l'emporte toujours sur cette reprise automatique, y compris
  sur une vidéo terminée — c'est un geste volontaire, pas la reprise.
- **Garde-fou sur l'enchaînement automatique.** Corrige un effet de
  bord découvert à l'usage réel : reprendre une vidéo déjà terminée la
  positionnait autrefois à sa propre fin, ce qui déclenchait `ended`
  quasi instantanément et enchaînait en cascade sur toutes les vidéos
  terminées suivantes jusqu'au vrai point de reprise. La reprise au
  début d'une vidéo terminée (règle précédente) supprime la cause de
  cette cascade précise ; le garde-fou `player.played` protège en plus,
  indépendamment, contre tout autre `ended` déclenché sans lecture
  réelle — les deux corrections viennent du même passage, pas l'une
  après l'autre. L'écouteur `ended` qui enchaîne sur la vidéo suivante
  vérifie désormais `player.played` (mesure native de
  ce qui a réellement défilé, distincte de `currentTime`) : en dessous
  d'un plancher de 0,25 seconde de lecture réelle, ce n'est pas une
  vraie fin, pas d'enchaînement. Le plancher porte sur la quantité
  réellement jouée, pas sur un délai depuis le chargement de la page —
  ça tient donc aussi bien sur une vidéo très courte.
- **Bouton principal du hero.** Vise désormais la première vidéo non
  terminée dans l'ordre du programme, ou la première vidéo de l'item
  si tout est déjà terminé — plus systématiquement la première vidéo
  quel que soit l'état d'avancement. Le libellé lui-même reste celui
  d'avant cette tranche à ce stade : le second état (aujourd'hui
  « Continuer ») appartient à la tranche d'affichage suivante.

Non testable en pytest : le garde-fou `player.played` dépend d'un
vrai minutage de lecture dans un navigateur, absent de cette suite de
tests. Le test correspondant
(`test_enchainement_automatique_garde_fou_present`) vérifie seulement
que le garde-fou est bien présent dans le gabarit rendu — une
protection contre une régression du code, pas une simulation du
comportement réel. Vérifié à la main sur la bibliothèque de test
(Motion Design) : reprise directe à la bonne vidéo, pas de cascade,
enchaînement normal préservé sur une vidéo qui se termine réellement,
vidéo terminée qui repart du début.

`pytest tests/` (106 tests) au vert.

### Lecteur audio M4B (fait)

Route dédiée `/listen/<media_id>` (studia.py, `listen_audio`), gabarit
séparé `templates/audio_player.html` — délibérément pas une
réutilisation de `/watch` : un audiobook est un fichier unique, sans
playlist ni précédent/suivant à afficher, et le texte du repère de
note (voir plus bas) doit lui être propre. `<audio controls
autoplay>`, contrôles natifs du navigateur uniquement — pas de barre
de transport maison, pas de bouton ±15 s, pas de réglage de vitesse
ajouté à la main (déjà exposé nativement par Chrome sur `<audio
controls>`) : même sobriété que le lecteur vidéo.

Les chapitres internes du M4B restent hors de cette tranche (voir
"Objectif suivant" ci-dessus et le backlog) : décidé avec Gautier pour
ne pas mêler un chantier de lecteur à un chantier de scanner qui
demanderait une nouvelle table.

**Progression, réutilisée à l'identique.** Les règles qui ne
filtraient déjà pas par type de média (`fetch_media_progress`,
`save_video_progress`, `is_video_completed`, `resolve_resume_seconds`)
s'appliquent à l'audio sans aucun changement — même seuil du
"terminé", même reprise, même coche définitive. Ce qui filtrait sur
`media_type = 'video'` a été élargi, piloté par
`TRACKED_PROGRESS_MEDIA_TYPE` (`course` -> `video`, `audiobook` ->
`audio`) :

    fetch_item_video_progress    -> fetch_item_media_progress(conn, item_id, item_type)
    fetch_video_progress_states  -> fetch_media_progress_states(conn, item_id, media_type)
    resolve_watch_target_video_id -> resolve_watch_target_media_id
    fetch_video_media            -> fetch_playable_media (filtre élargi à video+audio)

`/watch` et `/listen` gardent chacune leur propre garde de type (une
vidéo ne s'ouvre pas via `/listen`, et inversement) ; `/media/<id>/file`
et `/media/<id>/progress` acceptent les deux, puisqu'ils ne servent
jamais un livre (pas encore de lecteur pour `media_type = 'book'`).

**Pourcentage de la carte grille : deux règles, pas une seule tordue
pour les deux** (`compute_item_progress_percent`, décidé avec
Gautier) :
- formation : médias terminés / total de médias — inchangé, toujours
  pas les secondes vues sur la durée totale (ne correspondrait à
  aucune coche "terminé" précise sur plusieurs vidéos).
- audiobook : position / durée du fichier unique, en continu. L'objection
  qui avait fait écarter ce calcul pour la vidéo ne s'applique pas ici :
  un seul fichier, donc aucune coche intermédiaire à respecter. Un
  livre audio à 40 % affiche 40 %, pas 0 ou 100 par paliers.

**Bouton hero et message.** `resolve_hero_cta(item_type,
progress_status)` renvoie le verbe et l'endpoint
(`watch_video`/`listen_audio`). `first_video_id` devient
`first_playable_media_id`, générique au type. Le message "Ce format ne
peut pas encore être lu dans l'application." se resserre sur
`item_type == 'book'` seul. (Le verbe lui-même est devenu neutre
— Commencer/Continuer/Revoir — dans une tranche ultérieure, voir
"Tout recommencer" ci-dessous.)

**Repère de note.** Le motif reconnu (`MARKER_PATTERN`,
_note_widget.html) accepte `/watch/id?t=secondes` et
`/listen/id?t=secondes`. Sur l'audiobook, le texte inséré n'a ni
numéro ni titre à répéter (un seul fichier) : juste l'horodatage et le
lien, contrairement au "Vidéo N — titre — mm:ss" du lecteur vidéo.

**Correctif trouvé en cours de route.** Le module `mimetypes` de
Python ne connaît pas `.m4b` par défaut (contrairement à `.m4a`,
mappé sur `audio/mp4`) : sans `mimetypes.add_type("audio/mp4",
".m4b")`, `/media/<id>/file` servait un livre audio sans Content-Type
exploitable par `<audio>`. Vérifié directement en HTTP (curl, requête
Range) sur le fichier réel de la bibliothèque de test : réponse 206,
`Content-Type: audio/mp4`, `Accept-Ranges: bytes` corrects.

Vérifié à l'œil sur "S organiser pour reussir" (fiche et lecteur) et
sur "Adobe Illustrator CS6" (message resserré). Limite de vérification
rencontrée et non levée : dans cet environnement de navigateur
automatisé, l'élément `<audio>` (et, vérifié en comparaison, l'élément
`<video>` existant aussi) ne déclenche aucune requête réseau vers
`/media/<id>/file`, même après un appel explicite à `player.load()` —
le serveur ne reçoit rien. Le contrat serveur (Content-Type, Range) est
lui confirmé indépendamment par curl et par pytest ; la lecture audio
réelle dans un navigateur reste à confirmer par Gautier lui-même.

`pytest tests/` (145 tests) au vert.

### "Tout recommencer" (fait)

Remplace trois essais successifs, écartés dans la même tranche : un
contrôle de remise à zéro par média (icône, puis bouton texte) dans le
Programme et la playlist, puis un bouton icône seule dans le hero
(flèche circulaire façon Jellyfin) — retirés parce que glisser la
barre de lecture est plus rapide et que personne ne devine ce qu'une
icône seule efface. `POST /media/<id>/reset-progress`, devenue sans
appelant, est supprimée plutôt que laissée morte.

Ce qui reste : un seul bouton texte "Tout recommencer" dans le hero,
visible seulement s'il y a une progression à effacer (à côté du CTA
principal, jamais dans le menu ⋮ — une action de lecture, pas de
maintenance). Une seule boîte de dialogue, titre en gras plutôt qu'entre
guillemets français (qui se cassent mal sur un titre long), qui nomme
précisément ce qui va disparaître — décompte des vidéos terminées plus
une phrase sur la position des vidéos en cours quand elle existe
(`has_in_progress_media`), ou la position d'écoute pour un audiobook.
Une case à cocher obligatoire («&nbsp;Je comprends que cette action est
définitive.&nbsp;») garde le bouton de validation désactivé tant qu'elle
n'est pas cochée, et se décoche à chaque fermeture de la boîte (croix,
"Annuler", clic hors du cadre, Échap — tous explicitement câblés,
jamais le seul évènement natif `close`, jamais fiable ici à l'usage).
Confirmer efface tout et enchaîne directement sur la lecture depuis le
début, plutôt que de rester sur la fiche.

`resolve_hero_cta` renvoie un verbe neutre, identique aux deux types
suivis (Commencer/Continuer/Revoir) — "Regarder", "Écouter" et
"Reprendre" ont disparu de l'interface, seul l'endpoint choisi
(`watch_video`/`listen_audio`) dépend encore du type.

`pytest tests/` (167 tests) au vert.

### Progression visible et liste de lecture (fait)

Trois écrans, un seul composant de barre (`_progress_bar.html`,
`progress_bar(percent)`) partagé entre la carte de la grille et le
hero de la fiche — jamais un second calcul, le pourcentage vient
toujours de `compute_item_progress_percent` via `fetch_item_media_progress`.

- **Barre à 100 %.** Revient sur la décision d'origine (section 17 de
  la spec) : à 100 %, même barre pleine qu'aux autres valeurs, avec son
  "100 %", plutôt qu'un texte seul sans barre. `.card-progress-done`
  supprimée, devenue inutile.
- **Fiche.** Même barre, pleine largeur de `.hero-info` (qui aligne ses
  enfants sur leur propre largeur par défaut, contrairement à
  `.card-body` — `align-self: stretch` posé exprès), entre la ligne de
  métadonnées et la rangée d'actions. Une ligne de texte dessous
  (`build_progress_summary_line`) : "37 % · 18 vidéos sur 49" pour une
  formation (même accord 0/1/2+ que la boîte "Tout recommencer"),
  "42 % · 1 h 12 sur 3 h 05" pour un audiobook (position/durée, pas de
  décompte de fichiers — il n'y en a qu'un). Rien du tout si jamais
  ouvert, ni pour un livre (pas de progression).
- **Ligne de playlist**, refonte complète (`/watch` uniquement — le
  Programme de la fiche n'y touche pas) : numéro de tête séparé du
  titre (`split_leading_number`, ex. "001 - Interface" ->
  numéro "001" + titre "Interface" ; le nom de fichier réel et son tag
  ne changent pas, seul l'affichage sépare les deux), titre en gras sur
  deux lignes, durée en petit dessous. Retour à la ligne aux espaces
  uniquement, avec un filet de secours (`overflow-wrap: break-word`)
  pour le seul cas d'un mot unique plus long que la colonne. La césure
  automatique (`hyphens: auto`) essayée d'abord a été retirée : le
  dictionnaire du navigateur coupe mal des noms de fichiers dont les
  accents ont été retirés (ex. "auteurs" coupé en "au-teurs"). Le mot
  "Terminé" disparaît des lignes : une coche d'affichage à droite
  (`.lesson-check`, rond avec ✓ ou vide, `role="img"` + `aria-label`
  puisqu'elle n'est plus un texte) le dit à la place - jamais cliquable,
  jamais un contrôle, et jamais mise à jour en direct (voir "Affichage
  en direct" ci-dessous). La vidéo en cours (`current_media_id`,
  indépendant de son propre état terminé/non terminé) affiche à la
  place de sa durée seule "0:10 / 11 min 28 · en cours" (`format_clock`,
  horodatage compact, distinct de `format_duration`) plus une
  micro-barre de position sous le titre. Ligne passée d'environ 30 à
  48px : assumé, jugé à l'usage sur les 258 vidéos de Motion Design.
- **Affichage en direct de la ligne courante.** Le texte et la
  micro-barre de position de la ligne en cours se mettent à jour sur
  l'évènement `timeupdate` du lecteur, pas seulement au chargement de
  la page — sans écriture serveur supplémentaire, la sauvegarde de
  position garde exactement le même rythme qu'avant (30 s/pause/fin/
  fermeture). Seule cette ligne est touchée, jamais toute la liste. La
  coche "terminé" (`.lesson-check`), elle, reste volontairement
  statique : elle ne reflète que le dernier état enregistré par le
  serveur, jamais recalculée en direct pendant la lecture — cette coche
  ne redescend jamais une fois vraie (voir "Coche définitive"
  ci-dessus), et la faire vivre en direct pendant qu'on avance/recule
  dans la vidéo aurait exigé de rejouer cette même règle côté
  navigateur, avec un risque de scintillement pendant qu'on cherche une
  position, pour un bénéfice mineur (elle finit de toute façon à jour
  à la prochaine navigation).
- **Espaces insécables.** Toute construction nombre + unité (durées -
  "5 h 44", "2 min 30", "55 s" -, décomptes - "49 vidéos", "27
  chapitres" -, pourcentage de la ligne de résumé de progression)
  utilise une espace insécable (`NBSP`, U+00A0) entre le nombre et le
  mot qui suit, pour que le bloc ne se coupe jamais au milieu à
  l'affichage.
- **Défilement automatique** de la playlist sur la vidéo en cours.
  Centre la ligne courante (`current.offsetTop - clientHeight/2 +
  offsetHeight/2`, borné entre 0 et `scrollHeight - clientHeight`) — le
  bornage donne les deux extrémités sans cas particulier : négatif à un
  mot dans "les 15 premières vidéos" -> 0 (liste en haut, l'item
  descend jusqu'au centre), au-delà de max dans "les 15 dernières" ->
  max (liste au bout, l'item continue de descendre). Le calcul ne
  dépend plus de `loadedmetadata` ni d'aucun script de mesure : depuis
  que `.playlist` est bornée en pur CSS (`position: sticky`,
  `max-height: calc(100vh - ...)`, voir la correction à la Tranche 6
  ci-dessus), sa hauteur est stable dès le rendu de la page, le script
  de centrage s'exécute donc directement. Animé (`scrollTo({behavior:
  'smooth'})`) en venant d'un autre `/watch` (Précédent/Suivant,
  enchaînement — détecté via `document.referrer`), instantané sinon
  (arrivée directe depuis la fiche, URL tapée).

  Vérifié réellement dans le navigateur : les trois bornes (`scrollTop`
  resté à 0 en début de liste, mesuré égal au calcul manuel au milieu,
  bloqué au maximum en fin de liste) confirmées sur Motion Design avec
  le nouveau mécanisme sticky. Vérifié aussi que `.playlist` ne dépasse
  jamais la hauteur de l'écran, y compris avec une colonne de notes
  simulée bien plus haute que le viewport (défilement de `.main` seul,
  `.playlist` fixe). Reste à confirmer par Gautier : la distinction
  animé/instantané elle-même (dépend de `document.referrer`, non
  vérifiable en naviguant par URL directe dans cette suite).

`pytest tests/` (187 tests) au vert.

### Changement de vidéo sans rechargement (fait)

Précédent, Suivant, clic sur une ligne de la playlist et enchaînement
automatique remplacent la source du lecteur et les quelques morceaux
de DOM concernés (titre, boutons précédent/suivant, les deux lignes de
playlist affectées, chapitre courant) à la place de charger une
nouvelle page (`goToMedia()`, `templates/video_player.html`) - le
rendu vient toujours du serveur (`fetch` de la même page `/watch/<id>`
qu'une visite directe, jamais un calcul de progression refait côté
navigateur), seuls les morceaux nécessaires sont replacés.

- **URL et bouton Retour.** `history.pushState` à chaque changement ;
  un `popstate` (Retour/Suivant du navigateur) rejoue la même mise à
  jour de DOM sans repousser d'entrée d'historique.
- **Sauvegarde de la position avant le changement.** La position de la
  vidéo qu'on quitte est écrite (`fetch`, attendu) avant de toucher à
  la source du lecteur - c'est le seul moment où `currentTime` lui
  appartient encore, et ce qui garantit que le rendu de la page
  suivante voit déjà l'état à jour (coche "Terminé" incluse). Cette
  attente est bornée à 1 seconde (`AbortController`) : passé ce délai
  ou en cas d'erreur, la position n'est pas perdue pour autant - un
  `sendBeacon` "tire et oublie" la renvoie, même mécanisme que pour une
  fermeture d'onglet - et le changement de vidéo se poursuit sans
  message à l'écran. **Conséquence de ce repli** : la coche "Terminé"
  de la vidéo qu'on vient de quitter peut alors n'apparaître qu'à la
  navigation suivante, puisque le serveur n'a pas fini d'écrire avant
  le rendu de la page qu'on va chercher.
- **Note inchangée.** Elle appartient à l'item, pas au média : jamais
  touchée par `goToMedia()`, donc une frappe en cours (y compris son
  minuteur de sauvegarde différée) survit à un changement de vidéo.
  Le bouton "Insérer un repère" lit le numéro/titre/id de la vidéo sur
  `player.dataset` (mis à jour à chaque navigation) plutôt que sur des
  valeurs Jinja figées au premier chargement, pour viser la bonne
  vidéo même après plusieurs changements sans rechargement.
- **Playlist.** Seules les deux lignes concernées (l'ancienne, la
  nouvelle) sont remplacées - jamais toute la liste, pour ne pas
  perdre l'état ouvert/fermé des autres chapitres ni la position de
  défilement. Le chapitre qui perd/gagne le statut courant s'ajuste en
  conséquence (l'ancien retombe sur sa préférence mémorisée, comme un
  premier chargement ; le nouveau s'ouvre). Le surlignage de la ligne
  courante passe par une transition CSS (fondu sur fond/bordure/
  couleur, ~0,2s) plutôt qu'un second calcul de défilement. La liste
  ne se repositionne que si la nouvelle ligne courante sort de la zone
  déjà visible, et de façon animée dans ce cas seulement (jamais au
  premier affichage d'une page, qui reste invisible jusqu'à sa
  position finale - voir "Progression visible et liste de lecture"
  ci-dessus).
- **Garde-fou `player.played` inchangé.** Il continue de fonctionner
  sans adaptation : `player.played` se remet naturellement à zéro à
  chaque changement de source, avec ou sans rechargement de page.
- **Fondu entrant sur l'image du lecteur** (~120-150ms, 130ms retenu),
  pour adoucir le changement brutal d'image qu'un rechargement de page
  masquait auparavant. Entrant seulement : l'ancienne image disparaît
  sans transition au moment du changement de source (`opacity: 0` posé
  sans transition, jamais ralenti), la nouvelle apparaît en fondu une
  fois réellement prête (évènement `loadeddata` du lecteur - pas
  `loadedmetadata`, qui ne garantit qu'une durée/dimension connues, pas
  une image affichable). Respecte `prefers-reduced-motion` : première
  utilisation de cette media query dans le projet, la tranche
  accessibilité n'avait couvert ni le contraste ni le focus ni les
  modales que sous cet angle-là, jamais les animations.

`pytest tests/` (187 tests) au vert.

## Méthode — backlog

Avant de commencer une tranche, relire le backlog et signaler les
lignes qui touchent le périmètre de cette tranche. Une ligne concernée
doit être traitée ou explicitement écartée avec sa raison, jamais
ignorée en silence. Ne pas coder quelque chose qui rend une ligne du
backlog plus difficile à corriger sans le signaler d'abord.

## Backlog (ne pas traiter sans demande explicite)

- `fetch_item_author()` (grille) relit et reparse la page de
  présentation de chaque item à chaque chargement de `/`, sans cache
  ni champ stocké. Mesuré : 4,45 ms/item. Extrapolé linéairement (pas
  mesuré à cette échelle) : ≈ 890 ms pour 200 items, ≈ 4,45 s pour
  1000 — inquiétant. À revoir si la bibliothèque grossit, par exemple
  en stockant l'auteur résolu en base au moment du scan/de la
  validation plutôt qu'en le recalculant à chaque requête.
- « Récemment ajoutés » (tri de la grille) trie sur `items.created_at`,
  écrit une seule fois à la première insertion et jamais réécrit par
  un rescan (vérifié dans le SQL d'upsert) — fiable tant que la base
  n'est pas reconstruite depuis zéro. Sur la base de test actuelle,
  les 4 items ont été insérés en une seule passe à 22 ms d'écart : ce
  tri n'y est pas significatif, seulement sur une bibliothèque
  alimentée au fil du temps.
- Depuis la suppression de book_audio, un item contenant un PDF et un
  M4B est un audiobook et prend la pochette du M4B comme couverture ;
  le PDF, devenu ressource, n'est plus source d'image. Cela contredit
  l'ordre de priorité des couvertures acté en spécification, qui place
  la première page du PDF possédé avant la pochette. À trancher
  lorsque cet ordre sera implémenté : soit le PDF-ressource d'un
  audiobook redevient source de couverture, soit la spécification est
  amendée. Aucun item concerné dans la bibliothèque de test ; concerne
  au moins « La programmation neuro-linguistique » dans la vraie
  bibliothèque de Gautier (PDF + M4B + ressources dans le même
  dossier).
- Les fichiers .mp4 des formations portent un tag `title` contenant le
  vrai titre éditorial, avec accents et apostrophes (vérifié : 307/307
  sur Copywriter et Motion Design). Ce titre diffère du nom de fichier
  au-delà de la ponctuation et n'est pas toujours plus complet (ex.
  004, dont le nom de fichier porte un sous-titre absent du tag). À
  prévoir : lecture du tag par le scanner, stockage à côté du nom de
  fichier sans le remplacer, règle de choix du titre affiché, et
  comportement pour les fichiers sans tag. Aucun renommage de fichier.
  Le futur module d'import (voir plus bas) empêche ce décalage de se
  reproduire pour un nouvel import — titre de tag et nom de fichier
  viendraient de la même table validée — mais ne corrige pas
  l'existant : la V1 refuse de réimporter un dossier déjà présent dans
  la bibliothèque, donc les 307 fichiers actuels de Copywriter et
  Motion Design restent concernés par cette ligne tant qu'elle n'est
  pas traitée séparément.
- `extract_hero_fields` retrouve l'auteur par correspondance sur le
  texte du libellé ("Auteur" ou "Formateur(s)"). Un libellé est un
  texte d'affichage, pas un identifiant : renommer `author_label` dans
  `resolve_metadata_fields` ferait disparaître l'auteur du hero
  silencieusement. À remplacer par une clé stable indépendante du
  libellé affiché.
- `accept_book_candidate` et `save_manual_candidate` écrasent
  silencieusement un candidat accepté d'origine manuelle — une saisie
  manuelle ne doit jamais être remplacée par une source automatique
  sans confirmation explicite. Découvert en écrivant la résolution des
  champs de métadonnées (tranche "restructuration visuelle des
  métadonnées") : `resolve_metadata_fields` ne fait que lire le seul
  candidat `accepted` existant, il n'y a rien à arbitrer à son niveau —
  le problème est dans le workflow d'acceptation, pas l'affichage.
- Fichier renommé = nouvel id = progression perdue. Appariement par
  empreinte à prévoir. (Ne concerne plus les notes : elles survivent à
  un renommage de dossier en devenant orphelines et récupérables, voir
  "Bloc-notes" — reste vrai pour la progression de lecture par média.)
- Le compteur « sans durée » du résumé compte aussi les PDF, qui n'en ont
  pas. Affichage à corriger.
- Chapitres internes des M4B (ffprobe -show_chapters), distincts des
  chapitres par sous-dossier.
- Nombre de pages des PDF.
- Couvertures : deux étapes de l'ordre de priorité acté (voir
  « Priorité des couvertures » ci-dessus) restent non implémentées —
  l'import manuel d'image (étape 1) et la couverture Google Books si
  des métadonnées de livre sont validées (étape 5). Le reste de
  l'ordre (image du dossier, première page du PDF, pochette M4B,
  image de vidéo, placeholder) est fait depuis la tranche 3, pour la
  fiche comme pour la grille.
- `describe_cover_source` (studia.py) réimplémente l'ordre de priorité
  de covers.py pour afficher la provenance de la couverture dans les
  informations techniques. Deux endroits à garder synchronisés : toute
  modification de l'ordre dans covers.py doit être répercutée ici,
  sinon le panneau ment sans erreur visible. À supprimer le jour où la
  provenance sera stockée avec la couverture en cache plutôt que
  reconstruite.
- Métadonnées de formations par moissonnage des plateformes commerciales
  (TUTO.com, Udemy, LinkedIn, Elephorm...). Autorisé (usage strictement
  personnel, décision explicite de Gautier), mais pas encore fait : pas
  d'API publique sur ces sites, donc un scraper par plateforme, plus
  fragile qu'un appel d'API (casse si le site change sa page). À
  cadrer dans un plan séparé le moment venu. Pour les livres, voir
  "Métadonnées de livres" ci-dessus (fait). Restent aussi, pour toutes
  les fiches : les faits déjà lisibles par le scanner (durée, chapitres,
  nombre de médias) à afficher en tête de fiche, et une saisie manuelle
  générique pour les contenus de Gautier lui-même.
- Si un moissonnage de plateforme ne trouve rien : donner le nom de
  l'item à Gautier et soit attendre une URL (pour retenter le
  moissonnage dessus), soit proposer la saisie manuelle — même logique
  que "Aucune ne convient" côté livres.
- requirements-dev.txt pour pytest.
- Clé SSH GitHub à la place du token en clair dans ~/.git-credentials.
- Watcher automatique — seulement après un scanner manuel fiable.
- Multi-utilisateur réel, authentification, rôles, HTTPS : V2 — dont
  dépendent aussi favoris, notifications et avatar (retirés des écrans
  en V1, voir "Refonte visuelle").
- Éditeur de notes enrichi (le Markdown s'affiche mis en forme au lieu
  d'être tapé) : V2. Le stockage reste le même Markdown brut, posé dès
  la V1 pour ne rien casser au passage.
- Lecture des documents dans le navigateur. Tout fichier lisible —
  PDF, EPUB, TXT, Markdown — doit s'ouvrir dans un lecteur interne de
  l'application, avec mode plein écran, plutôt que d'être seulement
  téléchargeable. Vaut aussi bien pour un fichier média d'un livre que
  pour une ressource d'une formation : une ressource s'ouvre dans le
  même lecteur qu'un livre, sans changer de contexte. Chaque fichier
  reste par ailleurs téléchargeable. Écarté explicitement : la
  présentation en double page façon catalogue feuilletable, trop
  lourde pour le bénéfice. Les ressources n'ont pas besoin de
  mémoriser une position de lecture (fiches, exemples, compléments) ;
  les livres oui, par page.
- Section « Continuer » (grille de la bibliothèque). Écartée pour
  l'instant : la bibliothèque de test n'a que quatre items dont deux
  formations, l'écran ferait doublon avec la grille et son résultat ne
  serait pas jugeable dans ces conditions. À faire une fois la vraie
  bibliothèque de Gautier chargée.

Cinq chantiers cadrés avec Gautier pour la suite, dans cet ordre
(chacun est le prérequis du suivant) :

- **Studia en conteneur, avec dossiers configurables.** Aujourd'hui
  les chemins de bibliothèque et de base sont locaux et figés. Cible :
  Studia servi par Docker, avec deux emplacements distincts définis
  par un administrateur depuis une page d'administration — le dossier
  de dépôt (où arrivent les contenus à importer) et le dossier de
  bibliothèque (propre et figé). Ils doivent être montés dans le
  conteneur, et l'un ne doit jamais être l'autre ni un de ses
  sous-dossiers : une règle de validation doit le refuser, sinon le
  scanner indexerait des contenus en cours de préparation. Prérequis
  de tout le reste : tant que Studia ne sait pas où est sa
  bibliothèque, l'import n'a nulle part où écrire.

- **Module d'import, version 1.** Transforme un contenu de source
  inconnue (téléchargement, production personnelle) en item propre
  dans la bibliothèque. Adapté du mode opératoire manuel documenté
  dans Notion (« Préparer une formation pour OfflineU », 53 formations
  traitées), à transposer à Studia : ce qui était produit pour
  OfflineU en HTML devient du JSON écrit directement, et les
  métadonnées de livres ne viennent plus de Calibre mais de Google
  Books et des sources déjà en place.

  Deux voies d'entrée, un seul pipeline derrière :
  - priorité au dossier de dépôt sur le serveur — les fichiers y sont
    copiés par partage réseau, aucun transfert par le navigateur ;
  - depuis le poste de l'utilisateur, par le sélecteur de dossier du
    navigateur, avec envoi par morceaux permettant de reprendre après
    une coupure (sans quoi une interruption sur 10 Go recommence
    tout).

  Le pipeline reprend les six points de contrôle du mode opératoire,
  qui sont sa vraie valeur — ce sont eux qui ont détecté un
  téléchargement incomplet, un décalage de numérotation qui aurait
  faussé onze titres, et une troncature de 96 secondes invisible
  autrement :
  1. nombre de leçons annoncées = nombre de fichiers ;
  2. durée mesurée de chaque position = durée du sommaire (tolérance
     1 seconde) — seul moyen de détecter un décalage de numérotation ;
  3. nombre de copies produites ;
  4. aucune apostrophe dans les noms produits ;
  5. durée totale source = durée totale destination ;
  6. affichage correct dans Studia.

  La table de correspondance position → titre est le seul endroit qui
  demande un humain : le module la propose à partir des sources
  disponibles (fichier texte, README, HTML, noms de fichiers déjà
  propres, saisie manuelle), l'utilisateur la corrige, le contrôle des
  durées la valide. L'import n'est jamais silencieux : il présente un
  plan avant d'agir.

  Deux modes de métadonnées : production personnelle (formulaire
  saisi par l'utilisateur, avec propositions automatiques quand c'est
  possible) ou plateforme (extraction depuis un fichier texte,
  markdown ou HTML fourni, ou saisie de l'identifiant et du lien vers
  la fiche en ligne).

  Renommage et écriture des tags autorisés : c'est le rôle même de
  l'import. L'interdit n°3 (ne jamais modifier ni renommer les
  fichiers médias) protège la bibliothèque, pas la zone de dépôt — à
  préciser dans cet interdit quand ce module arrivera.

  Numérotation : suite continue (001 à 0NN, sous-dossiers de chapitre
  en 0100, 0200…), pas de trous réservés, ressources en 900. Décision
  prise après examen d'un schéma type CH01V10 : l'adresse
  chapitre/position existe déjà en base via parent_path et sort_order,
  la recopier dans les noms de fichiers n'apporterait rien et les
  rendrait moins lisibles.

  Version 1 volontairement fermée : un dossier inconnu devient un
  nouvel item ; un dossier déjà présent dans la bibliothèque est
  refusé avec explication. Aucune fusion, aucun écrasement, aucune
  mise à jour — c'est le module suivant (voir plus bas). Après import
  réussi et contrôles passés, la source est déplacée dans un
  sous-dossier « traités » du dossier de dépôt, jamais supprimée
  automatiquement.

  L'accès à l'import sera réservé à un administrateur quand les
  comptes existeront (V2, voir plus bas). D'ici là, un seul
  utilisateur : ne pas construire d'authentification pour ce module,
  mais faire passer son accès par un point unique qu'on branchera sur
  les rôles le moment venu.

- **Manifeste JSON par item.** Fichier de métadonnées écrit par
  l'import dans le dossier de l'item, lisible par machine, remplaçant
  le HTML produit pour OfflineU. Il préserve la règle fondatrice : la
  base reste un index reconstructible. Sans lui, auteur, année,
  plateforme, description et avertissements n'existeraient plus qu'en
  base et disparaîtraient à sa reconstruction.

  Contenu, de deux natures distinctes :
  - ce qui n'existe nulle part ailleurs : auteur, année, plateforme et
    identifiant externe, description, avertissement (contenu daté,
    leçons périmées), raison de conservation ;
  - un état de référence à l'import, pour chaque fichier : chemin,
    taille, durée, titre du tag, plus les totaux.

  Le second n'est pas un doublon des faits mesurables, à une condition
  stricte : ces valeurs ne s'affichent jamais. La mesure fait toujours
  foi à l'écran — c'est la leçon de « 5h33 (mesurée) » contre la durée
  réelle, deux chiffres du même fait montrés côte à côte. Le manifeste
  ne sert qu'à comparer et à signaler une divergence.

  Il doit être écrit complet dès le premier import, même si rien ne le
  relit encore : écrit au rabais, il obligerait à tout réimporter le
  jour où la mise à jour arrivera.

  Si un item importé n'a pas de manifeste, l'import en crée un.

- **Fonction de consolidation, page d'administration.** Compare le
  manifeste de chaque item au contenu réel du disque et rapporte les
  divergences :
  - fichier du manifeste absent du disque → fichier perdu ;
  - durée plus courte que celle notée → troncature ;
  - taille différente à durée identique → fichier remplacé ou
    réencodé ;
  - fichier présent sur le disque et absent du manifeste → ajout hors
    import, signalé en rouge avec une action pour l'intégrer au
    manifeste ;
  - taille et durée identiques sous un autre nom → fichier renommé.

  Ce dernier cas règle la ligne de backlog « fichier renommé = nouvel
  id = progression perdue » ci-dessus : taille plus durée constituent
  une empreinte suffisante, aucun hash nécessaire. C'est la seule
  réparation automatique autorisée, parce qu'elle est sûre — le
  rattachement préserve la progression. Tout le reste est rapporté,
  jamais réparé : un fichier manquant peut avoir été supprimé
  volontairement, une durée plus courte peut venir d'un réencodage
  voulu.

  Elle distingue « invérifiable » (item sans manifeste) de
  « conforme » — deux états différents, pas un seul.

  Elle tourne à la demande, jamais à chaque scan : sonder 300 fichiers
  par ffprobe est trop coûteux pour une taxe au démarrage.

- **Module de mise à jour d'un item importé.** Beaucoup plus tard,
  après l'import v1. Permet de compléter ou corriger un item existant
  sans le réimporter en entier : ajouter des chapitres à la suite (les
  13, 14 et 15 après le 12), ou remplacer un chapitre existant par une
  version retravaillée, y compris avec un nombre de vidéos différent
  (les fichiers en trop sont à supprimer, ceux en plus se posent à la
  suite dans le chapitre). Ajout de ressources ou de bonus également.

  Le manifeste est le pivot : c'est lui qui dit ce que contient déjà
  l'item, ce qui permet de classer chaque fichier entrant en nouveau,
  identique, modifié ou disparu.

  Contraintes à respecter :
  - la numérotation existante est préservée, jamais recalculée
    globalement — un renumérotage changerait les chemins, donc les
    ids, donc la progression ;
  - remplacer un fichier au même emplacement préserve son id et sa
    ligne progress. Reste à trancher à ce moment-là si une progression
    enregistrée sur une version remplacée garde du sens ;
  - pas d'insertion entre deux positions existantes : on remplace en
    place ou on ajoute à la suite, jamais de 3,5.

  Distingue trois cas à l'entrée : même nom et contenu identique → rien
  à faire ; même nom, contenu différent → proposer une fusion en
  montrant précisément ce qui change ; nom inconnu → nouvel item.

## Méthode de travail

- Petits commits cohérents et testables, messages en anglais.
- pytest tests/ doit passer avant chaque commit.
- git push après chaque commit : c'est la seule sauvegarde du projet.
- Les médias ne sont jamais touchés, la base de données est un index
  reconstructible.
