"""FR-R005 line-level CSV export — the server layer (docs/csv-export.md).

Deliberately free of DRF imports: `@extend_schema` captures
`REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"]` at *decoration* time, so a test
module that imports the views before the demo-rig settings override lands in
place gets a broken schema class (found the hard way — spectacular raised
``AutoSchema.get_operation() takes 3 positional arguments but 6 were
given``). Client projects copy this file next to the model whose export they
want; the view only wraps it in an HttpResponse.

The writer is the byte-identical twin of app/src/lib/csv.ts: QUOTE_MINIMAL,
CRLF, empty for null, lowercase booleans, formula guard on text only, floats
rendered with ECMAScript's `String()` form (`js_number_text`), datetimes
rendered the way DRF's own JSON body renders them (`drf_datetime_text`), UTF-8
BOM on the document. Keep the two in sync the same way ``brandToCss()``
mirrors ``branding.render_css()``.
"""
import csv
import io
import re
from datetime import datetime
from decimal import Decimal

# Django's own timezone helpers (NOT DRF — the DRF-free rule above exists
# because @extend_schema captures the schema class at decoration time). A plain
# datetime.isoformat() would re-spell UTC as "+00:00" where the API's JSON body
# writes "Z", which is divergence #2 in docs/csv-export.md §2.
from django.utils import timezone

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
    "weight",
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


def js_number_text(value):
    """float -> exactly what ECMAScript's ``String()`` writes for it.

    Layer 1 (the browser) gets a float from ``JSON.parse`` and renders it with
    ``String()``; layer 2 (this file) formats it in Python. ``str()`` and the
    ECMAScript form disagree on integral floats (``1.0`` vs ``1``), on exponent
    padding (``1e-07`` vs ``1e-7``) and on the switch points (Python leaves
    ``1e-05``/``1e+17`` exponential, a browser writes ``0.00001``/
    ``100000000000000000``). A client project with a FloatField therefore gets
    two buttons producing two files. Both round-trip to the same double, so
    Python's shortest repr is the digit string the spec would have chosen; what
    differs is only presentation, which is re-laid out here per
    ECMA-262 Number::toString (``s`` = digits, ``k`` = its length, the value is
    ``0.s * 10^n``). Not a Decimal — a Decimal's own serial form is data and
    must never be re-flowed (see the module docstring).
    """
    if value != value:
        return "NaN"
    if value == float("inf"):
        return "Infinity"
    if value == float("-inf"):
        return "-Infinity"
    if value == 0:
        return "0"  # String(-0) is "0", not "-0"

    sign = "-" if value < 0 else ""
    serial = Decimal(repr(abs(value))).as_tuple()
    digits = "".join(str(d) for d in serial.digits)
    power = serial.exponent  # value = digits * 10**power
    trailing = len(digits) - len(digits.rstrip("0"))
    digits = digits.rstrip("0")
    power += trailing  # stripping a zero multiplies the mantissa's place by 10
    k = len(digits)
    n = power + k

    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return f"{sign}{digits[:n]}.{digits[n:]}"
    if -6 < n <= 0:
        return f"{sign}0.{'0' * -n}{digits}"
    exponent = n - 1
    mantissa = digits if k == 1 else f"{digits[0]}.{digits[1:]}"
    return f"{sign}{mantissa}e{'+' if exponent >= 0 else '-'}{abs(exponent)}"


def drf_datetime_text(value):
    """datetime -> exactly the text DRF's JSON body carries for the same value.

    Layer 1 has nothing to re-format: it receives a string and writes it. So the
    server layer must emit that same string, which means mirroring DRF's
    ``DateTimeField.to_representation`` rather than calling
    ``datetime.isoformat()``: DRF reads a naive value as project-local, moves an
    aware value into the project timezone, and writes UTC with a trailing ``Z``
    where ``isoformat()`` spells the offset ``+00:00``. Getting it from
    ``django.utils.timezone`` (not a hard-coded UTC) is what keeps the two layers
    agreeing in a client project whose ``TIME_ZONE`` is not UTC — the same
    divergence, one setting over. A project that overrides
    ``REST_FRAMEWORK["DATETIME_FORMAT"]`` overrides this rule too: match it there
    or the export stops being one byte format.
    """
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    else:
        value = timezone.localtime(value)
    text = value.isoformat()
    return text[:-6] + "Z" if text.endswith("+00:00") else text


def csv_cell(value):
    """One model value -> the text written to the file (never a display string)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    is_text = isinstance(value, str)
    if is_text:
        text = value
    elif isinstance(value, float):
        # A float is rendered the way the client renders it, or the two export
        # layers of one API disagree on every FloatField column (js_number_text).
        text = js_number_text(value)
    elif isinstance(value, datetime):
        # Same law for a datetime: the client never re-formats DRF's text, so
        # this side writes DRF's text (drf_datetime_text). Checked before the
        # isoformat branch because a datetime IS a date subclass.
        text = drf_datetime_text(value)
    elif hasattr(value, "isoformat"):
        # a date (no time part) — nothing to re-spell.
        text = value.isoformat()
    else:
        text = str(value)
    # Guard applies to *text* only: a negative Decimal is data, not a formula,
    # and a numeric-shaped STRING is the same data arriving from DRF's
    # DecimalField (see NUMERIC_SHAPED above). Numbers never carry an
    # apostrophe — `-1e-9` renders unguarded here and in app/src/lib/csv.ts,
    # where the check is literally `typeof value === "string"`.
    if is_text and is_formula_text(text):
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
            # The FR-R005 witness column: a float straight off the model, which
            # is what the JSON body ALSO carries (as a number) — so this cell
            # must equal the browser's String() byte for byte (js_number_text).
            csv_cell(order.weight),
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
