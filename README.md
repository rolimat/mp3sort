# mp3sort

A Python tool, with a terminal interface and a desktop GUI, that takes the `.mp3` files from a downloads folder, renames them to `Artist - Title.mp3`, cleans their tags and moves them into a flat destination folder. Before touching anything it shows a preview, and you decide what gets applied.

## Goal

Downloads arrive with messy names (`Lumen - Prisma - www.example.com.mp3`, `07. Nova Delta - Open Sky 122.mp3`) and tags full of web addresses, comments and junk genres. mp3sort leaves every file as `Artist - Title.mp3` with consistent tags, and flags anything doubtful with a ⚠ for you to review by hand instead of guessing.

## Installation

```sh
git clone <repository-url>
cd mp3sort
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # mutagen, pytest, pywebview
```

Any Python 3.14 works. `requirements.txt` also installs `pywebview` and the macOS libraries it needs, so the GUI runs from the same venv as the terminal version; no extra system packages are required.

## Terminal usage

```sh
.venv/bin/python mp3sort.py "<destination folder>"
.venv/bin/python mp3sort.py --source "<source folder>" "<destination folder>"
```

Without `--source`, the source folder last chosen in the GUI is used; if there is none, you get an error asking for `--source`. If the source or destination does not exist, you get an error and nothing is done. The destination cannot be inside the source (or the other way round).

The preview has one line per file:

```
⚠   1  Lumen - Prisma - www.example.com.mp3 → Lumen - Prisma.mp3  320 kbps  [reason]
  ✓ 2  ...
```

Columns: ⚠ flag, ✓ (selected), number, original → proposed name (names over 50 characters are cut with `…`), bitrate (`VBR` where applicable, `? kbps` if unknown) and the ⚠ reasons in `[...]`. A summary line `N ok · M ⚠` closes the list. Flagged files start deselected. The prompt `> ` appears on its own line:

- numbers (`3,5` or `3 5`): toggle those lines in or out of the selection;
- Enter: apply the selected files;
- `q` (or end of input): quit without doing anything.

A file with no proposed name cannot be included. If the source has no mp3 files it prints `No mp3 files in source`. While applying, it prints one line per file (`✓` moved, `!` copied but original not deleted, `✗` failed with the message), then `Moved: N · Left in source: M`.

## GUI usage

The GUI is a native pywebview window (spreadsheet layout) in which every tag that will be written can be edited before moving. Launch it with either:

```sh
.venv/bin/python mp3sort_gui.py
```

or double-click `mp3sort-gui.command` in Finder. macOS may block the first double-click because the script is not signed: right-click it and choose Open, or allow it in System Settings > Privacy & Security.

The page is local only: it is loaded from files inside the package, makes no network requests and runs under a strict Content-Security-Policy.

1. **Choose folders.** Use the `Choose…` buttons next to Source and Destination; they open the native folder picker. Both choices are remembered in `~/Library/Application Support/mp3sort/settings.json`. On first launch (no settings file yet) both fields show `(not set)`.
2. **Scan.** `Scan` is enabled once both folders are set. The table lists every `.mp3` with the columns: checkbox, chip (⚠ warning, ✎ edited), `#`, `Artist`, `Title`, `Genre`, `Year`, `Key`, `BPM` and `kbps` (read-only, `VBR` where applicable; in a group of duplicates, a lower bitrate than the best one is shown in red). Hover a ⚠ to see the reasons.
3. **Select.** Flagged rows start unchecked. Click the checkbox of a row to toggle it. A row with no file name (empty artist or title) cannot be checked. The footer shows `N tracks · N ok · N ⚠ · N edited · N selected`.
4. **Edit.** Double-click a cell, or focus it and press Enter, to edit it. Enter saves, Esc cancels, Tab saves and moves to the next editable cell (Shift+Tab to the previous one). Edited cells are shown in purple and the row gets a ✎ chip; typing the suggested value back clears the mark. `↺ Reset row` restores the suggested values of all fields of the selected row.
5. **Strip.** Selecting a row fills the strip under the table: the resulting file name (updated live), the editable `Album`, `Label` and `Comment` fields (same keys: Enter saves, Esc cancels), `From` (the source file name) and `Removed` (the APE tag if present, plus the old Album, Genre and Comment values that will be removed).
6. **Move.** The button reads `Move K tracks`. It asks for confirmation (`To <destination>.`, plus how many selected tracks have edited tags), then moves the files while showing `Moving i / n · <name>` and a progress bar.
7. **Results.** A results list shows each file with `✓` (moved), `!` (copied but original not deleted) or `✗` (failed, with the message), and the footer shows the same `Moved: …` summary as the terminal. The source is then rescanned automatically, so the table is up to date when you press `Scan again`.

### Validation

