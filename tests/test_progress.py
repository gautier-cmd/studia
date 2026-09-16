"""Tests de la sauvegarde de la position de lecture (vidéo).

Règles métier testées d'abord isolément (is_video_completed,
aggregate_item_progress, resolve_resume_seconds,
resolve_watch_target_video_id), puis via les routes qui les utilisent
(POST /media/<id>/progress, reprise sur GET /watch/<id>, bouton
"Regarder" sur /item/<id>).

L'écouteur "ended" du gabarit vidéo (garde-fou "played", voir
video_player.html) n'est vérifié qu'au niveau du gabarit rendu : il
n'y a pas de navigateur dans cette suite pour simuler une vraie
lecture, donc pas de simulation de timing - seulement la présence du
garde-fou, en non-régression.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from library_index import scan_library  # noqa: E402
from studia import (  # noqa: E402
    aggregate_item_progress,
    create_app,
    is_video_completed,
    resolve_resume_seconds,
    resolve_watch_target_video_id,
)


def make_file(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


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


# --- resolve_watch_target_video_id : cible du bouton "Regarder" --------


def test_cible_regarder_aucune_video() -> None:
    assert resolve_watch_target_video_id([], set()) is None


def test_cible_regarder_rien_de_commence_prend_la_premiere() -> None:
    assert resolve_watch_target_video_id([1, 2, 3], set()) == 1


def test_cible_regarder_premiere_video_non_terminee() -> None:
    assert resolve_watch_target_video_id([1, 2, 3], {1}) == 2


def test_cible_regarder_tout_termine_revient_a_la_premiere() -> None:
    assert resolve_watch_target_video_id([1, 2, 3], {1, 2, 3}) == 1


# --- Routes : écriture, reprise ----------------------------------------


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"

    course = root / "Motion Design - la formation complete (TUTO.com)"
    make_file(course / "01 - Bases" / "001 - Interface.mp4")
    make_file(course / "01 - Bases" / "002 - Calques.mp4")

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

    assert response.status_code == 200
    assert b"player.currentTime =" not in response.data


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

    assert response.status_code == 200
    assert b"player.currentTime =" not in response.data


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

    assert f'href="/watch/{second_id}">▶ Regarder' in data


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

    assert f'href="/watch/{first_id}">▶ Regarder' in data


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
