# Human-readable version — bump this manually when releasing a new version.
VERSION = "0.1"

_build_cache: str | None = None


def get_build_hash() -> str:
    """
    Return a 6-character hex string derived from the modification time of the
    newest .py or .html source file in the project tree.

    Computed once per process start (cached in ``_build_cache``), so there is
    no file-system overhead after the first call.  The value changes whenever
    any source file is saved and the development server reloads — giving an
    automatic, zero-effort build indicator.
    """
    global _build_cache
    if _build_cache is not None:
        return _build_cache

    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent

    # Directories that contain generated or third-party files — skip them so
    # only project source influences the build hash.
    _SKIP = {".venv", "__pycache__", "node_modules", "staticfiles", "media"}

    latest_mtime = 0.0
    for path in project_root.rglob("*"):
        if any(part in _SKIP for part in path.parts):
            continue
        if path.suffix in (".py", ".html"):
            try:
                mtime = path.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime
            except OSError:
                pass

    # Take the low-order 24 bits of the unix timestamp as 6 hex digits.
    # This gives a compact, readable indicator that changes with every save.
    _build_cache = format(int(latest_mtime) & 0xFFFFFF, "06x") if latest_mtime else "000000"
    return _build_cache
