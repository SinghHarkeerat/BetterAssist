# Better Assist

A static transfer planner with a course-equivalency chart and a personal course checklist. Made by **Harkeerat Singh**.

## Run locally

```sh
python newserver.py
```

Open http://127.0.0.1:8000. You can also use any static HTTP server. Opening `index.html` directly with `file://` will block course-data requests in most browsers.

The planner works on GitHub Pages, including a repository subdirectory. There is no JavaScript build step or browser runtime library dependency. Google Fonts are optional; local font fallbacks are provided. **Shared traffic counts, admin login, and feedback submissions require the included Python backend.** GitHub Pages cannot execute it; those features show an honest unavailable message on static hosting until the site is hosted with the backend.

The index retains the original top-level `campuses` field for older cached pages, and the new UI accepts both index formats. CSS and JavaScript URLs are versioned; bump their query version in `index.html` when publishing changed assets. The local server disables caching. If a previously opened GitHub Pages tab still shows the old interface, use Ctrl+Shift+R once to refresh its HTML.

## Included data

The bundled 2025–2026 agreements cover **De Anza College**, 26 destination campuses, and 2,571 majors. Both UC and CSU destinations are supported. These are saved agreements, not a live feed.

**Foothill agreements are not bundled.** Choosing Foothill displays an explanation and a link to ASSIST; it never substitutes De Anza courses. To add Foothill, place its actual agreement JSON files under `data/uc_to_foothill/<campus>/<YYYY_year_ID>/`, then rebuild:

```sh
python build.py
```

The builder validates the sending college and indexes actual major agreements, excluding metadata such as `reports.json`. It reads university names and major titles from agreement contents. Add additional agreement-year directories using the same layout.

## Planning behavior

- Campus, year, and major must be selected explicitly. Campus and major fields show live suggestions; use click or arrow keys and Enter to select, and Escape to dismiss. Editing either field clears its previous selection.
- The chart preserves honors alternatives, course sequences, group conjunctions, and agreement notes. Missing connectors are marked “see agreement,” not inferred.
- “Add N courses” adds the entire AND set. Selecting an OR alternative replaces the previous alternative, preserving courses shared by both sets. Honors and regular versions are mutually exclusive throughout the plan. Switching versions does not transfer completion credit to the newly selected course.
- Plans are saved separately for each college/campus/year/major in browser local storage. Reloading restores the last opened plan. Resetting the search keeps saved plans.
- The progress chart defaults to **planned matches**: fully selected course sets divided by interpretable course matches. It updates as courses are added, switched, or removed. **Completed courses** shows checked-off courses divided by the courses in the personal plan. Neither measures admission eligibility. Copy and print/PDF include planning context.
- Storage or clipboard restrictions produce a helpful fallback. Imported HTML is displayed as plain text.

## Cal-GETC

The 2025–26 Cal-GETC checklist works for De Anza and Foothill, independently of major-agreement availability. Type a course code or title under a requirement to see approved courses for that area, college, and year; click the field to browse. Each suggestion shows its title and units when available. Click or use arrow keys and Enter to select it. Selected courses are planned; checkboxes record completed coursework. Editing or replacing a selection clears its completion flag.

The bundled course snapshot contains 370 De Anza courses/course sets and 310 Foothill courses. Lecture/lab combinations retain both components. The picker prevents reusing a selected course or its honors version across unrelated GE areas, permits shared science/lab credit, and requires different subject prefixes in the two Area 4 slots. Students with approved interdisciplinary exceptions, other-college work, or exam credit should review those with a counselor rather than treating an unmatched note as an approved course.

The 12 checkpoints represent 11 courses plus the laboratory requirement. Selections, completion, and existing notes are saved by college and checklist year. Grades, total units, eligibility, and final certification still require college review; course suggestions are a dated snapshot, not live registration availability. One De Anza code (NAIS 32) has no title in the bundled major data and is shown by code without inventing a title.

The course snapshot is generated with `python tools/build_calgetc.py DEANZA_PDF FOOTHILL_PDF` using the two source PDFs below. De Anza approvals come from its advising sheet (including visually verified lab underlines), with titles and units enriched from the local sending-course records. Foothill approvals, titles, and units come directly from its ASSIST course-list export. Regeneration requires the optional PDF dependency in `requirements-dev.txt`.

