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
7. Quand une bibliothèque tierce fournit un fichier (CSS, JavaScript, ou
   autre chose qu'elle livre), on l'utilise tel quel. On ne réécrit pas
   une version partielle « du minimum nécessaire » - décidé après le
   bug de sélection de texte du lecteur PDF (voir "Lecteur PDF"),
   coûteux en plusieurs séances : la feuille de style de PDF.js
   réécrite à la main avait oublié des règles dont l'absence ne se
   voyait sur aucun rendu de test, seulement sur une mesure précise et
   un PDF particulier. Si une partie du fichier fourni doit
   explicitement être écartée (une fonctionnalité entière que Studia
   n'utilise pas, par exemple), la raison est écrite en commentaire à
   côté de ce qui est repris, et ce qui est écarté est vérifié comme
   réellement inutilisé dans notre propre code - jamais supposé.

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

Tables SQLite, schéma version 9 :
schema_info, users, items, media, resources, progress, book_search,
book_candidates, notes, media_chapters, preferences.

    media       item_id, relative_path, parent_path, sort_order,
                media_type, extension, size_bytes,
                duration_seconds, probed_at, chapters_probed_at,
                page_count, created_at
                UNIQUE(item_id, relative_path)
    resources   mêmes colonnes sans durée
    progress    UNIQUE(user_id, media_id) — jamais media_id seul.
                position_seconds (vidéo/audio) et page_number (livre)
                cohabitent dans la même table, chacun NULL pour l'autre
                type — voir "Lecteur PDF" plus bas.

    media_chapters   media_id, chapter_index (brut ffprobe, jamais
                     renuméroté), title (NULL si absent du fichier),
                     start_seconds, end_seconds
                     UNIQUE(media_id, chapter_index)
                     FOREIGN KEY(media_id) ON DELETE CASCADE
                     — voir "Chapitres internes des M4B" plus bas

    preferences   user_id (clé), reading_mode ('scroll'|'paginated'),
                  reading_zoom (multiplicateur, NULL = zoom par
                  défaut), reading_text_scale (multiplicateur, NULL =
                  taille par défaut — lecteur EPUB),
                  epub_reading_mode ('scroll'|'chapter'),
                  note_panel_left/top/width/height (position/taille du
                  panneau de notes flottant) — réglages des lecteurs
                  PDF et EPUB, un seul par utilisateur, jamais par
                  livre. Voir "Lecteur PDF" et "Lecteur EPUB" plus bas.

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
    /read/<media_id>        lecteur PDF : défilement continu ou page par
                            page, zoom, reprise en pages, panneau de
                            notes flottant ; ?p=<page> ouvre directement
                            à cette page (repère, l'emporte sur la
                            reprise, n'écrase pas la position tant que
                            rien n'est relu depuis là)
    /read-epub/<media_id>   lecteur EPUB : défilement continu par
                            chapitre, table des matières, taille de
                            texte, reprise en chapitres, panneau de
                            notes flottant (repris du lecteur PDF) ;
                            ?c=<chapitre> ouvre directement ce chapitre
                            (repère, mêmes règles que ?p= pour le PDF) ;
                            EPUB3 sans NCX -> message de format illisible
    /media/<media_id>/epub-chapter/<n>      HTML assaini d'un chapitre
                                             EPUB, rendu dans l'iframe
                                             sandboxée du lecteur
    /media/<media_id>/epub-asset/<chemin>   sert un actif interne d'un
                                             EPUB (image, police, CSS
                                             réassaini) ; refuse ".."
    /media/<media_id>/file  sert le fichier vidéo, audio ou PDF/EPUB
                            (Range HTTP géré par Flask, permet
                            d'avancer/reculer)

    POST /media/<media_id>/progress   enregistre la position de lecture
                                       (position_seconds vidéo/audio,
                                       page_number pour un livre PDF ou
                                       chapitre courant pour un EPUB)
    POST /preferences                 enregistre le mode de lecture, le
                                       zoom, la taille de texte EPUB
                                       (reading_text_scale) et/ou la
                                       position/taille du panneau de
                                       notes flottant (réglages de
                                       l'application, pas d'un livre)

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

Un seul champ texte par item, édité et affiché dans le même panneau
flottant partagé (`templates/_note_panel.html`, `_note_widget.html`)
depuis la fiche de l'item et depuis chacun des quatre lecteurs - un
bouton "Notes" l'ouvre à chaque endroit, jamais une variante par
écran. Modifier la note à un endroit la met à jour partout ailleurs au
prochain chargement de page, puisque c'est la même donnée et le même
composant (détail des lecteurs : "Panneau de notes flottant : lecteur
vidéo" ; détail de la fiche : "Notes sur la fiche d'item", plus bas).

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
les métadonnées de livre validées), suivi des onglets À propos /
Programme / Ressources (bascule en JS pur, `data-tab-target` /
`data-panel`, pas de bibliothèque) — un quatrième, Notes, conditionnel,
s'y ajoute depuis (voir "Notes sur la fiche d'item" plus bas).

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
ci-dessous), PDF (fait, voir "Lecteur PDF" plus bas), EPUB (fait, voir
"Lecteur EPUB" plus bas). La progression vient juste après la vidéo
parce qu'elle ne se pose qu'une fois et sert ensuite à tous les
lecteurs suivants, plutôt que d'être refaite à chacun.

Progression selon le type : secondes pour vidéo et audio, page pour un
livre PDF (fait), chapitre pour un livre EPUB (fait) — voir "Les trois
règles du « terminé », côte à côte" plus haut.

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
  quels sous ce plafond pour une vidéo courte. **Cette règle est
  propre aux médias temporels (vidéo, audio)** : un livre a sa propre
  règle, différente et volontairement sans marge — voir
  `is_book_completed` dans "Lecteur PDF" plus bas.

  **Les trois règles du « terminé », côte à côte.** Le projet a trois
  unités de progression différentes, une par famille de média, et
  chacune a sa propre définition de « terminé » — volontairement, pas
  par oubli :
  1. **Temps** (vidéo, audio) — `is_video_completed` : à moins de 5 %
     de la durée totale, plafonné à 15 secondes. Une position, pas un
     compteur discret : une marge a du sens parce qu'on ne s'arrête
     jamais pile sur la dernière milliseconde.
  2. **Pages** (livre PDF) — `is_book_completed` : dernière page
     atteinte, sans aucune marge. Une page est une unité discrète et
     déjà coordonnée dans le document ; il n'y a pas de raison de
     tolérer un écart.
  3. **Chapitres** (livre EPUB) — même fonction `is_book_completed`,
     réutilisée telle quelle : un EPUB n'a pas de pages fixes (le
     texte se recompose selon la fenêtre et la taille du texte), donc
     `media.page_count` et `progress.page_number` sont réinterprétés
     comme « nombre de chapitres » et « index du chapitre courant ».
     Dernier chapitre atteint = terminé, sans marge, même principe que
     la page pour un PDF. Voir "Lecteur EPUB" plus bas.

  Ces trois règles cohabitent délibérément dans le projet, chacune
  adaptée à son unité ; une future tranche sur un nouveau type de
  média ne doit pas en réinventer une quatrième sans y réfléchir
  d'abord.
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

### Hauteur et position des colonnes latérales (fait)

**`position: sticky` (ci-dessus) était le mauvais mécanisme**, trouvé
par Gautier sur Motion Design (258 vidéos, 27 chapitres) et sur "La
boîte à outils" (88 chapitres, table des matières EPUB - même colonne,
même bug). Un ancrage collant garde la colonne visible à l'écran
pendant qu'on fait défiler la page - or c'est l'inverse qui est voulu :
en descendant vers les notes, le haut de la colonne doit sortir de
l'écran exactement comme le haut de la vidéo/du cadre de lecture, elle
n'a pas vocation à rester affichée plus longtemps qu'eux. Second défaut
constaté séparément : la colonne démarre au niveau du fil d'Ariane (le
haut de `.layout`), pas au niveau de la vidéo/du cadre - `.main` a un
fil d'Ariane et un titre au-dessus de son contenu, pas la colonne.

Règle commune à la playlist vidéo (`.playlist`, `video_player.html`) et
à la table des matières EPUB (`#playlist`, `epub_reader.html`) -
strictement la même dans les deux templates :
- **Position** : la colonne est un élément de page normal (plus de
  `position: sticky` ni de `top`), qui défile avec la page comme
  n'importe quel autre élément - jamais collée à l'écran.
- **Alignement du sommet** sur celui de la vidéo/du cadre de lecture,
  via un `margin-top` calculé en JS (`videoDocTop - playlistDocTop`,
  mesurés en coordonnées de document - `rect.top + window.scrollY` -
  pour rester valables quelle que soit la position de défilement au
  moment du calcul) : une valeur purement CSS ne peut pas connaître la
  hauteur du fil d'Ariane/titre au-dessus, qui varie avec le texte.
- **Hauteur** calculée pour que le bas de la colonne arrive
  `PLAYLIST_BOTTOM_MARGIN` (20px) avant le bas de la fenêtre visible
  **quand la page est en haut** - jamais la hauteur du contenu ni celle
  de la colonne de gauche. Calculée une fois au chargement (et sur
  `resize` de la fenêtre), jamais en fonction du défilement courant :
  recalculer pendant qu'on défile donnerait une hauteur qui rétrécit à
  mesure qu'on descend, ce qui n'est pas ce qui est demandé.
- `overflow-y: auto` inchangé : la colonne continue de défiler en
  interne pour ses propres 258 vidéos ou 88 chapitres, sans jamais
  dépasser la hauteur qui lui est allouée - un défilement de page (la
  colonne qui défile avec `.main`) et un défilement interne (sa propre
  liste, plus longue que la hauteur allouée) sont deux choses
  différentes qui cohabitent normalement ; le double défilement à
  éviter était celui, différent, de l'iframe EPUB dans
  `#reader-viewport` (voir "Lecteur EPUB").

Palier smartphone (`<720px`, colonne sous la vidéo/le lecteur, pleine
largeur) non concerné : sa propre règle CSS (`position: static;
max-height: 40vh`) reste inchangée, le calcul JS se désactive lui-même
sous ce seuil.

Vérifié dans le navigateur, page en haut puis défilée jusqu'aux notes,
sans double barre de défilement imbriquée : Motion Design (258 vidéos,
27 chapitres) et "La boîte à outils" (88 chapitres).

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

### Chapitres internes des M4B (fait)

Rend un audiobook navigable par chapitre au lieu d'un seul bloc continu
(voir `media_chapters`, "Modèle de données" ci-dessus). Décision de
données actée avec Gautier : les chapitres sont lus par ffprobe
`-show_chapters` au moment du scan, au même titre que la durée — la
valeur mesurée fait toujours foi, jamais une entrée fabriquée. Un
fichier sans chapitre ne produit aucune ligne dans `media_chapters`,
jamais une entrée unique couvrant tout le fichier.

