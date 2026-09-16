"""Tests de l'application web Studia (grille + fiche d'item).

Reprend les mêmes fixtures que test_library_index.py : une
bibliothèque jetable construite dans un dossier temporaire, scannée
avant chaque test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from library_index import format_duration, scan_library  # noqa: E402
from studia import create_app  # noqa: E402


def make_file(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"

    book = root / "Adobe Illustrator CS6 (Adobe Press)"
    make_file(book / "920 - Adobe Illustrator CS6 - Adobe Press.pdf")
    make_file(book / "Exercices.zip")
    make_file(
        book / "000 - presentation.html",
        """
        <html><body>
        <h1>Adobe Illustrator CS6</h1>
        <table>
        <tr><td class="k">Auteur</td><td>Adobe Press</td></tr>
        </table>
        <h2>Description</h2>
        <p>Bonjour Adobe.</p>
        </body></html>
        """.encode(),
    )

    deep = root / "Motion Design - la formation complete (TUTO.com)"
    make_file(deep / "01 - Bases" / "001 - Interface.mp4")
    make_file(deep / "01 - Bases" / "002 - Calques.mp4")
    make_file(deep / "02 - Animation" / "003 - Keyframes.mp4")
    make_file(deep / "Ressources" / "projets.zip")

    return root


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "data" / "studia.db"


@pytest.fixture
def client(library: Path, db: Path):
    scan_library(library, db, verbose=False)
    app = create_app(library, db)
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        yield test_client


def item_id_by_title(client, title: str) -> int:
    import sqlite3

    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)

    try:
        row = conn.execute(
            "SELECT id FROM items WHERE title = ?", (title,)
        ).fetchone()
    finally:
        conn.close()

    return row[0]


def book_candidate_id(client, item_id: int, source: str) -> int:
    import sqlite3

    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)

    try:
        row = conn.execute(
            "SELECT id FROM book_candidates WHERE item_id = ? AND source = ?",
            (item_id, source),
        ).fetchone()
    finally:
        conn.close()

    return row[0]


def media_id_by_relative_path(client, relative_path: str) -> int:
    import sqlite3

    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)

    try:
        row = conn.execute(
            "SELECT id FROM media WHERE relative_path = ?", (relative_path,)
        ).fetchone()
    finally:
        conn.close()

    return row[0]


def test_grille_liste_les_items(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert b"Adobe Illustrator CS6" in response.data
    assert b"Motion Design" in response.data


def test_grille_bibliotheque_vide_affiche_un_etat_dedie(tmp_path: Path) -> None:
    empty_library = tmp_path / "empty-library"
    empty_library.mkdir()
    db_path = tmp_path / "empty.db"
    scan_library(empty_library, db_path, verbose=False)

    app = create_app(empty_library, db_path)
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        response = test_client.get("/")
        data = response.data.decode()

        assert response.status_code == 200
        assert "Bibliothèque vide" in data
        # Pas de barre de recherche/filtres pour une bibliothèque sans contenu.
        assert 'id="library-search"' not in data


def test_fiche_item_liste_les_chapitres_en_ordre(client) -> None:
    item_id = item_id_by_title(client, "Motion Design - la formation complete (TUTO.com)")

    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert "01 - Bases" in data
    assert "02 - Animation" in data
    assert data.index("01 - Bases") < data.index("02 - Animation")
    assert "Interface" in data
    assert "Keyframes" in data


def test_fiche_item_liste_les_ressources(client) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")

    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert "Exercices.zip" in data


def test_fiche_item_inconnu_renvoie_404(client) -> None:
    response = client.get("/item/999")

    assert response.status_code == 404
    assert "introuvable" in response.data.decode()


def test_chapitre_racine_non_consecutif_reste_un_seul_groupe(
    tmp_path: Path, db: Path
) -> None:
    """Des médias à la racine avant et après un sous-dossier ne doivent
    former qu'un seul groupe "Racine", pas deux.

    Les noms sont choisis pour que le tri naturel place les deux
    fichiers de racine de part et d'autre du sous-dossier : media_rows
    n'est alors plus consécutif par parent_path, ce que groupby()
    traiterait à tort comme deux chapitres "" distincts.
    """

    root = tmp_path / "library"
    item = root / "Item entrelace"

    make_file(item / "1 - Root A.mp4")
    make_file(item / "2 - Chapitre" / "1 - Video B.mp4")
    make_file(item / "3 - Root C.mp4")

    scan_library(root, db, verbose=False)

    app = create_app(root, db)
    app.config["TESTING"] = True

    with app.test_client() as test_client:
        item_id = item_id_by_title(test_client, "Item entrelace")
        response = test_client.get(f"/item/{item_id}")
        data = response.data.decode()

    assert response.status_code == 200
    # Un seul groupe "Racine", pas un par plage consecutive de fichiers.
    assert data.count(">Racine<") == 1
    # 2 chapitres (Racine + "2 - Chapitre") dans l'onglet Programme.
    assert data.count('class="chapter-title"') == 2
    # A l'interieur du groupe, l'ordre sort_order des deux fichiers de
    # racine est respecte malgre le sous-dossier intercale entre eux.
    assert data.index("Root A") < data.index("Root C")
    assert "Video B" in data


def test_page_lecteur_video_affiche_le_lecteur(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )

    response = client.get(f"/watch/{media_id}")

    assert response.status_code == 200
    assert b"<video" in response.data


def test_fichier_video_supporte_les_requetes_range(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )

    response = client.get(
        f"/media/{media_id}/file", headers={"Range": "bytes=0-0"}
    )

    assert response.status_code == 206
    assert response.headers["Content-Type"] == "video/mp4"


def test_media_non_video_renvoie_404_sur_lecteur_et_fichier(client) -> None:
    media_id = media_id_by_relative_path(
        client, "920 - Adobe Illustrator CS6 - Adobe Press.pdf"
    )

    assert client.get(f"/watch/{media_id}").status_code == 404
    assert client.get(f"/media/{media_id}/file").status_code == 404


def test_fiche_affiche_la_presentation_avec_nos_propres_moyens(client) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")

    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert response.status_code == 200
    # Rendu par notre propre gabarit, pas la page fournisseur telle quelle.
    assert "<iframe" not in data
    assert "Adobe Press" in data  # fait extrait de la fiche technique
    assert "Bonjour Adobe." in data  # paragraphe extrait
    # La presentation ne doit pas apparaitre en double dans la liste
    # de ressources generique.
    assert "000 - presentation.html" not in data


def test_lecteur_video_reprend_a_la_position_donnee(client) -> None:
    # Le fragment d'URL #t= n'est pas fiable pour positionner un
    # <video> local : la reprise se fait via un script sur
    # loadedmetadata, jamais via le fragment dans l'attribut src.
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )

    response = client.get(f"/watch/{media_id}?t=238")
    data = response.data.decode()

    assert response.status_code == 200
    assert "loadedmetadata" in data
    assert "player.currentTime = 238" in data
    assert "#t=" not in data


def test_lecteur_video_sans_position_ne_cherche_pas_a_reprendre(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )

    response = client.get(f"/watch/{media_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert "loadedmetadata" not in data


def test_lecteur_video_affiche_precedent_et_suivant(client) -> None:
    prev_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )
    current_id = media_id_by_relative_path(
        client, "01 - Bases/002 - Calques.mp4"
    )
    next_id = media_id_by_relative_path(
        client, "02 - Animation/003 - Keyframes.mp4"
    )

    response = client.get(f"/watch/{current_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert f"/watch/{prev_id}" in data
    assert f"/watch/{next_id}" in data
    # Playlist : les trois videos du cours doivent apparaitre.
    assert "Interface" in data
    assert "Calques" in data
    assert "Keyframes" in data


def test_lecteur_video_premiere_video_sans_precedent(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )

    response = client.get(f"/watch/{media_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert '<span class="disabled">← Précédent</span>' in data


def test_lecteur_video_derniere_video_sans_suivant(client) -> None:
    media_id = media_id_by_relative_path(
        client, "02 - Animation/003 - Keyframes.mp4"
    )

    response = client.get(f"/watch/{media_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert '<span class="disabled">Suivant →</span>' in data
    # Pas de video suivante : pas de script d'enchainement automatique
    # sur la fin de la vidéo (le bloc-notes a son propre JS, sans rapport).
    assert "addEventListener('ended'" not in data


# --------------------------------------------------------------------
# Métadonnées de livre (Google Books / Open Library)
# --------------------------------------------------------------------

FAKE_CANDIDATES = [
    {
        "source": "google_books",
        "source_id": "gb-1",
        "title": "Adobe Illustrator CS6",
        "authors": "Adobe Press",
        "publisher": "Pearson",
        "published_year": "2012",
        "isbn": "9782744025488",
        "cover_url": "https://example.com/gb.jpg",
    },
    {
        "source": "open_library",
        "source_id": "ol-1",
        "title": "Exploring Adobe Illustrator CS6",
        "authors": "Toni Toland",
        "publisher": None,
        "published_year": "2012",
        "isbn": None,
        "cover_url": None,
    },
]


def test_recherche_livre_affiche_les_candidats(client, monkeypatch) -> None:
    import studia

    monkeypatch.setattr(
        studia, "search_candidates", lambda query, isbn=None: FAKE_CANDIDATES
    )

    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")

    response = client.post(
        f"/item/{item_id}/book-search",
        data={"query": "Adobe Illustrator CS6"},
        follow_redirects=True,
    )
    data = response.data.decode()

    assert response.status_code == 200
    assert "Adobe Illustrator CS6" in data
    assert "Exploring Adobe Illustrator CS6" in data
    assert "Utiliser celle-ci" in data


def test_recherche_livre_sur_item_non_livre_renvoie_404(client, monkeypatch) -> None:
    import studia

    monkeypatch.setattr(
        studia, "search_candidates", lambda query, isbn=None: FAKE_CANDIDATES
    )

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )

    response = client.post(
        f"/item/{item_id}/book-search", data={"query": "Motion Design"}
    )

    assert response.status_code == 404


def test_accepter_candidat_affiche_les_metadonnees_validees(client, monkeypatch) -> None:
    import studia

    monkeypatch.setattr(
        studia, "search_candidates", lambda query, isbn=None: FAKE_CANDIDATES
    )

    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/book-search", data={"query": "Adobe Illustrator CS6"})

    candidate_id = book_candidate_id(client, item_id, "google_books")
    response = client.post(
        f"/item/{item_id}/book-candidate/{candidate_id}/accept",
        follow_redirects=True,
    )
    data = response.data.decode()

    assert response.status_code == 200
    assert "Pearson" in data
    assert "9782744025488" in data
    assert "Google Books" in data
    # Le candidat non retenu ne doit plus etre propose comme en attente.
    assert "Utiliser celle-ci" not in data


def test_rejeter_candidat_le_memorise_et_ne_le_represente_pas(
    client, monkeypatch
) -> None:
    import studia

    monkeypatch.setattr(
        studia, "search_candidates", lambda query, isbn=None: FAKE_CANDIDATES
    )

    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/book-search", data={"query": "Adobe Illustrator CS6"})

    candidate_id = book_candidate_id(client, item_id, "open_library")
    response = client.post(
        f"/item/{item_id}/book-candidate/{candidate_id}/reject",
        follow_redirects=True,
    )
    data = response.data.decode()

    assert response.status_code == 200
    assert "Candidats rejetés (1)" in data

    # Une nouvelle recherche qui retrouve le meme candidat (meme
    # source + source_id) ne doit pas le re-proposer.
    response = client.post(
        f"/item/{item_id}/book-search",
        data={"query": "Adobe Illustrator CS6"},
        follow_redirects=True,
    )
    data = response.data.decode()

    assert "Candidats rejetés (1)" in data


def test_annuler_rejet_remet_le_candidat_en_attente(client, monkeypatch) -> None:
    import studia

    monkeypatch.setattr(
        studia, "search_candidates", lambda query, isbn=None: FAKE_CANDIDATES
    )

    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/book-search", data={"query": "Adobe Illustrator CS6"})

    candidate_id = book_candidate_id(client, item_id, "open_library")
    client.post(f"/item/{item_id}/book-candidate/{candidate_id}/reject")

    response = client.post(
        f"/item/{item_id}/book-candidate/{candidate_id}/unreject",
        follow_redirects=True,
    )
    data = response.data.decode()

    assert response.status_code == 200
    assert "Exploring Adobe Illustrator CS6" in data
    assert "Utiliser celle-ci" in data


def test_saisie_manuelle_valide_directement(client) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")

    response = client.post(
        f"/item/{item_id}/book-manual",
        data={
            "title": "Adobe Illustrator CS6",
            "authors": "Adobe Press",
            "publisher": "Pearson",
            "published_year": "2012",
            "isbn": "9782744025488",
        },
        follow_redirects=True,
    )
    data = response.data.decode()

    assert response.status_code == 200
    assert "Pearson" in data
    assert "Saisie manuelle" in data


def test_rescan_ne_defait_pas_un_choix_valide(
    client, monkeypatch, library, db
) -> None:
    import studia
    from library_index import scan_library

    monkeypatch.setattr(
        studia, "search_candidates", lambda query, isbn=None: FAKE_CANDIDATES
    )

    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/book-search", data={"query": "Adobe Illustrator CS6"})
    candidate_id = book_candidate_id(client, item_id, "google_books")
    client.post(f"/item/{item_id}/book-candidate/{candidate_id}/accept")

    scan_library(library, db, verbose=False)

    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "Pearson" in data
    assert "9782744025488" in data


def test_recherche_isbn_priorisee_sur_le_titre(client, monkeypatch) -> None:
    import studia

    appels = []

    def fake_search(query, isbn=None):
        appels.append((query, isbn))
        return []

    monkeypatch.setattr(studia, "search_candidates", fake_search)

    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")

    client.post(
        f"/item/{item_id}/book-search",
        data={"query": "voir 9782744025488 pour cette edition"},
    )

    assert appels == [("voir 9782744025488 pour cette edition", "9782744025488")]


# Cas extrêmes (revue, point 34) : construits dans une base et une
# bibliothèque jetables (tmp_path), jamais dans la bibliothèque réelle
# de Gautier. Le but n'est pas d'obtenir des chiffres exacts ("128 h
# 35", "124 chapitres") mais de vérifier que la fiche ne plante pas et
# n'invente rien face à des valeurs bien plus grandes ou bien plus
# vides que celles de la bibliothèque de test habituelle.


def test_item_avec_titre_auteur_tres_longs_et_beaucoup_de_chapitres(
    tmp_path: Path,
) -> None:
    root = tmp_path / "library"
    long_title = (
        "Une formation complete et particulierement detaillee sur absolument "
        "tous les aspects du sujet, avec un titre si long qu il devrait se "
        "faire couper quelque part dans l interface (TUTO.com)"
    )
    course = root / long_title
    for n in range(1, 125):
        make_file(course / f"{n:04d} - Chapitre {n}" / "001 - Video.mp4")

    long_author = (
        "Jean-Baptiste-Alphonse-Theodore de Montmorency-Lavalette, avec la "
        "participation exceptionnelle de nombreux autres formateurs dont les "
        "noms ne tiendraient pas sur une seule ligne de la fiche"
    )
    make_file(
        course / "000 - presentation.html",
        f"""
        <html><body>
        <h1>{long_title}</h1>
        <table>
        <tr><td class="k">Formateur(s)</td><td>{long_author}</td></tr>
        </table>
        </body></html>
        """.encode(),
    )

    db = tmp_path / "data" / "studia.db"
    scan_library(root, db, verbose=False)

    app = create_app(root, db)
    app.config["TESTING"] = True

    with app.test_client() as client:
        import sqlite3

        conn = sqlite3.connect(db)
        try:
            item_id = conn.execute(
                "SELECT id FROM items WHERE title = ?", (long_title,)
            ).fetchone()[0]
            # 124 vidéos de 3735 secondes : plusieurs jours au total,
            # pour vérifier que le format d'affichage (h/min) ne
            # suppose pas une durée raisonnable.
            conn.execute(
                "UPDATE media SET duration_seconds = 3735.0, probed_at = 'test' "
                "WHERE item_id = ?",
                (item_id,),
            )
            conn.commit()
            total_seconds = conn.execute(
                "SELECT SUM(duration_seconds) FROM media WHERE item_id = ?",
                (item_id,),
            ).fetchone()[0]
        finally:
            conn.close()

        response = client.get(f"/item/{item_id}")
        data = response.data.decode()

        assert response.status_code == 200
        assert format_duration(total_seconds) in data
        assert "124 chapitres" in data
        assert long_title in data
        assert long_author in data
        assert data.count('class="programme-chapter"') == 124

        # La grille aussi doit survivre à un titre de cette taille.
        assert client.get("/").status_code == 200


def test_item_sans_metadonnees_ni_couverture_avec_beaucoup_de_ressources(
    tmp_path: Path,
) -> None:
    root = tmp_path / "library"
    item_dir = root / "Dossier sans aucune metadonnee"
    make_file(item_dir / "contenu.pdf")
    for n in range(1, 41):
        make_file(item_dir / f"ressource-{n:03d}.zip")

    db = tmp_path / "data" / "studia.db"
    scan_library(root, db, verbose=False)

    app = create_app(root, db)
    app.config["TESTING"] = True

    with app.test_client() as client:
        import sqlite3

        conn = sqlite3.connect(db)
        try:
            item_id = conn.execute(
                "SELECT id FROM items WHERE title = ?",
                ("Dossier sans aucune metadonnee",),
            ).fetchone()[0]
        finally:
            conn.close()

        response = client.get(f"/item/{item_id}")
        data = response.data.decode()

        assert response.status_code == 200
        # Aucune extraction de couverture n'a été lancée (--covers est
        # un pas manuel séparé) : pas d'image, juste le repli par type.
        assert "cover-placeholder" in data
        # Aucune présentation, aucune fiche livre validée : un état
        # vide honnête plutôt qu'une valeur inventée.
        assert "Pas de description disponible." in data
        # Deux fois chacune : le nom visible (sans extension) et
        # l'infobulle title="..." (nom complet, ajoutée pour les titres
        # tronqués).
        assert data.count("ressource-0") == 80
        assert "None" not in data