- [De Anza 2025–26 course sheet, hosted by CSU East Bay](https://www.csueastbay.edu/aps/cccge2526/de-anza-college-cal-getc-2025-26.pdf), revised August 4, 2025.
- [Foothill 2025–26 approved course list](https://fhweb.foothill.edu/articulation/pdf/25-26-FH-calgetc-course-list.pdf), generated June 10, 2025.

Sources: [De Anza advising sheet](https://www.deanza.edu/articulation/documents/ge-calgetc.pdf), [De Anza area requirements](https://www.deanza.edu/autotech/management/cal-getc.html), and [Foothill advising sheet](https://foothill.edu/transfer/pdf/cal-getc-advising-sheet-2025-26.pdf). Reviewed September 22, 2026; the checklist deliberately remains labeled 2025–26 to match the bundled major agreements.

## Admin, analytics, and feedback

Use **Admin** in the website footer, or open `/admin.html` on the same server as the planner. The footer uses a relative link so it also works at `/BetterAssist/admin.html` on GitHub Pages once published. All dashboard data requires a server-verified session; knowing the page address does not grant access. The requested code has been configured in this workspace's private storage; it is never embedded in HTML, JavaScript, or this repository.

For a new installation, set the code privately:

```sh
python tools/setup_admin.py
python newserver.py
```

The setup prompt hides the code. It stores a salted scrypt hash and a random server key in `~/.betterassist-private/secrets.json`, alongside the SQLite database `engagement.sqlite3`. Override the directory using `BETTERASSIST_PRIVATE_DIR`, pointing **outside the repository**. Keep this directory private, persistent, and backed up. Changing the code signs out existing sessions. Never commit this directory or copy it into a Pages upload. Local development binds to loopback only.

The backend enforces authentication on every dashboard request, one-hour HttpOnly sessions, SameSite=Strict cookies, Secure cookies on HTTPS, exact-origin JSON POST requests, and persistent throttling (five failed login attempts per IP per 15 minutes, plus a global attempt cap). A successful login resets that IP's failure count. Requests for source files, dotfiles, private files, and directory listings are denied. A six-digit code is still a short shared secret: these protections reduce guessing; they do not promise that nobody can gain access if the code is shared or the host is compromised.

Visitors can accept or decline analytics and reopen Cookie settings in the footer. No analytics request or visitor cookie is created before acceptance. Acceptance creates a random first-party browser cookie; declining later removes it and stops tracking. Course plans and cookie preferences use local storage regardless of analytics choice. Feedback requires an explicit submit, works without accepting analytics, and is visible only to the owner.

The dashboard shows total tracked page loads, approximate unique browsers, today's opens, average ratings, and the latest 50 suggestions. The recent-days chart has been removed. The default, clearly labeled **Demo numbers** view previews 14,286 opens, 14,031 visitors, 24 opens today, and a 4.8/5 rating. **View actual traffic** switches to measured totals. Demo numbers are presentation-only and never create visitor events or fake rating submissions; the feedback inbox always contains real submissions. Reloads count as opens, retries do not count twice, and the admin page does not track itself. Cookie clearing, separate devices, blocked tracking, and declined consent affect the counts; they are not a count of verified people. The app stores hashed random browser identifiers and UTC dates, without names, referrers, course plans, raw IP addresses, or user-agent strings. IP-derived HMACs are retained for at most an hour for throttling. Hosting infrastructure may maintain its own access logs. Counts and submitted feedback remain in private SQLite storage until the owner removes them.

### Run with a production server

```sh
python -m pip install -r requirements.txt
python tools/setup_admin.py
python server.py
```

Serve the **whole site and API on the same origin**, behind an HTTPS reverse proxy. Configure these environment variables in the host's private settings:

- `BETTERASSIST_PRIVATE_DIR`: an absolute path to a private persistent volume, outside the checkout. Run setup with this same value before starting the server.
- `BETTERASSIST_ORIGIN`: the exact public HTTPS origin, such as `https://planner.example.com` (no subdirectory).
- `HOST` and `PORT`: bind address and port for Waitress; defaults are `127.0.0.1` and `8000`. Use `0.0.0.0` when required by your host.
- `BETTERASSIST_TRUSTED_PROXY`: the immediate reverse proxy's IP, when applicable. Only trust a proxy that sanitizes forwarded headers and prevents direct public access to the backend. This makes per-IP throttling use the visitor's address rather than sharing a limit across all visitors. Do not accept arbitrary forwarded headers from the public internet.

Use one persistent SQLite volume shared by this app's processes; do not deploy multiple independent copies with separate databases. The application fails closed when admin credentials or the production origin are missing. Production API errors and dashboard responses are not cached. No external hosting or deployment has been configured by these local changes.

References: [GitHub Pages is static hosting](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages), [Waitress behind a reverse proxy](https://docs.pylonsproject.org/projects/waitress/en/latest/reverse-proxy.html).

## Verify

Install the browser test dependency (Chrome must be installed):

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Tests start their own local server. They cover all bundled agreements, real UCLA sequences and honors courses, search validation, plan persistence and isolation, failed requests, stale requests, missing Foothill data, storage restrictions, copy/print, responsive layouts, legacy API path validation, admin authorization/expiry/logout, brute-force limits, cross-origin rejection, consent and revocation, shared count persistence, feedback validation/retries, and safe rendering of submitted text. Security tests use temporary private storage and a separate test code.
