# Contributing to Polyglass

Thanks for helping! Bug reports, ideas, translations of the docs and code are all welcome.

## Reporting a bug or asking for a feature

Open an issue using the templates. For bugs, the version (tray menu → About), what you were translating
and an excerpt of the log (tray menu → Open log folder) make it much faster to fix. Check the log for
anything private before pasting it.

Security problems: please don't open a public issue, see [SECURITY.md](SECURITY.md).

## Setting up for development

You need Windows 10/11 and Python 3.11+.

```powershell
py -3.11 -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\pre-commit install      # lint and format automatically on every commit
.venv\Scripts\python -m polyglass     # run with a console, so log output is visible
```

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains how the pieces fit together.

## Before you open a pull request

```powershell
.venv\Scripts\ruff check .
.venv\Scripts\ruff format .
.venv\Scripts\python -m pytest
```

CI runs the same checks on every pull request. The OCR test needs the French Windows OCR language and is
skipped where it isn't installed.

Keep pull requests focused on one change, add or update tests for behaviour changes, and add a line under
"Unreleased" in [CHANGELOG.md](CHANGELOG.md) when users will notice the difference.

## Building the installer locally

```powershell
.venv\Scripts\pyinstaller --noconfirm polyglass.spec        # dist\Polyglass\Polyglass.exe
dist\Polyglass\Polyglass.exe --selftest                      # reads a sample page through the packaged OCR
winget install JRSoftware.InnoSetup                          # once
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" /DAppVersion=0.1.0 installer\polyglass.iss
```

The installer lands in `dist\`. The self-test exits with 0 on success and 2 when neither the French nor the
English Windows OCR language is installed.

## Releasing (maintainers)

1. Move the "Unreleased" notes in CHANGELOG.md under a new version heading.
2. Set the same version in `pyproject.toml` and `installer/version_info.txt`.
3. Commit, then tag and push: `git tag v0.2.0 && git push origin main v0.2.0`.
4. The Release workflow tests, builds the installer and publishes the GitHub release.

## Licensing of contributions

Polyglass is licensed under the GNU GPL v3 or later. By submitting a contribution you agree that it is
licensed under the same terms.
