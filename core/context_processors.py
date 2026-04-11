from .version import VERSION, get_build_hash


def app_version(request):
    """Inject app version and build hash into every template context."""
    return {
        "app_version": VERSION,
        "app_build": get_build_hash(),
    }


def site_currency(request):
    """Inject the site-wide currency code into every template context."""
    from .models import SiteSettings
    return {"SITE_CURRENCY": SiteSettings.get().currency}