- **BPM:** a number from 1 to 999; a decimal comma is accepted and stored with a dot (`128,5` becomes `128.5`).
- **Year:** `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, with the year between 1900 and 2099.
- Other fields are free text, trimmed, up to 500 characters.
- An invalid value is refused with a message and the cell stays open: fix it or press Esc.
- Values already in the file (for example BPM `128.0`) are shown as they are and only validated when you edit that cell.

### What gets written

- **Untouched fields behave as before:** artist and title are written clean, album, genre and comment are removed, and year, key, BPM and label are left as they are in the file.
- **Edited fields are written exactly as typed** (only trimmed); no cleaning is applied to your text. A field edited to empty has its frame removed.
- The file name is `Artist - Title.mp3` built from the current values, updated as you edit.
- Everything else in the engine is unchanged (see Tags and Safe moves below); the written tags are verified by reading them back.

### Warnings after edits

Once a row has been edited, the warnings that describe where the suggestion came from (`tag and file name differ`, `title contains the artist`, `artist and title swapped?`, `'(group)' added/missing from file name`, `no tags, taken from file name`, `tags unreadable`) are dropped, since you decided the values. Warnings are recomputed from the current values: `remix without parentheses, check`, `odd characters in artist or title`, `no artist or title`, `duplicate of N` and `already exists in destination`. `↺ Reset row` brings back the original warnings. Fixing a ⚠ does not check the row.

### While editing, while moving, closing

- While a cell or strip field is open (or holds a value that failed validation), `Move`, `Scan`, `Choose…` and `↺ Reset row` are disabled: save with Enter or cancel with Esc first.
- `Scan` and `Choose…` ask for confirmation (`Discard N edited tracks?`) when there are unsaved edits, since they are lost when the folders are scanned again.
- While files are being moved, the table, the strip and the folder controls are disabled and the window cannot be closed, either with the window button or with Cmd+Q; both go through the same check and are refused until the move finishes.

## How it works

### Name (artist and title)

- Artist and title start from the `artist`/`title` tags. If they are missing, or the title contains `Artist - `, they are taken from the file name (dropping the track number and a trailing release group such as `-abc`).
- Cleaning removes web addresses (`www...`, `http...`, `something.com/.net/.org/.ru/.info/.io`), empty `()`, `[brackets]`, duplicated parentheses and a trailing BPM (2-3 digits between 70 and 180, e.g. `Open Sky 122`).
- When the name comes from the tags, capitalization, artist separators (`,` `&` `x`) and `feat.`/`ft` are kept as they are. When it comes from a scene-style file name (no spaces), each word is capitalized, `_` becomes a space and `__` becomes `, `.
- In the file name, `/` and `:` become `-`; the tag keeps the original text.
- Mix/remix designations go in parentheses. The `(..)` group from the file name is reused, or the phrases `Original Mix`, `Extended Mix`, `Extended`, `Extended Version`, `Radio Edit`, `Club Mix` and `Dub Mix` are wrapped. A `<x> Remix` with no parentheses is left as is and flagged "remix without parentheses, check".

### Files flagged with ⚠ (not selected by default)

The reasons shown are: `tag and file name differ`; `artist and title swapped?`; `'(group)' missing from file name` / `'(group)' added from file name`; `no tags, taken from file name`; `title contains the artist`; `no artist or title`; `odd characters in artist or title` (`< > | * "`, or any stray symbol between spaces such as ` ? ` or ` ! `; `&` `+` `/` `-` and `x` are exempt, and a `?` attached to a word like `Where To Go?` is fine); `tags unreadable`; `remix without parentheses, check`; `duplicate of N` (within the batch); `already exists in destination`.

### Tags

- `album`, `comment` and `genre` are emptied; `artist` and `title` are written clean.
- The APEv2 tag is removed entirely.
- **Traktor:** the private frame `PRIV:TRAKTOR4` is kept on purpose. Traktor may store its own copy of the comment in that block and keep showing it even after the tag is emptied.
- All other ID3 frames are left untouched. ID3 v2.3/v2.4 is written (v2.2 is rewritten as v2.4) and an existing ID3v1 tag is updated too (none is created).

### Safe moves

Copy, write the tags on the copy, verify (tags read back, duration unchanged, no APEv2), then delete the original. If anything fails the copy is deleted and the original is left intact. Nothing is ever overwritten: duplicates and conflicts in the destination are skipped (`already exists in destination, not overwritten`). The destination is flat. Only `.mp3` files are processed (recursively); everything else stays in the source, as do hidden files starting with `.`. If the original cannot be deleted after the copy is verified, both remain and it is counted separately (`Copied without deleting original`).

## Tests and tools

```sh
.venv/bin/pytest
```

- `tests/fixtures/golden.csv` holds cases with invented names (`filename,tag_artist,tag_title,expected_filename,expected_flagged`). It is the feedback channel: add a row for each badly handled case.
- Real data lives only locally, in `tests/fixtures/local/` and `tests/fixtures/audio/` (both in `.gitignore`). Test audio is generated with `tools/make_audio_fixtures.sh <folder>`; tests that need it are skipped when it is absent.
- No test touches real folders: they work in `tmp_path` or on copies.

Tools:

- `tools/extract_cases.py <folder>...`: reads the `.mp3` files and dumps file names and tags to `tests/fixtures/local/cases.json` (local only).
- `tools/report.py`: applies the rules to `cases.json` and writes `report/report.md` (local) with the ⚠ first.
- `tools/make_audio_fixtures.sh <folder>`: truncated (3 MB) copies of the first 4 `.mp3` files into `tests/fixtures/audio/`.
- `tools/make_sandbox.sh <folder>...`: recreates `sandbox/` with `sandbox/complete` (a copy of the given folders) and `sandbox/dest`, so you can try things safely. It only deletes a `sandbox/` that contains the marker file `.mp3sort-sandbox`.

## v1 limitations

- `.mp3` only; no Discogs or other metadata sources.
- A `<x> Remix` without parentheses is not fixed automatically; it is flagged for review.
- The rules are heuristics; doubtful cases are flagged with ⚠ rather than resolved.
- The GUI is tested on macOS only.
