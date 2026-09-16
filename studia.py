#!/usr/bin/env python3
"""Application web de consultation de la bibliothèque Studia.

Lecture seule pour l'instant : grille des items puis fiche d'un item.
Les lecteurs (vidéo, audio, PDF) et l'écriture de la progression
viennent dans des tranches suivantes.
"""

from __future__ import annotations

import argparse
import mimetypes
import re
from datetime import date
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, send_file, url_for

from library_index import connect_database, format_duration, now_iso
from presentation import parse_presentation
from book_metadata import default_query, find_isbn, search_candidates
from covers import cover_cache_dir, cover_cache_path

BOOK_ITEM_TYPES = ("book", "audiobook")

BADGE_LABELS = {
    "course": "FORMATION",
    "book": "LIVRE",
    "audiobook": "AUDIOBOOK",
    "document": "DOCUMENT",
}

# Libellés de fiche technique qui désignent la même idée qu'"auteur" ou
# "année" selon la source (présentation locale) — pour le hero de la
# fiche, qui n'affiche qu'une seule ligne de chacun.
HERO_AUTHOR_LABELS = {"auteur", "autrice", "auteurs", "formateur", "formateurs"}
HERO_YEAR_LABELS = {"publié", "date de publication", "année"}

# Faits de présentation qui ont désormais un champ résolu équivalent
# ailleurs sur la fiche (voir resolve_metadata_fields) : ne plus les
# repasser tels quels, sous peine de répéter la même information avec
# un libellé différent. Couvre aussi bien "Auteur"/"Autrice" qu'un
# "Formateur(s)" de formation — même concept, mots différents selon
# qui a écrit le fichier.
PRESENTATION_FACTS_RESOLVED_ELSEWHERE = HERO_AUTHOR_LABELS | HERO_YEAR_LABELS | {"éditeur", "editeur"}

# Faits toujours supplantés par un comptage réel du scanner (durée,
# structure, ressources) : contrairement aux champs ci-dessus, le
# scanner a TOUJOURS une valeur, donc le texte annoncé par le fichier
# n'est jamais la seule information disponible — il ne s'affiche donc
# plus jamais, même sans fiche livre validée.
PRESENTATION_FACTS_SUPERSEDED_BY_SCANNER = {"durée totale", "structure", "ressources"}

# Remplace le libellé écrit dans le fichier de présentation à
# l'affichage seulement (jamais dans le fichier) : "Source" y désigne
# la plateforme de la formation, pas la provenance d'une métadonnée
# bibliographique validée (carte Métadonnées, "Provenance").
PRESENTATION_LABEL_DISPLAY_OVERRIDES = {"source": "Plateforme"}

BOOK_SOURCE_LABELS = {
    "google_books": "Google Books",
    "open_library": "Open Library",
    "manual": "Saisie manuelle",
}

# Unique utilisateur créé par le scanner (library_index.ensure_schema,
# ligne "local") : pas de compte en V1, voir "Refonte visuelle" dans
# CLAUDE.md — toute écriture de progression utilise cet id fixe.
LOCAL_USER_ID = 1

# Marge en dessous de la durée totale à partir de laquelle une lecture
# est considérée terminée : 5 % de la durée, plafonnés à 15 secondes.
# Le plafond évite qu'une vidéo de plusieurs heures exige d'atteindre
# la toute dernière seconde (un générique de fin de 10 minutes sur une
# formation de 3h ne devrait pas empêcher indéfiniment le "terminé") ;
# les 5 % s'appliquent tels quels sous ce plafond, pour une vidéo
# courte.
PROGRESS_COMPLETION_MARGIN_RATIO = 0.05
PROGRESS_COMPLETION_MARGIN_CAP_SECONDS = 15.0

# Mot au pluriel selon le media_type réellement présent dans l'item
# (pas selon son item_type) — un seul type par item depuis la
# suppression de book_audio, voir _media_label ci-dessous.
MEDIA_TYPE_LABELS = {"video": "vidéos", "audio": "pistes audio", "book": "documents"}

# Une année à 4 chiffres, jamais un fragment d'un nombre plus long
# (ex. une résolution "1920x1080" ne doit jamais matcher "1920").
_YEAR_PATTERN = re.compile(r"(?<!\d)(\d{4})(?!\d)")

# Types d'archive dont le nom d'usage diffère du format générique
# "Archive" — .zip est de loin le plus courant dans la bibliothèque de
# Gautier, distingué explicitement plutôt que fondu dans "Archive".
_ZIP_EXTENSIONS = {".zip"}
_ARCHIVE_EXTENSIONS = {".7z", ".rar", ".tar", ".gz", ".bz2", ".xz"}
_SPREADSHEET_EXTENSIONS = {".xls", ".xlsx", ".xlsm", ".ods"}
_SLIDESHOW_EXTENSIONS = {".ppt", ".pptx", ".odp"}

# Types de ressources dont le libellé ne dépend pas de l'extension.
RESOURCE_TYPE_LABELS = {
    "resource_index": "Page de ressources",
    "subtitle": "Sous-titres",
    "image": "Image",
}


def badge_label(item_type: str) -> str:
    return BADGE_LABELS.get(item_type, item_type.upper())


def clean_file_title(filename: str) -> str:
    """Nom de fichier sans son extension technique — rien d'autre.

    Ne touche pas à la ponctuation ni à l'orthographe du nom réel :
    un remplacement partiel de séparateur (le numéro en tête, mais pas
    les autres occurrences dans le reste du titre) produirait un titre
    qui mélange deux conventions différentes, pire que l'original.
    """

    return Path(filename).stem


def resource_type_label(resource_type: str, extension: str) -> str:
    """Type de ressource comprehensible, dérivé de l'extension quand
    le type brut du scanner ("document", "file") est trop générique
    pour dire quoi que ce soit d'utile à l'affichage."""

    if resource_type in RESOURCE_TYPE_LABELS:
        return RESOURCE_TYPE_LABELS[resource_type]

    ext = (extension or "").lower()

    if ext == ".pdf":
        return "PDF"
    if ext in _ZIP_EXTENSIONS:
        return "Archive ZIP"
    if ext in _ARCHIVE_EXTENSIONS:
        return "Archive"
    if ext in _SPREADSHEET_EXTENSIONS:
        return "Feuille de calcul"
    if ext in _SLIDESHOW_EXTENSIONS:
        return "Diaporama"
    if resource_type == "document":
        return "Document"

    return "Fichier"


