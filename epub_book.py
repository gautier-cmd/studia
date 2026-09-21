#!/usr/bin/env python3
"""Lecture et extraction d'un EPUB : table des matières, contenu d'un
chapitre, ressources (images, polices, feuilles de style).

EPUB2/NCX uniquement pour cette tranche (voir CLAUDE.md, "Lecteur
EPUB") - un EPUB3 sans repli NCX lève EpubFormatError, à charge de
l'appelant de retomber sur un message clair plutôt que de laisser
l'exception remonter jusqu'à l'utilisateur.

Un chapitre est une entrée de la table des matières (NCX), déjà décidé
avec Gautier - pas une page, l'EPUB n'en a pas. Dédupliquée par fichier
cible (le #fragment de l'entrée est ignoré) : la première entrée qui
pointe vers un fichier donné nomme le chapitre, une entrée suivante
vers le même fichier est une sous-partie de ce même chapitre plutôt
qu'un nouveau chapitre - nécessaire pour ne pas répéter un même fichier
sous plusieurs "chapitres" au contenu identique (vérifié sur un livre
réel : 22 entrées de table des matières, seulement 13 fichiers
distincts, 7 d'entre elles n'étant que des ancres dans un seul et même
fichier). Bénéfice direct de cette règle : un chapitre correspond
toujours à un fichier entier, donc à son contenu <body> complet - pas
de découpage interne par ancre à faire, un problème autrement bien
plus dur.

Sécurité (voir CLAUDE.md) : un EPUB contient du HTML arbitraire. Toute
balise <script>, tout attribut on*=, et toute URL absolue (schéma
explicite - http:, javascript:, data:... - ou protocole-relative
//...) sont retirés avant de servir le contenu d'un chapitre ou d'une
feuille de style. Deuxième barrière, indépendante de celle-ci : le
contenu est rendu dans une iframe sandboxée sans allow-scripts (voir
templates/epub_reader.html) - un script qui aurait échappé à cette
sanitisation ne s'exécuterait de toute façon pas.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from typing import Callable

from bs4 import BeautifulSoup

NCX_NS = "{http://www.daisy.org/z3986/2005/ncx/}"
OPF_NS = "{http://www.idpf.org/2007/opf}"
CONTAINER_NS = "{urn:oasis:names:tc:opendocument:xmlns:container}"

# Un schéma explicite (http:, https:, javascript:, data:, mailto:...)
# ou une URL protocole-relative (//hote/...) : jamais une URL relative
# interne à l'EPUB, la seule sorte qu'on accepte de réécrire vers nos
# propres routes.
_SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


class EpubFormatError(Exception):
    """EPUB sans table des matières NCX exploitable (EPUB3 sans repli,
    fichier corrompu, structure inattendue)."""


def _is_external_or_dangerous(url: str) -> bool:
    url = (url or "").strip()
    if not url:
        return False
    if url.startswith("//"):
        return True
    return bool(_SCHEME_PATTERN.match(url))


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    from xml.etree import ElementTree as ET

    try:
        container = zf.read("META-INF/container.xml")
    except KeyError as exc:
        raise EpubFormatError("META-INF/container.xml absent") from exc

    root = ET.fromstring(container)
    rootfile = root.find(f".//{CONTAINER_NS}rootfile")
    full_path = rootfile.get("full-path") if rootfile is not None else None

    if not full_path:
        raise EpubFormatError("container.xml sans rootfile exploitable")

    return full_path


def _find_ncx_path(zf: zipfile.ZipFile, opf_path: str) -> str:
    from xml.etree import ElementTree as ET

    opf_dir = posixpath.dirname(opf_path)
    opf_root = ET.fromstring(zf.read(opf_path))
    manifest = opf_root.find(f"{OPF_NS}manifest")
    spine = opf_root.find(f"{OPF_NS}spine")

    if manifest is None:
        raise EpubFormatError("OPF sans manifest")

    ncx_href = None
    ncx_id = spine.get("toc") if spine is not None else None

    if ncx_id:
        for item in manifest.findall(f"{OPF_NS}item"):
            if item.get("id") == ncx_id:
                ncx_href = item.get("href")
                break

    if ncx_href is None:
        # Repli : certains fichiers déclarent le NCX dans le manifest
        # par son type sans que <spine toc="..."> le référence.
        for item in manifest.findall(f"{OPF_NS}item"):
            if item.get("media-type") == "application/x-dtbncx+xml":
                ncx_href = item.get("href")
                break

    if not ncx_href:
        raise EpubFormatError("aucun NCX déclaré (EPUB3 sans repli ?)")

    return posixpath.normpath(posixpath.join(opf_dir, ncx_href))


def _walk_navpoints(el, ns: str):
    for nav in el.findall(f"{ns}navPoint"):
        label_el = nav.find(f"{ns}navLabel/{ns}text")
        content_el = nav.find(f"{ns}content")
        title = (label_el.text or "").strip() if label_el is not None else ""
        src = content_el.get("src") if content_el is not None else None
        if src:
            yield title, src
        yield from _walk_navpoints(nav, ns)


def parse_table_of_contents(epub_path) -> list[dict]:
    """Table des matières dédupliquée par fichier cible, dans l'ordre
    du document NCX. Chaque entrée : {"title": str, "href": str}, href
    étant le chemin (dans le zip) du fichier de ce chapitre, sans
    fragment.

    Lève EpubFormatError si aucun NCX exploitable n'est trouvé, ou si
    sa table des matières est vide.
    """
    from xml.etree import ElementTree as ET

    with zipfile.ZipFile(epub_path) as zf:
        opf_path = _find_opf_path(zf)
        ncx_path = _find_ncx_path(zf, opf_path)
        # Un chemin à l'intérieur du NCX (content src=...) est relatif
        # à l'EMPLACEMENT DU NCX, pas à celui de l'OPF - les deux
        # peuvent différer (constaté sur un vrai fichier : l'OPF vit
        # dans OEBPS/, le NCX et les chapitres à la racine de
        # l'archive ; résoudre par rapport à OEBPS/ pointerait vers des
        # fichiers inexistants).
        ncx_dir = posixpath.dirname(ncx_path)

        ncx_root = ET.fromstring(zf.read(ncx_path))
        nav_map = ncx_root.find(f"{NCX_NS}navMap")

        if nav_map is None:
            raise EpubFormatError("NCX sans navMap")

        seen_files: set[str] = set()
        chapters: list[dict] = []

        for title, src in _walk_navpoints(nav_map, NCX_NS):
            file_part = src.split("#", 1)[0]
            if not file_part:
                continue

            resolved = posixpath.normpath(posixpath.join(ncx_dir, file_part))
            if resolved in seen_files:
                continue

            seen_files.add(resolved)
            chapters.append(
                {"title": title or f"Chapitre {len(chapters) + 1}", "href": resolved}
            )

        if not chapters:
            raise EpubFormatError("table des matières vide")

        return chapters


def count_chapters(epub_path) -> int | None:
    """Nombre de chapitres (voir parse_table_of_contents) - None si
    l'EPUB n'a pas de table des matières exploitable, jamais
    d'exception propagée (mêmes garanties que probe_page_count côté
    PDF)."""

    try:
        return len(parse_table_of_contents(epub_path))
    except (EpubFormatError, zipfile.BadZipFile, KeyError, SyntaxError, OSError):
        return None


def _sanitize_css(css_text: str, base_dir: str, asset_url_for: Callable[[str], str | None]) -> str:
    def replace_url(match: re.Match) -> str:
        raw = match.group(1).strip("'\" ")
        if _is_external_or_dangerous(raw):
            return "url()"
        resolved = posixpath.normpath(posixpath.join(base_dir, raw))
        new_url = asset_url_for(resolved)
        return f'url("{new_url}")' if new_url else "url()"

    css_text = re.sub(r"url\(\s*([^)]*)\s*\)", replace_url, css_text)
    # @import peut charger une feuille de style externe (donc appeler
    # le réseau) sans passer par url() - retiré entièrement plutôt que
    # réécrit, une feuille de style importée n'a pas de raison d'être
    # dans un EPUB correctement empaqueté (tout est censé être dans
    # l'archive).
    css_text = re.sub(r"@import[^;]*;", "", css_text)
    return css_text


def render_stylesheet(epub_path, href: str, asset_url_for: Callable[[str], str | None]) -> str:
    """Contenu sanitisé d'une feuille de style référencée par un
    chapitre (voir _sanitize_css)."""

    with zipfile.ZipFile(epub_path) as zf:
        raw = zf.read(href).decode("utf-8", errors="replace")

    return _sanitize_css(raw, posixpath.dirname(href), asset_url_for)


def render_chapter(
    epub_path, chapter_href: str, asset_url_for: Callable[[str], str | None]
) -> dict:
    """Document HTML sanitisé d'un chapitre - un fichier entier du
    spine (jamais un découpage par ancre, voir le choix de dédupliquer
    la table des matières par fichier). Renvoie
    {"title": str, "body_html": str, "stylesheet_hrefs": [str]} :
    l'appelant (studia.py) compose la page complète servie dans
    l'iframe, stylesheet_hrefs étant déjà résolues vers leur route de
    service.
    """

    with zipfile.ZipFile(epub_path) as zf:
        raw = zf.read(chapter_href).decode("utf-8", errors="replace")

    soup = BeautifulSoup(raw, "html.parser")
    chapter_dir = posixpath.dirname(chapter_href)

    def resolve(url: str) -> str | None:
        if _is_external_or_dangerous(url):
            return None
        resolved = posixpath.normpath(posixpath.join(chapter_dir, url))
        return asset_url_for(resolved)

    # Feuilles de style déclarées par le chapitre - conservées (sous
    # leur URL de service, resolue comme toute autre ressource
    # interne), le corps ne suffit pas seul à une mise en page fidèle.
    stylesheet_hrefs = []
    for link in soup.find_all("link", rel=lambda v: v and "stylesheet" in v):
        href = link.get("href")
        if href:
            new_url = resolve(href)
            if new_url:
                stylesheet_hrefs.append(new_url)

    for script in soup.find_all("script"):
        script.decompose()

    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower().startswith("on"):
                del tag.attrs[attr]

        if tag.name == "a" and tag.has_attr("href"):
            # Un lien interne au livre n'a pas de sens hors contexte
            # de chapitre (pas de découpage par ancre, voir plus haut)
            # et un lien externe ne doit jamais être suivi depuis une
            # page sandboxée - retiré plutôt que réécrit, le texte du
            # lien reste lisible.
            del tag.attrs["href"]

        for attr in ("src", "href"):
            if tag.has_attr(attr) and tag.name != "a":
                new_url = resolve(tag[attr])
                if new_url:
                    tag[attr] = new_url
                else:
                    del tag.attrs[attr]

        if tag.has_attr("style"):
            tag["style"] = re.sub(
                r"url\(\s*([^)]*)\s*\)",
                lambda m: (
                    f'url("{resolve(m.group(1).strip(chr(39) + chr(34) + " "))}")'
                    if resolve(m.group(1).strip(chr(39) + chr(34) + " "))
                    else "url()"
                ),
                tag["style"],
            )

        if tag.name == "style" and tag.string:
            tag.string.replace_with(_sanitize_css(tag.string, chapter_dir, resolve))

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    body = soup.find("body")
    body_html = body.decode_contents() if body is not None else str(soup)

    return {
        "title": title,
        "body_html": body_html,
        "stylesheet_hrefs": stylesheet_hrefs,
    }


def read_asset(epub_path, href: str) -> bytes:
    """Contenu brut d'une ressource interne (image, police) - aucune
    sanitisation à faire, ce ne sont pas des documents interprétés.
    Lève KeyError si absente de l'archive (chemin invalide/traversée)."""

    with zipfile.ZipFile(epub_path) as zf:
        return zf.read(href)
