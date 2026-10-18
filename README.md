# pathvalidate-sanitizer-audit

Security and robustness audit of [`thombashi/pathvalidate`](https://github.com/thombashi/pathvalidate)
3.3.1 — a Python library that sanitises and validates filenames and file paths.

**Three defects found, reproduced, fixed, and locked down with 40 regression tests.**
The upstream test suite still passes in full (4184 → 4224, no existing test modified or deleted).

📄 **[Read the report](https://linluozi.github.io/pathvalidate-sanitizer-audit/)** — charts, before/after tables, and the risk list.
Also available as Markdown: [docs/AUDIT_REPORT.md](docs/AUDIT_REPORT.md).

---

## Why this library

`pathvalidate` sits on the "untrusted filename → disk" path: upload renaming, download
write-out, archive extraction. It has ~300 stars, is MIT licensed, has zero runtime
dependencies, and ships 4184 tests — enough surface to verify a claim against.

| Audit axis | Coverage |
|---|---|
| Input validation | ✅ main finding — replacement text used as a regex template |
| Path handling | ✅ main finding — drive-relative path promoted to absolute |
| Permission control | ⬜ N/A — pure string library, never touches mode bits |
| Resource release | ⬜ N/A — no file handles, sockets, or subprocesses |
| Timeout / retry | ⬜ N/A — no I/O |
| Dependency conflicts | ✅ checked: `python_requires>=3.9`, zero runtime deps |
| OS differences | ✅ verified on Windows path semantics + 3 CPython versions |

The N/A rows are architectural, not skipped work.

---

## The three defects

### A. `replacement_text` was used as a regex replacement template

`re.sub(pattern, repl, text)` treats `repl` as a **template** that expands backslash
escapes and group references. `replacement_text` is a plain caller-supplied string.
Passing it straight through affected 6 call sites plus 2 helpers in `_common.py`.

```python
>>> sanitize_filename("a?b", replacement_text="\\")
re.PatternError: bad escape (end of pattern) at position 0

>>> sanitize_filename("a?b", replacement_text="\\b")
'a\x08b'          # a backspace, silently

>>> sanitize_filename("a?b", replacement_text="\\g<0>")
'a?b'             # sanitisation became a no-op; '?' survives
```

Why it matters beyond ugly errors:

- `re.error` is **not** a `ValueError` (its MRO is `Exception → BaseException`), but the
  docstring promises `Raises: ValueError` and `ValidationError` really is one. Callers
  writing `except ValueError` miss it entirely.
- The exception class name changes across versions — `re.error` on 3.12,
  `re.PatternError` on 3.13/3.14 — so name-based dispatch breaks silently on upgrade.
- `\g<0>` re-emits the matched invalid character, so the sanitiser returns an invalid
  name and `is_valid_filepath()` says `False`.

**Fix** — a new `escape_replacement_text()` doubles backslashes before handing the value
to `re.sub`. Empty string short-circuits, so the default path adds one truthiness test.

### B. Drive-relative path silently promoted to absolute

`ntpath.splitdrive("C:x.txt")` returns `("C:", "x.txt")`. The old code joined the drive
back with a separator, producing `C:\x.txt` — **absolute**.

That matters because `os.path.join` discards its first argument when the second is
absolute:

```
BASE = r"C:\srv\uploads"
os.path.join(BASE, sanitize_filepath("D:payload.exe", platform="windows"))
# before: 'D:\payload.exe'   <- BASE dropped, different drive
# after:  'D:payload.exe'    <- still relative
```

It also created a self-contradiction: the validator accepts `C:x.txt`, but the sanitiser
returned something the validator rejects (`PV1201`), and strict mode raised on its own
output.

**Fix** — detect the drive-relative shape (drive non-empty, remainder non-empty, not
starting with a separator) and prefix the drive directly instead of inserting a
separator. Absolute paths are untouched, pinned by regression tests.

### C. Consecutive-collapse broke on multi-character replacements

```python
re.sub(f"{re.escape('ab')}+", ...)     # 'ab+'  -- + binds to 'b' only
re.sub(f"(?:{re.escape('ab')})+", ...) # '(?:ab)+' -- + binds to the whole text
```

`replace_symbol("a---b", "ab", is_replace_consecutive_chars=True)` returned `'aababab'`
instead of `'aab'`. Independent of A/B, but same class of regex-construction error, in
the same function that A already had to rewrite.

---

## Four things that are **not** vulnerabilities

Judging from code patterns or scanner output alone would have produced four false
positives here. All were checked empirically:

1. **`_filepath.py` builds a `ValidationError` and never raises it.** Looks like dead
   code. It is merely redundant — the actual raise happens on the `err_object` built
   afterwards. Behaviour is correct.
2. **Sanitisers do not guarantee valid output.** Upstream issues
   [#49](https://github.com/thombashi/pathvalidate/issues/49) and
   [#69](https://github.com/thombashi/pathvalidate/issues/69) are **closed by the
   maintainer** as a deliberate trade-off, with `validate_after_sanitize=True` as the
   opt-in compensation (verified: it does raise). Not a bug — documented limitation.
3. **`..` components pass through.** `sanitize_filepath("../../etc/passwd")` returns the
   input. Intentional: this is a sanitiser, not a security boundary. "Hardening" it
   would break legitimate relative paths.
4. **The replacement-template semantics themselves.** `grep` for `\g<0>` across the
   repo: zero hits. No internal code relies on template behaviour, so switching to
   literal insertion breaks no contract.

---

## Verification

| Check | Result |
|---|---|
| Upstream suite, baseline | 4184 passed, 14 skipped |
| Upstream suite, patched | **4224 passed**, 14 skipped |
| Delta | +40 = the new tests exactly; **no existing test modified or deleted** |
| Reverse feed | 24 new tests fail on the original code (behavioural asserts, not `ImportError`) |
| Mutation test | **9/9 killed** — M9 survived round one and exposed a real blind spot |
| Differential | 3000 random cases vs a `lambda m: repl` oracle: zero mismatches |
| Cross-version | CPython 3.12.10 / 3.13.14 / 3.14.5, each proving which file it imported |
| Static | `ruff check` clean, `ruff format` clean, `mypy` clean, **0 new lint issues** |
| Patch | applies to a pristine LF checkout → 10 files byte-identical (sha1) |
| Integrity | 86 of 96 upstream files byte-identical to their blobs |

Notes on methodology, because two of these nearly produced wrong answers:

- The cross-version script forces the sibling package onto `sys.path[0]` and **prints the
  resolved path**. This is not paranoia: this machine's Python 3.14 has an unpatched
  3.3.1 in site-packages, and an early run reported "all passed" while measuring that
  copy.
- A/A noise floor on this machine measured **0.881 – 1.314**, wider than any plausible
  effect, so no timing point value is reported. The deterministic cost of the added
  helper is 46.5 ns (empty) vs ~18–21 µs per `sanitize_filename` call — about 0.25%.

---

## Unresolved risks

Listed in full in the [report](https://linluozi.github.io/pathvalidate-sanitizer-audit/).
The one that matters most:

> **The sanitiser is not a security boundary.** After the fix,
> `sanitize_filepath("../../etc/passwd")` still returns the input. Any code that joins
> an untrusted name onto a directory must do its own containment check
> (`realpath` + `commonpath`). This audit removed one class of bypass — a relative name
> being rewritten as absolute — but cannot turn a string sanitiser into a traversal
> guard.

Also open: default mode does not guarantee validity (#49/#69); replacement text can
still be used to defeat sanitisation if it is attacker-controlled; non-UTF-8
`fs_encoding` raises a bare `UnicodeEncodeError`; only Windows hosts were tested.

---

## Repository layout

```
pathvalidate/         source — 5 files changed, the rest byte-identical to upstream
test/                 upstream suite + 40 new regression tests
fixes.patch           complete unified diff (18 hunks)
audit/                probe scripts, cross-version check, mutation test, A/A benchmark
docs/index.html       the report page (self-contained, images inlined)
NOTICE.md             modification notice, upstream copyright retained
LICENSE               upstream MIT license, unmodified
```

Reproduce:

```bash
python -m pytest test -q                  # 4224 passed, 14 skipped
python audit/cross_version_check.py       # prints the file it imported, then asserts
python audit/mutation_test.py             # 9/9 killed
```

## License

MIT, Copyright (c) 2016-2025 Tsuyoshi Hombashi — retained verbatim. See
[NOTICE.md](NOTICE.md) for the list of modifications. The `audit/` scripts are original
work under the same terms.

This is an independent review, not an upstream release, and has not been reviewed by
the upstream maintainer.
