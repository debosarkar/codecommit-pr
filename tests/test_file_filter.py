from pr_reviewer.file_filter import (
    ChangedFile,
    SkippedFile,
    content_skip_reason,
    language_for,
    select_files,
)


def cf(path, change="M", before="b1", after="a1"):
    return ChangedFile(path, change, before, after)


def test_language_for_supported_extensions():
    assert language_for("a/b.py") == "python"
    assert language_for("x.tsx") == "typescript"
    assert language_for("x.mjs") == "javascript"
    assert language_for("Foo.java") == "java"
    assert language_for("build.gradle.kts") == "kotlin"
    assert language_for("README.md") is None


def test_select_files_skips_with_reasons_and_sorts():
    files = [
        cf("z.py"),
        cf("gone.py", change="D", after=None),
        cf("docs/readme.md"),
        cf("web/dist/app.js"),
        cf("web/lib/app.min.js"),
        cf("types/index.d.ts"),
        cf("a.ts", change="A", before=None),
    ]
    selected, skipped = select_files(files, max_files=30)
    assert [f.path for f in selected] == ["a.ts", "z.py"]
    assert SkippedFile("gone.py", "deleted") in skipped
    assert SkippedFile("docs/readme.md", "unsupported file type") in skipped
    assert SkippedFile("web/dist/app.js", "generated or vendored") in skipped
    assert SkippedFile("web/lib/app.min.js", "generated or vendored") in skipped
    assert SkippedFile("types/index.d.ts", "generated or vendored") in skipped


def test_pure_rename_is_skipped():
    selected, skipped = select_files([cf("new_name.py", before="same", after="same")], 30)
    assert selected == []
    assert skipped == [SkippedFile("new_name.py", "renamed or mode change without content changes")]


def test_select_files_applies_cap():
    files = [cf(f"f{i:02}.py") for i in range(5)]
    selected, skipped = select_files(files, max_files=3)
    assert [f.path for f in selected] == ["f00.py", "f01.py", "f02.py"]
    assert skipped == [
        SkippedFile("f03.py", "not reviewed: over the 3-file limit"),
        SkippedFile("f04.py", "not reviewed: over the 3-file limit"),
    ]


def test_content_skip_reason_size():
    assert content_skip_reason(b"x" * 101, max_bytes=100) == "larger than 100 bytes"
    assert content_skip_reason(b"x" * 100, max_bytes=100) is None


def test_content_skip_reason_binary_and_non_utf8():
    assert content_skip_reason(b"abc\x00def", max_bytes=1000) == "binary file"
    assert content_skip_reason(b"\xff\xfe\xfa", max_bytes=1000) == "not UTF-8 text"
    assert content_skip_reason("ünïcode".encode(), max_bytes=1000) is None
