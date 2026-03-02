"""Tests for diff visualization utilities."""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def unified_diff_lines(a: str, b: str) -> list[str]:
    """Return a list of unified-diff lines between two strings."""
    import difflib

    return list(
        difflib.unified_diff(
            a.splitlines(keepends=True),
            b.splitlines(keepends=True),
            fromfile="a",
            tofile="b",
        )
    )


def count_added(diff_lines: list[str]) -> int:
    return sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))


def count_removed(diff_lines: list[str]) -> int:
    return sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))


def apply_diff(original: str, diff_lines: list[str]) -> str:
    """Naively reconstruct the 'b' side of a diff from 'original'."""
    # For testing, just re-run difflib patch via patch utility isn't available;
    # instead verify round-trip via the actual strings.
    return original  # placeholder -- real tests compare strings directly


# ---------------------------------------------------------------------------
# Basic diff tests
# ---------------------------------------------------------------------------


class TestUnifiedDiff:
    def test_identical_strings_produce_no_diff(self):
        assert unified_diff_lines("hello\n", "hello\n") == []

    def test_added_line(self):
        diff = unified_diff_lines("a\n", "a\nb\n")
        assert count_added(diff) == 1
        assert count_removed(diff) == 0

    def test_removed_line(self):
        diff = unified_diff_lines("a\nb\n", "a\n")
        assert count_removed(diff) == 1
        assert count_added(diff) == 0

    def test_changed_line_counts_as_remove_and_add(self):
        diff = unified_diff_lines("old\n", "new\n")
        assert count_added(diff) == 1
        assert count_removed(diff) == 1

    def test_empty_to_nonempty(self):
        diff = unified_diff_lines("", "line1\nline2\n")
        assert count_added(diff) == 2

    def test_nonempty_to_empty(self):
        diff = unified_diff_lines("line1\nline2\n", "")
        assert count_removed(diff) == 2

    def test_multiline_change(self):
        a = "line1\nline2\nline3\n"
        b = "line1\nchanged\nline3\n"
        diff = unified_diff_lines(a, b)
        assert count_added(diff) == 1
        assert count_removed(diff) == 1


# ---------------------------------------------------------------------------
# Diff counting
# ---------------------------------------------------------------------------


class TestDiffCounting:
    def test_count_added_zero(self):
        diff = unified_diff_lines("a\n", "a\n")
        assert count_added(diff) == 0

    def test_count_removed_zero(self):
        diff = unified_diff_lines("a\n", "a\n")
        assert count_removed(diff) == 0

    def test_count_multiple_additions(self):
        diff = unified_diff_lines("x\n", "x\na\nb\nc\n")
        assert count_added(diff) == 3

    def test_count_multiple_removals(self):
        diff = unified_diff_lines("a\nb\nc\n", "a\n")
        assert count_removed(diff) == 2

    def test_header_lines_not_counted(self):
        diff = unified_diff_lines("a\n", "b\n")
        # +++ and --- lines should NOT be counted
        plus_lines = [l for l in diff if l.startswith("+")]
        minus_lines = [l for l in diff if l.startswith("-")]
        assert not any(l.startswith("+++") for l in plus_lines if count_added([l]) > 0)


# ---------------------------------------------------------------------------
# Whitespace and edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_whitespace_only_change(self):
        diff = unified_diff_lines("hello\n", "hello \n")
        assert len(diff) > 0

    def test_case_change(self):
        diff = unified_diff_lines("Hello\n", "hello\n")
        assert count_added(diff) == 1
        assert count_removed(diff) == 1

    def test_empty_strings(self):
        assert unified_diff_lines("", "") == []

    def test_newline_only(self):
        diff = unified_diff_lines("\n", "\n")
        assert diff == []

    def test_large_identical_block(self):
        block = "line\n" * 100
        assert unified_diff_lines(block, block) == []

    def test_unicode_content(self):
        diff = unified_diff_lines("caf\u00e9\n", "caf\u00e8\n")
        assert count_added(diff) == 1
        assert count_removed(diff) == 1


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


class TestDiffRendering:
    def test_diff_has_header(self):
        diff = unified_diff_lines("a\n", "b\n")
        headers = [l for l in diff if l.startswith("---") or l.startswith("+++ ")]
        assert len(headers) == 2

    def test_diff_hunk_marker(self):
        diff = unified_diff_lines("a\n", "b\n")
        hunks = [l for l in diff if l.startswith("@@")]
        assert len(hunks) >= 1

    def test_context_lines_present(self):
        a = "\n".join([f"line{i}" for i in range(10)]) + "\n"
        b = a.replace("line5", "changed")
        diff = unified_diff_lines(a, b)
        context = [l for l in diff if l.startswith(" ")]
        assert len(context) > 0

    def test_render_summary(self):
        a = "old content\n"
        b = "new content\n"
        diff = unified_diff_lines(a, b)
        summary = f"+{count_added(diff)} -{count_removed(diff)}"
        assert summary == "+1 -1"

    def test_diff_is_list_of_strings(self):
        diff = unified_diff_lines("foo\n", "bar\n")
        assert isinstance(diff, list)
        assert all(isinstance(l, str) for l in diff)
