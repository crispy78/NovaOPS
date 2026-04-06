from __future__ import annotations

import ast
import operator
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone


SAFE_OPS: dict = {
    ast.Add:  operator.add,
    ast.Sub:  operator.sub,
    ast.Mult: operator.mul,
    ast.Div:  operator.truediv,
    ast.Pow:  operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: lambda x: x,
}


def safe_eval_formula(formula: str, variables: dict[str, Decimal]) -> Decimal:
    """
    Evaluate a restricted arithmetic formula string.
    Allowed: numeric literals, variable names, +  -  *  /  **  unary minus/plus, parentheses.
    Raises ValueError on unsupported syntax or unknown variables.
    """
    try:
        tree = ast.parse(formula.strip(), mode='eval')
    except SyntaxError as exc:
        raise ValueError(f'Formula syntax error: {exc}') from exc
    return _eval_node(tree.body, variables)


def _eval_node(node: ast.expr, variables: dict[str, Decimal]) -> Decimal:
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError(f'Only numeric literals are allowed (got {node.value!r}).')
        return Decimal(str(node.value))
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ValueError(f'Unknown variable: {node.id!r}')
        return variables[node.id]
    if isinstance(node, ast.BinOp):
        op_fn = SAFE_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f'Unsupported operator: {type(node.op).__name__}')
        left  = _eval_node(node.left,  variables)
        right = _eval_node(node.right, variables)
        try:
            return Decimal(str(op_fn(left, right)))
        except ZeroDivisionError:
            raise ValueError('Division by zero in formula.')
    if isinstance(node, ast.UnaryOp):
        op_fn = SAFE_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f'Unsupported unary operator: {type(node.op).__name__}')
        return Decimal(str(op_fn(_eval_node(node.operand, variables))))
    raise ValueError(f'Unsupported expression element: {type(node).__name__}')


def validate_formula(formula: str, variable_names: list[str]) -> str | None:
    """Validate formula syntax and variable references. Returns an error string or None if valid."""
    dummy: dict[str, Decimal] = {n: Decimal('1') for n in variable_names}
    dummy.update({
        'duration_years':        Decimal('1'),
        'duration_months':       Decimal('12'),
        'quote_total':           Decimal('1'),
        'order_total':           Decimal('1'),
        'asset_purchase_price':  Decimal('1'),
    })
    try:
        safe_eval_formula(formula, dummy)
        return None
    except ValueError as exc:
        return str(exc)


def build_variable_context(contract) -> tuple[dict[str, Decimal], list[str]]:
    """
    Resolve all variables for a Contract into a dict ready for formula evaluation.
    Returns (variables_dict, list_of_missing_variable_names).
    """
    from .models import ContractVariableType

    variables: dict[str, Decimal] = {}
    missing:   list[str]          = []

    # Built-in: duration
    dy = contract.duration_years
    dm = contract.duration_months
    if dy is not None:
        variables['duration_years']  = dy
        variables['duration_months'] = dm
    else:
        missing += ['duration_years', 'duration_months']

    # Built-in: quote total
    if contract.quote_id:
        agg = contract.quote.lines.aggregate(s=Sum('line_total'))
        variables['quote_total'] = agg['s'] or Decimal('0')
    else:
        variables['quote_total'] = Decimal('0')

    # Built-in: order total
    if contract.sales_order_id:
        agg = contract.sales_order.lines.aggregate(s=Sum('line_total'))
        variables['order_total'] = agg['s'] or Decimal('0')
    else:
        variables['order_total'] = Decimal('0')

    # Built-in: asset purchase price (from linked order line if available)
    if contract.asset_id and contract.asset.order_line_id:
        ol = contract.asset.order_line
        variables['asset_purchase_price'] = Decimal(str(ol.unit_price))
    else:
        variables['asset_purchase_price'] = Decimal('0')

    # Template variables
    values_by_var_id = {
        vv.variable_id: vv.value
        for vv in contract.variable_values.all()
    }

    for var in contract.template.variables.select_related('service_rate').order_by('sort_order', 'name'):
        if var.variable_type == ContractVariableType.SERVICE_RATE:
            if var.service_rate:
                variables[var.name] = Decimal(str(var.service_rate.rate_per_hour))
            else:
                missing.append(var.name)
        elif var.variable_type == ContractVariableType.CONSTANT:
            if var.constant_value is not None:
                variables[var.name] = Decimal(str(var.constant_value))
            else:
                missing.append(var.name)
        else:  # USER_INPUT
            if var.id in values_by_var_id:
                variables[var.name] = values_by_var_id[var.id]
            elif var.default_value is not None:
                variables[var.name] = Decimal(str(var.default_value))
            else:
                missing.append(var.name)

    return variables, missing


def compute_contract(contract) -> tuple[Decimal | None, str | None]:
    """
    Evaluate a contract's formula.
    Returns (result, error_message). result is None when evaluation fails.
    """
    variables, missing = build_variable_context(contract)
    if missing:
        return None, f'Missing values for: {", ".join(missing)}'
    try:
        result = safe_eval_formula(contract.template.formula, variables)
        return result, None
    except ValueError as exc:
        return None, str(exc)


def refresh_computed_result(contract) -> tuple[Decimal | None, str | None]:
    """Compute, cache the result on the contract, and return (result, error)."""
    from .models import Contract
    result, error = compute_contract(contract)
    Contract.objects.filter(pk=contract.pk).update(
        computed_result=result,
        computed_at=timezone.now() if result is not None else None,
    )
    contract.computed_result = result
    contract.computed_at = timezone.now() if result is not None else None
    return result, error


def create_variable_value_stubs(contract) -> None:
    """
    Ensure a ContractVariableValue row exists for every user_input variable
    in the contract's template. Existing rows are left untouched.
    """
    from .models import ContractVariableType, ContractVariableValue

    existing = set(
        ContractVariableValue.objects.filter(contract=contract).values_list('variable_id', flat=True)
    )
    to_create = [
        ContractVariableValue(
            contract=contract,
            variable=var,
            value=var.default_value if var.default_value is not None else Decimal('0'),
        )
        for var in contract.template.variables.filter(variable_type=ContractVariableType.USER_INPUT)
        if var.id not in existing
    ]
    if to_create:
        ContractVariableValue.objects.bulk_create(to_create)
