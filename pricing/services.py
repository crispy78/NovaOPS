from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from catalog.models import Product
    from .models import PricingRule

_ROUNDING_INCREMENTS: dict[str, Decimal] = {
    'nearest_cent': Decimal('0.01'),
    'nearest_10c':  Decimal('0.10'),
    'nearest_50c':  Decimal('0.50'),
    'nearest_euro': Decimal('1.00'),
    'nearest_5':    Decimal('5'),
    'nearest_10':   Decimal('10'),
}


def _apply_rounding(price: Decimal, rule: 'PricingRule') -> Decimal:
    from .models import RoundingMethod
    if rule.rounding == RoundingMethod.NONE:
        return price.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
    if rule.rounding == RoundingMethod.CUSTOM:
        increment = rule.rounding_increment
    else:
        increment = _ROUNDING_INCREMENTS[rule.rounding]
    return (price / increment).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * increment


def compute_price(product: 'Product', rule: 'PricingRule') -> Decimal | None:
    """
    Apply *rule* to *product* and return the computed selling price.
    Returns None when the required source field is not set on the product.
    """
    from .models import PricingMethod
    v = rule.value
    method = rule.method

    if method == PricingMethod.COST_MARKUP:
        if product.purchase_price is None:
            return None
        price = product.purchase_price * (1 + v / Decimal('100'))

    elif method == PricingMethod.GROSS_MARGIN:
        if product.purchase_price is None:
            return None
        divisor = Decimal('1') - v / Decimal('100')
        if divisor <= 0:
            return None
        price = product.purchase_price / divisor

    elif method == PricingMethod.MSRP_DISCOUNT:
        if product.msrp is None:
            return None
        price = product.msrp * (1 - v / Decimal('100'))

    elif method == PricingMethod.LIST_DISCOUNT:
        if product.list_price is None:
            return None
        price = product.list_price * (1 - v / Decimal('100'))

    elif method == PricingMethod.FIXED_MULTIPLIER:
        if product.purchase_price is None:
            return None
        price = product.purchase_price * v

    else:
        return None

    return _apply_rounding(price, rule)


def get_effective_rule(product: 'Product') -> 'PricingRule | None':
    """
    Find the highest-priority active rule applicable to *product*.

    Resolution order (lowest priority number wins within each tier):
      1. Direct product assignment
      2. Product's own category
      3. Parent category, grandparent, … (upward tree walk)
    """
    from .models import PricingRuleAssignment

    direct = (
        PricingRuleAssignment.objects
        .filter(product=product, rule__is_active=True)
        .select_related('rule')
        .order_by('priority')
        .first()
    )
    if direct:
        return direct.rule

    category = product.category
    visited: set = set()
    while category is not None and category.pk not in visited:
        visited.add(category.pk)
        cat_assignment = (
            PricingRuleAssignment.objects
            .filter(category=category, rule__is_active=True)
            .select_related('rule')
            .order_by('priority')
            .first()
        )
        if cat_assignment:
            if category.pk == product.category_id or cat_assignment.include_subcategories:
                return cat_assignment.rule
        if category.parent_id is None:
            break
        category = category.parent

    return None


def _collect_category_ids(root_id) -> set:
    """BFS to collect root + all descendant category IDs."""
    from catalog.models import ProductCategory
    result = {root_id}
    queue = [root_id]
    while queue:
        current = queue.pop()
        children = list(
            ProductCategory.objects
            .filter(parent_id=current)
            .values_list('id', flat=True)
        )
        for cid in children:
            if cid not in result:
                result.add(cid)
                queue.append(cid)
    return result


def preview_products_for_rule(rule: 'PricingRule') -> list[dict]:
    """
    Return [{product, computed_price}, …] for all products covered by
    *rule*'s assignments. Used by the detail view preview panel.
    """
    from catalog.models import Product

    assignments = list(
        rule.assignments
        .select_related('product', 'category')
        .order_by('priority')
    )

    product_ids: set = set()
    for assignment in assignments:
        if assignment.product_id:
            product_ids.add(assignment.product_id)
        elif assignment.category_id:
            cat_ids = (
                _collect_category_ids(assignment.category_id)
                if assignment.include_subcategories
                else {assignment.category_id}
            )
            ids = Product.objects.filter(
                category_id__in=cat_ids, is_archived=False,
            ).values_list('id', flat=True)
            product_ids.update(ids)

    products = (
        Product.objects
        .filter(id__in=product_ids)
        .select_related('category')
        .order_by('name')
    )
    return [
        {'product': p, 'computed_price': compute_price(p, rule)}
        for p in products
    ]