- **Sondage (`library_index.py`).** `chapters_probed_at` (colonne sur
  `media`, comme `probed_at` pour la durée) dit si les chapitres d'un
  fichier ont déjà été examinés — `NULL` = jamais examiné, une date =
  examiné, qu'il y ait 0 ou N chapitres ensuite. Sans cette colonne,
  "aucune ligne dans `media_chapters`" aurait été ambigu : impossible
  de distinguer "jamais regardé" de "regardé, rien trouvé", et chaque
  `--probe` aurait resondé indéfiniment tout fichier sans chapitre.
  `probe_missing_media_info()` (ex-`probe_missing_durations`,
  renommée puisqu'elle fait maintenant les deux) sélectionne tout
  média où `duration_seconds IS NULL OR chapters_probed_at IS NULL`,
  **sans filtre de type** : une vidéo peut porter des chapitres au
  même titre qu'un audio, et la colonne doit dire ce qui a été
  examiné, pas ce qui est affiché aujourd'hui — seul `/listen` montre
  une colonne de chapitres pour l'instant (voir plus bas), le lecteur
  vidéo n'affiche rien de nouveau même si des lignes existent pour lui.
  Chaque fichier sélectionné ne refait que ce qui lui manque
  réellement (durée seule, chapitres seuls, ou les deux) : une
  bibliothèque déjà entièrement sondée pour la durée n'a besoin que
  d'un seul `--probe` pour recevoir ses chapitres, pas d'un
  `--reprobe` complet. `--reprobe` remet les trois colonnes à NULL
  (`duration_seconds`, `probed_at`, `chapters_probed_at`).
- **Invalidation.** Re-sondage d'un média = ses lignes `media_chapters`
  effacées puis réinsérées, jamais fusionnées — pas de colonne de
  fraîcheur séparée pour ça, le même signal (`chapters_probed_at`)
  sert à décider *quand* resonder. Quand la taille du fichier change
  (upsert du scan), `chapters_probed_at` repasse à NULL comme
  `duration_seconds`/`probed_at`, et les lignes déjà stockées sont
  effacées tout de suite plutôt que de rester affichées, fausses,
  jusqu'au prochain `--probe` — même logique que la durée, qui
  redevient NULL immédiatement plutôt que de garder une valeur
  périmée à l'écran.
- **Numéro affiché ≠ index stocké.** `chapter_index` garde la valeur
  brute ffprobe (`id`) en base, pour traçabilité, mais n'est jamais
  montré tel quel : le numéro affiché (1, 2, 3…) est la position dans
  la liste triée par `start_seconds` (`fetch_media_chapters`,
  studia.py), puisque l'id ffprobe n'a aucune raison d'être stable ou
  de commencer à 1.
- **Titre jamais reformaté.** Stocké exactement comme `tags.title` le
  donne ; `NULL` si le fichier n'en fournit pas. Aucun repli fabriqué
  (pas de "Chapitre N") : un chapitre sans titre affiche son numéro et
  sa durée, rien à la place du titre — un repli inventerait une
  information qui n'existe pas dans le fichier.
- **Affichage (`/listen`, `audio_player.html`), seulement si la liste
  n'est pas vide.** Reprend le composant `.playlist`/`.file-row` de la
  playlist vidéo tel quel (numéro à gauche, titre en gras, durée en
  dessous, ancrage collant borné à la fenêtre visible, centrage du
  chapitre courant au chargement) plutôt que d'écrire un second
  mécanisme de défilement — seule différence structurelle : chaque
  ligne est un `<button>` (un clic déplace la lecture, il ne change
  jamais de page) et non un `<a>`, et le titre est limité à deux
  lignes avec troncature (`-webkit-line-clamp`, `.chapter-row
  .file-title`), une vraie limite ici plutôt qu'une longueur habituelle
  comme sur la playlist vidéo. Pas de coche : un chapitre n'a pas
  d'état "terminé" propre, la progression reste une position unique
  sur le fichier entier (inchangée, voir ci-dessous). Le surlignage du
  chapitre courant se met à jour sur `timeupdate` (comparaison directe
  des `start`/`end` en JavaScript, aucune écriture serveur), et suit la
  même initialisation "invisible jusqu'à positionné" que la playlist
  vidéo pour ne montrer aucun mouvement au chargement.
- **Hors périmètre, explicitement.** Ni le seuil du "terminé", ni la
  règle de reprise, ni le calcul du pourcentage de la carte n'ont
  changé — la progression d'un audiobook reste une position unique sur
  le fichier entier, un chapitre n'ajoute aucun état propre. Le lecteur
  vidéo n'affiche aucune colonne de chapitres, même pour un fichier qui
  en a désormais en base : tranche à part, pas encore faite.

Vérifié avec le vrai audiobook de la bibliothèque de test (16
chapitres réels, `--probe`) : liste affichée, surlignage qui suit la
lecture, clic qui déplace la position. Testé en pytest : sélection du
sondage (durée seule/chapitres seuls/les deux, sans filtre de type),
invalidation à la taille, non-invention de titre, absence de colonne
sans chapitre, absence de toute colonne sur `/watch`.

`pytest tests/` (199 tests) au vert.

### Lecteur PDF (fait)

Rend un livre PDF lisible dans l'application (`/read/<media_id>`),
sur le modèle de `/watch` et `/listen`. Décision de données actée
avec Gautier : la progression d'un livre se mesure en pages, jamais
en pourcentage de temps — voir "Seuil du « terminé »" ci-dessus pour
la cohabitation des deux règles.

- **PDF.js, vendu localement.** `static/vendor/pdfjs/` (`pdf.mjs`,
  `pdf.worker.mjs`, `cmaps/`, `standard_fonts/`, `LICENSE`) — version
  **6.3.289**, ~5,4 Mo, 188 fichiers. Jamais un CDN : Studia est une
  application hors ligne, une dépendance réseau la casserait.
  `workerSrc` pointe vers le chemin local servi par Flask
  (`static/vendor/pdfjs/pdf.worker.mjs`), et `getDocument()` reçoit
  `cMapUrl`/`standardFontDataUrl` vers `cmaps/`/`standard_fonts/` du
  même dossier — sans ça, un PDF en écriture non latine s'afficherait
  en blocs vides (glyphes absents), et un PDF qui n'intègre pas ses
  polices (cas très courant) se rendrait avec des substitutions
  approximatives. Deux défauts invisibles sur le livre de test, visibles
  sur une vraie bibliothèque - d'où l'exigence de les inclure dès le
  départ plutôt que de les découvrir plus tard. Seuls `build/pdf.mjs`,
  `build/pdf.worker.mjs`, `web/cmaps/` et `web/standard_fonts/` du zip
  de distribution officiel sont repris : ni le visualiseur prêt à
  l'emploi de Mozilla (`web/viewer.*`, non utilisé — Studia a son
  propre gabarit), ni les fichiers `.map` (cartes source de débogage
  du projet PDF.js lui-même, aucun usage ici).
- **Progression : `progress.page_number`**, colonne présente depuis le
  schéma d'origine mais jamais utilisée jusqu'ici. `position_seconds`
  reste NULL pour un livre, `page_number` NULL pour une vidéo/un
  audio — les deux cohabitent dans la même table sans opposition.
- **`media.page_count`**, sondée par `pdfinfo` (poppler-utils, déjà
  utilisé par `covers.py` pour les couvertures — aucune nouvelle
  dépendance), dans la même passe que la durée et les chapitres
  (`probe_missing_media_info`) mais restreinte à `media_type =
  'book'` : contrairement aux chapitres (voir plus haut), compter les
  pages d'une vidéo ou d'un audio n'a aucun sens et `pdfinfo`
  échouerait systématiquement — inutile de resonder en vain tout le
  reste de la bibliothèque à chaque `--probe`. Invalidée (NULL) au
  changement de taille du fichier, comme `duration_seconds`.
  `--reprobe` remet les trois colonnes sondées à NULL d'un coup
  (`reset_probed_media`, fonction partagée avec le CLI et les tests -
  jamais une copie du SQL).
- **Sans `page_count` connu (pdfinfo en échec, livre pas encore sondé,
  ou format non-PDF).** Décidé avec Gautier : le livre s'ouvre et se
  lit normalement (la page couante continue de s'enregistrer), mais la
  fiche et la carte n'affichent ni barre ni texte de progression, et le
  livre ne peut jamais être « terminé » — jamais un pourcentage
  calculé sur une valeur absente, jamais un message d'erreur.
  `fetch_item_media_progress` renvoie alors exactement le même résultat
  que « jamais ouvert » (`{"status": "not_started", "percent": 0}`),
  qu'il y ait ou non une page enregistrée : la fiche ne fait ainsi
  aucune distinction particulière, les gabarits existants (`{% if
  progress_status != 'not_started' %}`) suffisent sans modification.
- **Seul le PDF est lisible.** Un item de type « book » peut contenir
  n'importe quelle extension de `BOOK_EXTENSIONS` (EPUB, MOBI, CBZ…),
  pas seulement du PDF — `is_readable_book_media`
  (`media_type != 'book' or extension == '.pdf'`) restreint
  `fetch_playable_media`, le calcul du bouton hero et la playlist du
  Programme à ce seul format ; un livre dans un autre format continue
  d'afficher « Ce format ne peut pas encore être lu dans
  l'application. », inchangé.
- **Le hero d'un livre PDF reçoit son bouton principal**
  (Commencer/Continuer/Revoir, endpoint `read_book`) et « Tout
  recommencer », exactement comme les autres types, sans toucher aux
  gabarits : les blocs `{% if progress_status != 'not_started' %}` /
  `{% if first_playable_media_id %}` du hero ne contenaient déjà aucune
  exclusion propre au livre, c'était l'absence de média suivi
  (`TRACKED_PROGRESS_MEDIA_TYPE`) qui neutralisait ces blocs jusqu'ici
  — les y ajouter suffit. La ligne de résumé : `"42 % · page 128 sur
  305"` — la page courante, pas un décompte de pages lues comme pour
  une formation.
- **Préférences de lecture (mode, zoom), table `preferences`.** Un
  seul réglage pour toute l'application, jamais par livre (décidé avec
  Gautier). Rien n'existait déjà pour ce genre de réglage (pas de
  session Flask, pas de cookie, pas de table settings) — vérifié avant
  de créer celle-ci plutôt qu'un second mécanisme. Une ligne par
  utilisateur (`user_id` clé), sur le même principe que `progress` :
  prête sans effort pour le multi-utilisateur du backlog. Lue côté
  serveur au rendu de `/read` (jamais de flash du mauvais mode/zoom au
  chargement). `reading_zoom` est un multiplicateur appliqué par-dessus
  le calcul automatique de taille, jamais une largeur en pixels figée
  qui serait fausse sur un autre écran ou un autre livre. Écriture
  différée côté navigateur pour le zoom (anti-rebond ~900ms, même
  principe que la sauvegarde différée des notes) : sans ça, chaque cran
  de la molette écrirait une ligne. Le changement de mode, lui, s'écrit
  immédiatement (un clic, pas une rafale).
