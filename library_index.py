#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from offlineu_core import (
    VIDEO_EXTENSIONS,
    AUDIO_EXTENSIONS,
    BOOK_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    RESOURCE_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
)
from epub_book import count_chapters as count_epub_chapters

SCHEMA_VERSION = 9

PROBE_TIMEOUT_SECONDS = 60
PROBE_COMMIT_EVERY = 50


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def natural_key(text: str) -> list:
    """Cle de tri qui compare les nombres comme des nombres.

    "10" se place ainsi apres "9", et non avant comme le ferait
    un tri purement textuel.
    """

    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", text)
    ]


# Espace insécable : un nombre et l'unité qui le suit ("258 vidéos",
# "5 h 44") ne doivent jamais se retrouver coupés entre deux lignes -
# voir format_duration ci-dessous et son usage dans studia.py.
NBSP = " "


def format_duration(seconds: float | None) -> str:
    if not seconds:
        return "—"

    total = int(seconds)
    heures, reste = divmod(total, 3600)
    minutes, secondes = divmod(reste, 60)

    if heures:
        return f"{heures}{NBSP}h{NBSP}{minutes:02d}"

    if minutes:
        return f"{minutes}{NBSP}min{NBSP}{secondes:02d}"

    return f"{secondes}{NBSP}s"


