"""Tests du lecteur EPUB.

Contrairement au lecteur PDF (dont le rendu se fait entièrement côté
navigateur via PDF.js, jamais lu par le serveur), le lecteur EPUB fait
sonder et parser l'archive côté serveur (table des matières, contenu
d'un chapitre) : les tests ici utilisent de vrais fichiers EPUB
synthétiques (write_minimal_epub), pas des fichiers vides comme pour
le PDF.
"""

from __future__ import annotations

import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from library_index import scan_library  # noqa: E402
from epub_book import (  # noqa: E402
    EpubFormatError,
    count_chapters,
    parse_table_of_contents,
    render_chapter,
)
from studia import create_app  # noqa: E402


CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""


def write_minimal_epub(
    path: Path, chapters: list[tuple[str, str]], with_image: bool = False
) -> None:
    """EPUB2 minimal mais valide (NCX, spine plat) - chapters : liste
    de (titre, contenu du corps). Le premier chapitre porte un
    <script> (à retirer par render_chapter) et, si with_image, une
    image et un lien externe (à neutraliser)."""

    path.parent.mkdir(parents=True, exist_ok=True)

    manifest_items = []
    spine_items = []
    navpoints = []
    chapter_files: list[tuple[str, str]] = []

    for i, (title, body) in enumerate(chapters, start=1):
        href = f"chap{i}.xhtml"
        extra = "<script>alert(1)</script>"
        if with_image and i == 1:
            extra += (
                '<img src="images/pic.jpg" alt="illustration"/>'
                '<a href="https://example.com/">externe</a>'
                '<p onclick="alert(2)">cliquable</p>'
            )
        manifest_items.append(
            f'<item id="c{i}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        spine_items.append(f'<itemref idref="c{i}"/>')
        navpoints.append(
            f'<navPoint id="n{i}" playOrder="{i}">'
            f"<navLabel><text>{title}</text></navLabel>"
            f'<content src="{href}"/></navPoint>'
        )
        chapter_html = (
            "<?xml version='1.0'?>"
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            f"<head><title>{title}</title>"
            '<link href="styles.css" rel="stylesheet" type="text/css"/>'
            "</head>"
            f"<body><h1>{title}</h1><p>{body}</p>{extra}</body></html>"
        )
        chapter_files.append((f"OEBPS/{href}", chapter_html))

    if with_image:
        manifest_items.append(
            '<item id="img1" href="images/pic.jpg" media-type="image/jpeg"/>'
        )

    manifest_items.append(
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>'
    )

    opf = (
        "<?xml version='1.0'?>"
        '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" '
        'unique-identifier="BookID">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Livre de test</dc:title><dc:language>fr</dc:language>"
        "</metadata>"
        f'<manifest>{"".join(manifest_items)}</manifest>'
        f'<spine toc="ncx">{"".join(spine_items)}</spine>'
        "</package>"
    )

    ncx = (
        "<?xml version='1.0'?>"
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
        "<head></head><docTitle><text>Livre de test</text></docTitle>"
        f'<navMap>{"".join(navpoints)}</navMap></ncx>'
    )

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/toc.ncx", ncx)
        zf.writestr("OEBPS/styles.css", "body { color: black; }")
        for href, html in chapter_files:
            zf.writestr(href, html)
        if with_image:
            zf.writestr("OEBPS/images/pic.jpg", b"\xff\xd8\xff\xd9")


def write_epub3_without_ncx(path: Path) -> None:
    """EPUB3 sans repli NCX (nav.xhtml seul) - doit être détecté comme
    illisible par ce lecteur (voir EpubFormatError), sans lever
    d'exception jusqu'à l'utilisateur."""

    path.parent.mkdir(parents=True, exist_ok=True)

    opf = (
        "<?xml version='1.0'?>"
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="BookID">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Livre EPUB3</dc:title></metadata>"
        '<manifest>'
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        '<item id="c1" href="chap1.xhtml" media-type="application/xhtml+xml"/>'
        "</manifest>"
        '<spine><itemref idref="c1"/></spine>'
        "</package>"
    )
    nav = (
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops">'
        '<body><nav epub:type="toc"><ol><li><a href="chap1.xhtml">'
        "Chapitre 1</a></li></ol></nav></body></html>"
    )

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/nav.xhtml", nav)
        zf.writestr("OEBPS/chap1.xhtml", "<html><body><p>Contenu</p></body></html>")


# --- epub_book.py : fonctions pures, sans app Flask ---------------------


def test_parse_table_of_contents_ordre_et_titres(tmp_path: Path) -> None:
    epub_path = tmp_path / "livre.epub"
    write_minimal_epub(
        epub_path,
        [("Introduction", "a"), ("Chapitre un", "b"), ("Chapitre deux", "c")],
    )

    toc = parse_table_of_contents(epub_path)

    assert [c["title"] for c in toc] == ["Introduction", "Chapitre un", "Chapitre deux"]


def test_count_chapters_epub3_sans_ncx_renvoie_none(tmp_path: Path) -> None:
    epub_path = tmp_path / "livre3.epub"
    write_epub3_without_ncx(epub_path)

    assert count_chapters(epub_path) is None


def test_parse_table_of_contents_epub3_sans_ncx_leve_epub_format_error(
    tmp_path: Path,
) -> None:
    epub_path = tmp_path / "livre3.epub"
    write_epub3_without_ncx(epub_path)

    with pytest.raises(EpubFormatError):
        parse_table_of_contents(epub_path)


def test_render_chapter_retire_script_et_gestionnaire_devenement(
    tmp_path: Path,
) -> None:
    epub_path = tmp_path / "livre.epub"
    write_minimal_epub(epub_path, [("Un", "a"), ("Deux", "b")], with_image=True)
    toc = parse_table_of_contents(epub_path)

    chapter = render_chapter(epub_path, toc[0]["href"], lambda p: f"/asset/{p}")

    assert "<script" not in chapter["body_html"]
    assert "onclick" not in chapter["body_html"]


def test_render_chapter_retire_lien_externe(tmp_path: Path) -> None:
    epub_path = tmp_path / "livre.epub"
    write_minimal_epub(epub_path, [("Un", "a")], with_image=True)
    toc = parse_table_of_contents(epub_path)

    chapter = render_chapter(epub_path, toc[0]["href"], lambda p: f"/asset/{p}")

    assert "example.com" not in chapter["body_html"]
    # Le texte du lien reste lisible, seul l'attribut href est retiré.
    assert "externe" in chapter["body_html"]


def test_render_chapter_reecrit_les_ressources_internes(tmp_path: Path) -> None:
    epub_path = tmp_path / "livre.epub"
    write_minimal_epub(epub_path, [("Un", "a")], with_image=True)
    toc = parse_table_of_contents(epub_path)

    chapter = render_chapter(epub_path, toc[0]["href"], lambda p: f"/asset/{p}")

    assert "/asset/OEBPS/images/pic.jpg" in chapter["body_html"]
    assert chapter["stylesheet_hrefs"] == ["/asset/OEBPS/styles.css"]


# --- Application Flask : routes -----------------------------------------


def make_file(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"

    book = root / "Un livre EPUB (Auteur)"
    write_minimal_epub(
        book / "livre.epub",
        [
            ("Introduction", "Début du livre."),
            ("Chapitre un", "Contenu du premier chapitre."),
            ("Chapitre deux", "Contenu du second chapitre."),
        ],
        with_image=True,
    )

    broken = root / "Un livre EPUB3 sans NCX (Auteur)"
    write_epub3_without_ncx(broken / "livre3.epub")

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


def fetch_preferences(client):
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        return conn.execute("SELECT * FROM preferences WHERE user_id = 1").fetchone()
    finally:
        conn.close()


def set_page_count(client, media_id: int, page_count: int | None) -> None:
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)

    try:
        conn.execute(
            "UPDATE media SET page_count = ? WHERE id = ?", (page_count, media_id)
        )
        conn.commit()
    finally:
        conn.close()


def mark_chapters_probed(client, media_id: int) -> None:
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)

    try:
        conn.execute(
            "UPDATE media SET chapters_probed_at = 'x' WHERE id = ?", (media_id,)
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


def test_scan_classe_epub_en_livre(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")
    db_path = client.application.config["DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        row = conn.execute(
            "SELECT media_type, extension FROM media WHERE id = ?", (media_id,)
        ).fetchone()
    finally:
        conn.close()

    assert row["media_type"] == "book"
    assert row["extension"] == ".epub"


def test_probe_page_count_compte_les_chapitres_dun_epub(tmp_path: Path) -> None:
    epub_path = tmp_path / "livre.epub"
    write_minimal_epub(
        epub_path, [("Un", "a"), ("Deux", "b"), ("Trois", "c")]
    )

    assert count_chapters(epub_path) == 3


def test_route_read_epub_rend_le_lecteur(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")

    response = client.get(f"/read-epub/{media_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert "Introduction" in data
    assert "Chapitre un" in data
    assert "Chapitre deux" in data
    assert "epub-chapter-frame" in data
    # Jamais allow-scripts sur l'iframe elle-même : un EPUB contient du
    # HTML arbitraire. On isole précisément la balise (pas tout le
    # document, dont les commentaires du script mentionnent
    # légitimement "allow-scripts" en prose pour expliquer ce choix).
    frame_tag = data.split("<iframe id=\"epub-chapter-frame\"", 1)[1].split(">", 1)[0]
    assert 'sandbox="allow-same-origin"' in frame_tag
    assert "allow-scripts" not in frame_tag


def test_route_read_epub_bascule_defilement_chapitre_pas_page_par_page(client) -> None:
    # Décidé avec Gautier : deux modalités de lecture pour un EPUB -
    # défilement continu et chapitre par chapitre - jamais un mode page
    # par page comme le PDF (n'a pas de sens sans pages fixes).
    media_id = media_id_by_relative_path(client, "livre.epub")

    data = client.get(f"/read-epub/{media_id}").data.decode()

    assert "reader-mode-scroll" in data
    assert "reader-mode-chapter" in data
    assert "reader-mode-paginated" not in data


def test_route_read_epub_mode_par_defaut_defilement(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")

    data = client.get(f"/read-epub/{media_id}").data.decode()

    assert 'var mode = "scroll";' in data


def test_route_read_epub_reprend_le_mode_enregistre(client) -> None:
    client.post("/preferences", data={"epub_reading_mode": "chapter"})
    media_id = media_id_by_relative_path(client, "livre.epub")

    data = client.get(f"/read-epub/{media_id}").data.decode()

    assert 'var mode = "chapter";' in data


def test_enregistrement_du_mode_de_lecture_epub(client) -> None:
    response = client.post("/preferences", data={"epub_reading_mode": "chapter"})

    assert response.status_code == 204
    assert fetch_preferences(client)["epub_reading_mode"] == "chapter"


def test_mode_de_lecture_epub_invalide_400(client) -> None:
    response = client.post(
        "/preferences", data={"epub_reading_mode": "n_importe_quoi"}
    )

    assert response.status_code == 400


def test_mode_de_lecture_epub_separe_du_mode_pdf(client) -> None:
    # reading_text_scale est séparée de reading_zoom (voir CLAUDE.md) :
    # même principe pour le mode de lecture, une colonne par lecteur -
    # jamais de contamination entre les deux réglages.
    client.post("/preferences", data={"reading_mode": "paginated"})
    client.post("/preferences", data={"epub_reading_mode": "chapter"})

    row = fetch_preferences(client)
    assert row["reading_mode"] == "paginated"
    assert row["epub_reading_mode"] == "chapter"


def test_epub_chapter_retire_le_script_et_reecrit_les_ressources(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")

    data = client.get(f"/media/{media_id}/epub-chapter/1").data.decode()

    assert "<script" not in data
    assert f"/media/{media_id}/epub-asset/OEBPS/images/pic.jpg" in data
    assert f"/media/{media_id}/epub-asset/OEBPS/styles.css" in data
    assert "example.com" not in data


def test_epub_chapter_hors_limites_404(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")

    assert client.get(f"/media/{media_id}/epub-chapter/0").status_code == 404
    assert client.get(f"/media/{media_id}/epub-chapter/99").status_code == 404


def test_epub_asset_sert_l_image(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")

    response = client.get(f"/media/{media_id}/epub-asset/OEBPS/images/pic.jpg")

    assert response.status_code == 200
    assert response.data == b"\xff\xd8\xff\xd9"


def test_epub_asset_refuse_la_traversee_de_chemin(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")

    response = client.get(f"/media/{media_id}/epub-asset/../../etc/passwd")

    assert response.status_code == 404


def test_epub_asset_sert_la_feuille_de_style_sanitisee(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")

    response = client.get(f"/media/{media_id}/epub-asset/OEBPS/styles.css")

    assert response.status_code == 200
    assert response.content_type.startswith("text/css")


def test_route_read_epub_epub3_sans_ncx_message_clair(client) -> None:
    media_id = media_id_by_relative_path(client, "livre3.epub")

    response = client.get(f"/read-epub/{media_id}")
    data = response.data.decode()

    assert response.status_code == 200
    assert "Ce livre utilise un format que Studia ne sait pas encore lire." in data
    # Pas de barre d'outils ni de panneau de notes pour un lecteur
    # qu'on ne peut pas construire faute de table des matières.
    assert "epub-chapter-frame" not in data


def test_hero_epub3_sans_ncx_confirme_illisible_apres_sondage(client) -> None:
    media_id = media_id_by_relative_path(client, "livre3.epub")
    item_id = item_id_by_title(client, "Un livre EPUB3 sans NCX (Auteur)")

    # Avant sondage : pas encore de signal "confirmé illisible", le
    # bouton reste affiché (comme un PDF dont pdfinfo n'a pas encore
    # tourné) - jamais un message d'erreur prématuré.
    data_avant = client.get(f"/item/{item_id}").data.decode()
    assert "ne peut pas encore être lu" not in data_avant

    # Après sondage (chapters_probed_at posé, page_count resté None -
    # voir library_index.probe_missing_media_info) : confirmé
    # illisible, message existant plutôt qu'un bouton menant à une
    # page cassée.
    mark_chapters_probed(client, media_id)
    data_apres = client.get(f"/item/{item_id}").data.decode()
    assert "ne peut pas encore être lu" in data_apres


def test_route_read_epub_reprend_au_chapitre_enregistre(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")
    client.post(f"/media/{media_id}/progress", data={"page_number": "2"})

    data = client.get(f"/read-epub/{media_id}").data.decode()

    assert "var resumeChapter = 2;" in data


def test_route_read_epub_livre_termine_repart_du_premier_chapitre(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")
    set_page_count(client, media_id, 3)
    client.post(f"/media/{media_id}/progress", data={"page_number": "3"})
    assert fetch_progress_row(client, media_id)["completed"] == 1

    data = client.get(f"/read-epub/{media_id}").data.decode()

    assert "var resumeChapter = 1;" in data


def test_route_read_epub_accepte_c_et_ouvre_a_ce_chapitre(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")
    client.post(f"/media/{media_id}/progress", data={"page_number": "1"})

    data = client.get(f"/read-epub/{media_id}?c=2").data.decode()

    assert "var resumeChapter = 2;" in data
    assert "var openedAtMarker = true;" in data


def test_route_read_epub_repere_n_ecrase_pas_la_position_tant_que_pas_relu(
    client,
) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")
    client.post(f"/media/{media_id}/progress", data={"page_number": "1"})

    client.get(f"/read-epub/{media_id}?c=2")

    assert fetch_progress_row(client, media_id)["page_number"] == 1


def test_progression_epub_pourcentage_et_ligne_de_resume(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")
    item_id = item_id_by_title(client, "Un livre EPUB (Auteur)")
    set_page_count(client, media_id, 3)
    client.post(f"/media/{media_id}/progress", data={"page_number": "2"})

    data = client.get(f"/item/{item_id}").data.decode()

    assert "chapitre" in data
    assert "sur 3" in data


def test_marker_pattern_reconnait_read_epub(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")

    data = client.get(f"/read-epub/{media_id}").data.decode()

    assert "\\/read-epub\\/\\d+\\?c=\\d+" in data


def test_repere_epub_utilise_le_titre_pas_le_numero(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")

    data = client.get(f"/read-epub/{media_id}").data.decode()

    assert "var marker = chapterTitle + ' (/read-epub/" in data
    assert "'Chapitre ' + chapterNumber" in data  # repli seulement


def test_bouton_repere_epub_dans_le_panneau(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")

    data = client.get(f"/read-epub/{media_id}").data.decode()

    assert 'id="insert-marker"' in data
    assert "Insérer le chapitre" in data
    assert 'id="dialog-note"' in data


def test_repere_epub_insere_et_retrouve_sur_la_fiche(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")
    item_id = item_id_by_title(client, "Un livre EPUB (Auteur)")

    marker_text = f"Chapitre un (/read-epub/{media_id}?c=2)\n"
    client.post(f"/item/{item_id}/note", data={"text": marker_text})

    fiche = client.get(f"/item/{item_id}").data.decode()
    reader_page = client.get(f"/read-epub/{media_id}").data.decode()
    assert f"(/read-epub/{media_id}?c=2)" in fiche
    assert f"(/read-epub/{media_id}?c=2)" in reader_page

    data = client.get(f"/read-epub/{media_id}?c=2").data.decode()
    assert "var resumeChapter = 2;" in data


def test_panneau_notes_epub_non_modal_deplacable_redimensionnable(client) -> None:
    # Même panneau que les lecteurs PDF/vidéo/audio, factorisé dans un
    # seul gabarit partagé (templates/_note_panel.html) - voir CLAUDE.md.
    media_id = media_id_by_relative_path(client, "livre.epub")

    data = client.get(f"/read-epub/{media_id}").data.decode()

    assert "notesDialog.show();" in data
    assert "notesDialog.showModal()" not in data
    # Redimensionnement géré à la main (poignée dessinée, plus de
    # ResizeObserver ni de poignée native) - voir le même commentaire
    # dans test_progress.py, test_lecteur_pdf_panneau_notes_deplacable_et_redimensionnable.
    assert "resizeHandle.addEventListener('pointerdown'" in data
    assert "new ResizeObserver(" not in data
    assert "PANEL_MIN_VISIBLE" in data


def test_reset_progress_epub_redirige_vers_read_epub(client) -> None:
    media_id = media_id_by_relative_path(client, "livre.epub")
    client.post(f"/media/{media_id}/progress", data={"page_number": "2"})

    item_id = item_id_by_title(client, "Un livre EPUB (Auteur)")
    response = client.post(f"/item/{item_id}/reset-progress")

    assert response.status_code in (302, 303)
    assert response.headers["Location"] == f"/read-epub/{media_id}"
    assert fetch_progress_row(client, media_id) is None


def test_preferences_taille_du_texte_epub(client) -> None:
    response = client.post("/preferences", data={"reading_text_scale": "1.3"})

    assert response.status_code == 204

    media_id = media_id_by_relative_path(client, "livre.epub")
    data = client.get(f"/read-epub/{media_id}").data.decode()
    assert "var textScale = 1.3;" in data