- **Affichage.** Défilement continu par défaut : les pages
  s'enchaînent verticalement, rendues progressivement (un
  `IntersectionObserver` déclenche le rendu réel d'une page en
  approchant de l'écran, avec une marge de préchargement) plutôt que
  les 500+ pages d'un gros livre d'un coup. Taille par défaut : la
  largeur disponible sans jamais dépasser la hauteur de l'écran (repris
  du comportement par défaut de Chrome pour un PDF), calculée une fois
  sur la première page — l'immense majorité des PDF gardent la même
  taille de page tout du long. Bascule vers le mode page par page :
  une page à l'écran, navigation par flèches à l'écran et au clavier
  (uniquement dans ce mode — en défilement continu les flèches n'ont
  pas de sens propre au-delà du défilement natif). Numéro de page et
  total toujours visibles, champ pour aller directement à une page.
  Reprise : la page enregistrée en défilement continu est la page la
  plus visible à l'écran, déterminée par un second
  `IntersectionObserver` (comparaison des ratios d'intersection) —
  même mécanisme d'enregistrement (intervalle 30s + fermeture
  d'onglet) que les lecteurs vidéo/audio. Un livre terminé repart de
  la première page à la réouverture, comme un média temporel terminé
  repart du début (`resolve_resume_page`, même principe que
  `resolve_resume_seconds`).
- **Hauteur bornée à la hauteur visible, défilement interne à
  `#reader-viewport`** — même mécanisme que `.playlist` du lecteur
  vidéo (voir "Progression visible et liste de lecture" plus haut),
  jamais un second : sans lui, les 500+ pages d'un livre faisaient
  défiler la page entière, emportant avec elles la sidebar, le fil
  d'Ariane, le titre et la barre d'outils, qui disparaissaient dès
  qu'on descendait dans le livre. Contrairement à `.playlist` (calc()
  CSS fixe, rien d'autre au-dessus d'elle dans sa colonne), la hauteur
  disponible est calculée en JS (`computeAvailableHeight`,
  `applyViewportBounds`) : le titre et la barre d'outils au-dessus ont
  une hauteur variable (un ou deux mots, barre qui peut passer à la
  ligne). **Point de vigilance corrigé au passage** : les deux
  `IntersectionObserver` (rendu progressif, page la plus visible pour
  la reprise) doivent avoir `root: #reader-viewport`, jamais `root:
  null` (la fenêtre) - sans ce `root` explicite, aucune page ne se
  rendrait ni ne s'enregistrerait plus, puisque la fenêtre elle-même
  ne défile plus du tout.
  **Deuxième bug trouvé en vérifiant cette correction** : un
  changement de zoom ou de mode vide puis reconstruit `#reader-pages`
  (`renderScrollAround`), ce qui remet transitoirement le défilement du
  conteneur à 0 avant que `scrollIntoView` ne le replace - si
  l'observateur de visibilité se déclenchait pendant cette fenêtre, il
  enregistrait à tort la page 1 comme "la plus visible" et écrasait la
  vraie position (constaté : la position enregistrée dérivait vers 1 à
  chaque zoom). `suppressVisibilityBriefly()` suspend cet observateur
  le temps du repositionnement ; une navigation explicite (`goToPage`,
  `renderScrollAround`) enregistre désormais elle-même la page visée,
  immédiatement, sans attendre l'observateur - qui ne sert plus qu'à
  suivre un défilement naturel (molette, barre de défilement).
- **Séparation entre les pages en défilement continu**, dans l'esprit
  des lecteurs PDF courants (Chrome, Adobe) : fond neutre
  (`--color-border`) et espace (`gap`) autour et entre les pages,
  chacune se détachant de ce fond par une ombre légère
  (`.reader-page`) - jamais une ligne dessinée, jamais un numéro de
  page flottant par-dessus. Le mode page par page réutilise le même
  conteneur (donc le même fond), mais une seule page y est présente à
  la fois : rien à séparer.
  **Troisième bug trouvé en vérifiant cette correction** : le `gap`
  était posé sur `.reader-viewport`, mais les `.reader-page` sont des
  enfants de `#reader-pages` (le conteneur intermédiaire créé en JS),
  pas de `.reader-viewport` directement - celui-ci n'a qu'un seul
  enfant flex (`#reader-pages` lui-même), donc le `gap` n'avait aucun
  effet visible entre les pages, qui restaient soudées les unes aux
  autres malgré le fond et l'ombre corrects. Corrigé en déplaçant
  `display: flex; flex-direction: column; align-items: center; gap:
  var(--space-20)` (20px, l'espace demandé) sur `#reader-pages` ;
  `.reader-viewport` ne garde que le fond, le padding et le
  défilement interne.
- **Repositionnement en haut de page en mode page par page.** Un
  changement de page (Suivant/Précédent, flèches clavier, champ de
  numéro de page - tous passent par `renderPaginated`) doit toujours
  afficher la nouvelle page depuis son sommet, jamais depuis l'ancienne
  position de défilement de la page précédente (sensible surtout à un
  zoom qui rend la page plus haute que l'écran). `renderPaginated`
  remet `viewport.scrollTop = 0`, une fois immédiatement et une
  seconde fois une fois le rendu terminé (la hauteur réelle du canevas
  n'est connue qu'à ce moment-là). Sans effet sur le suivi de
  visibilité ou l'enregistrement de la position : `renderPaginated`
  déconnecte déjà les deux `IntersectionObserver` avant ce reset, donc
  ce repositionnement ne peut pas être interprété comme un changement
  de page à enregistrer - le mode défilement continu (`goToPage`,
  `renderScrollAround`, `suppressVisibilityBriefly`) n'est pas touché.
- **Hors périmètre, explicitement, pour cette tranche.** Le lecteur
  EPUB, la recherche dans le texte, le sommaire interne du PDF. Les
  notes et les repères de page ont leur propre tranche, voir plus bas.
- **Bug trouvé après coup par Gautier : sélection de texte décalée à
  fort zoom (280 % et au-delà).** `.reader-page` et son canevas avaient
  `max-width: 100%` : dès que la page zoomée dépassait la largeur du
  cadre de lecture, le navigateur la réduisait visuellement pour
  qu'elle y tienne. La couche de texte suivait cette même réduction
  pour sa propre boîte, mais PDF.js positionne chaque mot à l'intérieur
  d'après `--total-scale-factor` (le zoom réel, non réduit) - les mots
  se retrouvaient donc placés comme si la page faisait sa taille
  normale, alors qu'elle était affichée plus petite. Confirmé par
  mesure : à 280 %, une page voulue à 1423 px de large était réduite à
  1213 px par le CSS, désynchronisant la couche de texte du rendu
  visible. Invisible à 100/170 % : la page zoomée tenait encore dans le
  cadre, `max-width: 100%` ne faisait donc rien.
  Corrigé en choisissant le débordement plutôt que la réduction, comme
  n'importe quel lecteur PDF : `max-width: 100%` retiré de `.reader-page`
  et de son canevas, `.reader-viewport` défile désormais aussi
  horizontalement (`overflow-x: auto`) quand la page dépasse. Le zoom
  maximal (400 %) n'a pas été abaissé pour éviter le problème : agrandir
  un schéma dense est justement la raison de zoomer aussi fort.
  **Second bug trouvé en corrigeant celui-ci** : `#reader-pages` centre
  ses pages (`align-items: center`), et un centrage simple rend une
  partie d'une page qui déborde purement et simplement inatteignable au
  défilement - ni tout à gauche ni tout à droite du défilement
  horizontal ne montraient le bord gauche de la page, une bande d'une
  centaine de pixels restant coupée dans les deux cas. Corrigé avec le
  mot-clé CSS `safe` (`align-items: safe center`) : bascule sur un
  alignement au début dès que le centrage perdrait du contenu, sans
  rien changer quand la page tient dans le cadre.
  Vérifié par mesure exacte (largeur de la page, du canevas et de la
  couche de texte, toutes trois identiques) à 100 %, 170 %, 280 % et
  400 %, en défilement continu et en page par page, plus l'atteinte des
  deux bords de la page par défilement horizontal aux deux extrémités
  et la stabilité du défilement vertical pendant un défilement
  horizontal.
  **Troisième bug, trouvé par Gautier après cette vérification - le
  vrai problème, différent du premier.** La vérification ci-dessus ne
  contrôlait que les dimensions d'ensemble (page, canevas, conteneur
  de la couche de texte) - jamais la position de chaque caractère à
  l'intérieur. Gautier a mesuré au caractère près, sur ses propres
  captures d'écran à 100 %, 150 % et 290 %, comparant ce qui est
  surligné à l'écran à ce que renvoie `window.getSelection().toString()` :
  décalage présent à TOUS les zooms (imperceptible à 100 %, net à
  150 %, grossier à 290 %), grandissant le long de chaque ligne, et
  variable d'une ligne à l'autre sur une même page - signature d'un
  problème d'échelle horizontale appliqué mot par mot, pas d'un
  glissement global de la couche (qui aurait décalé tout, dans le même
  sens, quel que soit le zoom).
  Cause trouvée dans `pdf.mjs` (classe `TextLayer`, méthode `#layout`
  et `#appendText`) : pour chaque bloc de texte, PDF.js calcule et pose
  en variables CSS `--font-height` (sa hauteur), `--scale-x` (le
  facteur pour étirer horizontalement le texte dessiné avec la police
  de substitution du navigateur jusqu'à la largeur réelle du texte dans
  le PDF) et `--rotate` - mais ne pose JAMAIS directement `font-size` ni
  `transform` en style : ces trois variables sont conçues pour être
  consommées par des règles CSS, normalement fournies par le fichier
  officiel `text_layer_builder.css` de PDF.js (jamais vendu ici, voir
  plus haut) - que notre propre réécriture, en ne posant que
  `transform-origin`, n'a jamais fournies. Sans elles, chaque bloc de
  texte s'affichait à la taille de police par défaut du navigateur,
  sans jamais être étiré pour compenser la police de substitution -
  d'où un écart qui grandit caractère après caractère le long d'une
  ligne, et qui grandit en pixels absolus avec le zoom (la même erreur
  relative, sur un texte plus grand). Repris intégralement dans
  `static/style.css` (comparé règle par règle à la version officielle
  du paquet PDF.js utilisé, 6.3.289 - voir le commentaire au-dessus de
  `.textLayer` pour le détail de ce qui a été gardé et pourquoi certaines
  parties du fichier officiel - éditeur de surbrillance, images extraites
  du texte - ne s'appliquent jamais à ce lecteur).
  Vérifié par comparaison exacte entre le surlignage affiché et
  `window.getSelection().toString()`, caractère par caractère, sur un
  passage précis des deux livres PDF de test, à 100 %, 150 %, 290 % et
  400 % - voir plus bas pour le détail.

Vérifié à l'œil : le livre de test dans les deux modes, à zoom par
défaut et agrandi, la reprise après fermeture, la fiche dans ses trois
états (jamais ouvert, en cours, terminé), la grille, deux pages
consécutives en défilement continu (séparation visible) et
l'enchaînement de deux pages en mode page par page à un zoom où la
page dépasse l'écran (arrivée en haut de la nouvelle page).

### Notes dans le lecteur PDF (fait)

Transpose ce qui existe déjà dans `/watch` et `/listen` (voir "Bloc-
notes", "Format des notes" et "Tranche 8 — notes" plus haut) au lecteur
PDF, sans réinventer : même note, même composant, mêmes décisions déjà
actées.

- **Une seule note par livre, celle de l'item** (`fetch_note`/
  `save_note`, identifiée par `library_path`) : rien de nouveau côté
  modèle, pas de note par page, pas de table de repères séparée. Un
  repère vise une page entière, jamais une position dans la page (un
  décalage de position deviendrait faux au premier changement de
  zoom).
- **Panneau flottant, NON modal, déplaçable et redimensionnable**,
  contrairement à `/watch`/`/listen` où la note est directement sous le
  lecteur : la zone de lecture du PDF ne doit jamais rétrécir pour lui
  faire de la place, et tout doit rester utilisable pendant qu'il est
  ouvert - défilement, changement de page, zoom, et surtout sélection
  de texte dans le PDF pour copier-coller vers la note (voir plus bas).
  `<dialog class="modal modal-note">` affiché par `.show()` (jamais
  `.showModal()`) : pas de `::backdrop`, pas d'inertie du reste de la
  page. Conséquence assumée, decidée avec Gautier après un premier
  essai en modal : **plus de piège de focus ni de fermeture au clic en
  dehors** (un clic en dehors sert à lire) - seuls le bouton "Notes" de
  la barre d'outils (qui ouvre et ferme, comme avant) et Échap
  (déclenché globalement, pas seulement quand le panneau a le focus)
  ferment le panneau.
  Déplaçable par sa barre de titre : `.note-header` (le "Notes" + menu
  "⋮" déjà là, réutilisé tel quel, jamais dupliqué) sert de poignée via
  des évènements pointeur - un clic sur un bouton/le résumé "⋮" qu'elle
  contient n'entame pas de déplacement. Redimensionnable par un coin :
  poignée native du navigateur (`resize: both` en CSS), aucun code de
  glisser-déposer réinventé pour ça. Jamais traînable/redimensionnable
  hors d'atteinte : une position/taille est toujours clampée pour
  laisser au moins 80px de la barre de titre visibles et cliquables sur
  l'écran (haut jamais négatif, un peu de la largeur toujours visible à
  gauche/droite) - vérifié aux deux extrêmes.
  Position et taille mémorisées comme des réglages d'application (pas
  par livre), dans la même table `preferences` que le mode/zoom -
  schéma v7, quatre colonnes `REAL` nullables ajoutées
  (`note_panel_left/top/width/height`), confirmées avec Gautier avant
  écriture. Une valeur enregistrée sur un autre écran (ou une fenêtre
  depuis redimensionnée) est ramenée dans l'écran actuel à l'ouverture
  sans jamais écraser la valeur stockée pour autant - seul un vrai
  déplacement/redimensionnement par l'utilisateur la réécrit
  (`schedulePanelSave`, absent de la fonction qui ne fait que replacer
  visuellement).
  Le composant `_note_widget.html` (éditeur, aperçu, anti-rebond) est
  repris tel quel à l'intérieur, sans aucune duplication : une
  modification faite dans le panneau du lecteur se retrouve sur la
  fiche et inversement, gratuitement, puisque c'est la même route et le
  même enregistrement. Ouvrir/fermer/déplacer/redimensionner le panneau
  ne touche à aucun état du lecteur (rendu, défilement, observateurs) :
  la lecture et l'enregistrement de la position continuent sans être
  perturbés.
