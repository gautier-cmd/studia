"""Tests du scanner SQLite de Studia.

Chaque test construit une bibliotheque jetable dans un dossier
temporaire fourni par pytest (tmp_path), la scanne, puis verifie
l'etat de la base. Aucun fichier reel de la bibliotheque de test
n'est touche.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from library_index import (  # noqa: E402
    NBSP,
    SCHEMA_VERSION,
    format_duration,
    natural_key,
    parent_of,
    probe_duration,
    scan_library,
)


def make_file(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def query(db_path: Path, sql: str, params: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(db_path)

    try:
        return conn.execute(sql, params).fetchall()

    finally:
        conn.close()


def execute(db_path: Path, sql: str, params: tuple = ()) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        conn.execute(sql, params)
        conn.commit()

    finally:
        conn.close()


def set_progress(db_path: Path, media_id: int, seconds: float) -> None:
    execute(
        db_path,
        """
        INSERT OR REPLACE INTO progress(
            user_id, media_id, position_seconds, completed, updated_at
        )
        VALUES (1, ?, ?, 0, datetime('now'))
        """,
        (media_id, seconds),
    )


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """Une bibliotheque miniature couvrant les quatre cas de test reels."""

    root = tmp_path / "library"

    # Cas 1 : livre PDF + ressource ZIP + page de presentation.
    book = root / "Adobe Illustrator CS6 (Adobe Press)"
    make_file(book / "920 - Adobe Illustrator CS6 - Adobe Press.pdf")
    make_file(book / "Exercices.zip")
    make_file(book / "000 - presentation.html")

    # Cas 2 : livre audio M4B.
    audiobook = root / "S organiser pour reussir (David Allen)"
    make_file(audiobook / "S organiser pour reussir.m4b")
    make_file(audiobook / "Ressources.zip")

    # Cas 3 : formation video a plat, avec des PDF qui sont
    # des ressources et non des livres.
    course = root / "Devenez Copywriter avec les IA (TUTO.com)"
    make_file(course / "001 - Presentation.mp4")
    make_file(course / "002 - Le metier.mp4")
    make_file(course / "Support de cours.pdf")
    make_file(course / "Modeles.zip")

    # Cas 4 : hierarchie profonde.
    deep = root / "Motion Design - la formation complete (TUTO.com)"
    make_file(deep / "01 - Bases" / "001 - Interface.mp4")
    make_file(deep / "01 - Bases" / "002 - Calques.mp4")
    make_file(deep / "02 - Animation" / "003 - Keyframes.mp4")
    make_file(deep / "Ressources" / "projets.zip")

    return root


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "data" / "studia.db"


# --------------------------------------------------------------------
# Fonctions utilitaires
# --------------------------------------------------------------------


def test_tri_naturel_place_10_apres_9() -> None:
    noms = ["10 - dix.mp4", "9 - neuf.mp4", "1 - un.mp4"]

    assert sorted(noms, key=natural_key) == [
        "1 - un.mp4",
        "9 - neuf.mp4",
        "10 - dix.mp4",
    ]


def test_parent_of() -> None:
    assert parent_of("fichier.mp4") == ""
    assert parent_of("01 - Bases/001 - Interface.mp4") == "01 - Bases"
    assert parent_of("a/b/c.mp4") == "a/b"


def test_format_duration() -> None:
    # Espace insécable entre le nombre et son unité (voir NBSP) : le
    # bloc entier ne doit jamais se couper entre deux lignes.
    assert format_duration(None) == "—"
    assert format_duration(0) == "—"
    assert format_duration(45) == f"45{NBSP}s"
    assert format_duration(125) == f"2{NBSP}min{NBSP}05"
    assert format_duration(3725) == f"1{NBSP}h{NBSP}02"


def test_probe_duration_sur_faux_fichier(tmp_path: Path) -> None:
    faux = tmp_path / "faux.mp4"
    faux.write_bytes(b"pas une video")

    # Sans ffprobe installe comme avec, un fichier invalide
    # ne doit jamais faire echouer le scanner.
    assert probe_duration(faux) is None


# --------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------


def test_classification_des_items(library: Path, db: Path) -> None:
    scan_library(library, db, verbose=False)

    types = dict(
        query(db, "SELECT title, item_type FROM items")
    )

    assert types["Adobe Illustrator CS6 (Adobe Press)"] == "book"
    assert types["S organiser pour reussir (David Allen)"] == "audiobook"
    assert types["Devenez Copywriter avec les IA (TUTO.com)"] == "course"
    assert types["Motion Design - la formation complete (TUTO.com)"] == "course"


def test_pdf_de_formation_est_une_ressource(library: Path, db: Path) -> None:
    scan_library(library, db, verbose=False)

    medias = query(
        db,
        """
        SELECT m.relative_path FROM media m
        JOIN items i ON i.id = m.item_id
        WHERE i.item_type = 'course'
        """,
    )
    chemins = {row[0] for row in medias}

    assert "Support de cours.pdf" not in chemins

    ressources = query(
        db,
        """
        SELECT r.relative_path FROM resources r
        JOIN items i ON i.id = r.item_id
        WHERE i.title LIKE 'Devenez Copywriter%'
        """,
    )

    assert "Support de cours.pdf" in {row[0] for row in ressources}

    livres = query(
        db,
        """
        SELECT m.media_type FROM media m
        JOIN items i ON i.id = m.item_id
        WHERE i.title LIKE 'Adobe Illustrator%'
        """,
    )

    assert livres == [("book",)]


# --------------------------------------------------------------------
# Structure : chapitres et ordre
# --------------------------------------------------------------------


def test_hierarchie_profonde(library: Path, db: Path) -> None:
    scan_library(library, db, verbose=False)

    chemins = {
        row[0]
        for row in query(
            db,
            """
            SELECT m.relative_path FROM media m
            JOIN items i ON i.id = m.item_id
            WHERE i.title LIKE 'Motion Design%'
            """,
        )
    }

    assert chemins == {
        "01 - Bases/001 - Interface.mp4",
        "01 - Bases/002 - Calques.mp4",
        "02 - Animation/003 - Keyframes.mp4",
    }


def test_parent_path_identifie_les_chapitres(
    library: Path, db: Path
) -> None:
    scan_library(library, db, verbose=False)

    chapitres = {
        row[0]
        for row in query(
            db,
            """
            SELECT DISTINCT m.parent_path FROM media m
            JOIN items i ON i.id = m.item_id
            WHERE i.title LIKE 'Motion Design%'
            """,
        )
    }

    assert chapitres == {"01 - Bases", "02 - Animation"}

    # Un item a plat n'a aucun chapitre.
    plats = {
        row[0]
        for row in query(
            db,
            """
            SELECT DISTINCT m.parent_path FROM media m
            JOIN items i ON i.id = m.item_id
            WHERE i.title LIKE 'Devenez Copywriter%'
            """,
        )
    }

    assert plats == {""}


def test_sort_order_suit_le_tri_naturel(tmp_path: Path, db: Path) -> None:
    root = tmp_path / "library"
    item = root / "Formation non paddee"

    for nom in ["1 - un.mp4", "2 - deux.mp4", "9 - neuf.mp4", "10 - dix.mp4"]:
        make_file(item / nom)

    scan_library(root, db, verbose=False)

    ordre = [
        row[0]
        for row in query(
            db,
            "SELECT relative_path FROM media ORDER BY sort_order",
        )
    ]

    assert ordre == [
        "1 - un.mp4",
        "2 - deux.mp4",
        "9 - neuf.mp4",
        "10 - dix.mp4",
    ]


def test_sort_order_repart_de_un_pour_chaque_item(
    library: Path, db: Path
) -> None:
    scan_library(library, db, verbose=False)

    for (titre,) in query(db, "SELECT title FROM items"):
        rangs = [
            row[0]
            for row in query(
                db,
                """
                SELECT m.sort_order FROM media m
                JOIN items i ON i.id = m.item_id
                WHERE i.title = ?
                ORDER BY m.sort_order
                """,
                (titre,),
            )
        ]

        assert rangs == list(range(1, len(rangs) + 1))


# --------------------------------------------------------------------
# Rescan : ids, progression, suppressions
# --------------------------------------------------------------------


def test_rescan_preserve_ids_et_progression(library: Path, db: Path) -> None:
    scan_library(library, db, verbose=False)

    avant = query(db, "SELECT id, relative_path FROM media ORDER BY id")
    set_progress(db, avant[0][0], 123.4)

    scan_library(library, db, verbose=False)

    apres = query(db, "SELECT id, relative_path FROM media ORDER BY id")

    assert apres == avant

    progression = query(
        db, "SELECT media_id, position_seconds FROM progress"
    )

    assert progression == [(avant[0][0], 123.4)]


def test_fichier_supprime_disparait_sans_toucher_aux_voisins(
    library: Path, db: Path
) -> None:
    scan_library(library, db, verbose=False)

    item = "Devenez Copywriter avec les IA (TUTO.com)"

    medias = query(
        db,
        """
        SELECT m.id, m.relative_path FROM media m
        JOIN items i ON i.id = m.item_id
        WHERE i.title = ?
        ORDER BY m.relative_path
        """,
        (item,),
    )

    garde_id, garde_path = medias[0]
    supprime_id, supprime_path = medias[1]

    set_progress(db, garde_id, 42.0)
    set_progress(db, supprime_id, 99.0)

    (library / item / supprime_path).unlink()

    scan_library(library, db, verbose=False)

    restants = {row[0] for row in query(db, "SELECT id FROM media")}

    assert garde_id in restants
    assert supprime_id not in restants

    progression = query(
        db, "SELECT media_id, position_seconds FROM progress"
    )

    assert progression == [(garde_id, 42.0)]


def test_item_supprime_disparait_de_lindex(library: Path, db: Path) -> None:
    scan_library(library, db, verbose=False)

    assert len(query(db, "SELECT id FROM items")) == 4

    shutil.rmtree(library / "Adobe Illustrator CS6 (Adobe Press)")

    scan_library(library, db, verbose=False)

    titres = {row[0] for row in query(db, "SELECT title FROM items")}

    assert "Adobe Illustrator CS6 (Adobe Press)" not in titres
    assert len(titres) == 3


def test_unicode_et_apostrophes(tmp_path: Path, db: Path) -> None:
    root = tmp_path / "library"
    item = root / "Formation accentuée"

    noms = [
        "Leçon 1 - l'apostrophe droite.mp4",
        "Leçon 2 — l\u2019œuvre (été).mp4",
        "Fichier ÀÉÎÔÙ çæœ.mp4",
    ]

    for nom in noms:
        make_file(item / nom)

    scan_library(root, db, verbose=False)

    chemins = {
        row[0]
        for row in query(db, "SELECT relative_path FROM media")
    }

    assert chemins == set(noms)


# --------------------------------------------------------------------
# Durees
# --------------------------------------------------------------------


def test_duree_conservee_si_le_fichier_ne_change_pas(
    library: Path, db: Path
) -> None:
    scan_library(library, db, verbose=False)

    media_id = query(db, "SELECT id FROM media ORDER BY id")[0][0]

    execute(
        db,
        "UPDATE media SET duration_seconds = 600.0, probed_at = 'test' "
        "WHERE id = ?",
        (media_id,),
    )

    scan_library(library, db, verbose=False)

    duree = query(
        db, "SELECT duration_seconds FROM media WHERE id = ?", (media_id,)
    )

    assert duree == [(600.0,)]


def test_duree_invalidee_si_la_taille_change(
    library: Path, db: Path
) -> None:
    scan_library(library, db, verbose=False)

    item = "Devenez Copywriter avec les IA (TUTO.com)"

    media_id, relative_path = query(
        db,
        """
        SELECT m.id, m.relative_path FROM media m
        JOIN items i ON i.id = m.item_id
        WHERE i.title = ?
        ORDER BY m.sort_order
        """,
        (item,),
    )[0]

    execute(
        db,
        "UPDATE media SET duration_seconds = 600.0, probed_at = 'test' "
        "WHERE id = ?",
        (media_id,),
    )

    set_progress(db, media_id, 12.0)

    # Le fichier est remplace par un autre, de taille differente.
    (library / item / relative_path).write_bytes(b"contenu plus long")

    scan_library(library, db, verbose=False)

    ligne = query(
        db,
        "SELECT id, duration_seconds, probed_at FROM media WHERE id = ?",
        (media_id,),
    )

    assert ligne == [(media_id, None, None)]

    # L'id ne bouge pas, donc la progression reste en place meme si
    # la duree est a resonder.
    assert query(db, "SELECT media_id FROM progress") == [(media_id,)]


# --------------------------------------------------------------------
# Migration de schema
# --------------------------------------------------------------------


SCHEMA_V1 = """
CREATE TABLE schema_info (version INTEGER NOT NULL);

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    library_path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    item_type TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    relative_path TEXT NOT NULL,
    media_type TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(item_id, relative_path),
    FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE resources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    relative_path TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(item_id, relative_path),
    FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);

