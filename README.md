# Better Assist

A static transfer planner with a course-equivalency chart and a personal course checklist. Made by **Harkeerat Singh**.

## Run locally

```sh
python newserver.py
```

Open http://127.0.0.1:8000. You can also use any static HTTP server. Opening `index.html` directly with `file://` will block course-data requests in most browsers.

The site works on GitHub Pages, including a repository subdirectory. There is no JavaScript build step or runtime library dependency. Google Fonts are optional; local font fallbacks are provided.

## Included data

The bundled 2025–2026 agreements cover **De Anza College**, 26 destination campuses, and 2,571 majors. Both UC and CSU destinations are supported. These are saved agreements, not a live feed.

**Foothill agreements are not bundled.** Choosing Foothill displays an explanation and a link to ASSIST; it never substitutes De Anza courses. To add Foothill, place its actual agreement JSON files under `data/uc_to_foothill/<campus>/<YYYY_year_ID>/`, then rebuild:

```sh
python build.py
```

The builder validates the sending college and indexes actual major agreements, excluding metadata such as `reports.json`. It reads university names and major titles from agreement contents. Add additional agreement-year directories using the same layout.

## Planning behavior

- Campus, year, and major must be selected explicitly. Major search filters the list without guessing a selection.
- The chart preserves honors alternatives, course sequences, group conjunctions, and agreement notes. Missing connectors are marked “see agreement,” not inferred.
- “Add N courses” adds the entire AND set. OR choices remain separate. The checklist is a personal selection, not an automatic determination of satisfied requirements; selecting alternatives does not prevent you from planning extra courses.
- Plans are saved separately for each college/campus/year/major in browser local storage. Reloading restores the last opened plan. Resetting the search keeps saved plans.
- The completion chart measures checked-off courses in the personal plan, not admission eligibility. Copy and print/PDF include planning context.
- Storage or clipboard restrictions produce a helpful fallback. Imported HTML is displayed as plain text.

## Verify

Install the browser test dependency (Chrome must be installed):

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Tests start their own local server. They cover all bundled agreements, real UCLA sequences and honors courses, search validation, plan persistence and isolation, failed requests, stale requests, missing Foothill data, storage restrictions, copy/print, responsive layouts, and legacy API path validation.
