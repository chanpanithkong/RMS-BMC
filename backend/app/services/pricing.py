"""Calculation engine (SRS §12.3, BR-008, BR-010, BR-033, BR-037).

Pure and side-effect free: inputs in, bill figures out. Decimal only.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from app.utils.money import ZERO, q, q4


@dataclass(frozen=True)
class LineInput:
    key: str
    unit_price: Decimal
    modifiers_total: Decimal
    quantity: Decimal
    tax_profile_id: object
    item_discount_kind: str | None = None  # Percent | Amount
    item_discount_value: Decimal | None = None


@dataclass(frozen=True)
class ChargeRule:
    charge_kind: str  # ServiceCharge | Tax
    name: str
    rate: Decimal
    base_rule: str  # DiscountedSubtotal | SubtotalPlusServiceCharge
    inclusive: bool
    order_types: tuple[str, ...]
    rule_id: object = None


@dataclass
class LineResult:
    key: str
    gross: Decimal
    item_discount: Decimal
    order_discount: Decimal
    net: Decimal


@dataclass
class ChargeResult:
    charge_type: str
    name: str
    rate: Decimal | None
    base_amount: Decimal
    amount: Decimal
    rule_id: object = None
    inclusive: bool = False


@dataclass
class BillResult:
    lines: list[LineResult]
    gross_total: Decimal
    item_discount_total: Decimal
    order_discount_total: Decimal
    discount_total: Decimal
    subtotal: Decimal
    service_charge_total: Decimal
    tax_total: Decimal
    delivery_fee: Decimal
    rounding_total: Decimal
    total: Decimal
    charges: list[ChargeResult] = field(default_factory=list)


def discount_amount(kind: str | None, value: Decimal | None, base: Decimal) -> Decimal:
    if not kind or value is None or base <= 0:
        return ZERO
    raw = base * value / Decimal(100) if kind == "Percent" else value
    return min(q4(raw), base)  # BR-037: never make a line negative


def calculate(lines: list[LineInput], order_type: str, rules_by_profile: dict[object, list[ChargeRule]], order_discount_kind: str | None = None,
              order_discount_value: Decimal | None = None, delivery_fee: Decimal = ZERO, currency: str = "USD",
              fee_rules: list[ChargeRule] | tuple = ()) -> BillResult:
    # Steps 1–3: line gross, item discounts.
    results: list[LineResult] = []
    for ln in lines:
        gross = q4((ln.unit_price + ln.modifiers_total) * ln.quantity)
        item_disc = discount_amount(ln.item_discount_kind, ln.item_discount_value, gross)
        results.append(LineResult(ln.key, gross, item_disc, ZERO, gross - item_disc))

    # Step 4: order-level discount allocated pro rata to line nets; remainder to the last line.
    nets_total = sum((r.net for r in results), ZERO)
    order_disc = q(discount_amount(order_discount_kind, order_discount_value, nets_total), currency)
    if order_disc > 0 and nets_total > 0:
        allocated = ZERO
        positive = [r for r in results if r.net > 0]
        for i, r in enumerate(positive):
            share = order_disc - allocated if i == len(positive) - 1 else q4(order_disc * r.net / nets_total)
            r.order_discount = share
            r.net -= share
            allocated += share

    gross_total = q(sum((r.gross for r in results), ZERO), currency)
    item_disc_total = q(sum((r.item_discount for r in results), ZERO), currency)
    subtotal = gross_total - item_disc_total - order_disc  # Step 5

    # Steps 6–7: service charge and taxes per the line's tax profile.
    charges: list[ChargeResult] = []
    line_profile = {ln.key: ln.tax_profile_id for ln in lines}
    by_rule: dict[tuple, dict] = {}
    for r in results:
        for rule in rules_by_profile.get(line_profile[r.key], []):
            if order_type not in rule.order_types:
                continue
            k = (rule.rule_id, rule.charge_kind, rule.name, rule.rate, rule.base_rule, rule.inclusive)
            by_rule.setdefault(k, {"rule": rule, "base": ZERO})["base"] += r.net

    service_total = ZERO
    for v in by_rule.values():
        rule: ChargeRule = v["rule"]
        if rule.charge_kind != "ServiceCharge":
            continue
        base = q(v["base"], currency)
        amount = q(base * rule.rate, currency)
        charges.append(ChargeResult("ServiceCharge", rule.name, rule.rate, base, amount, rule.rule_id))
        service_total += amount

    tax_total = ZERO
    inclusive_tax = ZERO
    for v in by_rule.values():
        rule = v["rule"]
        if rule.charge_kind != "Tax":
            continue
        base = q(v["base"], currency)
        if rule.base_rule == "SubtotalPlusServiceCharge" and subtotal > 0:
            base += q(service_total * v["base"] / subtotal, currency)
        if rule.inclusive:
            amount = q(base * rule.rate / (1 + rule.rate), currency)  # extracted, price unchanged (§6.9)
            inclusive_tax += amount
        else:
            amount = q(base * rule.rate, currency)
        charges.append(ChargeResult("Tax", rule.name, rule.rate, base, amount, rule.rule_id, rule.inclusive))
        tax_total += amount

    # BR-044: the delivery fee is a separate charge taxed by its own profile (not part of the food subtotal or its service charge).
    for rule in fee_rules:
        if rule.charge_kind != "Tax" or order_type not in rule.order_types or delivery_fee <= 0:
            continue
        if rule.inclusive:
            amount = q(delivery_fee * rule.rate / (1 + rule.rate), currency)
            inclusive_tax += amount
        else:
            amount = q(delivery_fee * rule.rate, currency)
        charges.append(ChargeResult("Tax", f"{rule.name} (delivery fee)", rule.rate, delivery_fee, amount, rule.rule_id, rule.inclusive))
        tax_total += amount

    exclusive_tax = tax_total - inclusive_tax
    total = q(subtotal + service_total + exclusive_tax + delivery_fee, currency)  # Steps 8–9
    if delivery_fee:
        charges.append(ChargeResult("DeliveryFee", "Delivery fee", None, delivery_fee, delivery_fee))
    return BillResult(results, gross_total, item_disc_total, order_disc, item_disc_total + order_disc, subtotal, service_total, tax_total, delivery_fee, ZERO, total, charges)


def split_equal(total: Decimal, parts: int, currency: str = "USD") -> list[Decimal]:
    """BR-032: shares sum to the total; the rounding remainder goes to the last bill."""
    if parts < 1:
        raise ValueError("parts must be >= 1")
    share = q(total / parts, currency)
    if share * parts > total:
        share = (total / parts).quantize(Decimal("0.01") if currency == "USD" else Decimal("1"), rounding="ROUND_DOWN")
    shares = [share] * (parts - 1)
    shares.append(total - share * (parts - 1))
    return shares
