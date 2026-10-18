# NOTICE

## Upstream project

- **Name:** pathvalidate
- **Repository:** https://github.com/thombashi/pathvalidate
- **Author:** Tsuyoshi Hombashi (tsuyoshi.hombashi@gmail.com)
- **License:** MIT License — Copyright (c) 2016-2025 Tsuyoshi Hombashi
- **Baseline commit:** `1ca0a50fce51d5b5bd633457a72abf74dbe3112d` (master, 2026-05-10)
- **Version:** 3.3.1

The original `LICENSE` file is included unmodified at the repository root. All
copyright notices and the `__author__` / `__copyright__` / `__license__` fields in
`pathvalidate/__version__.py` are preserved as-is.

## Modifications

This distribution contains **modifications** to the original work, made on
2026-10-18 for a security / robustness audit. Modified files:

```
pathvalidate/_common.py
pathvalidate/_filename.py
pathvalidate/_filepath.py
pathvalidate/_symbol.py
pathvalidate/_ltsv.py
test/test_common.py
test/test_filename.py
test/test_filepath.py
test/test_symbol.py
test/test_ltsv.py
```

No files were deleted. No public API signatures, default parameter values, or
return types were changed. No new runtime dependencies were introduced.

All other 86 files are **byte-for-byte identical** to the upstream blobs at the
baseline commit (verified by SHA-1 comparison against `git cat-file -p` output).

The complete unified diff is provided as `fixes.patch`. It reproduces the
modified files byte-for-byte when applied to a pristine LF checkout of the
baseline commit.

## Added files

```
AUDIT_REPORT.md     audit findings, fix rationale, test evidence, residual risks
fixes.patch         unified diff of all source and test changes
audit/              probe scripts, cross-version check, mutation test, benchmark
```

The `audit/` scripts are original work released under the same MIT terms.

## Scope of the audit

This is an independent review. It is **not** an official upstream release and has
not been reviewed by the upstream maintainer. See `AUDIT_REPORT.md` §8 for
unresolved risks, including the important caveat that `pathvalidate` is a
string-sanitization library and **not** a path-traversal security boundary.
