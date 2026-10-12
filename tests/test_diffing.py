from pr_reviewer.diffing import build_file_diff


def test_new_file_marks_every_line_changed():
    diff = build_file_diff("a.py", "", "x = 1\ny = 2\n")
    assert diff.changed_lines == frozenset({1, 2})
    assert "+     1 | x = 1" in diff.annotated_diff
    assert "+     2 | y = 2" in diff.annotated_diff


def test_modified_line_reports_after_line_number_and_removed_line():
    before = "a\nb\nc\nd\n"
    after = "a\nb\nC\nd\ne\n"
    diff = build_file_diff("f.py", before, after)
    assert diff.changed_lines == frozenset({3, 5})
    lines = diff.annotated_diff.splitlines()
    assert "-       | c" in lines
    assert "+     3 | C" in lines
    assert "      2 | b" in lines  # context keeps its AFTER number
    assert lines[0].startswith("@@ ")


def test_deleted_lines_only_have_no_changed_after_lines():
    diff = build_file_diff("f.py", "a\nb\n", "a\n")
    assert diff.changed_lines == frozenset()
    assert "-       | b" in diff.annotated_diff


def test_identical_content_produces_empty_diff():
    diff = build_file_diff("f.py", "same\n", "same\n")
    assert diff.annotated_diff == ""
    assert diff.changed_lines == frozenset()


def test_trailing_newline_only_change_has_no_changed_lines():
    diff = build_file_diff("f.py", "x = 1", "x = 1\n")
    assert diff.changed_lines == frozenset()
    assert diff.annotated_diff == ""


def test_far_apart_changes_produce_separate_hunks():
    before = "\n".join(str(i) for i in range(1, 41)) + "\n"
    after = before.replace("5\n", "five\n", 1).replace("35\n", "thirty-five\n", 1)
    diff = build_file_diff("f.py", before, after)
    assert diff.annotated_diff.count("@@ ") == 2
    assert diff.changed_lines == frozenset({5, 35})