def _extract_year(text: str) -> str | None:
    """Premier nombre à 4 chiffres plausible comme année dans un texte
    libre (borne haute calculée à l'exécution, jamais figée) — ni un
    nom de logiciel, ni une résolution, ni une taille de fichier.

    Le champ vient d'un libellé de date (voir HERO_YEAR_LABELS) : le
    premier candidat valide rencontré est donc aussi celui qui suit le
    plus immédiatement ce libellé.
    """

    current_year = date.today().year
    for match in _YEAR_PATTERN.finditer(text):
        year = int(match.group(1))
        if 1900 <= year <= current_year:
            return match.group(1)
    return None


def _media_label(count: int, distinct_type_count: int, sample_type: str | None) -> str | None:
    """Compteur de médias à afficher, ou None pour le masquer.

    Masqué à 0 ou 1 (un seul élément ne dit rien qu'on ne voie déjà
    ailleurs sur la fiche).

    Le repli sur "médias" quand distinct_type_count > 1 protège un
    invariant : depuis la suppression de book_audio, un item n'a plus
    qu'un seul media_type parmi ses médias (course -> video,
    audiobook -> audio, book -> book, jamais un mélange). Cette
    branche ne devrait donc jamais s'exécuter — si elle s'exécutait
    quand même, mieux vaut annoncer "12 médias" que "12 vidéos" sur un
    item qui contient autre chose."""

    if count < 2:
        return None
    if distinct_type_count == 1:
        label = MEDIA_TYPE_LABELS.get(sample_type, "médias")
    else:
        label = "médias"
    return f"{count} {label}"


def describe_media_count(media_rows) -> str | None:
    types = {m["media_type"] for m in media_rows}
    sample_type = next(iter(types)) if len(types) == 1 else None
    return _media_label(len(media_rows), len(types), sample_type)


def describe_count(count: int, plural_word: str) -> str | None:
    """Compteur générique (ressources, chapitres...), masqué à 0 ou 1."""

    if count < 2:
        return None
    return f"{count} {plural_word}"


def build_meta_line(*segments: str | None) -> str:
    """Assemble des segments de métadonnées courtes avec un séparateur
    « · », en écartant ceux qui sont vides — jamais de séparateur en
    tête, en fin, ou en double : il vient toujours d'un join, jamais
    d'une concaténation conditionnelle segment par segment."""

    return " · ".join(segment for segment in segments if segment)


def fetch_video_media(conn, media_id: int):
    """Media de type vidéo, avec le chemin de bibliothèque et le titre
    de son item.

    None si l'id n'existe pas ou si ce n'est pas une vidéo : cette
    fonction sert de garde commune aux deux routes vidéo.
    """

    return conn.execute(
        """
        SELECT
            media.id,
            media.item_id,
            media.relative_path,
            media.extension,
            media.duration_seconds,
            items.title AS item_title,
            items.library_path
        FROM media
        JOIN items ON items.id = media.item_id
        WHERE media.id = ? AND media.media_type = 'video'
        """,
        (media_id,),
    ).fetchone()


def is_video_completed(position_seconds: float, duration_seconds: float | None) -> bool:
    """Règle du "terminé" : dans les 5% de la fin, plafonnés à 15
    secondes (voir PROGRESS_COMPLETION_MARGIN_*). Sans durée connue
    (sonde ffprobe en échec), jamais "terminé" : rien à comparer."""

    if not duration_seconds or duration_seconds <= 0:
        return False

    margin = min(
        duration_seconds * PROGRESS_COMPLETION_MARGIN_RATIO,
        PROGRESS_COMPLETION_MARGIN_CAP_SECONDS,
    )

    return position_seconds >= duration_seconds - margin


def save_video_progress(
    conn, media_id: int, position_seconds: float, duration_seconds: float | None
) -> None:
    """Enregistre la position et calcule "terminé" à partir de la durée
    connue côté serveur (jamais celle envoyée par le client).

    "completed" ne redescend jamais tout seul : revenir en arrière
    dans une vidéo déjà marquée terminée continue de mettre à jour
    position_seconds (le point de reprise reste exact), mais ne retire
    pas la coche — "terminé" signifie "déjà vu en entier au moins une
    fois", pas "actuellement positionné à la fin". MAX(...) dans la
    requête porte cette règle : une remise à zéro explicite (à venir,
    hors de cette tranche) est la seule façon de la défaire.
    """

    position_seconds = max(0.0, position_seconds)
    completed = 1 if is_video_completed(position_seconds, duration_seconds) else 0

    conn.execute(
        """
        INSERT INTO progress (user_id, media_id, position_seconds, completed, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, media_id) DO UPDATE SET
            position_seconds = excluded.position_seconds,
            completed = MAX(progress.completed, excluded.completed),
            updated_at = excluded.updated_at
        """,
        (LOCAL_USER_ID, media_id, position_seconds, completed, now_iso()),
    )
    conn.commit()


def fetch_media_progress(conn, media_id: int):
    """Ligne de progression d'un média (position_seconds, completed),
    ou None si jamais ouvert."""

    return conn.execute(
        "SELECT position_seconds, completed FROM progress WHERE media_id = ? AND user_id = ?",
        (media_id, LOCAL_USER_ID),
    ).fetchone()


def resolve_resume_seconds(progress_row) -> int | None:
    """Position à proposer pour la reprise automatique (sans repère
    explicite) : la position enregistrée tant que la vidéo n'est pas
    terminée. Une vidéo déjà terminée repart du début si on la
    rouvre - ouvrir une vidéo qu'on a déjà finie, c'est vouloir la
    revoir, pas reprendre à sa dernière seconde. La ligne progress
    elle-même n'est pas modifiée : seule cette position de départ à
    l'ouverture change.
    """

    if progress_row is None or progress_row["completed"]:
        return None

    if progress_row["position_seconds"] is None:
        return None

    return int(progress_row["position_seconds"])


