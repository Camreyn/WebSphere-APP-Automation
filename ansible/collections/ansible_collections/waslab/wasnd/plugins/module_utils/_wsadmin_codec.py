# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import ast
import json
import math


text_type = type(u"")
binary_type = type(b"")
integer_types = (int, type(1 << 100))


def _unicode_literal(value):
    escaped = value.encode("unicode_escape")
    if not isinstance(escaped, text_type):
        escaped = escaped.decode("ascii")
    return "u'" + escaped.replace("'", "\\'") + "'"


def jython21_literal(value):
    """Encode JSON-shaped data as a literal understood by Jython 2.1."""
    if value is None:
        return "None"
    if isinstance(value, bool):
        # True and False were not builtins in the Python language level used by
        # the WAS 8.5.5 Jython 2.1 runtime. The bridge treats 1/0 as flags.
        return "1" if value else "0"
    if isinstance(value, integer_types):
        return repr(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("Non-finite floats cannot be sent to wsadmin")
        return repr(value)
    if isinstance(value, binary_type) and not isinstance(value, text_type):
        value = value.decode("utf-8")
    if isinstance(value, text_type):
        # Escaping non-ASCII code points means the payload does not depend
        # on the old interpreter's source-file encoding.
        return _unicode_literal(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(jython21_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        items = sorted(value.items(), key=lambda item: repr(item[0]))
        return "{" + ", ".join(
            "%s: %s" % (jython21_literal(key), jython21_literal(item))
            for key, item in items
        ) + "}"
    raise TypeError("Unsupported wsadmin payload value: %s" % type(value).__name__)


def parse_wsadmin_result(value):
    """Parse either the legacy literal protocol or an older JSON bridge result."""
    try:
        result = json.loads(value)
    except (TypeError, ValueError):
        try:
            result = ast.literal_eval(value)
        except (SyntaxError, ValueError) as exc:
            raise ValueError("wsadmin returned an invalid result payload: %s" % exc)
    if not isinstance(result, dict):
        raise ValueError("wsadmin result payload must be a mapping")
    if "changed" in result:
        result["changed"] = bool(result["changed"])
    return result
