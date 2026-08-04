# AGENTS.md

> Python library and CLI for archiving public Instagram and Threads data through their public web GraphQL endpoints.

## Commands

- Build the development image: `make build`
- Run the complete suite and coverage: `make test`
- Run offline Instagram parser tests: `pytest -q tests/test_instagram_unit.py`
- Run live Instagram smoke tests explicitly: `OUTGRAM_RUN_SMOKE=1 pytest -m instagram_smoke tests/test_instagram_smoke.py`
- Run lint: `make lint`
- Build and validate distributions: `make package-build`
- Open a development shell: `make bash`

`make test` includes doctests and coverage. Instagram live tests are opt-in; do not enable them for routine local or CI runs. Existing Threads integration tests still make real public requests. The Docker Compose development image installs the `img` and `dev` extras; rebuild it with `make build` after dependency or packaging changes.

## Packaging

- `pyproject.toml` is the packaging source of truth; do not reintroduce `setup.py` or `setup.cfg`.
- Keep the declared Python requirement at 3.7 or newer, including build-system and runtime dependency constraints.
- Put optional runtime dependencies in an appropriate extra and development-only tools in the `dev` extra. Validate distributable artifacts with `make package-build`.

## Scope and compatibility

- This is a public, unauthenticated client. Do not add login automation, cookie import, challenge solving, proxy rotation or rate-limit evasion.
- Support Python 3.7 and newer. Preserve the existing `typing.Optional`, `typing.List` and `typing.Union` style rather than introducing syntax unsupported by Python 3.7.
- Keep the library layer free of CLI output and process termination. Dataclasses in `outgram.models` are the public high-level data model; preserve their serialization and media contracts when changing parsers.
- Prefer the standard library; add a dependency only when the benefit is clear. Do not add `pandas` for CSV work.
- Use `pathlib.Path` for new path manipulation. Keep changes narrow and follow the surrounding style in existing modules.

## HTTP and scraper maintenance

- Keep request pacing conservative. Stop or retry later on `429`, `401`, `403`, challenges and login walls.
- Public query IDs, headers, variables and response shapes change without notice. Keep request-specific settings in named configuration dictionaries and parser fields optional only where public responses legitimately omit them.
- For Instagram changes, read `docs/instagram-maintenance.md` first. Follow its workflow: small logged-out HAR -> sanitized summary -> minimal fixture and unit test -> opt-in smoke test.
- HAR files, cookies, CSRF/LSD values, device identifiers and temporary media URLs are sensitive. Never commit, log or copy them into fixtures. Use `scripts/analyze_har.py HAR --profile USERNAME` for a safe summary.
- Profile pages can return SSR GraphQL data or metadata-only fallback depending on navigation headers. Preserve both paths and do not invent absent profile fields.
- Preserve the distinction between profile, post, picture, video and carousel data. Test every changed media type, pagination and compact/optional response fields.

## CLI and output

- Keep the `outgram <network> <action>` command structure and use `argparse` for new options.
- CSV output uses `csv.DictWriter` with explicit field names. Create output parent directories before writing.
- Preserve `--quiet` behavior and configured `--min-wait`/`--max-wait` pacing. Do not print progress when quiet is selected.
- Archives contain CSV metadata and downloaded media in a ZIP. Respect requested post limits before downloading media.
- `outgram instagram export` is an offline transformation of a collected post CSV into Markdown and/or HTML. Create output parent directories, preserve the requested output-path semantics (a prefix for both formats; the exact path for one), and escape CSV-derived text in HTML.

## Tests and documentation

- Use `pytest` and plain `assert`; test behavior rather than parser implementation details.
- Default to sanitized fixtures and offline unit tests. Live tests must be explicitly marked and opt-in.
- Update `README.md` when public library behavior, CLI commands, output columns, installation or supported workflows change.
- Update `docs/instagram-maintenance.md` when verified Instagram maintenance behavior changes.

## Git

- Make atomic commits with one cohesive intent. Keep preparatory refactors separate from functional changes and bugs discovered during refactoring in a following commit.
- Commit messages, code, comments, docstrings, CLI text, tests and documentation are in English.
- Do not use `git add .`; review and stage intended changes selectively.

If an instruction here becomes inaccurate, propose the correction with code or documentation evidence.