def resolve_watch_target_video_id(
    video_ids: list[int], completed_ids: set[int]
) -> int | None:
    """Cible du bouton "Regarder" : la première vidéo non terminée
    dans l'ordre du programme ; si toutes le sont, la première vidéo
    de l'item (la rouvrir, c'est vouloir la revoir depuis le début -
    même règle que resolve_resume_seconds). None si l'item n'a aucune
    vidéo.
    """

    if not video_ids:
        return None

    for video_id in video_ids:
        if video_id not in completed_ids:
            return video_id

    return video_ids[0]


def fetch_completed_video_ids(conn, item_id: int) -> set[int]:
    rows = conn.execute(
        """
        SELECT media.id
        FROM media
        JOIN progress
            ON progress.media_id = media.id AND progress.user_id = ?
        WHERE media.item_id = ? AND progress.completed = 1
        """,
        (LOCAL_USER_ID, item_id),
    ).fetchall()

    return {row["id"] for row in rows}


def aggregate_item_progress(media_progress: list[tuple[bool, bool]]) -> str:
    """Règle d'agrégation média -> item : 'not_started', 'in_progress'
    ou 'completed', à partir d'une ligne (a_une_progression, terminé)
    par média principal de l'item (ceux de la table media - jamais les
    resources, voir la clé étrangère de progress).

    Un item sans aucun média principal (ex. un item classé 'document',
    ou un livre dont le PDF n'est qu'une ressource) reçoit une liste
    vide : il ne doit jamais ressortir 'completed' par vacuité (all()
    sur une liste vide vaudrait True) - le cas est donc écarté
    explicitement avant l'agrégation réelle, avant même de regarder
    'in_progress'.
    """

    if not media_progress:
        return "not_started"

    if all(completed for _has_progress, completed in media_progress):
        return "completed"

    if any(has_progress for has_progress, _completed in media_progress):
        return "in_progress"

    return "not_started"


def fetch_item_progress_status(conn, item_id: int) -> str:
    rows = conn.execute(
        """
        SELECT
            progress.completed IS NOT NULL AS has_progress,
            COALESCE(progress.completed, 0) AS completed
        FROM media
        LEFT JOIN progress
            ON progress.media_id = media.id AND progress.user_id = ?
        WHERE media.item_id = ?
        """,
        (LOCAL_USER_ID, item_id),
    ).fetchall()

    return aggregate_item_progress(
        [(bool(row["has_progress"]), bool(row["completed"])) for row in rows]
    )


def fetch_item_video_progress(conn, item_id: int) -> dict:
    """Statut ('not_started'/'in_progress'/'completed', voir
    aggregate_item_progress) et pourcentage d'un item, à partir de ses
    vidéos uniquement - seul type suivi pour l'instant, un livre ou un
    audiobook n'a donc jamais de ligne ici.

    "percent" est le nombre de vidéos terminées sur le nombre total de
    vidéos, jamais les secondes vues sur la durée totale : ça
    bougerait en permanence sans jamais correspondre exactement à la
    coche "terminé" d'une vidéo précise.
    """

    rows = conn.execute(
        """
        SELECT
            progress.completed IS NOT NULL AS has_progress,
            COALESCE(progress.completed, 0) AS completed
        FROM media
        LEFT JOIN progress
            ON progress.media_id = media.id AND progress.user_id = ?
        WHERE media.item_id = ? AND media.media_type = 'video'
        """,
        (LOCAL_USER_ID, item_id),
    ).fetchall()

    total = len(rows)
    completed_count = sum(1 for row in rows if row["completed"])
    status = aggregate_item_progress(
        [(bool(row["has_progress"]), bool(row["completed"])) for row in rows]
    )
    percent = round(completed_count / total * 100) if total else 0

    return {"status": status, "percent": percent}


def fetch_video_progress_states(conn, item_id: int) -> dict[int, str]:
    """media_id -> 'in_progress' ou 'completed' pour chaque vidéo de
    l'item ayant une ligne progress ; absente du dict sinon (non
    commencée - état par défaut, rien à afficher)."""

    rows = conn.execute(
        """
        SELECT media.id, progress.completed
        FROM media
        JOIN progress
            ON progress.media_id = media.id AND progress.user_id = ?
        WHERE media.item_id = ? AND media.media_type = 'video'
        """,
        (LOCAL_USER_ID, item_id),
    ).fetchall()

    return {
        row["id"]: ("completed" if row["completed"] else "in_progress")
        for row in rows
    }


def fetch_video_playlist(conn, item_id: int):
    """Toutes les vidéos d'un item, dans l'ordre de sort_order."""

    return conn.execute(
        """
        SELECT id, relative_path, parent_path, sort_order, duration_seconds
        FROM media
        WHERE item_id = ? AND media_type = 'video'
        ORDER BY sort_order
        """,
        (item_id,),
    ).fetchall()


def read_presentation(library_root: Path, library_path: str, relative_path: str):
    """Lit et analyse la page de présentation HTML d'un item.

    None si le fichier a disparu du disque depuis le scan : une fiche
    ne doit pas planter pour autant, elle s'affiche juste sans
    présentation.
    """

    file_path = (library_root / library_path / relative_path).resolve()

    if library_root not in file_path.parents:
        return None

    try:
        html_text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    return parse_presentation(html_text)


def fetch_book_candidates(conn, item_id: int):
    return conn.execute(
        """
        SELECT id, source, source_id, title, authors, publisher,
               published_year, isbn, cover_url, decision
        FROM book_candidates
        WHERE item_id = ?
        ORDER BY id
        """,
        (item_id,),
    ).fetchall()


