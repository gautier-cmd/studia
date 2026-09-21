"""Tests du bloc-notes par formation.

Les notes sont rattachées au chemin de bibliothèque (library_path) de
l'item, pas à son id : elles doivent survivre à un item supprimé puis
recréé par le scanner (dossier disparu puis revenu à l'identique), et
rester récupérables si le dossier est renommé (note orpheline).
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from library_index import scan_library  # noqa: E402
from studia import create_app  # noqa: E402


def make_file(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"

    book = root / "Adobe Illustrator CS6 (Adobe Press)"
    make_file(book / "920 - Adobe Illustrator CS6 - Adobe Press.pdf")

    course = root / "Motion Design - la formation complete (TUTO.com)"
    make_file(course / "01 - Bases" / "001 - Interface.mp4")
    make_file(course / "01 - Bases" / "002 - Calques.mp4")

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
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)

    try:
        row = conn.execute(
            "SELECT id FROM items WHERE title = ?", (title,)
        ).fetchone()
    finally:
        conn.close()

    return row[0]


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


def test_note_enregistree_puis_relue_sur_la_fiche(client) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")

    response = client.post(
        f"/item/{item_id}/note", data={"text": "Chapitre 3 a revoir"}
    )

    assert response.status_code == 200
    assert response.get_json()["updated_at"]

    fiche = client.get(f"/item/{item_id}").data.decode()
    assert "Chapitre 3 a revoir" in fiche


def test_note_visible_aussi_sur_le_lecteur_video(client) -> None:
    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    client.post(f"/item/{item_id}/note", data={"text": "Note partagee"})

    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )
    player_page = client.get(f"/watch/{media_id}").data.decode()

    assert "Note partagee" in player_page
    assert "Insérer le repère" in player_page


def test_note_visible_aussi_sur_le_lecteur_pdf(client) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/note", data={"text": "Note partagee"})

    media_id = media_id_by_relative_path(
        client, "920 - Adobe Illustrator CS6 - Adobe Press.pdf"
    )
    reader_page = client.get(f"/read/{media_id}").data.decode()

    assert "Note partagee" in reader_page
    # Bouton du panneau de notes du lecteur PDF, libellé différemment
    # de "Repère" (vidéo/audio) - voir test_progress.py pour le détail.
    assert "Insérer la page" in reader_page


def test_note_modifiee_depuis_le_lecteur_pdf_se_retrouve_sur_la_fiche(client) -> None:
    # La note est celle de l'item (même route /item/<id>/note, qu'on
    # écrive depuis la fiche ou depuis le panneau du lecteur) : rien de
    # nouveau à vérifier côté stockage, seulement que c'est bien le
    # même texte des deux côtés.
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/note", data={"text": "Ecrite depuis le lecteur"})

    fiche = client.get(f"/item/{item_id}").data.decode()

    assert "Ecrite depuis le lecteur" in fiche


def test_note_absente_du_lecteur_sur_fiche_sans_note(client) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")

    fiche = client.get(f"/item/{item_id}").data.decode()

    assert '<textarea id="note-text"' in fiche
    assert "Insérer un repère" not in fiche  # pas de lecteur sur cette fiche


# --------------------------------------------------------------------
# Notes sur la fiche d'item : bouton du hero, panneau flottant partagé,
# onglet "Notes" en aperçu seul - voir CLAUDE.md.
# --------------------------------------------------------------------


def test_bouton_notes_toujours_present_dans_le_hero(client) -> None:
    # Seul moyen d'écrire une première note : présent même sans note
    # existante, contrairement à l'ancien bloc tout en bas de la fiche.
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")

    fiche = client.get(f"/item/{item_id}").data.decode()

    assert '<div class="hero-actions">' in fiche
    assert 'id="reader-toggle-notes"' in fiche
    assert 'class="notes-indicator"' not in fiche


def test_bouton_notes_ouvre_le_panneau_partage_pas_une_variante(client) -> None:
    # Même gabarit que les quatre lecteurs (templates/_note_panel.html)
    # : le <dialog> non modal, jamais une seconde implémentation.
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")

    fiche = client.get(f"/item/{item_id}").data.decode()

    assert 'id="dialog-note"' in fiche
    assert "notesDialog.show();" in fiche
    assert "notesDialog.showModal()" not in fiche
    assert "resizeHandle.addEventListener('pointerdown'" in fiche


def test_indicateur_notes_apparait_quand_une_note_existe(client) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/note", data={"text": "Une note"})

    fiche = client.get(f"/item/{item_id}").data.decode()

    assert 'class="notes-indicator"' in fiche


def test_onglet_notes_absent_sans_note(client) -> None:
    # Même règle que l'onglet Ressources : l'onglet Notes ne s'affiche
    # que si la note n'est pas vide.
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")

    fiche = client.get(f"/item/{item_id}").data.decode()

    assert 'data-tab-target="notes"' not in fiche
    assert 'data-panel="notes"' not in fiche


def test_onglet_notes_present_avec_apercu_et_reperes_cliquables(client) -> None:
    item_id = item_id_by_title(
        client, "Motion Design - la formation complete (TUTO.com)"
    )
    media_id = media_id_by_relative_path(
        client, "01 - Bases/001 - Interface.mp4"
    )
    marker = f"Vidéo 1 — Interface — 0:05 (/watch/{media_id}?t=5)\n"
    client.post(f"/item/{item_id}/note", data={"text": marker + "Texte libre."})

    fiche = client.get(f"/item/{item_id}").data.decode()

    assert 'data-tab-target="notes"' in fiche
    assert 'data-panel="notes"' in fiche
    assert 'id="notes-tab-preview"' in fiche
    # Aperçu seul, jamais d'édition dans l'onglet : pas de <textarea>
    # dans son propre panneau (celle du panneau flottant reste la
    # seule, ailleurs dans la page).
    tab_panel = fiche[
        fiche.index('data-panel="notes"') : fiche.index(
            "</div>", fiche.index('id="notes-tab-preview"')
        )
    ]
    assert "<textarea" not in tab_panel
    # Rendu Markdown (window.renderNoteMarkdown, exposé par
    # _note_widget.html) plutôt qu'une seconde implémentation, avec le
    # repère toujours cliquable dans ce rendu.
    assert "window.renderNoteMarkdown(" in fiche
    assert f"/watch/{media_id}?t=5" in fiche


def test_onglet_notes_a_son_propre_bouton_imprimer(client) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/note", data={"text": "Une note"})

    fiche = client.get(f"/item/{item_id}").data.decode()

    assert 'id="notes-tab-print"' in fiche


def test_note_videe_fait_disparaitre_onglet_et_indicateur(client) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/note", data={"text": "Une note"})
    assert 'class="notes-indicator"' in client.get(f"/item/{item_id}").data.decode()

    client.post(f"/item/{item_id}/note", data={"text": ""})
    fiche = client.get(f"/item/{item_id}").data.decode()

    assert 'class="notes-indicator"' not in fiche
    assert 'data-tab-target="notes"' not in fiche


def test_note_survit_a_une_disparition_puis_retour_identique(
    client, library: Path, db: Path
) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/note", data={"text": "Ne pas perdre ceci"})

    book_dir = library / "Adobe Illustrator CS6 (Adobe Press)"
    moved = library.parent / "moved-away"
    shutil.move(str(book_dir), str(moved))

    scan_library(library, db, verbose=False)  # le dossier a disparu

    conn = sqlite3.connect(db)
    try:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM items WHERE title = 'Adobe Illustrator CS6 (Adobe Press)'"
            ).fetchone()[0]
            == 0
        )
        # La note, elle, reste en base, non liee a l'item supprime.
        assert (
            conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
        )
    finally:
        conn.close()

    shutil.move(str(moved), str(book_dir))
    scan_library(library, db, verbose=False)  # le dossier revient a l'identique

    new_item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    fiche = client.get(f"/item/{new_item_id}").data.decode()

    assert "Ne pas perdre ceci" in fiche


def test_note_devient_orpheline_apres_renommage_du_dossier(
    client, library: Path, db: Path
) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/note", data={"text": "Notes sur ce livre"})

    (library / "Adobe Illustrator CS6 (Adobe Press)").rename(
        library / "Adobe Illustrator CS6 (renomme)"
    )
    scan_library(library, db, verbose=False)

    grid = client.get("/").data.decode()
    assert "Notes sans formation (1)" in grid

    orphans_page = client.get("/notes-orphelines").data.decode()
    assert "Adobe Illustrator CS6 (Adobe Press)" in orphans_page
    assert "Notes sur ce livre" in orphans_page
    assert "Adobe Illustrator CS6 (renomme)" not in fetch_library_paths_with_notes(db)


def fetch_library_paths_with_notes(db: Path) -> list[str]:
    conn = sqlite3.connect(db)
    try:
        return [row[0] for row in conn.execute("SELECT library_path FROM notes")]
    finally:
        conn.close()


def test_rattacher_note_orpheline_a_un_item_sans_note(
    client, library: Path, db: Path
) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/note", data={"text": "Notes originales"})

    (library / "Adobe Illustrator CS6 (Adobe Press)").rename(
        library / "Adobe Illustrator CS6 (renomme)"
    )
    scan_library(library, db, verbose=False)

    new_item_id = item_id_by_title(client, "Adobe Illustrator CS6 (renomme)")

    response = client.post(
        "/notes-orphelines/reattach",
        data={
            "library_path": "Adobe Illustrator CS6 (Adobe Press)",
            "target_item_id": str(new_item_id),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    fiche = client.get(f"/item/{new_item_id}").data.decode()
    assert "Notes originales" in fiche
    assert fetch_library_paths_with_notes(db) == [
        "Adobe Illustrator CS6 (renomme)"
    ]


def test_rattacher_note_orpheline_a_un_item_avec_note_les_fusionne(
    client, library: Path, db: Path
) -> None:
    item_id = item_id_by_title(client, "Adobe Illustrator CS6 (Adobe Press)")
    client.post(f"/item/{item_id}/note", data={"text": "Ancienne note"})

    (library / "Adobe Illustrator CS6 (Adobe Press)").rename(
        library / "Adobe Illustrator CS6 (renomme)"
    )
    scan_library(library, db, verbose=False)

    new_item_id = item_id_by_title(client, "Adobe Illustrator CS6 (renomme)")
    client.post(f"/item/{new_item_id}/note", data={"text": "Nouvelle note"})

    client.post(
        "/notes-orphelines/reattach",
        data={
            "library_path": "Adobe Illustrator CS6 (Adobe Press)",
            "target_item_id": str(new_item_id),
        },
    )

    fiche = client.get(f"/item/{new_item_id}").data.decode()
    assert "Nouvelle note" in fiche
    assert "Ancienne note" in fiche
    assert len(fetch_library_paths_with_notes(db)) == 1
