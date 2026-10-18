"""
.. codeauthor:: Tsuyoshi Hombashi <tsuyoshi.hombashi@gmail.com>
"""

import itertools

import pytest
from tcolorpy import tcolor

from pathvalidate import (
    ascii_symbols,
    replace_ansi_escape,
    replace_unprintable_char,
    unprintable_ascii_chars,
)

from ._common import alphanum_chars


class Test_replace_unprintable_char:
    TARGET_CHARS = unprintable_ascii_chars
    NOT_TARGET_CHARS = alphanum_chars + ascii_symbols
    REPLACE_TEXT_LIST = ["", "_"]

    @pytest.mark.parametrize(
        ["value", "replace_text", "expected"],
        [
            ["A" + c + "B", rep, "A" + rep + "B"]
            for c, rep in itertools.product(TARGET_CHARS, REPLACE_TEXT_LIST)
        ]
        + [
            ["A" + c + "B", rep, "A" + c + "B"]
            for c, rep in itertools.product(NOT_TARGET_CHARS, REPLACE_TEXT_LIST)
        ]
        + [
            ["", "", ""],
        ],
    )
    def test_normal(self, value, replace_text, expected):
        assert replace_unprintable_char(value, replace_text) == expected

    @pytest.mark.parametrize(
        ["value", "expected"],
        [
            [None, TypeError],
            [1, TypeError],
            [True, TypeError],
        ],
    )
    def test_abnormal(self, value, expected):
        with pytest.raises(expected):
            replace_unprintable_char(value)


class Test_replace_ansi_escape:
    def test_normal(self):
        value = "test"
        ansi_value = tcolor(value, color="ffffff", bg_color="111111", styles=["bold"])
        assert replace_ansi_escape(ansi_value) == value


class Test_escape_replacement_text:
    """Replacement text must be inserted literally.

    ``re.sub`` interprets backslash escapes and group references in its replacement
    argument. Passing caller-supplied text straight through either raised
    ``re.error`` (a bare ``Exception``, outside the documented ``ValueError``
    contract) or silently emitted a different character (``"\\b"`` became a
    backspace). See :py:func:`pathvalidate._common.escape_replacement_text`.
    """

    @pytest.mark.parametrize(
        ["replacement_text", "expected"],
        [
            ["", ""],
            ["_", "_"],
            ["-", "-"],
            ["\\", "\\\\"],
            ["\\b", "\\\\b"],
            ["\\g<0>", "\\\\g<0>"],
            ["x\\1", "x\\\\1"],
            ["a\\\\b", "a\\\\\\\\b"],
        ],
    )
    def test_normal(self, replacement_text, expected):
        from pathvalidate._common import escape_replacement_text

        assert escape_replacement_text(replacement_text) == expected

    @pytest.mark.parametrize(
        ["value", "replacement_text", "expected"],
        [
            ["a?b", "\\", "a\\b"],
            ["a?b", "\\b", "a\\bb"],
            ["a?b", "\\g<0>", "a\\g<0>b"],
            ["a?b", "\\\\", "a\\\\b"],
        ],
    )
    def test_normal_literal_insertion(self, value, replacement_text, expected):
        from pathvalidate import sanitize_filename

        assert (
            sanitize_filename(value, replacement_text=replacement_text, platform="windows")
            == expected
        )

    @pytest.mark.parametrize("replacement_text", ["\\", "x\\1", "\\x00"])
    def test_no_raw_regex_error(self, replacement_text):
        """A caller-supplied replacement must never raise ``re.error``."""
        from pathvalidate import sanitize_filename, sanitize_filepath

        sanitize_filename("a?b", replacement_text=replacement_text, platform="windows")
        sanitize_filepath("a/b?c", replacement_text=replacement_text, platform="windows")
