from django.db.models import Sum

from .models import Cart


def cart_item_count(request) -> dict:
    """
    Expose the current user's cart item count to templates.
    Count = sum of line quantities.
    """
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'cart_item_count': 0}

    try:
        cart = Cart.objects.only('id').get(user=request.user)
    except Cart.DoesNotExist:
        return {'cart_item_count': 0}

    n = cart.lines.aggregate(n=Sum('quantity')).get('n') or 0
    return {'cart_item_count': int(n)}

