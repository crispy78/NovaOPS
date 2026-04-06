from .version import VERSION, get_build_hash


def app_version(request):
    """Inject app version and build hash into every template context."""
    return {
        "app_version": VERSION,
        "app_build": get_build_hash(),
    }
