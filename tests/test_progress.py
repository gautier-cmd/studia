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

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from library_index import scan_library  # noqa: E402
from studia import (  # noqa: E402
    aggregate_item_progress,
    compute_item_progress_percent,
    create_app,
    fetch_item_media_progress,
    is_video_completed,
    resolve_hero_cta,
    resolve_resume_seconds,
    resolve_watch_target_media_id,
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
    # aucun lecteur pour ce type, message "format illisible" attendu.
    book = root / "Adobe Illustrator CS6 (Adobe Press)"
    make_file(book / "livre.pdf")

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


def test_carte_terminee_montre_100_pourcent_sans_barre(client) -> None:
    first_id = media_id_by_relative_path(client, "01 - Bases/001 - Interface.mp4")
    second_id = media_id_by_relative_path(client, "01 - Bases/002 - Calques.mp4")
    set_duration(client, first_id, 100.0)
    set_duration(client, second_id, 100.0)
    client.post(f"/media/{first_id}/progress", data={"position_seconds": "99"})
    client.post(f"/media/{second_id}/progress", data={"position_seconds": "99"})

    response = client.get("/")
    data = response.data.decode()

    assert 'class="card-progress-done"' in data
    assert "100 %" in data
    assert 'class="card-progress"' not in data


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

    assert '<span class="file-state file-state-done">✓ Terminé</span>' in data


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


def test_hero_livre_sans_bouton_principal_menu_seul(client) -> None:
    # Pas de lecteur pour un livre : plus de repli sur "Voir les
    # ressources" comme avant, le menu ⋮ reste la seule action du hero.
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    data = client.get(f"/item/{item_id}").data.decode()

    assert "ne peut pas encore être lu" in data
    assert 'class="hero-menu"' in data
    # Pas de <div class="hero-actions"> vide : absente, pas juste sans
    # enfant - aucun bouton principal à afficher pour un livre.
    assert '<div class="hero-actions">' not in data


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

    assert "recommencer depuis le début ? 1\n            vidéo terminée sur\n            2." in data
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

    assert "recommencer depuis le début ? 2\n            vidéos terminées sur\n            2." in data
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
    assert "Position actuelle :\n            1 h 12." in data


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
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
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

    assert response.status_code == 200
    assert b"player.currentTime =" not in response.data


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

    assert '<span class="file-state file-state-progress">En cours</span>' in data
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