def connect_database(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_info (
            version INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_path TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            item_type TEXT NOT NULL DEFAULT 'unknown',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            relative_path TEXT NOT NULL,
            parent_path TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            media_type TEXT NOT NULL,
            extension TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            duration_seconds REAL,
            probed_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(item_id, relative_path),
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            relative_path TEXT NOT NULL,
            parent_path TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            resource_type TEXT NOT NULL,
            extension TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(item_id, relative_path),
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS progress (
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

        CREATE TABLE IF NOT EXISTS book_search (
            item_id INTEGER PRIMARY KEY,
            query TEXT,
            searched_at TEXT,
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS book_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT,
            authors TEXT,
            publisher TEXT,
            published_year TEXT,
            isbn TEXT,
            cover_url TEXT,
            decision TEXT NOT NULL DEFAULT 'proposed',
            found_at TEXT NOT NULL,
            decided_at TEXT,
            UNIQUE(item_id, source, source_id),
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS notes (
            library_path TEXT PRIMARY KEY,
            text TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS media_chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id INTEGER NOT NULL,
            chapter_index INTEGER NOT NULL,
            title TEXT,
            start_seconds REAL NOT NULL,
            end_seconds REAL NOT NULL,
            UNIQUE(media_id, chapter_index),
            FOREIGN KEY(media_id) REFERENCES media(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS preferences (
            user_id INTEGER PRIMARY KEY,
            reading_mode TEXT NOT NULL DEFAULT 'scroll',
            reading_zoom REAL,
            note_panel_left REAL,
            note_panel_top REAL,
            note_panel_width REAL,
            note_panel_height REAL,
            reading_text_scale REAL,
            epub_reading_mode TEXT NOT NULL DEFAULT 'scroll',
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )

    conn.execute(
        """
        INSERT OR IGNORE INTO users(
            username,
            display_name,
            is_admin,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        ("local", "Utilisateur local", 1, now_iso()),
    )

    conn.commit()


def column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})")
    }


def migrate_schema(conn: sqlite3.Connection) -> list[str]:
    """Ajoute les colonnes manquantes a une base creee par une
    version anterieure.

    CREATE TABLE IF NOT EXISTS laisse intacte une table deja
    presente : sans cette etape, une base existante garderait
    l'ancien schema.
    """

    ajouts: list[str] = []

    attendu = {
        "media": [
            ("parent_path", "TEXT NOT NULL DEFAULT ''"),
            ("sort_order", "INTEGER NOT NULL DEFAULT 0"),
            ("duration_seconds", "REAL"),
            ("probed_at", "TEXT"),
            ("chapters_probed_at", "TEXT"),
            ("page_count", "INTEGER"),
        ],
        "resources": [
            ("parent_path", "TEXT NOT NULL DEFAULT ''"),
            ("sort_order", "INTEGER NOT NULL DEFAULT 0"),
        ],
        "preferences": [
            ("note_panel_left", "REAL"),
            ("note_panel_top", "REAL"),
            ("note_panel_width", "REAL"),
            ("note_panel_height", "REAL"),
            ("reading_text_scale", "REAL"),
            ("epub_reading_mode", "TEXT NOT NULL DEFAULT 'scroll'"),
        ],
    }

    for table, colonnes in attendu.items():
        presentes = column_names(conn, table)

        for nom, definition in colonnes:
            if nom in presentes:
                continue

            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {nom} {definition}"
            )
            ajouts.append(f"{table}.{nom}")

    conn.execute("DELETE FROM schema_info")
    conn.execute(
        "INSERT INTO schema_info(version) VALUES (?)",
        (SCHEMA_VERSION,),
    )

    conn.commit()

    return ajouts


def create_scan_workspace(conn: sqlite3.Connection) -> None:
    """Table temporaire listant les chemins vus pendant le scan d'un item.

    Elle n'existe que le temps de la connexion et n'est jamais ecrite
    dans le fichier de base de donnees.
    """

    conn.executescript(
        """
        CREATE TEMP TABLE IF NOT EXISTS seen_paths (
            kind TEXT NOT NULL,
            relative_path TEXT NOT NULL
        );
        """
    )


def classify_item(files: list[Path]) -> str:
    extensions = {f.suffix.lower() for f in files}

    has_video = bool(extensions & VIDEO_EXTENSIONS)
    has_audio = bool(extensions & AUDIO_EXTENSIONS)
    has_book = bool(extensions & BOOK_EXTENSIONS)

    if has_video:
        return "course"

    if has_audio:
        return "audiobook"

    if has_book:
        return "book"

    return "document"


def classify_file(
    file_path: Path,
    item_type: str,
) -> tuple[str, str] | None:

    ext = file_path.suffix.lower()
    name_lower = file_path.name.lower()

    # OfflineU helper pages are metadata/resources, not primary media.
    if (
        ext in {".html", ".htm"}
        and name_lower.startswith("000")
        and "presentation" in name_lower
    ):
        return ("resource", "presentation")

    if (
        ext in {".html", ".htm"}
        and name_lower.startswith("000")
        and "ressource" in name_lower
    ):
        return ("resource", "resource_index")

    if ext in VIDEO_EXTENSIONS:
        return ("media", "video")

    if ext in AUDIO_EXTENSIONS:
        return ("media", "audio")

    if ext in BOOK_EXTENSIONS:
        # In a course or an audiobook, a PDF/ebook alongside the
        # video/audio is a supporting resource, never the primary
        # media — only a "book" item (no video, no audio) has one as
        # its actual media.
        if item_type in ("course", "audiobook"):
            return ("resource", "document")

        return ("media", "book")

    if ext in SUBTITLE_EXTENSIONS:
        return ("resource", "subtitle")

    if ext in IMAGE_EXTENSIONS:
        return ("resource", "image")

    if ext in RESOURCE_EXTENSIONS:
        return ("resource", "file")

    if ext in DOCUMENT_EXTENSIONS:
        return ("resource", "document")

    return None


def parent_of(relative_path: str) -> str:
    """Sous-dossier contenant le fichier, chaine vide a la racine."""

    parent = Path(relative_path).parent.as_posix()

    return "" if parent == "." else parent


def upsert_media(
    conn: sqlite3.Connection,
    item_id: int,
    relative_path: str,
    parent_path: str,
    sort_order: int,
    media_type: str,
    extension: str,
    size_bytes: int,
    timestamp: str,
) -> None:
    """Insere ou met a jour un media sans changer son id.

    L'id stable est ce qui permet a progress.media_id de survivre
    a un rescan.

    La duree, l'examen des chapitres et le nombre de pages sont
    conserves tant que la taille du fichier ne bouge pas. Si elle
    change, le fichier n'est plus le meme : ces informations
    redeviennent NULL pour etre resondees - et les lignes de
    media_chapters deja stockees, qui decriraient alors un fichier qui
    n'existe plus, sont effacees tout de suite plutot que de rester
    affichees, fausses, jusqu'au prochain --probe.
    """

    existant = conn.execute(
        "SELECT id, size_bytes FROM media WHERE item_id = ? AND relative_path = ?",
        (item_id, relative_path),
    ).fetchone()

    conn.execute(
        """
        INSERT INTO media(
            item_id,
            relative_path,
            parent_path,
            sort_order,
            media_type,
            extension,
            size_bytes,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id, relative_path)
        DO UPDATE SET
            parent_path = excluded.parent_path,
            sort_order = excluded.sort_order,
            media_type = excluded.media_type,
            extension = excluded.extension,
            duration_seconds = CASE
                WHEN media.size_bytes = excluded.size_bytes
                THEN media.duration_seconds
                ELSE NULL
            END,
            probed_at = CASE
                WHEN media.size_bytes = excluded.size_bytes
                THEN media.probed_at
                ELSE NULL
            END,
            chapters_probed_at = CASE
                WHEN media.size_bytes = excluded.size_bytes
                THEN media.chapters_probed_at
                ELSE NULL
            END,
            page_count = CASE
                WHEN media.size_bytes = excluded.size_bytes
                THEN media.page_count
                ELSE NULL
            END,
            size_bytes = excluded.size_bytes
        """,
        (
            item_id,
            relative_path,
            parent_path,
            sort_order,
            media_type,
            extension,
            size_bytes,
            timestamp,
        ),
    )

    if existant is not None and existant["size_bytes"] != size_bytes:
        conn.execute(
            "DELETE FROM media_chapters WHERE media_id = ?",
            (existant["id"],),
        )


def upsert_resource(
    conn: sqlite3.Connection,
    item_id: int,
    relative_path: str,
    parent_path: str,
    sort_order: int,
    resource_type: str,
    extension: str,
    size_bytes: int,
    timestamp: str,
) -> None:

    conn.execute(
        """
        INSERT INTO resources(
            item_id,
            relative_path,
            parent_path,
            sort_order,
            resource_type,
            extension,
            size_bytes,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id, relative_path)
        DO UPDATE SET
            parent_path = excluded.parent_path,
            sort_order = excluded.sort_order,
            resource_type = excluded.resource_type,
            extension = excluded.extension,
            size_bytes = excluded.size_bytes
        """,
        (
            item_id,
            relative_path,
            parent_path,
            sort_order,
            resource_type,
            extension,
            size_bytes,
            timestamp,
        ),
    )


def delete_vanished_rows(conn: sqlite3.Connection, item_id: int) -> None:
    """Supprime les lignes dont le fichier n'existe plus.

    Seules ces lignes disparaissent : la progression attachee aux
    fichiers toujours presents n'est jamais touchee.
    """

    conn.execute(
        """
        DELETE FROM media
        WHERE item_id = ?
          AND relative_path NOT IN (
              SELECT relative_path FROM seen_paths WHERE kind = 'media'
          )
        """,
        (item_id,),
    )

    conn.execute(
        """
        DELETE FROM resources
        WHERE item_id = ?
          AND relative_path NOT IN (
              SELECT relative_path FROM seen_paths WHERE kind = 'resource'
          )
        """,
        (item_id,),
    )


def scan_item(
    conn: sqlite3.Connection,
    library_root: Path,
    item_path: Path,
) -> None:

    all_files = [
        file
        for file in item_path.rglob("*")
        if file.is_file() and not file.name.startswith(".")
    ]

    all_files.sort(
        key=lambda f: natural_key(
            f.relative_to(item_path).as_posix()
        )
    )

    item_type = classify_item(all_files)

    library_path = item_path.relative_to(library_root).as_posix()
    timestamp = now_iso()

    conn.execute(
        """
        INSERT INTO items(
            library_path,
            title,
            item_type,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(library_path)
        DO UPDATE SET
            title = excluded.title,
            item_type = excluded.item_type,
            updated_at = excluded.updated_at
        """,
        (
            library_path,
            item_path.name,
            item_type,
            timestamp,
            timestamp,
        ),
    )

    item = conn.execute(
        "SELECT id FROM items WHERE library_path = ?",
        (library_path,),
    ).fetchone()

    item_id = item["id"]

    conn.execute("DELETE FROM seen_paths")

    rang_media = 0
    rang_resource = 0

    for file_path in all_files:
        classification = classify_file(file_path, item_type)

        if classification is None:
            continue

        category, subtype = classification

        relative_path = file_path.relative_to(item_path).as_posix()
        parent_path = parent_of(relative_path)
        ext = file_path.suffix.lower()
        size = file_path.stat().st_size

        conn.execute(
            "INSERT INTO seen_paths(kind, relative_path) VALUES (?, ?)",
            (category, relative_path),
        )

        if category == "media":
            rang_media += 1
            upsert_media(
                conn,
                item_id,
                relative_path,
                parent_path,
                rang_media,
                subtype,
                ext,
                size,
                timestamp,
            )

        else:
            rang_resource += 1
            upsert_resource(
                conn,
                item_id,
                relative_path,
                parent_path,
                rang_resource,
                subtype,
                ext,
                size,
                timestamp,
            )

    delete_vanished_rows(conn, item_id)


def probe_duration(file_path: Path) -> float | None:
    """Duree d'un fichier en secondes, lue par ffprobe.

    ffprobe fait partie de ffmpeg. Il lit les en-tetes du fichier
    sans le decoder ni le modifier. Renvoie None si l'outil est
    absent, si le fichier n'est pas lisible ou s'il ne declare
    aucune duree.
    """

    try:
        resultat = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )

    except (OSError, subprocess.TimeoutExpired):
        return None

    try:
        duree = float(resultat.stdout.strip())

    except ValueError:
        return None

    return duree if duree > 0 else None


def probe_chapters(file_path: Path) -> list[dict]:
    """Chapitres internes d'un fichier, lus par ffprobe -show_chapters.

    Renvoie une liste vide si l'outil est absent, si le fichier n'est
    pas lisible, ou s'il ne declare reellement aucun chapitre - les
    trois cas sont indiscernables ici et traites pareil : rien a
    stocker. C'est chapters_probed_at (mis a jour par l'appelant) qui
    distingue "jamais examine" de "examine, rien trouve", pas cette
    fonction.

    Chaque chapitre garde son index brut ffprobe (`id`), jamais
    renumerote, et son titre tel quel (`tags.title`), absent (None)
    plutot qu'invente si le fichier n'en fournit pas.
    """

    try:
        resultat = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_chapters",
                "-of",
                "json",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )

    except (OSError, subprocess.TimeoutExpired):
        return []

    try:
        data = json.loads(resultat.stdout)
    except ValueError:
        return []

    chapitres = []

    for brut in data.get("chapters", []):
        try:
            index = int(brut["id"])
            debut = float(brut["start_time"])
            fin = float(brut["end_time"])
        except (KeyError, TypeError, ValueError):
            continue

        titre = (brut.get("tags") or {}).get("title") or None

        chapitres.append(
            {
                "index": index,
                "title": titre,
                "start_seconds": debut,
                "end_seconds": fin,
            }
        )

    return chapitres


def probe_page_count(file_path: Path) -> int | None:
    """Nombre de pages d'un PDF, lu par pdfinfo (poppler-utils, deja
    utilise par covers.py pour l'extraction de couverture - aucune
    nouvelle dependance). Renvoie None si l'outil est absent, si le
    fichier n'est pas lisible ou ne declare aucun nombre de pages -
    y compris pour un livre qui n'est pas un PDF (EPUB, MOBI...),
    que pdfinfo ne sait de toute facon pas lire.
    """

    try:
        resultat = subprocess.run(
            ["pdfinfo", str(file_path)],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    for ligne in resultat.stdout.splitlines():
        if ligne.startswith("Pages:"):
            try:
                pages = int(ligne.split(":", 1)[1].strip())
            except ValueError:
                return None
            return pages if pages > 0 else None

    return None


def reset_probed_media(conn: sqlite3.Connection) -> None:
    """Oublie tout ce que --probe a mesuré, pour tout resonder au
    prochain scan avec --reprobe : durée, chapitres et nombre de
    pages. Les trois colonnes ensemble, jamais une seule oubliée -
    sinon --reprobe ne pourrait plus jamais forcer le réexamen de
    celle laissée de côté.
    """

    conn.execute(
        """
        UPDATE media
        SET duration_seconds = NULL, probed_at = NULL,
            chapters_probed_at = NULL, page_count = NULL
        """
    )
    conn.commit()


def probe_missing_media_info(
    conn: sqlite3.Connection,
    library_root: Path,
    verbose: bool = True,
) -> tuple[int, int, int]:
    """Sonde la duree, les chapitres et/ou le nombre de pages des medias
    pas encore examines.

    Un media est repris s'il lui manque au moins une des informations
    qui le concernent (chacune independamment des autres). Aucun
    filtre de type pour la duree et les chapitres : une video peut
    porter des chapitres au meme titre qu'un audio, chapters_probed_at
    doit dire ce qui a ete examine, pas ce qui est affiche aujourd'hui
    (seul /listen montre une colonne de chapitres pour l'instant). Le
    nombre de pages, lui, ne concerne que les livres (page_count n'a
    aucun sens pour une video/un audio et pdfinfo y echouerait a coup
    sur) : restreint a media_type = 'book' pour ne pas resonder en vain
    tout le reste de la bibliotheque a chaque --probe.

    Renvoie (durees lues avec succes, fichiers ou au moins un chapitre
    a ete trouve, fichiers dont le nombre de pages a ete lu, nombre
    total de medias examines).
    """

    if shutil.which("ffprobe") is None:
        raise SystemExit(
            "ffprobe est introuvable. Installer ffmpeg, ou relancer "
            "sans --probe."
        )

    rows = conn.execute(
        """
        SELECT
            m.id,
            i.library_path,
            m.relative_path,
            m.media_type,
            m.extension,
            m.duration_seconds,
            m.chapters_probed_at,
            m.page_count
        FROM media m
        JOIN items i ON i.id = m.item_id
        WHERE m.duration_seconds IS NULL
           OR m.chapters_probed_at IS NULL
           OR (m.media_type = 'book' AND m.page_count IS NULL)
        ORDER BY i.library_path, m.sort_order
        """
    ).fetchall()

    total = len(rows)
    durees_reussies = 0
    avec_chapitres = 0
    pages_lues = 0

    for index, row in enumerate(rows, start=1):
        file_path = library_root / row["library_path"] / row["relative_path"]

        if row["duration_seconds"] is None:
            duree = probe_duration(file_path)

            if duree is not None:
                durees_reussies += 1

            conn.execute(
                """
                UPDATE media
                SET duration_seconds = ?, probed_at = ?
                WHERE id = ?
                """,
                (duree, now_iso(), row["id"]),
            )

        if row["chapters_probed_at"] is None:
            chapitres = probe_chapters(file_path)

            conn.execute(
                "DELETE FROM media_chapters WHERE media_id = ?",
                (row["id"],),
            )

            for chapitre in chapitres:
                conn.execute(
                    """
                    INSERT INTO media_chapters(
                        media_id, chapter_index, title,
                        start_seconds, end_seconds
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        chapitre["index"],
                        chapitre["title"],
                        chapitre["start_seconds"],
                        chapitre["end_seconds"],
                    ),
                )

            if chapitres:
                avec_chapitres += 1

            conn.execute(
                "UPDATE media SET chapters_probed_at = ? WHERE id = ?",
                (now_iso(), row["id"]),
            )

        if row["media_type"] == "book" and row["page_count"] is None:
            # Même colonne pour les deux formats lisibles, un sens
            # différent selon l'extension : nombre de pages pour un
            # PDF (pdfinfo), nombre de chapitres - entrées de la table
            # des matières, dédupliquées par fichier - pour un EPUB
            # (voir epub_book.py). Toute autre extension de livre
            # (MOBI...) n'a ni l'un ni l'autre : reste à None, comme
            # aujourd'hui.
            if row["extension"] == ".epub":
                pages = count_epub_chapters(file_path)
            elif row["extension"] == ".pdf":
                pages = probe_page_count(file_path)
            else:
                pages = None

            if pages is not None:
                pages_lues += 1

            conn.execute(
                "UPDATE media SET page_count = ? WHERE id = ?",
                (pages, row["id"]),
            )

        if index % PROBE_COMMIT_EVERY == 0:
            conn.commit()

            if verbose:
                print(f"  sondé {index}/{total}…")

    conn.commit()

    return durees_reussies, avec_chapitres, pages_lues, total


def scan_library(
    library_root: Path,
    db_path: Path,
    probe: bool = False,
    verbose: bool = True,
) -> None:
    library_root = library_root.resolve()

    if not library_root.is_dir():
        raise SystemExit(
            f"Bibliothèque introuvable : {library_root}"
        )

    conn = connect_database(db_path)

    try:
        create_schema(conn)

        ajouts = migrate_schema(conn)

        if ajouts and verbose:
            print("Migration du schéma, colonnes ajoutées :")
            for ajout in ajouts:
                print(f"  {ajout}")

        create_scan_workspace(conn)

        current_items = {
            path.relative_to(library_root).as_posix()
            for path in library_root.iterdir()
            if path.is_dir() and not path.name.startswith(".")
        }

        existing_items = {
            row["library_path"]
            for row in conn.execute(
                "SELECT library_path FROM items"
            )
        }

        removed_items = existing_items - current_items

        for removed in removed_items:
            conn.execute(
                "DELETE FROM items WHERE library_path = ?",
                (removed,),
            )

        for item_path in sorted(
            (
                path
                for path in library_root.iterdir()
                if path.is_dir() and not path.name.startswith(".")
            ),
            key=lambda p: natural_key(p.name),
        ):
            scan_item(conn, library_root, item_path)

        conn.commit()

        if probe:
            if verbose:
                print(
                    "Analyse des durées, chapitres et pages/chapitres "
                    "de livre par ffprobe/pdfinfo…"
                )

            durees_reussies, avec_chapitres, pages_lues, total = probe_missing_media_info(
                conn, library_root, verbose
            )

            if verbose:
                print(
                    f"Durées lues : {durees_reussies}/{total} — "
                    f"fichiers avec chapitres : {avec_chapitres} — "
                    f"livres avec pages/chapitres lus : {pages_lues}"
                )

    finally:
        conn.close()


def print_summary(db_path: Path) -> None:
    conn = connect_database(db_path)

    try:
        print()
        print("=== INDEX STUDIA ===")

        # Sous-requetes plutot que jointures : deux LEFT JOIN
        # simultanes multiplieraient les lignes et fausseraient
        # la somme des durees.
        rows = conn.execute(
            """
            SELECT
                i.id,
                i.title,
                i.item_type,
                (SELECT COUNT(*) FROM media m
                 WHERE m.item_id = i.id) AS media_count,
                (SELECT COUNT(*) FROM resources r
                 WHERE r.item_id = i.id) AS resource_count,
                (SELECT COUNT(DISTINCT parent_path) FROM media m
                 WHERE m.item_id = i.id
                   AND m.parent_path <> '') AS chapter_count,
                (SELECT SUM(duration_seconds) FROM media m
                 WHERE m.item_id = i.id) AS total_duration,
                (SELECT COUNT(*) FROM media m
                 WHERE m.item_id = i.id
                   AND m.duration_seconds IS NULL) AS missing_duration
            FROM items i
            ORDER BY i.title
            """
        ).fetchall()

        for row in rows:
            print(
                f"{row['title']}\n"
                f"  type       : {row['item_type']}\n"
                f"  médias     : {row['media_count']}\n"
                f"  ressources : {row['resource_count']}\n"
                f"  chapitres  : {row['chapter_count']}\n"
                f"  durée      : {format_duration(row['total_duration'])}"
                f"   (sans durée : {row['missing_duration']})"
            )

        print()
        print("=== CHAPITRES ===")

        rows = conn.execute(
            """
            SELECT
                i.title,
                m.parent_path,
                COUNT(*) AS n,
                SUM(m.duration_seconds) AS duree
            FROM media m
            JOIN items i ON i.id = m.item_id
            GROUP BY i.id, m.parent_path
            ORDER BY i.title, MIN(m.sort_order)
            """
        ).fetchall()

        for row in rows:
            libelle = row["parent_path"] or "(racine)"
            print(
                f"{row['title']} :: {libelle} — "
                f"{row['n']} média(s), {format_duration(row['duree'])}"
            )

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--library",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--database",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--probe",
        action="store_true",
        help="lire la durée, les chapitres et le nombre de pages des médias",
    )

    parser.add_argument(
        "--reprobe",
        action="store_true",
        help="oublier durées, chapitres et pages connus et tout resonder",
    )

    parser.add_argument(
        "--covers",
        action="store_true",
        help="extraire les couvertures manquantes (PDF, M4B, vidéo)",
    )

    parser.add_argument(
        "--recovers",
        action="store_true",
        help="ré-extraire toutes les couvertures, même déjà en cache",
    )

    args = parser.parse_args()

    if args.reprobe and args.database.exists():
        conn = connect_database(args.database)

        try:
            reset_probed_media(conn)

        finally:
            conn.close()

    scan_library(
        args.library,
        args.database,
        probe=args.probe or args.reprobe,
    )

    print_summary(args.database)

    if args.covers or args.recovers:
        from covers import cover_cache_dir, extract_all_covers

        conn = connect_database(args.database)

        try:
            print()
            print("Extraction des couvertures…")
            cache_dir = cover_cache_dir(args.database)
            reussites, total = extract_all_covers(
                conn,
                args.library.resolve(),
                cache_dir,
                force=args.recovers,
            )
            print(f"Couvertures : {reussites}/{total}")

        finally:
            conn.close()


if __name__ == "__main__":
    main()