- **Bouton "Insérer la page" dans le panneau, à côté des outils
  d'édition** (comme "Repère" pour vidéo/audio - jamais les deux à la
  fois : `_note_widget.html` n'affiche que celui qui correspond au
  lecteur). Vivait d'abord hors du panneau, dans la barre d'outils du
  lecteur, le temps que le panneau était modal (la raison : voir la
  page qu'on marque sans ouvrir le panneau) - cette raison disparaît
  avec un panneau non modal et déplaçable, Gautier a donc demandé de le
  ramener à sa place naturelle, à côté des outils d'édition, comme les
  autres lecteurs.
  Texte du repère, proposé et validé avant écriture : `Page 128
  (/read/310?p=128)` - sobre comme celui de `/listen` (un livre n'a
  qu'un seul fichier, rien à répéter contrairement à `/watch`).
  Le motif qui reconnaît un repère dans la note (`MARKER_PATTERN`,
  partagé lui aussi) a été étendu pour accepter `/read/id?p=page` en
  plus de `/watch|listen/id?t=secondes` : liste des repères, rendu en
  lien dans l'aperçu et à l'impression fonctionnent donc pour un livre
  sans aucun changement supplémentaire. Un repère cliqué depuis la
  fiche ouvre `/read/<media_id>?p=<page>`, qui affiche directement
  cette page.
- **`/read` accepte `?p=<page>`** et l'ouvre à cette page, en
  l'emportant toujours sur la reprise automatique - même règle que
  `?t=` sur `/watch`/`/listen`, y compris sur un livre déjà terminé.
  Ouvrir via un repère ne doit pourtant pas écraser la position
  enregistrée tant que rien n'a vraiment été relu depuis là : la page
  ciblée (`opened_at_marker`, calculé côté serveur) est pré-enregistrée
  côté client comme "déjà sauvegardée" (`lastSavedPage`) avant le tout
  premier rendu, qui appelle `savePage()` comme n'importe quel
  affichage de page mais ne l'écrit donc pas puisqu'elle égale déjà
  cette valeur - seule une vraie navigation ultérieure vers une autre
  page déclenche un envoi. C'est l'endroit où deux bugs de suivi de
  visibilité ont déjà été trouvés (voir plus haut) : la protection se
  fait ici en amont, avant même le tout premier rendu, plutôt qu'en
  s'appuyant sur le mécanisme de suppression déjà en place (pensé pour
  des reconstructions du DOM, pas pour ce cas).
- **Couche de texte sélectionnable (PDF.js `TextLayer`)**, ajoutée pour
  que le copier-coller vers la note fonctionne : le lecteur ne dessinait
  jusque-là qu'un canevas (une image) par page, rien à sélectionner. Un
  `<div class="textLayer">` (position absolue, `inset: 0`) est posé
  par-dessus le canevas de chaque page, dans `.reader-page` (désormais
  `position: relative` pour lui servir de repère). Construite page par
  page, dans `renderPageInto` juste après le rendu du canevas - jamais
  les 500+ pages d'un coup, même IntersectionObserver de préchargement
  que le canevas (voir plus haut). `--total-scale-factor` (lu par
  `TextLayer` pour positionner/dimensionner chaque span) est réglé sur
  `pageViewport.scale`, la même échelle que le canevas : la couche
  suit donc le zoom sans code séparé, puisqu'un changement de zoom
  reconstruit déjà entièrement chaque page visible (canevas et
  maintenant texte) via le même mécanisme existant. Un PDF sans texte
  (page scannée) ne produit ni message ni erreur : aucune branche
  spéciale pour ce cas, `page.streamTextContent()` renvoie simplement
  un flux vide et la couche reste vide.
  **Ce que « le minimum nécessaire » recouvre exactement**, précisé
  après le bug de sélection décalée trouvé par Gautier (voir plus haut,
  "Lecteur PDF") : PDF.js ne pose quasiment rien en style direct sur
  chaque bloc de texte - seulement sa position (`left`/`top`) et sa
  police (`fontFamily`). Tout le reste (taille de police, étirement
  horizontal pour compenser une police de substitution, rotation, prise
  en compte d'une taille de police minimale forcée par le navigateur)
  passe par des variables CSS (`--font-height`, `--scale-x`, `--rotate`,
  `--min-font-size`, `--scale-round-x/y`) que PDF.js pose mais ne
  consomme jamais lui-même - c'est au CSS de le faire, normalement celui
  du lecteur officiel (`text_layer_builder.css`, jamais vendu ici, voir
  plus haut). « Le minimum nécessaire » veut donc dire : toutes les
  règles qui consomment une variable que la classe `TextLayer` pose
  quelque part (vérifié dans `pdf.mjs` méthode par méthode) - ni plus
  (l'éditeur de surbrillance et les images extraites du texte, deux
  classes jamais instanciées ici, n'ont pas leurs règles), ni moins :
  une seule variable oubliée suffit à fausser la mise en page sans
  provoquer la moindre erreur visible ailleurs.
  **Bug trouvé en écrivant cet ajout** : le mémo de rendu
  (`entry.renderTask`, qui empêche un second rendu concurrent de la
  même page) était relâché juste après le canevas, avant que la couche
  de texte ne soit construite - une navigation vers cette page pendant
  cette fenêtre aurait déclenché un second rendu en double. Corrigé en
  ne relâchant le mémo qu'une fois les deux étapes terminées.
  « Vérifié : sélection alignée... à 100 % et 170 % » annoncé à ce
  stade, mais seulement à l'œil et sans comparer au caractère près -
  insuffisant pour repérer le bug d'étirement horizontal trouvé bien
  plus tard par Gautier (voir "Lecteur PDF"), qui ne se voit qu'en
  confrontant le surlignage affiché au texte réellement sélectionné.
  Non vérifié en conditions réelles dans cette session : la fluidité du
  défilement sur un livre de 507 pages - l'environnement de test de ce
  projet fait tourner l'onglet en arrière-plan (`document.hidden`), qui
  ralentit déjà fortement le rendu du canevas lui-même (limitation
  connue, documentée plus haut) au point de rendre un ressenti de
  fluidité non significatif ; la construction page par page (jamais
  eager) reste la garantie structurelle contre un ralentissement à
  l'ouverture d'un gros livre.

Vérifié à l'œil : panneau ouvert pendant qu'on fait défiler le PDF
(rien ne se bloque), une sélection de texte dans le PDF collée dans la
note, le panneau déplacé et redimensionné, sa position/taille
retrouvées après rechargement (y compris ramenées à l'écran sans
écraser la valeur enregistrée), Échap et le bouton "Notes" ferment le
panneau, un clic en dehors ne le ferme plus, un repère inséré depuis le
panneau, le même repère cliqué depuis la fiche ouvrant le lecteur à
cette page, la note identique des deux côtés.

`pytest tests/` (259 tests) au vert.

- **Bug trouvé par Gautier, bien après coup : le panneau semblait ne
  plus être ni déplaçable ni redimensionnable, dans les deux lecteurs.**
  Le code de glisser-déposer et de redimensionnement était en réalité
  correct - le vrai problème se trouvait dans l'enregistrement de sa
  géométrie. `schedulePanelSave` attend 900 ms (anti-rebond) avant de
  lire `getBoundingClientRect()` sur le dialogue ; si le panneau est
  fermé pendant ce délai (glisser puis fermer tout de suite, un geste
  naturel), le `<dialog>` est déjà caché quand le minuteur se
  déclenche - un élément caché renvoie un rectangle (0, 0, 0, 0), écrit
  tel quel dans `preferences`. Confirmé en base sur la bibliothèque de
  test (colonnes à 0 au lieu de `NULL`). Au réglage suivant : `width`/
  `height` utilisaient `valeur || défaut` (`0` étant "faux" en
  JavaScript, la corruption y était masquée), mais `left`/`top`
  utilisaient `valeur === null` (`0` n'est pas `null`, la corruption y
  passait telle quelle) - le panneau se retrouvait donc épinglé dans le
  coin supérieur gauche, superposé à la sidebar, à chaque ouverture
  suivante : moins "cassé" qu'il n'y paraissait, mais bloqué au même
  endroit indéfiniment.
  Corrigé à deux niveaux : côté client, `schedulePanelSave` (et son
  homologue EPUB) n'enregistre plus rien si le dialogue est fermé ou si
  le rectangle mesuré a une largeur/hauteur nulle ou négative, et
  `closeNotesDialog` annule le minuteur en attente plutôt que de le
  laisser se déclencher après coup. Côté serveur, en défense en
  profondeur (le client ne doit jamais être le seul rempart) : la route
  `/preferences` ignore les quatre champs de géométrie ensemble dès que
  la largeur ou la hauteur envoyée est inférieure ou égale à zéro,
  plutôt que d'écraser une géométrie valable par une dégénérée. Couvert
  par un test qui reproduit exactement le scénario (rectangle nul après
  une géométrie valable, puis sans aucune géométrie préalable) : la
  valeur précédente doit survivre, jamais être remplacée par du zéro.
- **Croix de fermeture explicite**, à côté du menu ⋮ dans l'en-tête du
  panneau (`_note_widget.html`, nouveau paramètre `floating` du macro
  `render_note` - seul le panneau flottant des lecteurs PDF/EPUB
  l'affiche, jamais la carte de notes de la fiche ou de `/watch`/
  `/listen`). Échap continue de fonctionner ; la croix est la première
  issue visible à la souris, sans devoir connaître le raccourci ni
  rouvrir le bouton "Notes" de la barre d'outils.
  **Bug trouvé par Gautier en vérifiant cet ajout : la croix se
  retrouvait sous le ⋮ plutôt qu'à côté, et seule une mince bande sous
  le ⋮ permettait de glisser le panneau.** `.hero-menu` (le ⋮) est
  conçu pour flotter en haut à droite du hero de la fiche
  (`position: absolute`) - une fois réutilisé tel quel dans
  `.note-header`, il échappait complètement au flux normal, ne
  laissant que le texte "Notes" et la croix (les seuls éléments
  encore en flux) définir la hauteur de l'en-tête - d'où la bande
  fine. Corrigé en repassant `.hero-menu` en `position: relative`
  (jamais `static` : il reste le repère de positionnement de son
  propre menu déroulant) à l'intérieur de `.note-header` seulement -
  il revient dans le flux, à côté de la croix, et l'en-tête retrouve
  sa vraie hauteur (celle du bouton ⋮, 36px) sur toute sa largeur.
  **Zone de glissement encore trop petite, signalé par Gautier une fois
  cette correction en place** : limitée à la hauteur de l'en-tête, alors
  que le dialogue a son propre padding (20px, hérité de `.modal`)
  au-dessus - une bande morte sur toute la largeur du panneau, entre son
  bord haut réel et le début de l'en-tête. Corrigé en étirant la boîte
  de `.note-header` par une marge négative égale à ce padding (haut et
  côtés), lui redonnée en padding propre - le texte et les icônes
  restent au même endroit à l'écran, mais toute la surface entre le
  bord haut du panneau et le début de la barre d'outils d'édition fait
  maintenant partie de la même boîte, donc de la même poignée de
  glissement (le clic sur ⋮/× reste exclu, inchangé).
  **Deux pièges trouvés en vérifiant cette correction à l'écran, la
  marge négative ne bougeait rien du tout au premier essai.** D'abord,
  une marge négative en haut d'un premier enfant "remonte" par fusion
  de marges (margin collapsing) dans son parent (`.note-card`) au lieu
  de déplacer l'enfant lui-même, tant que ce parent n'a ni padding ni
  bordure sur ce côté - `.modal-note .note-card { display: flow-root }`
  lui donne le contexte de mise en forme qui arrête cette fusion.
  Ensuite, une règle plus ancienne et plus générale,
  `body.page-player .card { margin-top: 20px }` (pensée pour espacer la
  carte de notes de la vidéo/du PDF quand elle est un élément de page
  normal, sur `/watch`/`/listen`/`/read`), s'appliquait aussi au
  panneau flottant et ajoutait 20px de plus, jamais vus dans les
  mesures de `.note-header` puisqu'ils venaient de `.note-card`, son
  parent. Annulée par une règle aussi qualifiée qu'elle
  (`body.page-player .modal-note .note-card { margin-top: 0 }`) : une
  règle moins qualifiée aurait perdu face à elle par spécificité, quel
  que soit l'ordre des deux dans le fichier.
  **Poignée de redimensionnement invisible sur fond sombre**, signalé
  dans la foulée : la poignée native du navigateur (coin bas-droit,
  `resize: both`) n'était indiquée par rien. Un motif décoratif (trois
  traits diagonaux, `repeating-linear-gradient` découpé en triangle par
  `clip-path`, couleur `--color-text-secondary`) est posé par-dessus en
  `::after`, avec `pointer-events: none` pour ne jamais intercepter le
  geste réel - la poignée native en dessous continue de fonctionner et
  de changer le curseur au survol sans rien de plus à écrire, c'est un
  comportement natif de `resize`, pas quelque chose que ce dégradé
  pilote.
  **Bug trouvé par Gautier : l'icône débordait sur le coin arrondi du
  panneau et se retrouvait sur le fond clair de la page (blanc sur
  blanc).** Posée à 2px du coin, elle tombait dans la zone que
  `border-radius: 16px` découpe - au plus près du vrai coin, cette zone
  ne montre que ce qu'il y a DERRIÈRE le panneau (la page de lecture,
  claire), jamais son propre fond. Corrigé en la rentrant à 15px (juste
  au-delà du rayon de 16px, le point le plus proche du coin reste dans
  la partie réellement peinte du panneau) - couleur déjà
  `--color-text-secondary` (le gris discret du projet, jamais du blanc)
  depuis le début, invisible seulement tant qu'elle débordait sur du
  clair.
- **Menu ⋮ retiré du panneau de notes**, une seule entrée ("Imprimer")
  ne justifiait pas un menu à ouvrir - remplacé par un bouton unique
  (icône imprimante 🖨, infobulle "Imprimer"). Vérifié avant de
  supprimer quoi que ce soit : `.hero-menu`/`.hero-menu-list`/
  `.hero-menu-item` sont des classes CSS partagées, réutilisées telles
  quelles ailleurs pour un vrai menu à trois entrées (le hero de la
  fiche, `item_detail.html` - Modifier les métadonnées / Rechercher-
  actualiser / Informations techniques) - seul le `<details
  class="hero-menu">` du panneau de notes (`_note_widget.html`) est
  retiré, rien de partagé n'est touché. Nouvelle classe générique
  `.icon-btn` (36px, couleur de texte secondaire, fond au survol -
  même gabarit que portait le ⋮ qu'elle remplace) plutôt que de
  réutiliser `.modal-close` (sémantiquement "ferme quelque chose", pas
  "imprime") ou `.hero-menu` (n'en est plus un).

### Panneau de notes flottant : lecteur vidéo (fait)

Le lecteur vidéo abandonne son bloc de notes fixe sous la vidéo au
profit du panneau flottant déjà en place dans les lecteurs PDF et EPUB
(voir "Notes dans le lecteur PDF" plus haut) - décidé avec Gautier :
repris tel quel, jamais adapté. Même composant (`_note_widget.html`,
`floating=True`), même JS de glisser-déposer/redimensionnement/
persistance (copié verbatim depuis `book_reader.html`/
`epub_reader.html`, comme ces deux-là l'avaient déjà fait l'un de
l'autre - toujours aucune seconde implémentation), et surtout **même
position/taille enregistrées** : `note_panel_left/top/width/height`
viennent de la même table `preferences`, sans nouvelle colonne - un
réglage d'application, pas un par lecteur. Vérifié : le panneau ouvert
depuis `/watch` réapparaît exactement là où on l'a laissé en repartant
de `/read`, et inversement.

- **Bouton "Notes"**, jamais dans `.nav-buttons` (Précédent/Suivant) :
  ce bloc est entièrement remplacé (`outerHTML`) à chaque changement de
  vidéo sans rechargement (voir "Changement de vidéo sans
  rechargement" plus haut) - un bouton posé dedans perdrait son
  écouteur et son état (`aria-expanded`) à chaque navigation. Sa propre
  barre, en dessous, réutilise `.reader-toolbar`/`.reader-toolbar-group`
  des lecteurs PDF/EPUB (un seul groupe ici) plutôt qu'un nouveau
  composant.
- **Bouton "Repère" déplacé dans le panneau**, comme "Insérer la page"
  (PDF) et "Insérer le chapitre" (EPUB) - en réalité, il y vivait déjà
  (`_note_widget.html` génère ce bouton dans son propre bloc d'outils
  selon `player_context.kind`, jamais un élément séparé posé dans le
  lecteur) : son déplacement visuel suit automatiquement celui du
  panneau lui-même, sans rien de plus à coder. Seul son libellé change,
  pour suivre la même forme "Insérer le/la ___" : **"Insérer le
  repère"** (`title="Insérer le repère courant"`) - "repère" reste le
  mot déjà établi dans le projet pour ce marqueur temporel (vidéo/
  audio), plutôt qu'un nom inventé pour l'occasion. Nouvelle branche
  `player_context.kind == 'video'` dans `_note_widget.html`,
  distincte de la branche générique (devenue le repli pour l'audio
  seul, qui garde "Repère" - hors périmètre de cette tranche).
- **Lecteur audio (`/listen`), même commit.** `audio_player.html`
  adopte le même panneau flottant que la vidéo, apporté par ce même
  commit (`a386396`) - pas une tranche séparée.
- **Hors périmètre, explicitement, à ce stade.** Le bloc de notes de
  la fiche d'item (`item_detail.html`) - tranche à part, faite depuis
  (voir "Notes sur la fiche d'item" plus bas).

Vérifié dans le navigateur : panneau ouvert/fermé sur `/watch`,
glissé et redimensionné (position/taille enregistrées, retrouvées sur
`/read` immédiatement après), bouton "Insérer le repère" inséré avec
le même format qu'avant (`Vidéo N — titre — horodatage
(/watch/id?t=secondes)`), aucune régression sur le changement de vidéo
sans rechargement. La playlist reprend toute la hauteur libérée par la
disparition du bloc de notes fixe (sa hauteur ne dépendait déjà que du
haut de la vidéo, jamais de ce qu'il y a en dessous - voir "Hauteur et
position des colonnes latérales").

`pytest tests/` (298 tests) au vert.

### Lecteur EPUB (fait)

Rend un livre EPUB lisible dans l'application (`/read-epub/<media_id>`),
sur le modèle du lecteur PDF — même barre d'outils, même sidebar, même
panneau de notes, mêmes décisions de progression déjà actées quand
elles s'appliquaient encore. Décisions actées avec Gautier avant tout
code (ARRÊT 1 : moteur de rendu, ARRÊT 2 : modèle de données) :
progression en **chapitres**, jamais en pages (un EPUB n'a pas de page
fixe, le texte se recompose selon la fenêtre et la taille du texte) ;
« terminé » = dernier chapitre atteint, même principe que la dernière
page d'un PDF ; pas de mode page par page (n'aurait aucun sens sans
page fixe) — voir "Les trois règles du « terminé », côte à côte" plus
haut.

- **Décompression et rendu entièrement côté serveur, sans bibliothèque
  tierce** — pas de PDF.js-like pour l'EPUB. Un EPUB est une archive
  zip (`zipfile`, stdlib) contenant du XML (`xml.etree.ElementTree`,
  stdlib) et du HTML (`bs4`/`BeautifulSoup`, déjà une dépendance du
  projet via `presentation.py` — zéro nouvelle dépendance). Choisi
  plutôt qu'une bibliothèque JS de lecture EPUB (type epub.js) parce
  que la contrainte de sécurité de Gautier (« un EPUB contient du HTML
  arbitraire, il ne doit pas pouvoir exécuter de script ni appeler le
  réseau depuis Studia ») est plus simple à garantir en assainissant le
  HTML une fois côté serveur qu'en configurant/auditant une
  bibliothèque tierce qui exécute ce HTML côté client.
- **EPUB2/NCX seulement** (décidé avec Gautier). `epub_book.py` lit
  `META-INF/container.xml` pour trouver l'OPF (`content.opf`), puis
  l'OPF pour trouver le NCX (`spine[toc]` → item du manifeste, avec un
  repli sur `media-type="application/x-dtbncx+xml"`) et la table des
  matières dans `<navMap>` du NCX. **Un EPUB3 sans NCX ne casse rien** :
  l'absence de NCX lève `EpubFormatError`, `count_epub_chapters`
  l'attrape et renvoie `None` (comme un PDF dont `pdfinfo` échoue), et
  `/read-epub` affiche alors le même message que pour un format
  illisible (« Ce livre utilise un format que Studia ne sait pas
  encore lire »), au même endroit et dans le même esprit — jamais de
  page cassée ni d'erreur technique. Vérifié par un test avec un EPUB3
  minimal sans NCX fabriqué pour l'occasion (aucun exemplaire réel sous
  la main).
- **Un chapitre = un fichier du spine, dédupliqué** — pas une plage de
  texte entre deux ancres. La table des matières d'un EPUB liste
  souvent plusieurs `navPoint` pointant vers le même fichier (des
  sous-titres internes), ce qui produirait sinon le même contenu rendu
  plusieurs fois sous des chapitres presque identiques : constaté sur
  le livre de test simple, 22 `navPoint` pour seulement 13 fichiers
  distincts. `parse_table_of_contents` aplatit récursivement le
  `navMap` dans l'ordre du document, résout chaque `src` (ancre
  ignorée) et ne garde que la première entrée par fichier cible — le
  titre de cette première entrée nomme le chapitre, les suivantes
  pointant vers le même fichier sont ignorées comme sous-titres du même
  chapitre. Contre-vérifié sur un second livre réel, structurellement
  différent (correspondance 1:1 fichier/chapitre) : 88 `navPoint` pour
  88 fichiers, aucune perte. Ceci évite aussi complètement le problème,
  bien plus dur, de découper le HTML d'un fichier entre deux ancres :
  un chapitre est toujours un fichier entier du spine.
  **Bug trouvé en testant sur un vrai EPUB** : le `src` d'un
  `<content>` du NCX doit se résoudre par rapport au dossier du NCX
  lui-même, pas à celui de l'OPF — les deux peuvent différer (constaté
  sur un EPUB Calibre réel où l'OPF vit dans `OEBPS/` mais le NCX et les
  fichiers de contenu vivent à la racine de l'archive). Corrigé en
  calculant `ncx_dir` et en s'en servant comme base de résolution, à la
  place de `opf_dir` utilisé par erreur au premier essai.
- **Sécurité en deux couches**, l'assainissement serveur et le sandbox
  du navigateur se couvrant l'un l'autre :
  1. `render_chapter` (via BeautifulSoup) supprime tous les `<script>`,
     tous les attributs `on*=`, et les `<a href>` en entier (le texte du
     lien est gardé, jamais le lien) ; toute URL avec un schéma explicite
     (`http:`, `data:`...) ou commençant par `//` est retirée, seuls les
     chemins relatifs internes sont réécrits vers une route Flask de
     service d'actif (`/media/<id>/epub-asset/<chemin>`) ; le CSS
     (balises `<style>` et attributs `style=`) subit le même traitement
     (`url(...)` externes supprimées, `@import` retiré entièrement).
  2. Le chapitre assaini est rendu dans un
     `<iframe sandbox="allow-same-origin">` **sans** `allow-scripts` —
     une garantie imposée par le navigateur, indépendante de la
     complétude de l'assainisseur : même un script qui aurait échappé au
     nettoyage ne peut pas s'exécuter. `allow-same-origin` est gardé
     uniquement pour que la page parente puisse lire/écrire
     `iframe.contentDocument` (mesure de hauteur, application de la
     taille de texte), sans donner la moindre capacité d'exécution de
     script au contenu encadré.
  `/media/<id>/epub-asset/<chemin>` sert les images/polices/CSS internes
  de l'archive (CSS réassaini au passage, reste servi tel quel) et
  refuse tout chemin contenant `..` en défense en profondeur.
- **Réutilisation du modèle de données existant, aucune nouvelle
  colonne de progression** (décidé avec Gautier à l'ARRÊT 2) :
  `media.page_count` devient « nombre de chapitres » et
  `progress.page_number` devient « index du chapitre courant » pour un
  `.epub` — même sens que pour un `.pdf`, juste une autre unité. Effet
  direct : `is_book_completed`, `save_book_progress`,
  `resolve_resume_page` et la branche livre de
  `compute_item_progress_percent` fonctionnent pour l'EPUB **sans
  aucune modification** — la meilleure confirmation que ce choix de
  réutilisation tenait la route. Seul `probe_missing_media_info`
  distingue les deux formats pour peupler `page_count` : `pdfinfo` pour
  un `.pdf`, `count_epub_chapters` (compte les entrées de la table des
  matières aplatie) pour un `.epub`.
  `media_chapters`/`chapters_probed_at` (table de chapitres horodatés
  des M4B) n'est délibérément **pas** réutilisée pour stocker la table
  des matières d'un EPUB : un chapitre M4B a une dimension temporelle
  qu'un chapitre EPUB n'a pas, l'analogie s'arrête à la ressemblance de
  nom. La table des matières d'un EPUB est reparsée à la volée à chaque
  ouverture de `/read-epub` et à chaque appel de `epub-chapter` (lecture
  d'archive + parsing XML, sans sous-processus - assez bon marché pour
  ne rien mettre en cache).
  En revanche, `chapters_probed_at` (déjà posée sans condition par
  `probe_missing_media_info` pour tout média, PDF ou EPUB compris,
  avant même cette tranche) **est** réutilisée telle quelle pour un
  usage inédit : distinguer « pas encore sondé » (`page_count` NULL et
  `chapters_probed_at` NULL - le livre peut encore fonctionner) de
  « format confirmé illisible » (`page_count` NULL mais
  `chapters_probed_at` NOT NULL - un `--probe` a déjà échoué à compter
  les chapitres) pour un `.epub` - zéro nouvelle colonne, zéro nouveau
  suivi. Le hero n'affiche le message « format illisible » qu'une fois
  ce second cas confirmé, jamais avant, exactement comme pour un PDF.
- **`READABLE_BOOK_EXTENSIONS`** (tuple, remplace l'ancien
  `READABLE_BOOK_EXTENSION` au singulier) contient désormais `.pdf` et
  `.epub` ; `BOOK_READER_ENDPOINTS` (`{".pdf": "read_book", ".epub":
  "read_epub_book"}`) aiguille le bouton hero, la remise à zéro de
  progression et la playlist du Programme vers le bon lecteur selon
  l'extension. Un livre dans un troisième format (MOBI, CBZ...)
  continue d'afficher « Ce format ne peut pas encore être lu dans
  l'application. », inchangé. **Bug évité de justesse** : élargir
  `fetch_playable_media` aux deux extensions laissait un EPUB passer
  aussi la garde de `/read` (le lecteur PDF), qui ne vérifiait que
  `media_type == 'book'` sans vérifier l'extension — corrigé en ajoutant
  la vérification `extension == '.pdf'` à `/read`, avant que ça ne soit
  jamais visible en vrai (attrapé par un test existant qui a
  échoué).
- **Table des matières en colonne latérale, sur le modèle exact de la
  playlist vidéo et de la liste de chapitres audio** (sticky, hauteur
  bornée, défilement interne, chapitre courant surligné) — mêmes
  classes CSS (`.playlist`, `.file-row`/`.chapter-row`, `.current`),
  aucun nouveau CSS pour la sidebar elle-même.
- **Taille de texte, mémorisée comme le zoom du PDF** : nouvelle colonne
  `preferences.reading_text_scale` (REAL, nullable — schéma v8),
  proposée à Gautier avant écriture. Appliquée par `applyTextScale()` en
  agissant directement sur `iframe.contentDocument` (rendu possible par
  `allow-same-origin` du sandbox, voir plus haut) - aucun rechargement
  de page. Résumée : le lecteur ouvre à la dernière taille utilisée,
  jamais un flash à la taille par défaut.
- **Panneau de notes flottant, repris tel quel du lecteur PDF** - même
  gabarit `<dialog class="modal modal-note">`, même JS (déplaçable,
  redimensionnable, non modal, Échap et le bouton "Notes" seuls le
  ferment), aucune seconde implémentation. Seule différence : le repère
  cible un chapitre entier, jamais une position à l'intérieur (un
  EPUB n'a pas de coordonnée stable dans un chapitre, contrairement à
  une page de PDF).
  **Texte du repère : le titre du chapitre, jamais son numéro** (décidé
  avec Gautier) - `Tâche 2 : Conversion (/read-epub/12?c=9)`, pas
  `Chapitre 9 (/read-epub/12?c=9)` : un numéro de chapitre ne dit rien
  de ce qui a été marqué, contrairement au numéro de page d'un PDF qui
  est une coordonnée en soi. Repli sur `Chapitre N` uniquement quand la
  table des matières ne fournit aucun titre exploitable pour ce
  chapitre. `MARKER_PATTERN` étendu pour reconnaître
  `/read-epub/id?c=chapitre` en plus des motifs déjà connus.
- **`/read-epub` accepte `?c=<chapitre>`**, même règle que `?p=` pour le
  PDF : l'emporte toujours sur la reprise automatique, y compris sur un
  livre déjà terminé, sans jamais écraser la position enregistrée tant
  que rien n'a vraiment été relu depuis là (même mécanisme de
  pré-enregistrement côté client que le PDF).
- **Toolbar, sommaire, titre et fil d'Ariane toujours visibles**, comme
  pour le lecteur PDF - aucun gabarit de site à adapter, la structure de
  page est entièrement reprise de `_base.html`.
- **Hors périmètre, explicitement, pour cette tranche.** Le lecteur PDF
  lui-même, le modèle de notes, les fichiers de bibliothèque et les
  montages réseau - rien de tout cela n'a été touché.

Vérifié à l'œil : les deux EPUB de test ouverts (un livre simple à 13
chapitres, un livre riche à 88 chapitres avec images), la table des
matières des deux, le changement de taille de texte sans rechargement,
la reprise après fermeture pour les deux livres, un repère inséré
depuis le panneau avec le titre du chapitre (pas son numéro) et cliqué
depuis la fiche pour ouvrir le bon chapitre, la fiche dans ses trois
états (jamais ouvert, en cours, terminé - avec « Chapitre N sur M »
dans la boîte « Tout recommencer »), la grille avec les deux nouveaux
items EPUB et leurs pourcentages corrects, et un EPUB3 sans NCX
fabriqué pour l'occasion affichant le message de format illisible sans
page cassée.

Limitation d'environnement constatée, sans lien avec cette tranche :
dans cette session d'automatisation, l'onglet de test tourne en
arrière-plan (`document.hidden`), ce qui empêche la touche Échap
envoyée par l'outil de fermer le panneau de notes - reproduit à
l'identique sur le lecteur PDF déjà validé, avec le même onglet, en
comparant une pression clavier réelle (échoue) à un
`dispatchEvent(KeyboardEvent('keydown', {key:'Escape'}))` direct en JS
(fonctionne, ferme bien le panneau) : le gestionnaire d'évènement est
donc correct, seule la simulation de touche de l'outil d'automatisation
est affectée par l'arrière-plan de l'onglet, comme le rendu canevas déjà
documenté plus haut pour le lecteur PDF.

`pytest tests/` (291 tests) au vert.

### Défilement continu EPUB (fait)

Constat de Gautier à l'origine de cette tranche : il n'y avait pas de
"mode page par page" à retirer dans l'EPUB - les flèches passaient déjà
d'un chapitre entier à l'autre, conformément à la décision d'origine.
Ce qui manquait, c'est l'enchaînement continu : arriver au bas d'un
chapitre en faisant défiler doit faire apparaître le suivant dans le
même mouvement, comme le lecteur PDF avec ses pages.

- **Deux modes, comme le PDF : "Défilement" (par défaut) et "Chapitre
  par chapitre".** Mémorisés dans une colonne séparée de celle du PDF
  - `preferences.epub_reading_mode` (`'scroll'|'chapter'`, schéma v9),
  proposée à Gautier puis écrite - même principe que
  `reading_text_scale` séparée de `reading_zoom` : deux lecteurs, deux
  réglages, même si conceptuellement proches. Le mode "Chapitre par
  chapitre" est exactement le comportement déjà existant avant cette
  tranche (un chapitre, un document, rechargé entièrement à chaque
  navigation) - rien n'y a changé.
- **Défilement continu : une seule iframe, un seul document
  persistant** (assigné une fois via `iframe.srcdoc`), plutôt qu'un
  document par chapitre. Les chapitres y sont ajoutés au fil de la
  lecture (`<section class="epub-chapter" data-chapter="n">`), jamais
  tous chargés d'un coup : une fenêtre contiguë `[loadedMin, loadedMax]`
  s'étend vers le bas (`appendChapter`) ou vers le haut
  (`prependChapter`) quand une sentinelle placée à chaque extrémité du
  contenu chargé approche de l'écran visible (marge de préchargement de
  800px, même principe que le rendu progressif des pages du PDF).
  Ouvrir un livre au chapitre 80 sur 88 (repère, reprise, sommaire) ne
  charge donc jamais les 79 chapitres qui précèdent - seul le chapitre
  visé, puis ses voisins au fil du défilement dans un sens ou l'autre.
  Toujours zéro changement serveur : chaque chapitre est récupéré via
  la route `/media/<id>/epub-chapter/<n>` déjà existante, son `<body>`
  et ses `<link rel="stylesheet">` extraits côté client avec
  `DOMParser` puis insérés dans le document partagé (feuilles de style
  dédupliquées par `href`) - toujours du HTML déjà assaini côté
  serveur, jamais de script, sandbox inchangée.
  **Vers le bas, un ajout ne déplace jamais ce qui est déjà affiché**
  (aucun saut) : le nouveau chapitre est simplement inséré après le
  dernier. **Vers le haut**, insérer avant pousse mécaniquement tout le
  contenu déjà affiché plus bas à l'intérieur de l'iframe - compensé
  aussitôt par un ajustement du défilement extérieur de la même valeur
  (mesurée avant/après insertion), technique standard pour un ajout "en
  amont" du point de lecture. C'est cette contrainte précise - la
  hauteur d'un chapitre à venir n'est jamais connue avant de l'avoir
  chargé, contrairement à une page de PDF - qui interdisait de reprendre
  tel quel le mécanisme du PDF (des conteneurs vides pré-dimensionnés
  pour chaque page, remplis paresseusement) : on ne réserve ici jamais
  de place à l'avance, on ajoute puis on compense.
- **Bug de conception trouvé en vérifiant dans le navigateur, avant
  toute présentation à Gautier : `IntersectionObserver` ne peut pas
  franchir la frontière iframe/document parent.** Le premier jet
  observait les sentinelles et les sections de chapitre (qui vivent
  dans le document de l'iframe) avec `root: viewport` (qui vit dans le
  document parent) - aucune erreur, mais l'observateur ne se déclenchait
  simplement jamais (confirmé par un test isolé : `.observe()` ne lève
  rien, son callback n'est juste jamais appelé quand cible et racine
  sont dans deux documents différents). Remplacé entièrement par un
  calcul manuel de géométrie sur l'évènement `scroll` de
  `#reader-viewport` : le rectangle de l'iframe dans le document parent
  combiné à celui de chaque élément dans le document de l'iframe donne
  sa position réelle par rapport à la zone visible, sans jamais avoir
  besoin d'observer à travers la frontière. Sert à la fois à détecter
  l'approche d'une sentinelle et à déterminer le chapitre qui occupe le
  plus l'écran (même notion de ratio qu'`intersectionRatio` - part de
  la propre hauteur du chapitre qui est visible, pas part de l'écran -
  recalculée à la main plutôt que fournie par le navigateur).
  **Second piège trouvé en corrigeant celui-ci** : l'anti-rebond de
  cette réévaluation était d'abord posé sur `requestAnimationFrame` -
  or un onglet en arrière-plan peut suspendre indéfiniment ses
  callbacks (constaté : plus de 45 secondes sans une seule exécution
  dans cet environnement de test). Un onglet de lecture mis de côté
  pendant qu'on lit ailleurs n'a rien d'exotique - remplacé par un
  anti-rebond `setTimeout` (100 ms), qui continue de fonctionner même
  arrière-plan.
- **Dernier chapitre très court (page de fin, colophon) : ne jamais
  dépendre uniquement du ratio pour marquer le livre terminé.** Question
  explicite de Gautier avant d'écrire cette partie. Un chapitre très
  court qui devient entièrement visible atteint quand même un ratio de
  1 (comme n'importe quel chapitre entièrement visible, sa propre
  taille n'entre pas en compte) - la comparaison de ratios seule
  s'en sortirait donc probablement déjà dans la plupart des cas. Mais
  plutôt que de compter dessus, une règle explicite et prioritaire a
  été ajoutée : avoir défilé jusqu'au tout bas du contenu chargé, quand
  ce contenu va jusqu'au tout dernier chapitre du livre, veut dire avoir
  atteint ce dernier chapitre - peu importe la portion d'écran qu'il
  occupe par ailleurs. Vérifié en conditions réelles sur les deux livres
  de test (13 et 88 chapitres) : défilement jusqu'au tout bas,
  `page_number` enregistré à `chapter_count`, livre marqué terminé
  (`completed = 1`, via `is_book_completed`, totalement inchangée).
- **Bug trouvé en vérifiant la reprise après le premier essai** :
  `setCurrentChapter` ne fait rien si le chapitre visé égale déjà
  `currentChapter` - protection nécessaire pour ignorer les réévaluations
  de ratio redondantes pendant un défilement naturel, mais qui empêchait
  aussi la toute première mise à jour des champs affichés (numéro,
  titre du repère, ligne du sommaire) à l'ouverture, puisque
  `currentChapter` vaut déjà le chapitre de reprise dès l'initialisation
  de la variable. `openScrollAt` met désormais ces champs à jour
  explicitement à l'ouverture, sans passer par cette protection.
- **Bande blanche au dézoom du texte (défauts d'affichage signalés par
  Gautier).** `resizeFrameToContent` mesurait
  `doc.documentElement.scrollHeight` - pour l'élément racine, la
  spécification plafonne cette valeur à AU MOINS la hauteur actuelle de
  l'iframe elle-même (rien à voir avec le contenu réel) : un dézoom qui
  réduit la hauteur du texte ne faisait donc jamais redescendre la
  hauteur de l'iframe sous sa valeur précédente, plus grande, laissant
  une bande blanche croissante sous le texte à chaque cran de dézoom.
  Confirmé par mesure (`body.scrollHeight` correctement plus petit après
  dézoom, `documentElement.scrollHeight` bloqué à l'ancienne valeur).
  Corrigé en mesurant `doc.body.scrollHeight` à la place : `<body>`
  n'est pas la racine et n'a pas ce plancher, sa hauteur reflète
  toujours le contenu réel, à la hausse comme à la baisse.
- **Table des matières plus haute que la zone de lecture (second défaut
  signalé).** `.playlist` reprenait le `max-height: calc(100vh - ...)`
  purement CSS de `/watch`, pensé pour une colonne qui démarre en haut
  de `.layout` - mais dans le lecteur, la table des matières démarre
  bien plus haut que `#reader-viewport` (qui a un titre et une barre
  d'outils au-dessus, elle n'a rien). Corrigée en donnant à `.playlist`
  sa propre borne calculée en JS, ancrée à son propre sommet plutôt
  qu'à celui du lecteur - même fonction (`computeAvailableHeightFrom`)
  que celle déjà utilisée pour `#reader-viewport`, appliquée à son
  propre `getBoundingClientRect().top`.
  **Cette correction ne réglait que la hauteur, pas la position ni le
  comportement au défilement** - toujours ancrée à l'écran
  (`position: sticky`, hérité de la règle `.playlist` partagée avec
  `/watch`) et toujours démarrée à son propre sommet plutôt qu'aligné
  sur celui du cadre de lecture. Reproduit et corrigé avec le même bug,
  sur la même colonne, trouvé sur la playlist vidéo - voir "Hauteur et
  position des colonnes latérales" plus haut pour la règle commune aux
  deux.

- **Bug trouvé par Gautier : deux barres de défilement verticales
  superposées, dans les deux modes.** L'iframe défilait à l'intérieur
  d'elle-même EN PLUS de `#reader-viewport` - alors qu'elle doit
  toujours être entièrement agrandie à son contenu, sans jamais
  défiler elle-même (voir plus haut). Deux causes distinctes trouvées
  par mesure (`documentElement.scrollHeight` comparé à
  `body.scrollHeight` et à la hauteur réellement appliquée à
  l'iframe) :
  1. La propre feuille de style d'un chapitre, chargée après le
     `<style>` du document partagé, pouvait redonner une marge à
     `body` (constaté : ~6,7px en haut et en bas sur un livre réel) -
     invisible pour `body.scrollHeight` (qui ne compte jamais sa
     propre marge externe), mais bien compté par
     `documentElement.scrollHeight`. Corrigé avec `margin: 0
     !important` sur `body`, dans le document partagé du défilement
     continu comme dans le document à chapitre unique
     (`epub_chapter.html`) - jamais un livre ne doit pouvoir modifier
     l'espacement du gabarit qui l'accueille.
  2. `epub_chapter.html` posait aussi `padding: 20px` sur `html` ET
     `body` à la fois (`html, body { ... }`) - les deux paddings se
     cumulaient (l'un imbriqué dans l'autre, ~40px de trop), ni vus
     par `body.scrollHeight` ni par le calcul de hauteur de l'iframe.
     Corrigé en ne posant le padding que sur `body` (jamais sur
     `html`, qui n'en a besoin nulle part ici).
  3. **Second bug trouvé en vérifiant la correction précédente** :
     une feuille de style externe ou une image d'un chapitre charge de
     façon asynchrone - `resizeFrameToContent`, appelé juste après
     l'insertion du chapitre, mesurait donc une hauteur d'avant leur
     chargement complet, sans qu'aucun code ne redéclenche la mesure
     une fois chargées. Constaté sur "La boîte à outils" (grandes
     images) : l'iframe restait ~230px trop petite pour son contenu
     réel. Corrigé en écoutant l'évènement `load` (et `error`) de
     chaque nouvelle feuille de style et de chaque image pas encore
     chargée, pour rappeler `resizeFrameToContent` une fois qu'elles
     le sont.
- **Séparation visible entre les chapitres en défilement continu**,
  sur le modèle du PDF : fond neutre (`#26323A`, la valeur de
  `--color-border` - fixe, les variables CSS de l'application ne
  traversent pas la frontière de l'iframe) posé sur `body`, chaque
  `.epub-chapter` gardant son propre fond blanc, son ombre légère et
  un espace (`margin-top: 20px`) avec le chapitre suivant - chacun
  reste une feuille distincte, jamais un long bloc de texte continu.
- **Bug trouvé par Gautier, la correction précédente ne tenait pas :
  la table des matières débordait toujours sur un livre long.** En la
  revérifiant, le calcul lui-même (borne propre à `.playlist`, ancrée
  à son propre sommet) s'est avéré correct dès la première mesure.
  L'explication la plus probable : **Flask garde les gabarits Jinja
  compilés en mémoire et ignore leurs modifications tant que le
  serveur de développement n'est pas redémarré à la main** (constaté
  plusieurs fois pendant cette tranche, y compris sur mes propres
  vérifications) - un correctif peut donc être réellement dans le
  fichier sans jamais atteindre un serveur déjà lancé. Plutôt que de
  compter sur un redémarrage systématique (facile à oublier),
  `app.config["TEMPLATES_AUTO_RELOAD"] = True` est maintenant posé
  dans `create_app` : un gabarit modifié est repris à la requête
  suivante, sans redémarrage. Rechargement des fichiers CSS/JS
  statiques inchangé (ils n'ont jamais été mis en cause - Flask ne les
  sert jamais depuis une copie en mémoire).

Vérifié dans le navigateur : "La boîte à outils" (88 chapitres) ouvert
au chapitre 1, chapitres suivants chargés au fil du défilement sans
jamais empiler tout le livre, saut direct au chapitre 80 depuis le
sommaire (charge uniquement autour de 80, pas les 79 précédents),
défilement jusqu'au tout dernier chapitre (88) avec livre marqué
terminé, fiche affichant « 100 % · chapitre 88 sur 88 » et le bouton
« Revoir » ; même vérification de bout en bout sur "Guide de démarrage
rapide" (13 chapitres) ; bascule "Chapitre par chapitre" ↔ "Défilement"
dans les deux sens, avec persistance après rechargement ; un repère
inséré en mode défilement (titre du chapitre) cliqué depuis la fiche
ouvrant le bon chapitre ; dézoom du texte sans bande blanche ; une
seule barre de défilement dans les deux modes, sur les deux livres ;
séparation visible entre chapitres (fond neutre, ombre, feuilles
distinctes) ; table des matières alignée sur la hauteur de la zone de
lecture, vérifiée sur les deux livres et dans les deux modes ; panneau
de notes déplacé, redimensionné et fermé par sa croix dans les deux
lecteurs (en-tête glissable sur toute sa hauteur, ⋮ et croix côte à
côte), position/taille retrouvées après rechargement, sans corruption
même en fermant juste après un déplacement.

`pytest tests/` (298 tests) au vert.

### Barre d'outils des lecteurs (fait)

Habillage seul, décidé avec Gautier : ni le modèle de données, ni la
progression, ni le panneau de notes lui-même n'y touchent. Les quatre
lecteurs ont désormais une barre d'outils au même endroit, à la même
hauteur, directement au-dessus du contenu - jamais un autre élément
entre les deux, contrairement à avant (la barre du lecteur vidéo vivait
sous `.nav-buttons`, celle du lecteur audio sous `<audio>`).

- **PDF et EPUB : contenu de la barre inchangé** (mode de lecture,
  navigation de page/chapitre, zoom/taille de texte, bouton "Notes" à
  droite comme avant).
- **Vidéo et audio : le titre du média rejoint la barre, à gauche du
  bouton "Notes".** Le `<h1>` séparé qui le portait auparavant
  disparaît - `.reader-toolbar-title` (`flex: 1 1 auto`, tronqué à
  l'ellipsis sur un titre long) occupe sa place, `justify-content:
  space-between` de `.reader-toolbar` suffit à séparer les deux sans
  correctif d'alignement supplémentaire (`.video-notes-toolbar`/
  `.audio-notes-toolbar`, qui forçaient `justify-content: flex-end`
  pour un unique groupe "Notes", deviennent inutiles et sont retirées).
  Pour la vidéo, `goToMedia` (changement de vidéo sans rechargement)
  met à jour ce titre à la place de l'ancien `<h1>` à chaque
  navigation. `.nav-buttons` (Précédent/Suivant) reste sous la vidéo,
  à sa place attendue - jamais remonté dans la barre.
- **`<h1>` retiré aussi pour PDF et EPUB**, sur une question distincte
  de Gautier : le titre du livre n'a pas sa place dans la barre comme
  pour vidéo/audio (un livre ne change jamais de titre d'une page à
  l'autre, contrairement à une leçon vidéo) - mais le fil d'Ariane
  juste au-dessus (`.back`, "← {{ media['item_title'] }}") porte déjà
  ce même titre : le garder en plus en `<h1>` le répétait à deux
  lignes d'intervalle, pour aucune information supplémentaire. Retiré
  purement et simplement, sans rejoindre la barre.
- **Colonne latérale et zone de contenu**, vérifiées après ce
  déplacement : leur position/hauteur (voir "Hauteur et position des
  colonnes latérales" plus haut) est calculée en JS à partir de la
  position réelle du lecteur/de `#reader-viewport`, jamais d'une
  valeur figée liée à la barre - rien à changer, la remontée du haut
  de page (disparition du `<h1>`) se répercute automatiquement, la
  zone de contenu gagne même en hauteur disponible pour PDF/EPUB.
- **Résidu mesuré, sans rapport avec cette demande** : la barre
  PDF/EPUB fait 3px de plus en hauteur que celle de vidéo/audio (42px
  contre 39px), à cause du champ numérique de page/chapitre (`<input>`,
  26px) légèrement plus haut que les boutons (23px) - déjà là avant
  cette tranche, non touché puisque le contenu de cette barre reste
  inchangé pour PDF/EPUB.

Vérifié par mesure (`getBoundingClientRect`, fenêtre 1440px) plutôt
qu'à l'œil seul : les quatre barres commencent au même `toolbar_top`
(56px), et la colonne latérale/le contenu de chaque lecteur restent
alignés sur le haut du lecteur lui-même, pas sur la barre.

`pytest tests/` (300 tests) au vert.

### Notes sur la fiche d'item (fait)

Termine l'unification commencée sur les quatre lecteurs : la fiche
(`item_detail.html`) n'a plus son propre bloc de notes intégré en bas
de page, pour les trois types de contenu (formation, livre,
audiobook) - remplacé par le même panneau flottant partagé
(`templates/_note_panel.html`) que les lecteurs, jamais une variante.
`render_note_panel_markup(item['id'], note_text, note_updated_at)`
pose le `<dialog>` (sans `player_context` : la fiche n'a pas de
position à marquer dans un média, contrairement à un lecteur - la
branche "Insérer un repère" de `_note_widget.html` ne s'affiche donc
pas ici) ; `render_note_panel_script(...)` reçoit les mêmes quatre
préférences (`note_panel_left/top/width/height`) que les lecteurs,
lues par `fetch_reading_preferences` dans la route `/item/<id>` - un
seul réglage d'application, jamais par item.

- **Bouton "Notes" dans la rangée d'actions du hero**, à côté de "Tout
  recommencer" - `<div class="hero-actions">` existe désormais
  systématiquement, même sans média lisible (livre dans un format que
  Studia ne sait pas encore ouvrir) : c'est le seul moyen d'écrire une
  première note, elle ne peut donc jamais être absente. Porte
  `id="reader-toggle-notes"`, l'identifiant que
  `render_note_panel_script` cherche pour câbler l'ouverture/
  fermeture - seule sa présentation change (`.btn-secondary`, comme
  "Tout recommencer", plutôt que `.btn-mini` dans un
  `.reader-toolbar`), jamais le mécanisme.
- **Indicateur discret** quand une note existe déjà pour l'item : un
  simple point plein (`.notes-indicator`, 6px, couleur d'accent)
  accolé au libellé du bouton. Posé par une seule condition Jinja,
  évaluée une fois en tête du hero
  (`{% set has_note = note_text and note_text.strip() %}`) et
  réutilisée telle quelle pour l'indicateur, le bouton de l'onglet et
  son panneau ci-dessous - jamais recalculée trois fois. Aucune donnée
  inventée au-delà de "une note existe" : pas de compte, pas d'aperçu.
- **Onglet "Notes", après "Ressources"** - gouverné par cette même
  variable `has_note`, à la fois sur son bouton
  (`data-tab-target="notes"`) et sur son panneau (`data-panel="notes"`) :
  absent des deux tant que la note est vide, jamais un onglet vide
  affiché à la place (contrairement à l'onglet Ressources, toujours
  présent, qui affiche "Aucune ressource." en son absence).
- **Contenu de l'onglet : aperçu seul, jamais d'édition.** Un
  `<div id="notes-tab-preview" class="note-preview">` rempli au
  chargement de la page par `window.renderNoteMarkdown(...)` - le
  moteur Markdown de `_note_widget.html` (`renderMarkdown`), exposé sur
  `window` pour cette seule raison plutôt que réimplémenté une seconde
  fois. Un repère (horodaté pour vidéo/audio, page pour un PDF,
  chapitre pour un EPUB) y reste un lien cliquable, rendu par ce même
  moteur : cliqué, il ouvre directement le lecteur correspondant
  (`/watch`, `/listen`, `/read` ou `/read-epub`) à la position, la page
  ou le chapitre visés.
- **Bouton d'impression propre à l'onglet** (`id="notes-tab-print"`),
  qui se contente d'appeler `window.print()` - le mécanisme
  d'impression est le même que celui du panneau (déjà câblé par
  `_note_widget.html`, sur l'unique instance de `render_note` de la
  page, celle du panneau) : la page imprimée montre le titre de
  l'item, la date du jour et la note rendue en Markdown
  (`render_print_block`, `#print-only`, `beforeprint`) - rien de
  propre à l'onglet, aucun second mécanisme d'impression.

Vérifié dans le navigateur, sur les trois types, avec et sans note :
bouton "Notes" toujours atteignable (y compris un livre sans bouton
principal) ; indicateur et onglet apparaissant après l'écriture d'une
première note depuis la fiche, disparaissant tous les deux si la note
est vidée ; panneau ouvert depuis la fiche identique en tout point à
celui des lecteurs (glisser-déposer, poignée de redimensionnement,
position/taille mémorisées). Le menu ⋮ du hero n'a pas été touché,
toujours ses trois entrées.

`pytest tests/` (307 tests) au vert.

## Méthode — backlog

Avant de commencer une tranche, relire le backlog et signaler les
lignes qui touchent le périmètre de cette tranche. Une ligne concernée
doit être traitée ou explicitement écartée avec sa raison, jamais
ignorée en silence. Ne pas coder quelque chose qui rend une ligne du
backlog plus difficile à corriger sans le signaler d'abord.

## Backlog (ne pas traiter sans demande explicite)

- La liste de fichiers en tête de "### État actuel" ne reflète plus ce
  qui est réellement présent : la moitié environ des gabarits de
  `templates/` n'y figurent pas (9 sur 18 constatés), dont
  `templates/_note_panel.html`, cité par la section "Notes sur la
  fiche d'item" ci-dessus sans jamais y avoir été ajouté ; un fichier
  Python racine manque (`epub_book.py`) ; deux fichiers de test
  manquent (`test_epub.py`, `test_progress.py`) ; le nombre de tests
  annoncé (70) date de très loin (307 aujourd'hui). À reprendre en une
  passe séparée, pas au fil des tranches suivantes.
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
- Sur la vraie bibliothèque de Gautier, la couverture des livres
  traités à la main pour OfflineU est encodée en base64 à l'intérieur
  du fichier de présentation HTML, jamais posée à côté en `cover.jpg` :
  `covers.py` (dossier de l'item, puis première page du PDF) ne la
  trouvera donc jamais pour ces items. À traiter avec le module
  d'import (voir plus bas) : en extraire l'image et la mettre en cache
  comme un fichier séparé. Les fichiers de la bibliothèque ne doivent
  jamais être modifiés pour ça — OfflineU tourne toujours dessus et a
  besoin de ce base64 tel quel.
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
- Signets internes d'un PDF (sa propre table des matières, embarquée
  dans le fichier - PDF.js sait la lire) : à afficher dans une colonne
  latérale, selon exactement les mêmes règles de position et de hauteur
  que la playlist vidéo et la table des matières EPUB (voir "Hauteur et
  position des colonnes latérales") - alignée sur le haut du cadre de
  lecture, défilant avec la page, jamais collée à l'écran. Explicitement
  hors périmètre du lecteur PDF actuel (voir "Lecteur PDF", "hors
  périmètre"). Tranche à part, à cadrer avec Gautier le moment venu -
  en particulier ce qui se passe pour un PDF sans signets.
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
