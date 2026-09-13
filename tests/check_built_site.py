"""Validate the generated website, including links emitted by custom templates.

Run after ``mkdocs build --strict``. This is a build check, not a pytest module;
the normal server tests do not require the optional documentation dependencies.
"""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml


class Page(HTMLParser):
    """Collect only the HTML attributes needed for the offline build check."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.downloads: list[str] = []
        self.external_assets: list[str] = []
        self.language: str | None = None
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if identifier := attributes.get("id"):
            self.ids.add(identifier)
        if tag == "html":
            self.language = attributes.get("lang")
        if tag == "title":
            self.in_title = True
        for key in ("href", "src"):
            if value := attributes.get(key):
                self.links.append(value)
        href = attributes.get("href") or ""
        if tag == "a" and href.endswith(".deb"):
            self.downloads.append(href)
        is_asset = tag in ("script", "img", "iframe") or (
            tag == "link" and attributes.get("rel") in ("stylesheet", "preconnect")
        )
        if is_asset:
            uri = attributes.get("src") or href
            if uri.startswith(("http:", "https:", "//")):
                self.external_assets.append(uri)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data


def main() -> None:
    """Check local destinations and the six public onboarding pages."""
    config = yaml.safe_load(Path("mkdocs.yml").read_text())
    root = Path("site").resolve()
    prefix = urlsplit(config["site_url"]).path
    pages: dict[Path, Page] = {}
    for path in root.rglob("*.html"):
        page = Page()
        page.feed(path.read_text())
        pages[path] = page
    assert pages, "Build the site before checking it"
    errors: list[str] = []
    link_count = 0
    for path, page in pages.items():
        for uri in page.links:
            parsed = urlsplit(uri)
            if parsed.scheme or parsed.netloc:
                continue
            local = unquote(parsed.path)
            # Material's 404 page uses absolute paths under the deployment prefix.
            if local.startswith(prefix):
                target = root / local.removeprefix(prefix)
            elif local.startswith("/"):
                errors.append(f"{path.relative_to(root)} -> {uri}: outside deployment prefix")
                continue
            else:
                target = path.parent / local if local else path
            target = target.resolve()
            if target.is_dir():
                target /= "index.html"
            link_count += 1
            if not target.exists():
                errors.append(f"{path.relative_to(root)} -> {uri}: missing file")
            elif (
                parsed.fragment
                and target in pages
                and unquote(parsed.fragment) not in pages[target].ids
            ):
                errors.append(f"{path.relative_to(root)} -> {uri}: missing anchor")
    onboarding = {
        "index.html": "en",
        "fr/index.html": "fr",
        "download/index.html": "en",
        "fr/telecharger/index.html": "fr",
        "try-it/index.html": "en",
        "fr/essayer/index.html": "fr",
    }
    release = config["extra"]["desktop_release"]
    version = release["version"]
    expected_download = (
        "https://github.com/fbossiere/proton-safe-mcp/releases/download/"
        f"v{version}/proton-safe-assistant_{version}_amd64.deb"
    )
    assert release["url"] == expected_download, "Release version and installer URL disagree"
    for relative, language in onboarding.items():
        page = pages[root / relative]
        if page.language != language:
            errors.append(f"{relative}: incorrect HTML language {page.language}")
        if page.external_assets:
            errors.append(f"{relative}: third-party assets {page.external_assets}")
        if relative not in ("try-it/index.html", "fr/essayer/index.html") and page.downloads != [
            expected_download
        ]:
            errors.append(f"{relative}: inconsistent download {page.downloads}")
        if not page.title or page.title in ("Home", "Accueil"):
            errors.append(f"{relative}: missing descriptive title")
    assert not errors, "\n".join(errors)
    print(f"{len(pages)} pages, {link_count} local links and six onboarding pages checked.")
    print("All four download buttons target the same official versioned release asset.")


if __name__ == "__main__":
    main()