def extract_hero_fields(metadata_fields: list[dict]) -> dict:
    """Auteur et année à afficher dans le hero — jamais une résolution
    indépendante : les mêmes valeurs déjà tranchées par
    resolve_metadata_fields pour l'onglet À propos (fiche livre
    validée d'abord, présentation locale ensuite), pour que le hero et
    l'onglet ne puissent plus jamais afficher deux valeurs différentes
    du même fait.

    Ne reprend que la valeur, jamais la source : le hero reste une
    ligne compacte, sans attribution visible — l'affichage de la
    source est réservé à l'onglet À propos.

    Retrouve les champs par leur clé stable ("author", "published_date"),
    pas par le texte de leur libellé affiché : un libellé change selon
    le type ("Auteur" vs "Formateur(s)") ou pourrait être renommé sans
    prévenir, une clé non.
    """

    author_field = next(
        (field for field in metadata_fields if field["key"] == "author"), None
    )
    year_field = next(
        (field for field in metadata_fields if field["key"] == "published_date"), None
    )

    return {
        "author": ", ".join(run["text"] for run in author_field["runs"]) if author_field else None,
        "year": ", ".join(run["text"] for run in year_field["runs"]) if year_field else None,
    }


def plain_run(text: str) -> list[dict]:
    """Enveloppe une chaîne simple dans la même forme que les "runs"
    extraits d'une page de présentation, pour que le composant
    d'affichage n'ait qu'une seule forme de valeur à connaître."""

    return [{"text": text, "href": None}]


def resolve_presentation_facts(facts: list[dict], book_validated: bool) -> list[dict]:
    """Faits de présentation à afficher tels quels : ceux qui n'ont pas
    de champ résolu équivalent ailleurs sur la fiche (voir
    resolve_metadata_fields), et — pour l'ISBN, imbriqué dans
    "Identifiants" avec un lien Google Books — ceux qui ne sont pas
    devenus redondants avec une fiche livre validée.

    Le contenu de la présentation n'est jamais modifié : seul
    l'affichage évite de répéter une information, et remplace un
    libellé quand deux concepts différents partagent le même mot dans
    des fichiers différents (voir PRESENTATION_LABEL_DISPLAY_OVERRIDES).
    """

    kept = []
    for fact in facts:
        label = fact["label"].strip().lower()
        if label in PRESENTATION_FACTS_RESOLVED_ELSEWHERE:
            continue
        if label in PRESENTATION_FACTS_SUPERSEDED_BY_SCANNER:
            continue
        if label == "identifiants" and book_validated:
            continue
        display_label = PRESENTATION_LABEL_DISPLAY_OVERRIDES.get(label, fact["label"])
        kept.append({"label": display_label, "runs": fact["runs"]})

    return kept


def describe_cover_source(item: dict, resources, media_rows) -> str:
    """D'où vient la couverture en cache, en réappliquant la même
    priorité que covers.py (image du dossier, puis PDF/M4B/vidéo selon
    le type) — jamais stockée nulle part, donc reconstruite ici pour
    l'affichage plutôt que devinée. Ne détecte pas un échec silencieux
    d'une étape (ex. copie d'image ratée) : décrit le premier candidat
    trouvé dans l'ordre de priorité, pas une garantie absolue.
    """

    if not item["cover_url"]:
        return "Aucune — le visuel de remplacement par type s'affiche à la place."

    if any(r["resource_type"] == "image" for r in resources):
        return "Image trouvée dans le dossier de l'item."
    if item["item_type"] == "book" and any(m["extension"] == ".pdf" for m in media_rows):
        return "Première page du PDF."
    if item["item_type"] == "audiobook" and any(m["extension"] == ".m4b" for m in media_rows):
        return "Pochette intégrée au fichier M4B."
    if item["item_type"] == "course" and any(m["media_type"] == "video" for m in media_rows):
        return "Image extraite d'une vidéo."
    return "Origine non déterminée."


def resolve_metadata_fields(
    item_type: str, presentation: dict | None, book: dict | None
) -> list[dict]:
    """Un seul champ résolu par concept bibliographique (Auteur ou
    Formateur(s) selon le type, Éditeur, Date de publication ou Année,
    ISBN), avec sa source — jamais les deux valeurs à la fois, jamais
    la présentation en cas de fiche livre validée.

    book_metadata validé fait toujours foi sur la présentation locale,
    car il vient d'une validation explicite ; la présentation reste le
    seul repli tant qu'aucune fiche n'a été validée (systématique pour
    une formation, qui n'a pas de workflow book_metadata).
    """

    facts_by_label: dict[str, dict] = {}
    if presentation:
        for fact in presentation["facts"]:
            facts_by_label.setdefault(fact["label"].strip().lower(), fact)

    accepted = book["accepted"] if book and book["status"] == "validated" else None
    accepted_source = (
        BOOK_SOURCE_LABELS.get(accepted["source"], accepted["source"])
        if accepted
        else None
    )

    author_label = "Formateur(s)" if item_type == "course" else "Auteur"

    fields = []

    if accepted and accepted["authors"]:
        fields.append(
            {
                "key": "author",
                "label": "Auteur",
                "runs": plain_run(accepted["authors"]),
                "source": accepted_source,
            }
        )
    else:
        fact = next(
            (facts_by_label[key] for key in HERO_AUTHOR_LABELS if key in facts_by_label), None
        )
        if fact:
            fields.append(
                {
                    "key": "author",
                    "label": author_label,
                    "runs": fact["runs"],
                    "source": "Présentation locale",
                }
            )

    if accepted and accepted["publisher"]:
        fields.append(
            {
                "key": "publisher",
                "label": "Éditeur",
                "runs": plain_run(accepted["publisher"]),
                "source": accepted_source,
            }
        )
    else:
        fact = facts_by_label.get("éditeur") or facts_by_label.get("editeur")
        if fact:
            fields.append(
                {"key": "publisher", "label": "Éditeur", "runs": fact["runs"], "source": "Présentation locale"}
            )

    if accepted and accepted["published_year"]:
        fields.append(
            {
                "key": "published_date",
                "label": "Date de publication",
                "runs": plain_run(accepted["published_year"]),
                "source": accepted_source,
            }
        )
    else:
        fact = next(
            (facts_by_label[key] for key in HERO_YEAR_LABELS if key in facts_by_label), None
        )
        if fact:
            text = ", ".join(run["text"] for run in fact["runs"])
            year = _extract_year(text)
            if year:
                fields.append(
                    {
                        "key": "published_date",
                        "label": "Date de publication",
                        "runs": plain_run(year),
                        "source": "Présentation locale",
                    }
                )

    if accepted and accepted["isbn"]:
        fields.append(
            {
                "key": "isbn",
                "label": "ISBN",
                "runs": plain_run(accepted["isbn"]),
                "source": accepted_source,
            }
        )

    return fields


