# Third-Party Notices

This repository contains only the source code and build scripts for Portable Backup Tool.
Generated artifacts such as `dist*`, `build*`, logs, and packaged binaries are intentionally excluded from source control.

## Included in source control

- Original project source under `app/` and `tests/`
- Build script `build.ps1`
- Project documentation `README.md`
- License notices in `third_party_licenses/`

## Release artifact dependencies

The Windows release package built by `PyInstaller` bundles the following third-party components:

- Python 3.10 runtime
- Tcl/Tk runtime used by Tkinter
- PyInstaller bootloader and runtime hooks

License notice files for those bundled components are included in `third_party_licenses/` and should be shipped alongside release artifacts.

## Excluded on purpose

The following are not committed to the repository and should not be uploaded as source files:

- `dist*` and `build*` directories
- runtime logs
- generated `.spec` files
- any personal backup data, test media, or third-party archives

## Practical legal note

This is a practical distribution checklist, not formal legal advice. For public or commercial redistribution, review the bundled third-party licenses and, if needed, have counsel verify the final release package.
