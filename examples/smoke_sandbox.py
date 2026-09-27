"""Live sandbox smoke test for the whole API-key surface. NOT run in CI.

Usage::

    DANIPA_API_KEY=dk_test_... python examples/smoke_sandbox.py

Runs, in order: merchants.me → balances.list → payment_links.create → list →
update → delete → invoices.create → get → send → void. It creates one payment
link (then deletes it) and one invoice (then voids it) in SANDBOX.

Prints only step names with OK / FAIL (and, on failure, the error class, HTTP
status and server error code). It never prints the API key or any response
body, since those can carry customer PII. Exit code 0 when every step passed.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from decimal import Decimal

from danipa import Danipa, DanipaApiError
from danipa.models import (
    CreateInvoiceRequest,
    CreatePaymentLinkRequest,
    InvoiceLineItemRequest,
    InvoiceStatus,
    UpdatePaymentLinkRequest,
)


def _describe(exc: BaseException) -> str:
    if isinstance(exc, DanipaApiError):
        return f"{type(exc).__name__} HTTP {exc.status} {exc.code}"
    return type(exc).__name__


def main() -> int:
    api_key = os.environ.get("DANIPA_API_KEY", "")
    if not api_key.startswith("dk_test_"):
        print("smoke: set DANIPA_API_KEY to a dk_test_ (sandbox) key", file=sys.stderr)
        return 2

    failures = 0
    state: dict[str, str] = {}

    def step(name: str, action: Callable[[], None]) -> None:
        nonlocal failures
        try:
            action()
        except Exception as exc:
            failures += 1
            print(f"{name:<24} FAIL ({_describe(exc)})")
        else:
            print(f"{name:<24} OK")

    with Danipa(api_key=api_key) as danipa:

        def me() -> None:
            assert danipa.merchants.me().id

        def balances() -> None:
            assert isinstance(danipa.balances.list(), list)

        def link_create() -> None:
            link = danipa.payment_links.create(
                CreatePaymentLinkRequest(title="SDK smoke (python)", amount=Decimal("1.00"))
            )
            state["link"] = link.id

        def link_list() -> None:
            page = danipa.payment_links.list(page=0, size=50)
            assert page.total_elements >= 1

        def link_update() -> None:
            link = danipa.payment_links.update(
                state["link"], UpdatePaymentLinkRequest(title="SDK smoke (python, updated)")
            )
            assert link.title == "SDK smoke (python, updated)"

        def link_delete() -> None:
            danipa.payment_links.delete(state["link"])

        def invoice_create() -> None:
            invoice = danipa.invoices.create(
                CreateInvoiceRequest(
                    customer_name="SDK Smoke",
                    line_items=[
                        InvoiceLineItemRequest(
                            description="SDK smoke line", quantity=1, unit_price=Decimal("1.00")
                        )
                    ],
                )
            )
            assert invoice.status is InvoiceStatus.DRAFT
            state["invoice"] = invoice.id

        def invoice_get() -> None:
            assert danipa.invoices.get(state["invoice"]).id == state["invoice"]

        def invoice_send() -> None:
            assert danipa.invoices.send(state["invoice"]).status is InvoiceStatus.SENT

        def invoice_void() -> None:
            assert danipa.invoices.void(state["invoice"]).status is InvoiceStatus.VOIDED

        step("merchants.me", me)
        step("balances.list", balances)
        step("payment_links.create", link_create)
        step("payment_links.list", link_list)
        step("payment_links.update", link_update)
        step("payment_links.delete", link_delete)
        step("invoices.create", invoice_create)
        step("invoices.get", invoice_get)
        step("invoices.send", invoice_send)
        step("invoices.void", invoice_void)

    print("smoke: PASS" if failures == 0 else f"smoke: FAIL ({failures} step(s))")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
