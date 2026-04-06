"""
Permission helpers for the catalog frontend.

Django model permissions used today:
  - catalog.change_product — edit product via the public edit form (and admin).

Custom permissions (see Product.Meta.permissions) for future RBAC:
  - catalog.view_product_purchase_price — show purchase price on detail / form.
  - catalog.edit_product_pricing — edit commercial price fields (list, MSRP, tax, discount).

Until roles are assigned, users with ``change_product`` keep full edit access; granular
perms can later revoke slices without changing view code.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AnonymousUser


def get_product_page_permissions(user: Any, product=None) -> dict[str, bool]:
    """Return flags for template conditionals and form field filtering."""
    if not user.is_authenticated or isinstance(user, AnonymousUser):
        return {
            'can_edit_product': False,
            'can_view_purchase_price': False,
            'can_edit_financial': False,
        }

    has_change = user.has_perm('catalog.change_product')
    has_view_cost = user.has_perm('catalog.view_product_purchase_price')
    has_edit_price = user.has_perm('catalog.edit_product_pricing')

    return {
        'can_edit_product': has_change,
        # Tighten later: require explicit view_product_purchase_price without the OR.
        'can_view_purchase_price': has_view_cost or has_change,
        'can_edit_financial': has_edit_price or has_change,
    }
