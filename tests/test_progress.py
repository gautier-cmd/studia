"""Tests de la sauvegarde de la position de lecture (vidéo).

Règles métier testées d'abord isolément (is_video_completed,
aggregate_item_progress, resolve_resume_seconds,
resolve_watch_target_media_id), puis via les routes qui les utilisent
(POST /media/<id>/progress, reprise sur GET /watch/<id>, bouton
"Commencer" sur /item/<id>).

L'écouteur "ended" du gabarit vidéo (garde-fou "played", voir
video_player.html) n'est vérifié qu'au niveau du gabarit rendu : il
n'y a pas de navigateur dans cette suite pour simuler une vraie
lecture, donc pas de simulation de timing - seulement la présence du
garde-fou, en non-régression.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from library_index import NBSP, scan_library  # noqa: E402
from studia import (  # noqa: E402
    aggregate_item_progress,
    build_progress_summary_line,
    compute_item_progress_percent,
    create_app,
    fetch_item_media_progress,
    format_clock,
    is_book_completed,
    is_video_completed,
    resolve_hero_cta,
    resolve_resume_page,
    resolve_resume_seconds,
    resolve_watch_target_media_id,
    split_leading_number,
)


def make_file(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


# --- split_leading_number : numéro / titre de la ligne de playlist -----


def test_split_leading_number_avec_numero() -> None:
    assert split_leading_number("001 - Interface") == ("001", "Interface")


def test_split_leading_number_avec_tirets_dans_le_reste() -> None:
    # Seul le numéro de tête est séparé - le reste du titre, tirets
    # compris, n'est jamais retouché.
    assert split_leading_number("003 - Phase 1 - Illustration madame Lee") == (
        "003",
        "Phase 1 - Illustration madame Lee",
    )


def test_split_leading_number_sans_numero() -> None:
    assert split_leading_number("Introduction") == (None, "Introduction")


# --- format_clock : horodatage compact, distinct de format_duration ----


def test_format_clock_secondes_seules() -> None:
    assert format_clock(10) == "0:10"


def test_format_clock_minutes() -> None:
    assert format_clock(688) == "11:28"


def test_format_clock_heures() -> None:
    assert format_clock(4320) == "1:12:00"


def test_format_clock_sans_valeur() -> None:
    assert format_clock(None) == "0:00"


# --- build_progress_summary_line : ligne sous la barre du hero ---------


def test_build_progress_summary_line_formation_pluriel() -> None:
    assert (
        build_progress_summary_line("course", 37, 18, 49, None, None)
        == f"37{NBSP}% · 18{NBSP}vidéos sur 49"
    )


def test_build_progress_summary_line_formation_singulier() -> None:
    assert (
        build_progress_summary_line("course", 2, 1, 49, None, None)
        == f"2{NBSP}% · 1{NBSP}vidéo sur 49"
    )


def test_build_progress_summary_line_audiobook() -> None:
    assert (
        build_progress_summary_line("audiobook", 42, 0, 0, 4320.0, 11106.0)
        == f"42{NBSP}% · 1{NBSP}h{NBSP}12 sur 3{NBSP}h{NBSP}05"
    )


# --- is_video_completed : règle du "terminé" ---------------------------


def test_terminé_video_courte_seuil_a_5_pourcent() -> None:
    # 40s : marge = min(40*5%, 15) = 2s -> seuil a 38s.
    assert is_video_completed(37.9, 40.0) is False
    assert is_video_completed(38.0, 40.0) is True


def test_terminé_video_longue_marge_plafonnee_a_15s() -> None:
    # 3h : marge = min(10800*5%, 15) = 15s -> seuil a 10785s, pas 10260s.
    assert is_video_completed(10784.9, 10800.0) is False
    assert is_video_completed(10785.0, 10800.0) is True


def test_terminé_sans_duree_connue_jamais_vrai() -> None:
    assert is_video_completed(999.0, None) is False
    assert is_video_completed(0.0, 0.0) is False


# --- aggregate_item_progress : règle d'agrégation média -> item --------


def test_agregation_liste_vide_jamais_termine_par_vacuite() -> None:
    assert aggregate_item_progress([]) == "not_started"


def test_agregation_aucun_media_ouvert() -> None:
    assert aggregate_item_progress([(False, False), (False, False)]) == "not_started"


def test_agregation_partiellement_ouvert_en_cours() -> None:
    assert aggregate_item_progress([(True, False), (False, False)]) == "in_progress"


def test_agregation_un_termine_un_non_en_cours() -> None:
    assert aggregate_item_progress([(True, True), (True, False)]) == "in_progress"


def test_agregation_tous_termines() -> None:
    assert aggregate_item_progress([(True, True), (True, True)]) == "completed"


# --- resolve_resume_seconds : une vidéo terminée repart du début -------


def test_resume_sans_ligne_progress() -> None:
    assert resolve_resume_seconds(None) is None


def test_resume_video_terminee_repart_du_debut() -> None:
    assert resolve_resume_seconds({"completed": 1, "position_seconds": 95.0}) is None


def test_resume_video_en_cours_reprend_sa_position() -> None:
    assert resolve_resume_seconds({"completed": 0, "position_seconds": 42.0}) == 42


def test_resume_sans_position_enregistree() -> None:
    assert resolve_resume_seconds({"completed": 0, "position_seconds": None}) is None


# --- resolve_watch_target_media_id : cible du bouton principal ---------


def test_cible_regarder_aucune_video() -> None:
    assert resolve_watch_target_media_id([], set()) is None


def test_cible_regarder_rien_de_commence_prend_la_premiere() -> None:
    assert resolve_watch_target_media_id([1, 2, 3], set()) == 1


def test_cible_regarder_premiere_video_non_terminee() -> None:
    assert resolve_watch_target_media_id([1, 2, 3], {1}) == 2


def test_cible_regarder_tout_termine_revient_a_la_premiere() -> None:
    assert resolve_watch_target_media_id([1, 2, 3], {1, 2, 3}) == 1


# --- Routes : écriture, reprise ----------------------------------------


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"

    course = root / "Motion Design - la formation complete (TUTO.com)"
    make_file(course / "01 - Bases" / "001 - Interface.mp4")
    make_file(course / "01 - Bases" / "002 - Calques.mp4")

    # Fichier unique a la racine, comme un vrai M4B - pas de sous-dossier,
    # donc pas de "chapitre" au sens de build_programme_chapters.
    audiobook = root / "S organiser pour reussir (David Allen)"
    make_file(audiobook / "livre-audio.m4b")

    # Un PDF seul (sans video ni audio) devient media_type 'book' :
    # lisible par /read depuis la tranche "Lecteur PDF".
    book = root / "Adobe Illustrator CS6 (Adobe Press)"
    make_file(book / "livre.pdf")

    # Un livre dans un format que BOOK_EXTENSIONS reconnaît mais que
    # /read ne sait pas ouvrir (EPUB) : message "format illisible"
    # toujours attendu pour celui-ci, contrairement au PDF ci-dessus.
    epub_book = root / "Un livre EPUB (Auteur)"
    make_file(epub_book / "livre.epub")

    # Aucune extension video/audio/book : item_type "document", donc
    # zero ligne dans `media` - le cas vise par la garde de vacuite.
    sans_media_principal = root / "Notes de stage"
    make_file(sans_media_principal / "notes.txt")

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


def media_id_by_relative_path(client, relative_path: str) -> int:
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)

    try:
        row = conn.execute(
            "SELECT id FROM media WHERE relative_path = ?", (relative_path,)
        ).fetchone()
    finally:
        conn.close()

    return row[0]


def item_id_by_title(client, title: str) -> int:
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)

    try:
        row = conn.execute(
            "SELECT id FROM items WHERE title = ?", (title,)
        ).fetchone()
    finally:
        conn.close()

    return row[0]


def set_duration(client, media_id: int, duration_seconds: float) -> None:
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)

    try:
        conn.execute(
            "UPDATE media SET duration_seconds = ?, probed_at = 'test' WHERE id = ?",
            (duration_seconds, media_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_chapters(client, media_id: int, chapters: list[tuple]) -> None:
    """chapters : liste de (chapter_index, title, start, end)."""

    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)

    try:
        conn.execute("DELETE FROM media_chapters WHERE media_id = ?", (media_id,))
        conn.executemany(
            "INSERT INTO media_chapters(media_id, chapter_index, title, "
            "start_seconds, end_seconds) VALUES (?, ?, ?, ?, ?)",
            [(media_id, *chapitre) for chapitre in chapters],
        )
        conn.commit()
    finally:
        conn.close()


def set_page_count(client, media_id: int, page_count: int | None) -> None:
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)

    try:
        conn.execute(
            "UPDATE media SET page_count = ? WHERE id = ?",
            (page_count, media_id),
        )
        conn.commit()
    finally:
        conn.close()


def fetch_preferences(client):
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        return conn.execute("SELECT * FROM preferences WHERE user_id = 1").fetchone()
    finally:
        conn.close()


def fetch_progress_row(client, media_id: int):
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        return conn.execute(
            "SELECT * FROM progress WHERE media_id = ?", (media_id,)
        ).fetchone()
    finally:
        conn.close()


def test_ecriture_position_cree_une_ligne_progress(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )
    set_duration(client, media_id, 100.0)

    response = client.post(
        f"/media/{media_id}/progress", data={"position_seconds": "42.5"}
    )

    assert response.status_code == 204

    row = fetch_progress_row(client, media_id)
    assert row["position_seconds"] == 42.5
    assert row["completed"] == 0


def test_ecriture_position_marque_termine_pres_de_la_fin(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )
    set_duration(client, media_id, 100.0)

    # Marge = min(100*5%, 15) = 5s -> seuil a 95s.
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "96"})

    row = fetch_progress_row(client, media_id)
    assert row["completed"] == 1


def test_completed_ne_redescend_jamais_apres_un_retour_en_arriere(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )
    set_duration(client, media_id, 100.0)

    client.post(f"/media/{media_id}/progress", data={"position_seconds": "99"})
    assert fetch_progress_row(client, media_id)["completed"] == 1

    # Retour en arriere pour revoir un passage : la position se met a
    # jour normalement, la coche "termine" ne se retire pas.
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "10"})

    row = fetch_progress_row(client, media_id)
    assert row["position_seconds"] == 10.0
    assert row["completed"] == 1


def test_ecriture_sans_position_400(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )

    response = client.post(f"/media/{media_id}/progress", data={})

    assert response.status_code == 400


def test_ecriture_sur_media_inconnu_404(client) -> None:
    response = client.post("/media/999999/progress", data={"position_seconds": "1"})

    assert response.status_code == 404


def test_reprise_utilise_la_position_enregistree(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )
    set_duration(client, media_id, 100.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "37"})

    response = client.get(f"/watch/{media_id}")

    assert response.status_code == 200
    assert b"player.currentTime = 37;" in response.data


def test_repere_explicite_prime_sur_la_reprise(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )
    set_duration(client, media_id, 100.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "37"})

    response = client.get(f"/watch/{media_id}?t=80")

    assert response.status_code == 200
    assert b"player.currentTime = 80;" in response.data


def test_sans_position_enregistree_pas_de_reprise(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/002 - Calques.mp4"
    )

    response = client.get(f"/watch/{media_id}")
    data = response.data.decode()

    assert response.status_code == 200
    # "player.currentTime = seekSeconds;" (une variable) est toujours
    # présent depuis le changement de vidéo sans rechargement : seul un
    # nombre littéral juste après signale une vraie reprise (voir
    # test_lecteur_video_reprend_a_la_position_donnee).
    assert not re.search(r"player\.currentTime = \d", data)
    assert 'data-seek="0"' in data


def test_item_sans_media_principal_jamais_termine(client) -> None:
    from studia import fetch_item_progress_status

    item_id = item_id_by_title(client, "Notes de stage")
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        status = fetch_item_progress_status(conn, item_id)
    finally:
        conn.close()

    assert status == "not_started"


def test_video_terminee_repart_du_debut_a_la_reouverture(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )
    set_duration(client, media_id, 100.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "99"})
    assert fetch_progress_row(client, media_id)["completed"] == 1

    response = client.get(f"/watch/{media_id}")
    data = response.data.decode()

    assert response.status_code == 200
    # Vidéo déjà terminée, rouverte sans repère explicite : repart du
    # début, aucune reprise (voir la même remarque plus haut).
    assert not re.search(r"player\.currentTime = \d", data)
    assert 'data-seek="0"' in data


def test_repere_explicite_fonctionne_meme_sur_video_terminee(client) -> None:
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )
    set_duration(client, media_id, 100.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "99"})
    assert fetch_progress_row(client, media_id)["completed"] == 1

    response = client.get(f"/watch/{media_id}?t=50")

    assert response.status_code == 200
    assert b"player.currentTime = 50;" in response.data


def test_bouton_regarder_pointe_vers_la_premiere_video_non_terminee(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    assert fetch_progress_row(client, first_id)["completed"] == 1

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    # class avant href dans le gabarit (hero-actions) : ancre le CTA
    # précisément, à distinguer des liens du Programme qui listent
    # aussi chaque vidéo (dont la première, terminée).
    assert f'class="btn-primary" href="/watch/{second_id}"' in data


def test_bouton_regarder_repart_de_la_premiere_video_si_tout_est_termine(
    client,
) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    set_duration(client, second_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    client.post(f"/media/{second_id}/progress", data={"position_seconds": "99"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert f'class="btn-primary" href="/watch/{first_id}"' in data


def test_centrage_playlist_present(client) -> None:
    # Non-régression sur le gabarit rendu, même principe que le
    # garde-fou "played" ci-dessous : pas de navigateur dans cette
    # suite pour vérifier le défilement réel, seulement la présence du
    # mécanisme. Plus de dépendance à "loadedmetadata" ni à un
    # ResizeObserver depuis que la hauteur de .playlist est purement
    # CSS (position: sticky) - le script s'exécute directement.
    # Positionnement initial direct (scrollTop), jamais animé : la
    # liste reste masquée (visibility: hidden) jusqu'à être
    # positionnée, pour qu'aucun mouvement ne soit visible à l'écran au
    # chargement. "scrollTo" (animé) n'est utilisé qu'après un
    # changement de vidéo sans rechargement, et seulement si la
    # nouvelle ligne courante sort de la zone déjà visible - jamais au
    # premier affichage.
    current_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )

    response = client.get(f"/watch/{current_id}")
    data = response.data.decode()

    assert "playlist.scrollTop = computeCenterTarget(initialCurrent)" in data
    assert "behavior: 'smooth'" in data
    assert "document.referrer" not in data
    assert 'id="playlist" style="visibility: hidden;"' in data
    assert "playlist.style.visibility = 'visible'" in data
    assert "new ResizeObserver" not in data
    assert "syncPlaylistHeight" not in data


def test_rafraichissement_direct_de_la_ligne_courante_present(client) -> None:
    # Idem : le rafraîchissement d'affichage sur "timeupdate" n'est
    # vérifiable qu'en présence dans le gabarit rendu, pas en exécution
    # réelle dans cette suite.
    current_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )

    response = client.get(f"/watch/{current_id}")
    data = response.data.decode()

    assert "timeupdate" in data
    assert "fill.style.width" in data
    assert "meta.textContent" in data


def test_enchainement_automatique_garde_fou_present(client) -> None:
    # Non-régression sur le gabarit uniquement (voir docstring du
    # fichier) : le garde-fou "played" doit rester en place autour de
    # la navigation, pas une vérification du comportement réel du
    # navigateur.
    current_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )

    response = client.get(f"/watch/{current_id}")
    data = response.data.decode()

    assert "hasPlayedGenuinely" in data
    assert "player.played" in data
    assert "window.location.href" in data


# --- fetch_item_media_progress : statut + pourcentage d'un item -------


def test_progression_item_rien_commence(client) -> None:
    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        result = fetch_item_media_progress(conn, item_id, "course")
    finally:
        conn.close()

    assert result == {"status": "not_started", "percent": 0}


def test_progression_item_une_video_sur_deux_terminee(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        result = fetch_item_media_progress(conn, item_id, "course")
    finally:
        conn.close()

    assert result == {"status": "in_progress", "percent": 50}


def test_progression_item_toutes_les_videos_terminees(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    set_duration(client, second_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    client.post(f"/media/{second_id}/progress", data={"position_seconds": "99"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        result = fetch_item_media_progress(conn, item_id, "course")
    finally:
        conn.close()

    assert result == {"status": "completed", "percent": 100}


# --- Carte de la grille -------------------------------------------------


def test_carte_sans_progression_ne_montre_rien(client) -> None:
    response = client.get("/")
    data = response.data.decode()

    assert "card-progress" not in data


def test_carte_en_cours_montre_barre_et_pourcentage(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})

    response = client.get("/")
    data = response.data.decode()

    assert 'class="card-progress"' in data
    assert "width: 50%;" in data
    assert "50 %" in data
    assert "card-progress-done" not in data


def test_carte_terminee_montre_100_pourcent_avec_barre_pleine(client) -> None:
    # Revenu sur la décision d'origine (section 17 de la spec) : à
    # 100 %, même composant qu'aux autres valeurs plutôt qu'un texte
    # seul sans barre.
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    set_duration(client, second_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    client.post(f"/media/{second_id}/progress", data={"position_seconds": "99"})

    response = client.get("/")
    data = response.data.decode()

    assert 'class="card-progress"' in data
    assert "width: 100%;" in data
    assert "100 %" in data
    assert "card-progress-done" not in data


# --- Libellé du bouton hero ----------------------------------------------


def test_bouton_hero_commencer_si_rien_commence(client) -> None:
    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "▶ Commencer" in data
    assert "▶ Continuer" not in data
    assert "▶ Revoir" not in data


def test_bouton_hero_continuer_si_en_cours(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "▶ Continuer" in data


def test_bouton_hero_revoir_si_tout_termine(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    set_duration(client, second_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    client.post(f"/media/{second_id}/progress", data={"position_seconds": "99"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    # Tout terminé : ni "Continuer" (rien à continuer), ni "Commencer"
    # (déjà fait) - "Revoir" est son propre état, pas un repli sur un
    # des deux autres verbes.
    assert "▶ Revoir" in data
    assert "▶ Continuer" not in data
    assert "▶ Commencer" not in data
    assert "▶ Reprendre" not in data


# --- États de leçon (programme et playlist) ------------------------------


def test_etats_de_lecon_dans_le_programme(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    client.post(f"/media/{second_id}/progress", data={"position_seconds": "10"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert '<span class="file-state file-state-done">✓ Terminé</span>' in data
    assert '<span class="file-state file-state-progress">En cours</span>' in data


def test_lecon_non_commencee_pas_de_badge_dans_le_programme(client) -> None:
    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "file-state" not in data


def test_etats_de_lecon_dans_la_playlist(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})

    response = client.get(f"/watch/{second_id}")
    data = response.data.decode()

    assert 'class="lesson-check done" role="img" aria-label="Terminé"' in data


def test_playlist_row_separe_numero_et_titre(client) -> None:
    media_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")

    response = client.get(f"/watch/{media_id}")
    data = response.data.decode()

    assert '<span class="file-number">001</span>' in data
    assert '<span class="file-title" title="001 - Interface">Interface</span>' in data


def test_playlist_row_pas_terminee_coche_vide(client) -> None:
    media_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")

    response = client.get(f"/watch/{media_id}")
    data = response.data.decode()

    assert 'class="lesson-check " role="img" aria-label="Non terminé"></span>' in data


def test_playlist_row_courante_affiche_position_et_barre(client) -> None:
    media_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, media_id, 688.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "10"})

    response = client.get(f"/watch/{media_id}")
    data = response.data.decode()

    assert f"0:10 / 11{NBSP}min{NBSP}28 · en cours" in data
    playlist_start = data.index('id="playlist"')
    first_row = data[playlist_start : data.index("</a>", playlist_start)]
    assert 'class="file-position-track"' in first_row
    assert "width: 1." in first_row  # 10/688*100 ~= 1.45%


def test_playlist_row_non_courante_pas_de_texte_en_cours(client) -> None:
    # Une vidéo avec une position réelle mais qui n'est pas celle
    # ouverte dans le lecteur n'affiche que sa durée, comme une vidéo
    # jamais commencée - seule la ligne courante montre "en cours".
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "10"})

    response = client.get(f"/watch/{second_id}")
    data = response.data.decode()

    first_row_start = data.index('<span class="file-number">001</span>')
    first_row = data[first_row_start : data.index("</a>", first_row_start)]
    assert "en cours" not in first_row


# --- Remise à zéro de la progression --------------------------------------


def test_remise_a_zero_efface_les_lignes_progress_de_l_item(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    client.post(f"/media/{second_id}/progress", data={"position_seconds": "10"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.post(f"/item/{item_id}/reset-progress")

    assert response.status_code in (302, 303)
    assert fetch_progress_row(client, first_id) is None
    assert fetch_progress_row(client, second_id) is None


def test_remise_a_zero_ne_touche_pas_a_la_note(client) -> None:
    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    client.post(f"/item/{item_id}/note", data={"text": "À revoir plus tard"})

    client.post(f"/item/{item_id}/reset-progress")

    response = client.get(f"/item/{item_id}")
    assert "À revoir plus tard" in response.data.decode()


def test_remise_a_zero_item_inconnu_404(client) -> None:
    response = client.post("/item/999999/reset-progress")

    assert response.status_code == 404


def test_bouton_hero_tout_recommencer_absent_sans_progression(client) -> None:
    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert 'id="dialog-reset-progress"' not in data
    assert "Tout recommencer" not in data


def test_bouton_hero_tout_recommencer_present_avec_progression(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "10"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "dialog-reset-progress" in data
    # Bouton texte visible, à côté du CTA principal - pas une icône
    # seule dans le hero (écarté par Gautier, personne ne devine ce
    # qu'une flèche circulaire efface), et pas dans le menu ⋮.
    assert (
        '<button type="button" class="btn-secondary" data-open-dialog="dialog-reset-progress">Tout recommencer</button>'
        in data
    )
    # Une action de lecture, plus une entrée de maintenance dans le
    # menu ⋮ : l'ancien libellé a disparu de la page entière.
    assert "Remettre la progression à zéro" not in data


def test_hero_sans_voir_les_ressources(client) -> None:
    # Retiré des trois types : l'onglet Ressources, juste en dessous,
    # rend le bouton redondant.
    for title in (
        "Motion Design - la formation complete (TUTO.com)",
        "S organiser pour reussir (David Allen)",
        "Adobe Illustrator CS6 (Adobe Press)",
    ):
        item_id = item_id_by_title(client, title)
        data = client.get(f"/item/{item_id}").data.decode()
        assert "Voir les ressources" not in data


def test_hero_livre_pdf_recoit_son_bouton_principal(client) -> None:
    # Depuis la tranche "Lecteur PDF" : un livre PDF a désormais un
    # lecteur, donc un bouton principal comme les autres types - plus
    # de message "format illisible" pour celui-ci.
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    media_id = media_id_by_relative_path(client, "livre.pdf")
    data = client.get(f"/item/{item_id}").data.decode()

    assert "ne peut pas encore être lu" not in data
    assert '<div class="hero-actions">' in data
    assert f'href="/read/{media_id}"' in data
    assert "▶ Commencer" in data


def test_hero_livre_non_pdf_sans_bouton_principal_menu_seul(client) -> None:
    # Un format que /read ne sait pas ouvrir (EPUB) : toujours pas de
    # lecteur, le menu ⋮ reste la seule action du hero - comportement
    # inchangé pour ce cas, contrairement au PDF ci-dessus.
    item_id = item_id_by_title(client, "Un livre EPUB (Auteur)")
    data = client.get(f"/item/{item_id}").data.decode()

    assert "ne peut pas encore être lu" in data
    assert 'class="hero-menu"' in data
    # Pas de <div class="hero-actions"> vide : absente, pas juste sans
    # enfant - aucun bouton principal à afficher pour ce livre.
    assert '<div class="hero-actions">' not in data


def test_hero_progress_absent_sans_progression(client) -> None:
    # Jamais ouvert : ni barre ni texte, rien du tout - pas une barre
    # à zéro.
    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    data = client.get(f"/item/{item_id}").data.decode()

    assert 'class="hero-progress"' not in data


def test_hero_progress_absent_pour_livre(client) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    data = client.get(f"/item/{item_id}").data.decode()

    assert 'class="hero-progress"' not in data


def test_hero_progress_formation_en_cours(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    set_duration(client, second_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    data = client.get(f"/item/{item_id}").data.decode()

    hero_progress = data[
        data.index('class="hero-progress"') : data.index(
            '<div class="hero-actions">'
        )
    ]
    assert 'class="card-progress"' in hero_progress
    assert "width: 50%;" in hero_progress
    assert f"50{NBSP}% · 1{NBSP}vidéo sur 2" in hero_progress


def test_hero_progress_audiobook_termine(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)
    # Marge = min(10800*5%, 15) = 15s -> seuil a 10785s.
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "10800"})

    item_id = item_id_by_title(client, "S organiser pour reussir (David Allen)")
    data = client.get(f"/item/{item_id}").data.decode()

    assert 'class="hero-progress"' in data
    assert f"100{NBSP}% · 3{NBSP}h{NBSP}00 sur 3{NBSP}h{NBSP}00" in data


def test_hero_menu_hors_de_la_rangee_actions(client) -> None:
    # Le menu ⋮ range les fonctions de maintenance, "Tout recommencer"
    # est une action de lecture : plus dans le même conteneur.
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "10"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    data = client.get(f"/item/{item_id}").data.decode()

    hero_actions = data[
        data.index('<div class="hero-actions">') : data.index(
            "</div>", data.index('<div class="hero-actions">')
        )
    ]
    assert "hero-menu" not in hero_actions


def test_dialog_tout_recommencer_formation_singulier_une_video(client) -> None:
    # Accord : "1 vidéo terminée" (singulier), pas "1 vidéos terminées".
    # Le second média est en cours (pas terminé) : le décompte seul
    # annoncerait "1 perte" alors qu'une position réelle sur un autre
    # fichier va aussi disparaître - la phrase supplémentaire le dit.
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    set_duration(client, second_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    client.post(f"/media/{second_id}/progress", data={"position_seconds": "10"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert (
        f"recommencer depuis le début ? 1{NBSP}vidéo\n            terminée sur\n            2."
        in data
    )
    assert "La position des vidéos en cours sera aussi effacée." in data


def test_dialog_tout_recommencer_formation_pluriel_plusieurs_videos(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    set_duration(client, second_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    client.post(f"/media/{second_id}/progress", data={"position_seconds": "99"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert (
        f"recommencer depuis le début ? 2{NBSP}vidéos\n            terminées sur\n            2."
        in data
    )
    # Aucun média "en cours" (les deux sont terminés) : pas de phrase
    # supplémentaire, elle serait fausse ici.
    assert "sera aussi effacée" not in data


def test_dialog_tout_recommencer_audiobook_annonce_la_position(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "4320"})

    item_id = item_id_by_title(client, "S organiser pour reussir (David Allen)")
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "dialog-reset-progress" in data
    assert "vidéo" not in data.split('id="dialog-reset-progress"')[1].split(
        "</dialog>"
    )[0]
    assert f"Position actuelle :\n            1{NBSP}h{NBSP}12." in data


def test_dialog_tout_recommencer_titre_en_gras_sans_guillemets(client) -> None:
    # Des guillemets français se cassent mal sur un titre long (le
    # fermant se retrouve seul en début de ligne suivante) : le titre
    # est en gras à la place, sans guillemets du tout.
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "10"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert (
        "<strong>Motion Design - la formation complete (TUTO.com)</strong>"
        in data
    )
    dialog_start = data.index('id="dialog-reset-progress"')
    dialog_html = data[dialog_start : data.index("</dialog>", dialog_start)]
    assert "«" not in dialog_html
    assert "»" not in dialog_html


def test_dialog_tout_recommencer_boutons(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "10"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "Annuler" in data
    assert "Effacer et recommencer" in data
    # Annulation au focus par défaut à l'ouverture de la boîte de
    # dialogue (autofocus natif de <dialog>.showModal()).
    assert "autofocus>Annuler</button>" in data


def test_dialog_tout_recommencer_case_obligatoire(client) -> None:
    # Bouton de validation désactivé tant que la case n'est pas cochée
    # - vérifié sur le HTML initial (l'activation elle-même est du JS,
    # non exécuté ici, voir test_dialog_case_gate_script_present).
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, first_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "10"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert '<input type="checkbox" id="confirm-reset-checkbox" data-confirm-gate="confirm-reset-button">' in data
    assert (
        '<button class="btn-mini reject" type="submit" id="confirm-reset-button" disabled>'
        in data
    )


def test_dialog_case_obligatoire_aussi_pour_audiobook(client) -> None:
    # Décidé : même mécanisme pour les deux types plutôt qu'une case en
    # moins pour l'audiobook - un seul fichier reste une perte réelle
    # (toute la position d'écoute), pas assez anodine pour justifier
    # deux comportements de confirmation différents.
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "4320"})

    item_id = item_id_by_title(client, "S organiser pour reussir (David Allen)")
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert 'data-confirm-gate="confirm-reset-button"' in data
    assert (
        '<button class="btn-mini reject" type="submit" id="confirm-reset-button" disabled>'
        in data
    )


def test_dialog_case_gate_script_present(client) -> None:
    # Non-régression sur le gabarit rendu (même principe que le
    # garde-fou "played") : le mécanisme qui décoche/désactive à la
    # fermeture doit rester en place, quelle que soit la façon dont la
    # boîte se ferme.
    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "data-confirm-gate" in data
    assert "gatedButton.disabled = !gateCheckbox.checked" in data
    assert "resetGate" in data


def test_reset_item_relance_la_lecture_depuis_la_premiere_video(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    set_duration(client, second_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    client.post(f"/media/{second_id}/progress", data={"position_seconds": "10"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.post(f"/item/{item_id}/reset-progress")

    assert response.status_code in (302, 303)
    assert response.headers["Location"] == f"/watch/{first_id}"
    assert fetch_progress_row(client, first_id) is None
    assert fetch_progress_row(client, second_id) is None


def test_reset_item_relance_la_lecture_audio(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "4320"})

    item_id = item_id_by_title(client, "S organiser pour reussir (David Allen)")
    response = client.post(f"/item/{item_id}/reset-progress")

    assert response.status_code in (302, 303)
    assert response.headers["Location"] == f"/listen/{media_id}"
    assert fetch_progress_row(client, media_id) is None


# --- compute_item_progress_percent : une règle par type -------------------
#
# La carte de la grille affiche un pourcentage calculé différemment
# selon item_type : médias terminés / total pour une formation
# (jamais les secondes vues, qui ne correspondraient à aucune coche
# précise sur plusieurs vidéos) ; position / durée en continu pour un
# audiobook (un seul fichier, donc aucune coche intermédiaire à
# respecter - l'objection ci-dessus ne s'applique pas ici).


def test_pourcentage_course_est_discret_medias_termines_sur_total() -> None:
    media_progress = [
        {"completed": True, "position_seconds": 99.0, "duration_seconds": 100.0},
        {"completed": False, "position_seconds": 10.0, "duration_seconds": 100.0},
    ]
    assert compute_item_progress_percent("course", media_progress) == 50


def test_pourcentage_course_ignore_la_position_en_cours() -> None:
    # Une vidéo à 99% de sa durée mais pas encore cochée "terminé" ne
    # doit rien ajouter au pourcentage d'une formation - seule la
    # coche compte, jamais la position brute.
    media_progress = [
        {"completed": False, "position_seconds": 99.0, "duration_seconds": 100.0},
    ]
    assert compute_item_progress_percent("course", media_progress) == 0


def test_pourcentage_audiobook_est_continu_position_sur_duree() -> None:
    media_progress = [
        {"completed": False, "position_seconds": 4320.0, "duration_seconds": 10800.0},
    ]
    assert compute_item_progress_percent("audiobook", media_progress) == 40


def test_pourcentage_audiobook_termine_vaut_100_meme_sous_la_marge() -> None:
    # is_video_completed coche "terminé" avant la toute dernière
    # seconde (marge plafonnée à 15s) : le pourcentage affiché doit
    # malgré tout valoir 100 une fois la coche posée, pas 99,86.
    media_progress = [
        {"completed": True, "position_seconds": 10785.0, "duration_seconds": 10800.0},
    ]
    assert compute_item_progress_percent("audiobook", media_progress) == 100


def test_pourcentage_audiobook_sans_position_enregistree_zero() -> None:
    media_progress = [
        {"completed": False, "position_seconds": None, "duration_seconds": 10800.0},
    ]
    assert compute_item_progress_percent("audiobook", media_progress) == 0


def test_pourcentage_sans_media_suivi_zero_quel_que_soit_le_type() -> None:
    assert compute_item_progress_percent("course", []) == 0
    assert compute_item_progress_percent("audiobook", []) == 0


# --- resolve_hero_cta : verbe et endpoint du bouton hero -------------------


def test_hero_cta_course_verbes_neutres() -> None:
    assert resolve_hero_cta("course", "not_started") == ("Commencer", "watch_video")
    assert resolve_hero_cta("course", "in_progress") == ("Continuer", "watch_video")
    assert resolve_hero_cta("course", "completed") == ("Revoir", "watch_video")


def test_hero_cta_audiobook_memes_verbes_que_la_formation() -> None:
    # Vocabulaire neutre, identique aux deux types - seul l'endpoint
    # change, pas le mot.
    assert resolve_hero_cta("audiobook", "not_started") == ("Commencer", "listen_audio")
    assert resolve_hero_cta("audiobook", "in_progress") == ("Continuer", "listen_audio")
    assert resolve_hero_cta("audiobook", "completed") == ("Revoir", "listen_audio")


# --- Audiobook : progression, lecteur, bouton hero ------------------------


def test_fetch_item_media_progress_audiobook_continu(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "4320"})

    item_id = item_id_by_title(client, "S organiser pour reussir (David Allen)")
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        result = fetch_item_media_progress(conn, item_id, "audiobook")
    finally:
        conn.close()

    assert result == {"status": "in_progress", "percent": 40}


def test_carte_audiobook_pourcentage_continu(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "4320"})

    response = client.get("/")
    data = response.data.decode()

    assert 'class="card-progress"' in data
    assert "width: 40%;" in data
    assert "40 %" in data


def test_route_listen_rend_le_lecteur_audio(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")

    response = client.get(f"/listen/{media_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert "<audio" in data
    assert f'src="/media/{media_id}/file"' in data
    # Fichier unique : pas de playlist ni de précédent/suivant, à la
    # différence du lecteur vidéo.
    assert "nav-buttons" not in data
    assert 'id="playlist"' not in data


def test_route_listen_refuse_une_video(client) -> None:
    video_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")

    response = client.get(f"/listen/{video_id}")

    assert response.status_code == 404


def test_route_watch_refuse_un_audio(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")

    response = client.get(f"/watch/{media_id}")

    assert response.status_code == 404


def test_media_file_m4b_a_un_content_type_audio(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")

    response = client.get(f"/media/{media_id}/file")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("audio/")


def test_reprise_fonctionne_pour_un_audiobook(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "37"})

    response = client.get(f"/listen/{media_id}")

    assert response.status_code == 200
    assert b"player.currentTime = 37;" in response.data


def test_repere_audio_construit_avec_la_route_listen(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")

    response = client.get(f"/listen/{media_id}")
    data = response.data.decode()

    assert f"(/listen/{media_id}?t=" in data
    # Pas de "Vidéo N" pour un fichier unique - contrairement au
    # lecteur vidéo (voir video_player.html).
    assert "'Vidéo " not in data


def test_marker_pattern_reconnait_watch_et_listen(client) -> None:
    # Non-régression sur le gabarit rendu (même principe que le
    # garde-fou "played", voir plus haut) : le motif qui détecte un
    # repère dans la note doit accepter les deux préfixes de route.
    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "\\/(?:watch|listen)\\/" in data


# --------------------------------------------------------------------
# Chapitres internes (M4B)
# --------------------------------------------------------------------


def test_listen_affiche_les_chapitres(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_chapters(
        client,
        media_id,
        [
            (0, "Introduction", 0.0, 60.0),
            (1, "Premier chapitre", 60.0, 185.0),
            (5, "Deuxième chapitre", 185.0, 245.0),
        ],
    )

    response = client.get(f"/listen/{media_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert 'id="playlist"' in data
    # Numéro affiché = position dans la liste triée par position, pas
    # l'index brut ffprobe (0, 1, 5 ici) - jamais montré tel quel.
    assert ">1<" in data
    assert ">2<" in data
    assert ">3<" in data
    assert "Introduction" in data
    assert "Premier chapitre" in data
    assert "Deuxième chapitre" in data
    # Durée de chaque chapitre (fin - début), pas la durée totale du
    # fichier : 60s, 125s, 60s.
    assert f"2{NBSP}min{NBSP}05" in data
    # Pas de coche : un chapitre n'a pas d'état "terminé" propre.
    assert "lesson-check" not in data


def test_listen_surligne_le_chapitre_courant(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 245.0)
    set_chapters(
        client,
        media_id,
        [
            (0, "Introduction", 0.0, 60.0),
            (1, "Milieu", 60.0, 185.0),
            (2, "Fin", 185.0, 245.0),
        ],
    )
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "90"})

    response = client.get(f"/listen/{media_id}")
    data = response.data.decode()

    # Le chapitre "Milieu" (position 90 dans [60, 185)) est surligné,
    # les deux autres ne le sont pas.
    assert 'class="file-row chapter-row current"' in data
    assert data.count('class="file-row chapter-row ') == 3


def test_listen_chapitre_sans_titre_naffiche_pas_de_repli(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_chapters(client, media_id, [(0, None, 0.0, 60.0)])

    response = client.get(f"/listen/{media_id}")
    data = response.data.decode()

    # Le numéro et la durée restent affichés, mais rien n'est inventé
    # à la place du titre absent - en particulier pas "Chapitre 1".
    assert ">1<" in data
    assert "Chapitre 1" not in data
    assert "file-title" not in data


def test_listen_sans_chapitres_pas_de_colonne(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")

    response = client.get(f"/listen/{media_id}")
    data = response.data.decode()

    assert 'id="playlist"' not in data
    assert "chapter-row" not in data


def test_watch_naffiche_aucune_colonne_de_chapitres(client) -> None:
    # chapters_probed_at/media_chapters ne sont pas restreints aux
    # fichiers audio (voir library_index.py), mais l'affichage, lui,
    # reste réservé à /listen dans cette tranche - même si des lignes
    # existent pour une vidéo.
    video_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_chapters(client, video_id, [(0, "Un chapitre vidéo", 0.0, 60.0)])

    response = client.get(f"/watch/{video_id}")
    data = response.data.decode()

    assert "chapter-row" not in data
    assert "Un chapitre vidéo" not in data


def test_clic_sur_un_chapitre_deplace_la_lecture_present(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_chapters(client, media_id, [(0, "Introduction", 0.0, 60.0)])

    response = client.get(f"/listen/{media_id}")
    data = response.data.decode()

    assert "player.currentTime = parseFloat(row.dataset.start)" in data


def test_surlignage_chapitre_suit_timeupdate_present(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_chapters(client, media_id, [(0, "Introduction", 0.0, 60.0)])

    response = client.get(f"/listen/{media_id}")
    data = response.data.decode()

    assert "player.addEventListener('timeupdate'" in data
    assert "row.classList.toggle('current'" in data


def test_bouton_hero_commencer_audiobook_jamais_commence(client) -> None:
    item_id = item_id_by_title(client, "S organiser pour reussir (David Allen)")
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "▶ Commencer" in data
    assert "▶ Continuer" not in data


def test_bouton_hero_continuer_audiobook_en_cours(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "4320"})

    item_id = item_id_by_title(client, "S organiser pour reussir (David Allen)")
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "▶ Continuer" in data


def test_bouton_hero_revoir_audiobook_termine(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)
    # Marge = min(10800*5%, 15) = 15s -> seuil a 10785s.
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "10800"})

    item_id = item_id_by_title(client, "S organiser pour reussir (David Allen)")
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert "▶ Revoir" in data
    assert "▶ Continuer" not in data


def test_message_format_illisible_absent_pour_audiobook(client) -> None:
    item_id = item_id_by_title(client, "S organiser pour reussir (David Allen)")
    response = client.get(f"/item/{item_id}")

    assert "ne peut pas encore être lu" not in response.data.decode()


def test_message_format_illisible_present_pour_un_livre(client) -> None:
    item_id = item_id_by_title(client, "Un livre EPUB (Auteur)")
    response = client.get(f"/item/{item_id}")

    assert "ne peut pas encore être lu" in response.data.decode()


def test_remise_a_zero_efface_aussi_la_progression_audio(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "4320"})

    item_id = item_id_by_title(client, "S organiser pour reussir (David Allen)")
    response = client.post(f"/item/{item_id}/reset-progress")

    assert response.status_code in (302, 303)
    assert fetch_progress_row(client, media_id) is None


# --- Position zéro : 0 est une valeur valide, pas une valeur absente ------
#
# sendPosition() (video_player.html, audio_player.html) comparait
# "!position" - en JavaScript, 0 est une valeur fausse, donc une
# position réellement à zéro n'était jamais envoyée au serveur. Le
# serveur, lui, distinguait déjà correctement 0 de l'absence (voir
# save_progress : "position_seconds is None"), donc rien à changer ici
# - seul le garde côté navigateur était en cause.


def test_ecriture_position_zero_est_enregistree(client) -> None:
    media_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, media_id, 100.0)

    response = client.post(
        f"/media/{media_id}/progress", data={"position_seconds": "0"}
    )

    assert response.status_code == 204
    row = fetch_progress_row(client, media_id)
    assert row["position_seconds"] == 0.0
    assert row["completed"] == 0


def test_ecriture_position_zero_audio_est_enregistree(client) -> None:
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)

    response = client.post(
        f"/media/{media_id}/progress", data={"position_seconds": "0"}
    )

    assert response.status_code == 204
    row = fetch_progress_row(client, media_id)
    assert row["position_seconds"] == 0.0


def test_sendposition_ne_confond_plus_zero_et_absent(client) -> None:
    # Non-régression sur le gabarit rendu (même principe que le
    # garde-fou "played") : l'ancien test de vérité JS a disparu, dans
    # les deux lecteurs.
    video_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    audio_id = media_id_by_relative_path(client, "livre-audio.m4b")

    video_data = client.get(f"/watch/{video_id}").data.decode()
    audio_data = client.get(f"/listen/{audio_id}").data.decode()

    for data in (video_data, audio_data):
        assert "if (!position)" not in data
        assert "typeof position !== 'number'" in data


def test_position_zero_enregistree_pas_de_script_de_reprise_car_inutile(
    client,
) -> None:
    # resolve_resume_seconds renvoie bien 0 pour une position à zéro
    # (voir son propre test plus haut), mais "{% if seek_seconds %}"
    # (Jinja) le traite comme absent - sans consequence : la vidéo
    # démarre déjà à 0 par défaut, un script qui la repositionnerait à
    # 0 ne changerait rien à l'écran. Documenté ici en non-régression
    # plutôt que corrigé, pour ne pas le confondre plus tard avec un
    # vrai bug.
    media_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, media_id, 100.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "0"})

    response = client.get(f"/watch/{media_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert not re.search(r"player\.currentTime = \d", data)
    assert 'data-seek="0"' in data


# --- Remise à zéro par média : retirée -------------------------------------
#
# La route dédiée (POST /media/<id>/reset-progress, sans confirmation)
# n'a plus aucun appelant : écartée du Programme et de la playlist (le
# geste dans la timeline suffit), puis du bouton de /listen lui-même
# (son libellé suggérait à tort qu'il relançait la lecture). Supprimée
# plutôt que laissée morte - "Tout recommencer" sur la fiche couvre
# maintenant les deux types, et une remise à zéro d'un seul fichier au
# milieu d'un item se recrée facilement le jour où elle reviendrait.


def test_reset_media_route_supprimee(client) -> None:
    media_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")

    response = client.post(f"/media/{media_id}/reset-progress")

    assert response.status_code == 404


def test_pas_de_controle_reset_par_media_dans_le_programme(client) -> None:
    # Écarté par Gautier : glisser la barre de lecture est plus rapide
    # et c'est ce que tout le monde fera - le contrôle par média
    # n'apparaît nulle part sur la fiche, même quand une vidéo a une
    # progression (donc un badge d'état visible).
    media_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, media_id, 100.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "10"})

    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    response = client.get(f"/item/{item_id}")
    data = response.data.decode()

    assert '<span class="file-state file-state-progress">En cours</span>' in data
    assert f'action="/media/{media_id}/reset-progress"' not in data


def test_pas_de_controle_reset_par_media_dans_la_playlist(client) -> None:
    media_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    set_duration(client, media_id, 100.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "10"})

    response = client.get(f"/watch/{media_id}")
    data = response.data.decode()

    assert "· en cours" in data
    assert "reset-progress" not in data


def test_pas_de_bouton_recommencer_sur_listen(client) -> None:
    # Retiré : son libellé ("Recommencer depuis le début") suggérait
    # qu'il relançait la lecture alors qu'il effaçait la progression -
    # "Tout recommencer" sur la fiche couvre maintenant l'audiobook.
    media_id = media_id_by_relative_path(client, "livre-audio.m4b")
    set_duration(client, media_id, 10800.0)
    client.post(f"/media/{media_id}/progress", data={"position_seconds": "4320"})

    response = client.get(f"/listen/{media_id}")
    data = response.data.decode()

    assert "Recommencer depuis le début" not in data
    assert "reset-progress" not in data


# --------------------------------------------------------------------
# Livre : lecteur PDF, progression en pages
# --------------------------------------------------------------------


def test_is_book_completed_derniere_page_atteinte() -> None:
    assert is_book_completed(305, 305) is True
    assert is_book_completed(304, 305) is False
    # Pas de seuil de pourcentage comme pour les médias temporels
    # (voir is_video_completed) : 304/305 est très proche de la fin
    # mais n'est pas la dernière page.


def test_is_book_completed_sans_page_count_jamais_termine() -> None:
    # pdfinfo en échec (ou livre pas encore sondé) : rien à comparer,
    # jamais "terminé".
    assert is_book_completed(999, None) is False
    assert is_book_completed(999, 0) is False


def test_resolve_resume_page_reprend_la_page_enregistree() -> None:
    row = {"page_number": 128, "completed": 0}
    assert resolve_resume_page(row) == 128


def test_resolve_resume_page_termine_repart_de_la_premiere_page() -> None:
    row = {"page_number": 305, "completed": 1}
    assert resolve_resume_page(row) is None


def test_resolve_resume_page_jamais_ouvert() -> None:
    assert resolve_resume_page(None) is None


def test_build_progress_summary_line_livre() -> None:
    assert (
        build_progress_summary_line(
            "book", 42, 0, 0, None, None, page_number=128, page_count=305
        )
        == f"42{NBSP}% · page{NBSP}128 sur 305"
    )


def test_compute_item_progress_percent_livre_continu() -> None:
    assert (
        compute_item_progress_percent(
            "book",
            [{"completed": False, "page_number": 128, "page_count": 305}],
        )
        == 42
    )


def test_compute_item_progress_percent_livre_termine_vaut_100(client) -> None:
    # Terminé force 100%, même si page_number enregistré serait
    # légèrement inférieur (index/annexes lus après la "dernière page"
    # qui a déclenché "terminé", ou simple retour en arrière ensuite).
    assert (
        compute_item_progress_percent(
            "book",
            [{"completed": True, "page_number": 300, "page_count": 305}],
        )
        == 100
    )


def test_fetch_item_media_progress_livre_avec_page_count(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)
    client.post(f"/media/{media_id}/progress", data={"page_number": "128"})

    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        progress = fetch_item_media_progress(conn, item_id, "book")
    finally:
        conn.close()

    assert progress["status"] == "in_progress"
    assert progress["percent"] == 42


def test_fetch_item_media_progress_livre_sans_page_count(client) -> None:
    # Correction demandée : sans page_count connu (pdfinfo en échec),
    # aucune progression n'est calculable ni affichable - jamais un
    # pourcentage sur une valeur absente, même si des pages ont bien
    # été enregistrées.
    media_id = media_id_by_relative_path(client, "livre.pdf")
    client.post(f"/media/{media_id}/progress", data={"page_number": "128"})

    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        progress = fetch_item_media_progress(conn, item_id, "book")
    finally:
        conn.close()

    assert progress == {"status": "not_started", "percent": 0}


def test_fiche_livre_sans_page_count_aucune_barre_ni_texte(client) -> None:
    # Même vérification que le test précédent, mais au niveau du rendu
    # complet de la fiche : ni barre, ni texte, ni "Tout recommencer" -
    # comme si le livre n'avait jamais été ouvert, jamais un message
    # d'erreur.
    media_id = media_id_by_relative_path(client, "livre.pdf")
    client.post(f"/media/{media_id}/progress", data={"page_number": "128"})

    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    data = client.get(f"/item/{item_id}").data.decode()

    assert "hero-progress" not in data
    assert "Tout recommencer" not in data
    assert "▶ Commencer" in data


def test_fiche_livre_avec_page_count_affiche_barre_et_texte(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)
    client.post(f"/media/{media_id}/progress", data={"page_number": "128"})

    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    data = client.get(f"/item/{item_id}").data.decode()

    assert "hero-progress" in data
    assert f"42{NBSP}% · page{NBSP}128 sur 305" in data
    assert "▶ Continuer" in data
    assert "Tout recommencer" in data


def test_carte_grille_affiche_pourcentage_du_livre(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)
    client.post(f"/media/{media_id}/progress", data={"page_number": "128"})

    data = client.get("/").data.decode()

    # _progress_bar.html utilise un espace normal ici (comportement
    # existant, partagé par tous les types - non spécifique au livre,
    # hors périmètre de cette tranche).
    assert "42 %" in data


def test_route_read_rend_le_lecteur_pdf(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)

    response = client.get(f"/read/{media_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert "vendor/pdfjs/pdf.mjs" in data
    assert "vendor/pdfjs/pdf.worker.mjs" in data
    assert "vendor/pdfjs/cmaps/" in data
    assert "vendor/pdfjs/standard_fonts/" in data
    # Jamais de CDN externe pour PDF.js - application hors ligne.
    assert "cdn." not in data


def test_lecteur_pdf_conteneur_borne_et_observateurs_sur_ce_conteneur(client) -> None:
    # Non-régression sur le gabarit rendu, même principe que le
    # garde-fou "played" du lecteur vidéo : pas de navigateur dans
    # cette suite pour vérifier le défilement réel. Les pages défilent
    # dans #reader-viewport (hauteur bornée en JS, défilement interne -
    # même mécanisme que .playlist du lecteur vidéo), plus sur la page
    # entière : la sidebar, le fil d'Ariane, le titre et la barre
    # d'outils doivent rester visibles. root: viewport (pas null) sur
    # les deux IntersectionObserver est le point précis à ne pas
    # casser : sans lui, ils calculeraient l'intersection par rapport à
    # la fenêtre, qui ne défile plus, et plus aucune page ne se
    # rendrait ni ne s'enregistrerait comme "la plus visible" pour la
    # reprise.
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)

    data = client.get(f"/read/{media_id}").data.decode()

    assert "applyViewportBounds" in data
    assert "root: viewport" in data
    assert "root: null" not in data


def test_lecteur_pdf_suspend_le_suivi_de_visibilite_pendant_le_repositionnement(
    client,
) -> None:
    # Découvert en vérifiant la correction ci-dessus : reconstruire
    # #reader-pages (changement de zoom, de mode, navigation) vide
    # brièvement le conteneur, dont le défilement revient alors à 0
    # avant que scrollIntoView ne le replace - si l'observateur de
    # visibilité se déclenche pendant cette fenêtre, il enregistre à
    # tort la page 1 comme "la plus visible" et écrase la vraie
    # position. suppressVisibilityBriefly() suspend l'observateur le
    # temps du repositionnement ; goToPage et renderScrollAround
    # enregistrent eux-mêmes la page visée, immédiatement, sans
    # attendre l'observateur.
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)

    data = client.get(f"/read/{media_id}").data.decode()

    assert "suppressVisibilityBriefly" in data
    assert "suppressVisibilityUntil" in data


def test_lecteur_pdf_espace_les_pages_sur_reader_pages(client) -> None:
    # Le flex/gap qui sépare visuellement les pages en défilement
    # continu doit être posé sur #reader-pages (le conteneur direct des
    # .reader-page), pas sur #reader-viewport : celui-ci n'a qu'un seul
    # enfant flex (#reader-pages), donc un gap posé dessus n'a aucun
    # effet visible entre les pages. Vérifié ici via le CSS servi, pas
    # via le gabarit (la règle vit dans static/style.css).
    css_path = Path(__file__).resolve().parent.parent / "static" / "style.css"
    css = css_path.read_text(encoding="utf-8")

    reader_pages_rule = css.split("#reader-pages {", 1)[1].split("}", 1)[0]
    assert "gap" in reader_pages_rule
    assert "display: flex" in reader_pages_rule

    reader_viewport_rule = css.split(".reader-viewport {", 1)[1].split("}", 1)[0]
    assert "gap" not in reader_viewport_rule


def test_lecteur_pdf_page_par_page_revient_en_haut_au_changement_de_page(
    client,
) -> None:
    # En mode page par page, une page plus haute que l'écran ne doit
    # jamais s'ouvrir à l'ancienne position de défilement de la page
    # précédente. renderPaginated (seule fonction qui affiche une
    # nouvelle page en mode paginé - Suivant/Précédent, clavier, champ
    # de saisie du numéro de page passent tous par elle) doit remettre
    # #reader-viewport en haut. Sans effet sur le suivi de visibilité :
    # renderPaginated déconnecte déjà les deux IntersectionObserver
    # avant ce reset, donc ce repositionnement ne peut pas être
    # interprété comme un changement de page à enregistrer.
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)

    data = client.get(f"/read/{media_id}").data.decode()

    assert "viewport.scrollTop = 0" in data
    render_paginated = data.split("function renderPaginated(", 1)[1].split(
        "\n    }\n", 1
    )[0]
    assert "renderObserver.disconnect()" in render_paginated
    assert "visibilityObserver.disconnect()" in render_paginated
    assert "viewport.scrollTop = 0" in render_paginated


def test_route_read_refuse_un_livre_non_pdf(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")

    assert client.get(f"/read/{media_id}").status_code == 404


def test_route_read_refuse_une_video(client) -> None:
    media_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")

    assert client.get(f"/read/{media_id}").status_code == 404


def test_route_read_reprend_a_la_page_enregistree(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)
    client.post(f"/media/{media_id}/progress", data={"page_number": "128"})

    data = client.get(f"/read/{media_id}").data.decode()

    assert "var resumePage = 128;" in data


def test_route_read_livre_termine_repart_de_la_premiere_page(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)
    client.post(f"/media/{media_id}/progress", data={"page_number": "305"})
    assert fetch_progress_row(client, media_id)["completed"] == 1

    data = client.get(f"/read/{media_id}").data.decode()

    assert "var resumePage = 1;" in data


def test_ecriture_progression_livre_page_zero_refusee(client) -> None:
    # Une page 0 n'existe pas (contrairement à une position de 0
    # seconde, valide pour une vidéo) - ramenée à 1 par
    # save_book_progress plutôt que rejetée, mais jamais stockée telle
    # quelle.
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)

    client.post(f"/media/{media_id}/progress", data={"page_number": "0"})

    assert fetch_progress_row(client, media_id)["page_number"] == 1


def test_ecriture_progression_livre_sans_page_number_400(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.pdf")

    response = client.post(f"/media/{media_id}/progress", data={})

    assert response.status_code == 400


def test_terminer_livre_ne_redescend_jamais(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)
    client.post(f"/media/{media_id}/progress", data={"page_number": "305"})
    assert fetch_progress_row(client, media_id)["completed"] == 1

    client.post(f"/media/{media_id}/progress", data={"page_number": "10"})

    row = fetch_progress_row(client, media_id)
    assert row["page_number"] == 10
    assert row["completed"] == 1


def test_reset_progress_livre_relance_la_lecture(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)
    client.post(f"/media/{media_id}/progress", data={"page_number": "128"})

    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    response = client.post(f"/item/{item_id}/reset-progress")

    assert response.status_code in (302, 303)
    assert response.headers["Location"] == f"/read/{media_id}"
    assert fetch_progress_row(client, media_id) is None


# --- Préférences de lecture (mode, zoom) --------------------------------


def test_preferences_par_defaut_sans_ligne(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)

    data = client.get(f"/read/{media_id}").data.decode()

    assert "var mode = \"scroll\";" in data


def test_enregistrement_du_mode_de_lecture(client) -> None:
    response = client.post("/preferences", data={"reading_mode": "paginated"})

    assert response.status_code == 204
    assert fetch_preferences(client)["reading_mode"] == "paginated"


def test_enregistrement_du_zoom_seul_ne_touche_pas_le_mode(client) -> None:
    client.post("/preferences", data={"reading_mode": "paginated"})
    client.post("/preferences", data={"reading_zoom": "1.5"})

    row = fetch_preferences(client)
    assert row["reading_mode"] == "paginated"
    assert row["reading_zoom"] == 1.5


def test_enregistrement_du_mode_seul_ne_touche_pas_le_zoom(client) -> None:
    client.post("/preferences", data={"reading_zoom": "1.5"})
    client.post("/preferences", data={"reading_mode": "paginated"})

    row = fetch_preferences(client)
    assert row["reading_zoom"] == 1.5
    assert row["reading_mode"] == "paginated"


def test_mode_de_lecture_invalide_400(client) -> None:
    response = client.post("/preferences", data={"reading_mode": "n_importe_quoi"})

    assert response.status_code == 400


def test_preferences_sont_globales_pas_par_livre(client) -> None:
    # Un seul réglage pour toute l'application (décidé avec Gautier) :
    # deux livres ouverts successivement voient le même mode/zoom, il
    # n'y a rien à identifier par item dans /preferences.
    client.post("/preferences", data={"reading_mode": "paginated", "reading_zoom": "2.0"})

    media_id = media_id_by_relative_path(client, "livre.pdf")
    set_page_count(client, media_id, 305)
    data = client.get(f"/read/{media_id}").data.decode()

    assert "var mode = \"paginated\";" in data
    assert "var zoom = 2.0;" in data
