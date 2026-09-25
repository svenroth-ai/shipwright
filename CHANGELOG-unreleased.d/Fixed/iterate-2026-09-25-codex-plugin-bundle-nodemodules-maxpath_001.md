build_codex_plugin.py no longer bundles a plugin's or shared/'s node_modules, which could exceed Windows' MAX_PATH and fail the build.
