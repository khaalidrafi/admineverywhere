"""FR-R005 line-level CSV export — the server layer (docs/csv-export.md).

Deliberately free of DRF imports: `@extend_schema` captures
`REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"]` at *decoration* time, so a test
module that imports the views before the demo-rig settings override lands in
place gets a broken schema class (found the hard way — spectacular raised
``AutoSchema.get_operation() takes 3 positional arguments but 6 were
given``). Client projects copy this file next to the model whose export they
want; the view only wraps it in an HttpResponse.

The writer is the byte-identical twin of app/src/lib/csv.ts: QUOTE_MINIMAL,
CRLF, empty for null, lowercase booleans, formula guard on text only, UTF-8
BOM on the document. Keep the two in sync the same way ``brandToCss()``
mirrors ``branding.render_css()``.
"""
import csv
import io
import re

# Parent columns, then child columns. Repeating the parent id on every child
# row is what makes a flattened export re-groupable downstream — a reader
# without the schema can still rebuild the parent.
ORDER_EXPORT_HEADER = [
    "order_id",
    "customer_id",
    "customer",
    "product_id",
    "product",
    "status",
    "total",
    "notes",
    "created_at",
    "history_id",
    "from_status",
    "to_status",
    "history_actor",
    "history_created_at",
]

FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")

# DRF serialises a DecimalField as a STRING ("−5.00"), so the writer cannot tell
# a negative decimal from the payload `-2+3` by type alone. Only a string that is
# nothing but a number is exempt from the guard: `-2+3` and `-IF(…)` keep their
# apostrophe, `-5.00` does not. app/src/lib/csv.ts applies the identical rule,
# which is what lets the two layers byte-diff; exempting one side only would
# re-open the divergence this closes.
NUMERIC_SHAPED = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")


def is_formula_text(text):
    """True when a TEXT cell must be neutralised (numbers never are)."""
    return bool(text) and text[0] in FORMULA_LEAD and not NUMERIC_SHAPED.match(text)


def csv_cell(value):
    """One model value -> the text written to the file (never a display string)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    is_text = isinstance(value, str)
    if is_text:
        text = value
    elif hasattr(value, "isoformat"):
        text = value.isoformat()
    else:
        text = str(value)
    # Guard applies to *text* only: a negative Decimal is data, not a formula,
    # and a numeric-shaped STRING is the same data arriving from DRF's
    # DecimalField (see NUMERIC_SHAPED above).
    if is_formula_text(text):
        text = f"'{text}"
    return text


def csv_text(rows):
    """Rows -> an RFC 4180 document (QUOTE_MINIMAL, every row CRLF-terminated)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def order_export_rows(orders):
    """One row per (order, history entry) pair, primary-key order.

    An order with no history entry still gets a row (empty child columns): an
    export that silently drops a record of the collection it was asked for is
    the same bug as a kanban column that swallows a card.
    """
    for order in orders:
        parent = [
            csv_cell(order.pk),
            csv_cell(order.customer_id),
            csv_cell(order.customer.name),
            csv_cell(order.product_id),
            csv_cell(order.product.name),
            csv_cell(order.status),
            csv_cell(order.total),
            csv_cell(order.notes),
            csv_cell(order.created_at),
        ]
        entries = list(order.history.order_by("created_at", "id"))
        if not entries:
            yield parent + ["", "", "", "", ""]
            continue
        for entry in entries:
            yield parent + [
                csv_cell(entry.pk),
                csv_cell(entry.from_status),
                csv_cell(entry.to_status),
                csv_cell(entry.actor.username if entry.actor_id else None),
                csv_cell(entry.created_at),
            ]
