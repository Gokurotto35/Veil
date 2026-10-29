# Pengu Loader source

This directory is based on the official Pengu Loader repository:

- Repository: https://github.com/PenguLoader/PenguLoader
- Upstream tag: v1.1.6
- Upstream commit: 4d641f52bc5d70aac4c09dfa1fa7a043a9069aff

It holds the loader (`loader/`), the core (`core/`, built as `core.dll`) and the preload UI the core embeds
(`plugins/`), all from that commit. `core/cef/` is the `core/cef` submodule at the commit that tag references:

- Repository: https://github.com/PenguLoader/cef-headers
- Commit: b85f32a2b40a6dbc50ef4c0bacee4ec681d4884f

Veil-specific changes are intentionally limited to:

- Veil branding and links in the UI.
- The CLI commands used by Veil: `--status`, `--set-league-path`, and `--restart-client`, plus `--silent`.
- Mirroring activation state to Veil's `config.ini`: the path in `VEIL_CONFIG_PATH`, else `%LOCALAPPDATA%\\VeilApp\\config.ini`.
- IFEO written through the registry API, as upstream's current loader does: v1.1.6 ran `cmd /C reg add`, which broke on `&` and `^` in the path. Activation compares the debugger's `core.dll` path rather than the exact value.
- Core: `config::loader_dir()` uses `[General] loaderpath` from `VEIL_CONFIG_PATH`, else `%LOCALAPPDATA%\\VeilApp\\config.ini`, when it names an existing folder, and the DLL's folder otherwise.
- Core: `src/utils/veil_log.cc` logs that resolution to `%LOCALAPPDATA%\\VeilApp\\core.log`, moved to `core.log.old` past 1 MiB.
- Preload UI: the welcome dialog, the command bar's home entry and the loading text show Veil and link to its repository.

Veil's Python integration invokes the executable; it does not write the registry itself.