CREATE TABLE progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    media_id INTEGER NOT NULL,
    position_seconds REAL,
    page_number INTEGER,
    completed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, media_id),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(media_id) REFERENCES media(id) ON DELETE CASCADE
);

INSERT INTO schema_info(version) VALUES (1);
INSERT INTO users(username, display_name, is_admin, created_at)
VALUES ('local', 'Utilisateur local', 1, '2026-01-01');
"""


def test_migration_depuis_schema_v1(library: Path, db: Path) -> None:
    """Une base creee par la version 1 doit etre completee sur place,
    sans perdre ni les lignes ni les identifiants."""

    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA_V1)

    item = "Devenez Copywriter avec les IA (TUTO.com)"

    conn.execute(
        "INSERT INTO items(library_path, title, item_type, "
        "created_at, updated_at) VALUES (?, ?, 'course', 'x', 'x')",
        (item, item),
    )
    conn.execute(
        "INSERT INTO media(item_id, relative_path, media_type, "
        "extension, size_bytes, created_at) "
        "VALUES (1, '001 - Presentation.mp4', 'video', '.mp4', 1, 'x')"
    )
    conn.execute(
        "INSERT INTO progress(user_id, media_id, position_seconds, "
        "completed, updated_at) VALUES (1, 1, 77.0, 0, 'x')"
    )
    conn.commit()
    conn.close()

    scan_library(library, db, verbose=False)

    colonnes = {
        row[1]
        for row in query(db, "PRAGMA table_info(media)")
    }

    assert {"parent_path", "sort_order", "duration_seconds", "probed_at"} <= colonnes
    assert query(db, "SELECT version FROM schema_info") == [(SCHEMA_VERSION,)]

    # Le media prealable garde son id 1, donc sa progression.
    assert query(
        db, "SELECT relative_path FROM media WHERE id = 1"
    ) == [("001 - Presentation.mp4",)]

    assert query(
        db, "SELECT media_id, position_seconds FROM progress"
    ) == [(1, 77.0)]
