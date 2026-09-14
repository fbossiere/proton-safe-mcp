# Maintainer checklist: first five users

The public entry points are the [English home page](index.md), the
[French home page](fr/index.md), [download instructions](download.md) and
[first-use guide](try-it.md). The installer remains on GitHub Releases; the site provides
a clear entry point rather than maintaining a second binary host.

## Before sharing the link

- Merge the website PR only after its checks and visual review pass. Confirm the subsequent
  **Documentation** deployment succeeds and the public English/French pages load.
- Click the download button on the **deployed** site. Confirm it targets the intended
  published release, and compare the downloaded installer with its published checksum.
- Confirm the feedback issue form is available on the default branch. Its link will not
  work from a pre-merge preview until GitHub has the template on `main`.
- Read the requirements from a new user's perspective: Ubuntu 24.04 x86_64, Bridge with a
  compatible plan, keyring, local compatible ChatGPT desktop / Codex. Do not promote this
  installer as a browser/mobile connector or a Windows/macOS app.
- Test the site at narrow mobile widths and 200% zoom; keep the download, prerequisites,
  privacy notice and language switch accessible. The site works on a phone, the installer does not.

## Recruit five people who can actually use this installer

Start with personal contacts who already have **all the requirements**, not just a Proton
Mail account. Invite a small first group individually, using the existing relationship and
asking whether they want to try it. Expand the group if needed; do not assume a response rate.

Offer a short optional installation call, then let them perform the three tasks themselves.
Do not ask to see their mailbox, password or confidential screen. Record whether they needed
help; an installation completed by the maintainer is not an unassisted success.

Use the same home-page link for each language. Send the first-use guide after installation.
If someone does not use GitHub, accept their feedback in the original private conversation.
Never publish their identity, quotations or screenshots without permission.

## What to learn

Keep a small **private** table with one row per consenting tester. Use an alias, not their
email address, and record only:

| Field | Why |
|---|---|
| Compatible setup confirmed | Distinguish a packaging limitation from an onboarding failure. |
| Installed unaided / with help / blocked | Measure whether the new assistant removes friction. |
| First useful search or summary | Distinguish configuration success from user value. |
| Draft checked in Proton Mail | Confirm the user understands the review-and-send boundary. |
| Used again after a few days | Learn whether the tool is useful beyond the first demonstration. |
| Main obstacle or useful task category | Decide the next improvement without collecting mail content. |

Follow up once in the original conversation after a few days, if the tester agreed.
Five useful first sessions are the initial learning target. GitHub download counts include
retries and automation; stars and downloads are **not active-user counts**. This site adds
no analytics, cookies, tracking scripts or remote fonts. GitHub hosting and download services
still have their own infrastructure and policies; do not advertise the site as “untracked.”

## Promotion after the first feedback

Fix recurring installation blockers before a broad launch. Ask testers whether an anonymous
summary of their feedback may be published. A short demonstration can then show the actual
setup, a search and a reviewed draft using a dedicated demo mailbox. No such video is implied
by the current interface screenshots; they are labelled synthetic-data renders.

Check each community's current self-promotion rules before posting. Where a post was blocked,
ask moderators about an acceptable format; do not repost variants to evade the block.
Additional directories or stores are separate publication decisions. APT, Snap and Flatpak
would introduce packaging/update maintenance; they are not prerequisites for these five trials.

## Keep downloads coherent at every release

The website deliberately links to a **specific published version**. Do not pair
`releases/latest/download/` with a versioned filename: a new latest release would break it.

1. Publish and verify the new release assets through the existing [release workflow](releasing.md).
2. In a website follow-up PR, update `extra.desktop_release` in `mkdocs.yml`, both download
   pages, the desktop guide and the stable version references. Replace the SHA-256 on both
   download pages with the value verified from the **published** installer, not a local rebuild.
   Update `size` and `size_bytes` from the published asset too: the home page and both
   download pages quote the size, and a local rebuild is not the file people receive.
3. Search the documentation for the previous version and inspect each remaining occurrence;
   examples and historical evidence may intentionally retain it.
4. Build with `mkdocs build --strict`, then run `python tests/check_built_site.py`. Verify that all download buttons agree on the release
   tag and filename, and check local links, screenshots, English/French text and mobile layout.
5. Merge and confirm the Pages deployment. Recheck the public download and feedback links.

The home page and both download pages present two systems, Ubuntu and Windows, and both
stay visible. A small script marks the visitor's likely system to bring one card forward;
it makes no request, stores nothing, and the page behaves identically without it.

While `extra.windows_release.available` is `false`, no page may link to a Windows
installer: naming the system and stating the status is right, offering a file is not.
`tests/check_built_site.py` fails the build if one appears. Flip that flag only once the
signed artefact is published and verified, and add the Windows size and digest at the same
time.

Until the follow-up deploys, the site keeps offering the previous verified installer instead
of advertising an asset that is not yet published. There is no automatic update mechanism
in the desktop app.
