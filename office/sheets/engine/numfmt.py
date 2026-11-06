"""Excel-style number formats: "0.00", "#,##0", "0%", "\\"€\\"#,##0.00", "0.00E+00".

Only the common shapes are understood; anything else falls back to General.
Shared by the TEXT() function and the grid's cell formatting, and the same
strings are written to .xlsx so Excel shows the same thing.
"""
import math
import re

GENERAL = "General"

# The choices the Sheets toolbar offers, as (label, Excel format code).
PRESETS = [
    ("General", GENERAL),
    ("Number  1234", "0"),
    ("Decimal  1234.50", "0.00"),
    ("Thousands  1,234", "#,##0"),
    ("Thousands  1,234.50", "#,##0.00"),
    ("Percent  12%", "0%"),
    ("Percent  12.50%", "0.00%"),
    ("Euro  €1,234.50", '"€"#,##0.00'),
    ("Pound  £1,234.50", '"£"#,##0.00'),
    ("Dollar  $1,234.50", '"$"#,##0.00'),
    ("Peso  ₱1,234.50", '"₱"#,##0.00'),
    ("Scientific  1.23E+03", "0.00E+00"),
]

_QUOTED = re.compile(r'"([^"]*)"')


def _split_literals(fmt):
    """'"€"#,##0.00" net"' -> ('€', '#,##0.00', ' net'). Also accepts bare $ £ € ₱."""
    prefix = suffix = ""
    core = fmt
    m = re.match(r'^(?:"([^"]*)"|([$£€₱¥]))', core)
    if m:
        prefix = m.group(1) if m.group(1) is not None else m.group(2)
        core = core[m.end():]
    m = re.search(r'(?:"([^"]*)"|([$£€₱¥]))$', core)
    if m:
        suffix = m.group(1) if m.group(1) is not None else m.group(2)
        core = core[:m.start()]
    return prefix, core.replace("\\", ""), suffix


def _round_half_up(x, digits):
    factor = 10 ** digits
    return math.copysign(math.floor(abs(x) * factor + 0.5) / factor, x)


def format_number(value: float, fmt: str) -> str | None:
    """Format a number, or return None when `fmt` is General or not understood."""
    if not fmt or fmt == GENERAL:
        return None
    fmt = fmt.split(";")[0]  # positive section only
    prefix, core, suffix = _split_literals(fmt)
    if not core or not set(core) <= set("#0,.%E+-"):
        return None
    if "E" in core:
        mant = core.split("E")[0]
        decimals = len(mant.split(".")[1]) if "." in mant else 0
        text = f"{value:.{decimals}E}"
        base, exp = text.split("E")
        sign = "-" if exp.startswith("-") else "+"
        return f"{prefix}{base}E{sign}{abs(int(exp)):02d}{suffix}"
    if core.endswith("%"):
        value *= 100
        core = core.rstrip("%")
        suffix = "%" + suffix
    decimals = len(core.split(".")[1]) if "." in core else 0
    thousands = "," in core
    rounded = _round_half_up(value, decimals)
    body = f"{abs(rounded):,.{decimals}f}" if thousands else f"{abs(rounded):.{decimals}f}"
    sign = "-" if rounded < 0 else ""
    return f"{sign}{prefix}{body}{suffix}"