def fetch_book_state(conn, item_id: int) -> dict:
    """État de la recherche de métadonnées pour un item livre.

    Le statut n'est pas stocké : il est déduit des candidats présents,
    pour ne jamais désynchroniser un champ "statut" du contenu réel de
    book_candidates.
    """

    search_row = conn.execute(
        "SELECT query, searched_at FROM book_search WHERE item_id = ?",
        (item_id,),
    ).fetchone()

    candidates = fetch_book_candidates(conn, item_id)
    accepted = next((c for c in candidates if c["decision"] == "accepted"), None)
    proposed = [c for c in candidates if c["decision"] == "proposed"]
    rejected = [c for c in candidates if c["decision"] == "rejected"]

    if accepted is not None:
        status = "validated"
    elif proposed:
        status = "has_candidates"
    elif search_row is not None:
        status = "searched_no_match"
    else:
        status = "never_searched"

    return {
        "status": status,
        "query": search_row["query"] if search_row else None,
        "accepted": accepted,
        "proposed": proposed,
        "rejected": rejected,
    }


def fetch_item_author(library_root: Path, conn, item) -> str | None:
    """Auteur/Formateur(s) résolu pour une carte de la grille.

    Même résolution que la fiche (resolve_metadata_fields puis
    extract_hero_fields, book_metadata validé avant présentation
    locale) — seule la collecte de la présentation et de l'état livre
    est refaite ici, la grille ne les a pas déjà en mémoire comme la
    route /item/<id>.
    """

    resources = conn.execute(
        "SELECT relative_path, resource_type FROM resources WHERE item_id = ?",
        (item["id"],),
    ).fetchall()
    presentation_resource = next(
        (r for r in resources if r["resource_type"] == "presentation"), None
    )
    presentation = (
        read_presentation(
            library_root, item["library_path"], presentation_resource["relative_path"]
        )
        if presentation_resource
        else None
    )
    book = (
        fetch_book_state(conn, item["id"])
        if item["item_type"] in BOOK_ITEM_TYPES
        else None
    )
    metadata_fields = resolve_metadata_fields(item["item_type"], presentation, book)
    return extract_hero_fields(metadata_fields)["author"]


def detect_isbn_for_item(conn, item) -> str | None:
    texts = [item["title"]]
    texts += [
        row["relative_path"]
        for row in conn.execute(
            """
            SELECT relative_path FROM media WHERE item_id = ?
            UNION ALL
            SELECT relative_path FROM resources WHERE item_id = ?
            """,
            (item["id"], item["id"]),
        )
    ]
    return find_isbn(*texts)


def run_book_search(conn, item_id: int, raw_query: str) -> None:
    """Lance une recherche et enregistre les candidats trouvés.

    Une recherche par ISBN écrase toujours une recherche par titre :
    si la requête contient un ISBN valide, c'est lui qui est utilisé
    (identifiant fiable), le reste du texte est ignoré pour la requête
    envoyée aux deux sources.
    """

    isbn = find_isbn(raw_query)
    candidates = search_candidates(query=raw_query.strip(), isbn=isbn)
    now = now_iso()

    conn.execute(
        """
        INSERT INTO book_search(item_id, query, searched_at)
        VALUES (?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET query = excluded.query, searched_at = excluded.searched_at
        """,
        (item_id, raw_query.strip(), now),
    )

    for candidate in candidates:
        conn.execute(
            """
            INSERT INTO book_candidates(
                item_id, source, source_id, title, authors, publisher,
                published_year, isbn, cover_url, decision, found_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?)
            ON CONFLICT(item_id, source, source_id) DO NOTHING
            """,
            (
                item_id,
                candidate["source"],
                candidate["source_id"],
                candidate["title"],
                candidate["authors"],
                candidate["publisher"],
                candidate["published_year"],
                candidate["isbn"],
                candidate["cover_url"],
                now,
            ),
        )


def demote_accepted_candidate(conn, item_id: int, except_id: int = -1) -> None:
    """Repasse à "proposé" l'éventuel candidat déjà validé de l'item.

    Appelé avant d'en valider un autre : changer d'avis ne doit rien
    effacer, l'ancien choix reste consultable comme un candidat parmi
    d'autres.
    """

    conn.execute(
        """
        UPDATE book_candidates SET decision = 'proposed', decided_at = NULL
        WHERE item_id = ? AND decision = 'accepted' AND id != ?
        """,
        (item_id, except_id),
    )


def accept_book_candidate(conn, item_id: int, candidate_id: int) -> None:
    demote_accepted_candidate(conn, item_id, except_id=candidate_id)

    conn.execute(
        """
        UPDATE book_candidates SET decision = 'accepted', decided_at = ?
        WHERE id = ? AND item_id = ?
        """,
        (now_iso(), candidate_id, item_id),
    )


def save_manual_candidate(conn, item_id: int, fields: dict) -> None:
    """Enregistre une saisie manuelle comme métadonnées validées.

    source_id fixe ("manual") : une seule fiche saisie à la main par
    item, une nouvelle saisie remplace la précédente plutôt que d'en
    accumuler.
    """

    demote_accepted_candidate(conn, item_id)
    now = now_iso()

    conn.execute(
        """
        INSERT INTO book_candidates(
            item_id, source, source_id, title, authors, publisher,
            published_year, isbn, cover_url, decision, found_at, decided_at
        )
        VALUES (?, 'manual', 'manual', ?, ?, ?, ?, ?, NULL, 'accepted', ?, ?)
        ON CONFLICT(item_id, source, source_id) DO UPDATE SET
            title = excluded.title,
            authors = excluded.authors,
            publisher = excluded.publisher,
            published_year = excluded.published_year,
            isbn = excluded.isbn,
            decision = 'accepted',
            decided_at = excluded.decided_at
        """,
        (
            item_id,
            fields.get("title") or None,
            fields.get("authors") or None,
            fields.get("publisher") or None,
            fields.get("published_year") or None,
            fields.get("isbn") or None,
            now,
            now,
        ),
    )


