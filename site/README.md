# Chronologer public website

Plain HTML and CSS, separate from the application frontend. The Pages workflow
publishes this directory unchanged from `main`; it needs no build tools.
Add future documentation pages under `docs/` and link them from `docs/index.html`.
Use relative local links so the site works at the `/chronoapp/` project path.

`assets/chronologer.png` is copied from `frontend/assets/chronologer_icon_light.png`;
`assets/calibration.png` is copied from `docs/screenshots/curve-overlay.png`.
Refresh both calibration images from the current application with
`conda run -n chronoapp python scripts/capture_site_screenshot.py` on Windows
with Chrome installed. The script calibrates two example determinations using
the local engine and captures an isolated browser session. It also updates the
screenshot URL's content hash in `index.html` so cached images refresh on deploy.
If replacing `assets/calibration.png` manually, update both `?v=` values to the
first 16 characters of its SHA256 hash. If the image size
changes, update its width and height in `index.html`.
The download URL is deliberately pinned to `v0.1.0-beta.1` and becomes available
when that GitHub Release and its Windows ZIP asset are published manually.
