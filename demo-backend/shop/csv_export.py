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
    # Guard applies to *text* only: a negative Decimal is data, not a formula.
    if is_text and text and text[0] in FORMULA_LEAD:
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