def group_by_parent(rows):
    """Regroupe des lignes media/resource par parent_path.

    Un dict garde l'ordre de première apparition de chaque
    parent_path, contrairement à itertools.groupby qui ne fusionne
    que des lignes déjà consécutives.
    """

    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row["parent_path"], []).append(row)

    return list(grouped.items())


def build_programme_chapters(media_rows) -> list[dict]:
    """Chapitres de l'onglet Programme : médias groupés, avec le
    total de médias et de durée par chapitre (calculé ici plutôt que
    dans le gabarit pour ne pas dépendre du filtre "sum" de Jinja face
    à des durées non encore sondées, donc NULL)."""

    chapters = []
    for parent_path, media_list in group_by_parent(media_rows):
        duration = sum(m["duration_seconds"] or 0 for m in media_list)
        chapters.append(
            {
                "parent_path": parent_path,
                "media": media_list,
                "count": len(media_list),
                "duration": duration,
                "meta": build_meta_line(
                    describe_media_count(media_list), format_duration(duration)
                ),
            }
        )

    return chapters


def fetch_note(conn, library_path: str):
    """Note d'un item, identifiée par son chemin de bibliothèque.

    Volontairement pas par item_id : un item supprimé puis recréé par
    le scanner (dossier disparu puis revenu à l'identique) a le même
    library_path mais pas forcément le même id. La note s'y retrouve
    donc automatiquement, sans dépendre de la table items.
    """

    return conn.execute(
        "SELECT text, updated_at FROM notes WHERE library_path = ?",
        (library_path,),
    ).fetchone()


def save_note(conn, library_path: str, text: str) -> str:
    now = now_iso()

    conn.execute(
        """
        INSERT INTO notes(library_path, text, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(library_path) DO UPDATE SET
            text = excluded.text,
            updated_at = excluded.updated_at
        """,
        (library_path, text, now),
    )

    return now


def fetch_orphan_notes(conn):
    """Notes dont le dossier n'existe plus dans la bibliothèque actuelle.

    Arrive quand un item est renommé : le scanner voit un nouveau
    chemin et un ancien chemin disparu, la note reste attachée à
    l'ancien.
    """

    return conn.execute(
        """
        SELECT library_path, text, updated_at
        FROM notes
        WHERE library_path NOT IN (SELECT library_path FROM items)
        ORDER BY updated_at DESC
        """
    ).fetchall()


def reattach_note(conn, source_library_path: str, target_library_path: str) -> None:
    """Rattache une note orpheline à un autre item existant.

    Si l'item cible a déjà une note, les deux textes sont fusionnés
    plutôt que d'en écraser un : aucune recopie manuelle, mais rien
    n'est perdu non plus.
    """

    source = conn.execute(
        "SELECT text FROM notes WHERE library_path = ?", (source_library_path,)
    ).fetchone()

    if source is None:
        return

    target = conn.execute(
        "SELECT text FROM notes WHERE library_path = ?", (target_library_path,)
    ).fetchone()

    now = now_iso()

    if target is None:
        conn.execute(
            "UPDATE notes SET library_path = ?, updated_at = ? WHERE library_path = ?",
            (target_library_path, now, source_library_path),
        )
        return

    merged_text = target["text"].rstrip() + "\n\n--- note récupérée ---\n\n" + source["text"]

    conn.execute(
        "UPDATE notes SET text = ?, updated_at = ? WHERE library_path = ?",
        (merged_text, now, target_library_path),
    )
    conn.execute("DELETE FROM notes WHERE library_path = ?", (source_library_path,))


def create_app(library_root: Path, db_path: Path) -> Flask:
    app = Flask(__name__)
    app.config["LIBRARY_ROOT"] = library_root.resolve()
    app.config["DB_PATH"] = db_path
    app.config["COVER_CACHE_DIR"] = cover_cache_dir(db_path)

    @app.route("/")
    def library_grid():
        conn = connect_database(app.config["DB_PATH"])

        try:
            rows = conn.execute(
                """
                SELECT
                    i.id,
                    i.title,
                    i.item_type,
                    i.library_path,
                    i.created_at,
                    (SELECT COUNT(*) FROM media m
                     WHERE m.item_id = i.id) AS media_count,
                    (SELECT COUNT(DISTINCT media_type) FROM media m
                     WHERE m.item_id = i.id) AS media_type_count,
                    (SELECT media_type FROM media m
                     WHERE m.item_id = i.id LIMIT 1) AS media_type_sample,
                    (SELECT COUNT(*) FROM resources r
                     WHERE r.item_id = i.id) AS resource_count,
                    (SELECT COUNT(DISTINCT parent_path) FROM media m
                     WHERE m.item_id = i.id
                       AND m.parent_path <> '') AS chapter_count,
                    (SELECT SUM(duration_seconds) FROM media m
                     WHERE m.item_id = i.id) AS total_duration
                FROM items i
                ORDER BY i.title
                """
            ).fetchall()
            orphan_note_count = len(fetch_orphan_notes(conn))

            cache_dir = app.config["COVER_CACHE_DIR"]
            library_root = app.config["LIBRARY_ROOT"]
            items = []
            type_counts: dict[str, int] = {}
            for row in rows:
                item = dict(row)
                cover_file = cover_cache_path(cache_dir, item["id"])
                item["cover_url"] = (
                    url_for("item_cover", item_id=item["id"])
                    if cover_file.is_file()
                    else None
                )
                item["meta_line"] = build_meta_line(
                    _media_label(
                        item["media_count"],
                        item["media_type_count"],
                        item["media_type_sample"],
                    ),
                    describe_count(item["resource_count"], "ressources"),
                    describe_count(item["chapter_count"], "chapitres"),
                )
                item["author"] = fetch_item_author(library_root, conn, item)
                video_progress = fetch_item_video_progress(conn, item["id"])
                item["progress_status"] = video_progress["status"]
                item["progress_percent"] = video_progress["percent"]
                type_counts[item["item_type"]] = type_counts.get(item["item_type"], 0) + 1
                items.append(item)
        finally:
            conn.close()

        return render_template(
            "library_grid.html",
            items=items,
            type_counts=type_counts,
            format_duration=format_duration,
            orphan_note_count=orphan_note_count,
            badge_label=badge_label,
        )

    @app.route("/cover/<int:item_id>")
    def item_cover(item_id: int):
        cover_file = cover_cache_path(app.config["COVER_CACHE_DIR"], item_id)

        if not cover_file.is_file():
            abort(404)

        return send_file(cover_file, mimetype="image/jpeg")

    @app.route("/item/<int:item_id>")
    def item_detail(item_id: int):
        conn = connect_database(app.config["DB_PATH"])

        try:
            item = conn.execute(
                """
                SELECT id, title, item_type, library_path, created_at, updated_at
                FROM items WHERE id = ?
                """,
                (item_id,),
            ).fetchone()

            if item is None:
                abort(404)

            media_rows = conn.execute(
                """
                SELECT
                    id, relative_path, parent_path, sort_order,
                    media_type, extension, size_bytes, duration_seconds
                FROM media
                WHERE item_id = ?
                ORDER BY sort_order
                """,
                (item_id,),
            ).fetchall()

            resources = conn.execute(
                """
                SELECT
                    id, relative_path, parent_path, sort_order,
                    resource_type, extension, size_bytes
                FROM resources
                WHERE item_id = ?
                ORDER BY sort_order
                """,
                (item_id,),
            ).fetchall()

            completed_video_ids = fetch_completed_video_ids(conn, item_id)
        finally:
            conn.close()

        item = dict(item)
        cover_file = cover_cache_path(app.config["COVER_CACHE_DIR"], item["id"])
        item["cover_url"] = (
            url_for("item_cover", item_id=item["id"]) if cover_file.is_file() else None
        )

        chapters = build_programme_chapters(media_rows)

        video_ids = [m["id"] for m in media_rows if m["media_type"] == "video"]
        first_video_id = resolve_watch_target_video_id(video_ids, completed_video_ids)

        total_duration = sum(m["duration_seconds"] or 0 for m in media_rows)

        presentation_resource = next(
            (r for r in resources if r["resource_type"] == "presentation"),
            None,
        )
        resources = [
            r for r in resources if r["resource_type"] != "presentation"
        ]

        cover_source = describe_cover_source(item, resources, media_rows)

        presentation = None
        if presentation_resource is not None:
            presentation = read_presentation(
                app.config["LIBRARY_ROOT"],
                item["library_path"],
                presentation_resource["relative_path"],
            )

        book = None
        if item["item_type"] in BOOK_ITEM_TYPES:
            conn = connect_database(app.config["DB_PATH"])
            try:
                book = fetch_book_state(conn, item_id)
                if book["query"] is None:
                    isbn = detect_isbn_for_item(conn, item)
                    book["suggested_query"] = isbn or default_query(item["title"])
                    book["isbn_detected"] = isbn
            finally:
                conn.close()

        book_validated = bool(book and book["status"] == "validated")
        presentation_facts = (
            resolve_presentation_facts(presentation["facts"], book_validated)
            if presentation
            else []
        )
        metadata_fields = resolve_metadata_fields(item["item_type"], presentation, book)
        hero = extract_hero_fields(metadata_fields)

        chapter_count = len([c for c in chapters if c["parent_path"]])
        hero_meta = build_meta_line(
            format_duration(total_duration) if total_duration else None,
            describe_media_count(media_rows),
            describe_count(chapter_count, "chapitres"),
            hero["year"],
        )

        conn = connect_database(app.config["DB_PATH"])
        try:
            note = fetch_note(conn, item["library_path"])
        finally:
            conn.close()

        return render_template(
            "item_detail.html",
            item=item,
            chapters=chapters,
            resources=resources,
            presentation=presentation,
            presentation_facts=presentation_facts,
            metadata_fields=metadata_fields,
            book=book,
            book_source_labels=BOOK_SOURCE_LABELS,
            hero=hero,
            hero_meta=hero_meta,
            first_video_id=first_video_id,
            total_duration=total_duration,
            note_text=note["text"] if note else "",
            note_updated_at=note["updated_at"] if note else None,
            format_duration=format_duration,
            badge_label=badge_label,
            clean_file_title=clean_file_title,
            resource_type_label=resource_type_label,
            cover_source=cover_source,
        )

    @app.route("/item/<int:item_id>/note", methods=["POST"])
    def item_note(item_id: int):
        conn = connect_database(app.config["DB_PATH"])

        try:
            item = conn.execute(
                "SELECT library_path FROM items WHERE id = ?", (item_id,)
            ).fetchone()

            if item is None:
                abort(404)

            text = request.form.get("text", "")
            updated_at = save_note(conn, item["library_path"], text)
            conn.commit()
        finally:
            conn.close()

        return {"updated_at": updated_at}

    @app.route("/notes-orphelines")
    def orphan_notes():
        conn = connect_database(app.config["DB_PATH"])

        try:
            notes = fetch_orphan_notes(conn)
            items = conn.execute(
                "SELECT id, title FROM items ORDER BY title"
            ).fetchall()
        finally:
            conn.close()

        return render_template("orphan_notes.html", notes=notes, items=items)

    @app.route("/notes-orphelines/reattach", methods=["POST"])
    def orphan_notes_reattach():
        source_library_path = request.form.get("library_path", "")
        target_item_id = request.form.get("target_item_id", type=int)

        conn = connect_database(app.config["DB_PATH"])

        try:
            target = (
                conn.execute(
                    "SELECT library_path FROM items WHERE id = ?",
                    (target_item_id,),
                ).fetchone()
                if target_item_id is not None
                else None
            )

            if target is not None:
                reattach_note(conn, source_library_path, target["library_path"])
                conn.commit()
        finally:
            conn.close()

        return redirect(url_for("orphan_notes"))

    def fetch_book_item_or_404(conn, item_id: int):
        item = conn.execute(
            "SELECT id, item_type FROM items WHERE id = ?", (item_id,)
        ).fetchone()

        if item is None or item["item_type"] not in BOOK_ITEM_TYPES:
            abort(404)

        return item

    @app.route("/item/<int:item_id>/book-search", methods=["POST"])
    def book_search(item_id: int):
        conn = connect_database(app.config["DB_PATH"])

        try:
            fetch_book_item_or_404(conn, item_id)
            raw_query = request.form.get("query", "").strip()

            if raw_query:
                run_book_search(conn, item_id, raw_query)
                conn.commit()
        finally:
            conn.close()

        return redirect(url_for("item_detail", item_id=item_id) + "#metadonnees")

    @app.route("/item/<int:item_id>/book-candidate/<int:candidate_id>/accept", methods=["POST"])
    def book_candidate_accept(item_id: int, candidate_id: int):
        conn = connect_database(app.config["DB_PATH"])

        try:
            fetch_book_item_or_404(conn, item_id)
            accept_book_candidate(conn, item_id, candidate_id)
            conn.commit()
        finally:
            conn.close()

        return redirect(url_for("item_detail", item_id=item_id) + "#metadonnees")

    @app.route("/item/<int:item_id>/book-candidate/<int:candidate_id>/reject", methods=["POST"])
    def book_candidate_reject(item_id: int, candidate_id: int):
        conn = connect_database(app.config["DB_PATH"])

        try:
            fetch_book_item_or_404(conn, item_id)
            conn.execute(
                """
                UPDATE book_candidates SET decision = 'rejected', decided_at = ?
                WHERE id = ? AND item_id = ?
                """,
                (now_iso(), candidate_id, item_id),
            )
            conn.commit()
        finally:
            conn.close()

        return redirect(url_for("item_detail", item_id=item_id) + "#metadonnees")

    @app.route("/item/<int:item_id>/book-candidate/<int:candidate_id>/unreject", methods=["POST"])
    def book_candidate_unreject(item_id: int, candidate_id: int):
        conn = connect_database(app.config["DB_PATH"])

        try:
            fetch_book_item_or_404(conn, item_id)
            conn.execute(
                """
                UPDATE book_candidates SET decision = 'proposed', decided_at = NULL
                WHERE id = ? AND item_id = ? AND decision = 'rejected'
                """,
                (candidate_id, item_id),
            )
            conn.commit()
        finally:
            conn.close()

        return redirect(url_for("item_detail", item_id=item_id) + "#metadonnees")

    @app.route("/item/<int:item_id>/book-manual", methods=["POST"])
    def book_manual(item_id: int):
        conn = connect_database(app.config["DB_PATH"])

        try:
            fetch_book_item_or_404(conn, item_id)
            save_manual_candidate(
                conn,
                item_id,
                {
                    "title": request.form.get("title", "").strip(),
                    "authors": request.form.get("authors", "").strip(),
                    "publisher": request.form.get("publisher", "").strip(),
                    "published_year": request.form.get("published_year", "").strip(),
                    "isbn": request.form.get("isbn", "").strip(),
                },
            )
            conn.commit()
        finally:
            conn.close()

        return redirect(url_for("item_detail", item_id=item_id) + "#metadonnees")

    @app.route("/watch/<int:media_id>")
    def watch_video(media_id: int):
        conn = connect_database(app.config["DB_PATH"])

        try:
            media = fetch_video_media(conn, media_id)

            if media is None:
                abort(404)

            playlist = fetch_video_playlist(conn, media["item_id"])
            stored_progress = fetch_media_progress(conn, media_id)
        finally:
            conn.close()

        chapters = group_by_parent(playlist)

        flat_ids = [row["id"] for row in playlist]
        position = flat_ids.index(media_id)
        prev_id = flat_ids[position - 1] if position > 0 else None
        next_id = (
            flat_ids[position + 1] if position + 1 < len(flat_ids) else None
        )

        conn = connect_database(app.config["DB_PATH"])
        try:
            note = fetch_note(conn, media["library_path"])
        finally:
            conn.close()

        filename = media["relative_path"].rsplit("/", 1)[-1]
        video_title = clean_file_title(filename)

        # Un repère explicite (?t=, cliqué depuis la note) l'emporte
        # toujours sur la reprise automatique, même sur une vidéo déjà
        # terminée - une personne qui clique un repère précis veut
        # aller là, un geste volontaire distinct de la reprise.
        seek_seconds = request.args.get("t", type=int)
        if seek_seconds is None:
            seek_seconds = resolve_resume_seconds(stored_progress)

        return render_template(
            "video_player.html",
            media=media,
            chapters=chapters,
            current_media_id=media_id,
            prev_id=prev_id,
            next_id=next_id,
            seek_seconds=seek_seconds,
            note_text=note["text"] if note else "",
            note_updated_at=note["updated_at"] if note else None,
            player_context={
                "number": position + 1,
                "title": video_title,
                "media_id": media_id,
            },
            clean_file_title=clean_file_title,
            format_duration=format_duration,
        )

    @app.route("/media/<int:media_id>/file")
    def media_file(media_id: int):
        conn = connect_database(app.config["DB_PATH"])

        try:
            media = fetch_video_media(conn, media_id)
        finally:
            conn.close()

        if media is None:
            abort(404)

        library_root = app.config["LIBRARY_ROOT"]
        file_path = (
            library_root / media["library_path"] / media["relative_path"]
        ).resolve()

        if library_root not in file_path.parents or not file_path.is_file():
            abort(404)

        mimetype, _ = mimetypes.guess_type(file_path.name)

        return send_file(file_path, mimetype=mimetype)

    @app.route("/media/<int:media_id>/progress", methods=["POST"])
    def save_progress(media_id: int):
        position_seconds = request.form.get("position_seconds", type=float)

        if position_seconds is None:
            abort(400)

        conn = connect_database(app.config["DB_PATH"])

        try:
            media = fetch_video_media(conn, media_id)

            if media is None:
                abort(404)

            save_video_progress(conn, media_id, position_seconds, media["duration_seconds"])
        finally:
            conn.close()

        return ("", 204)

    @app.errorhandler(404)
    def not_found(error):
        return render_template("not_found.html"), 404

    return app


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=5000, type=int)

    args = parser.parse_args()

    app = create_app(args.library, args.database)
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
