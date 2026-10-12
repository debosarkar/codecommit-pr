# Code Review Standards

These rules are read by the automated PR reviewer and by humans. Formatting is
owned by the team's code formatter in `nda-skills`: **no rule here covers
whitespace, import order, quote style or line length.**

Each rule has a stable ID. Cite the ID in review comments. The severity shown
is the default; raise it when the impact is clearly worse.

## General (all languages)

### GEN-001 · No secrets in code — critical
Credentials, tokens, private keys and connection strings with passwords must
come from configuration or a secrets manager, never literals.
- Bad: `API_KEY = "sk_live_51H..."`
- Good: `API_KEY = os.environ["PAYMENTS_API_KEY"]`

### GEN-002 · Never build queries or commands from untrusted input — critical
SQL, shell commands, LDAP/XPath queries and HTML must use parameterisation or
escaping APIs, never string concatenation/interpolation of input.
- Bad: `cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")`
- Good: `cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))`

### GEN-003 · Do not swallow errors — high
Catch the narrowest exception type you can handle. A catch block must handle,
translate, or re-raise; an empty or log-and-continue catch of a broad type
is not allowed.
- Bad: `except Exception: pass`
- Good: `except KeyError: raise OrderNotFound(order_id) from None`

### GEN-004 · Release resources deterministically — high
Files, sockets, DB connections and cursors are closed via the language's
scoped construct (`with`, try-with-resources, `use`, `finally`).

### GEN-005 · Validate external input at the boundary — high
Request bodies, query params, event payloads and file contents are validated
(type, range, length) before use. Fail with a clear error.

### GEN-006 · Log usefully, never log secrets or personal data — medium
Log with context (IDs, operation), at the right level. Never log passwords,
tokens, full card numbers, or personal data.

### GEN-007 · New behaviour comes with tests — medium
A change that adds or alters behaviour includes or updates tests that would
fail without the change.

### GEN-008 · No dead or commented-out code — low
Remove unused functions, unreachable branches and commented-out code.

## Python

### PY-001 · No mutable default arguments — high
- Bad: `def add(item, items=[]):`
- Good: `def add(item, items=None): items = [] if items is None else items`

### PY-002 · No bare `except:` — high
Bare `except:` also catches `KeyboardInterrupt` and `SystemExit`. See GEN-003.

### PY-003 · Public functions have type hints — medium
Parameters and return types of public functions and methods are annotated.

### PY-004 · Time-zone aware datetimes — medium
Use `datetime.now(timezone.utc)`; never naive `datetime.now()`/`utcnow()` for
stored or compared timestamps.

### PY-005 · `requests`/`httpx` calls set a timeout — high
- Bad: `requests.get(url)`
- Good: `requests.get(url, timeout=10)`

## TypeScript / JavaScript

### TS-001 · No floating promises — high
Every promise is awaited, returned, or explicitly handled with `.catch`.
- Bad: `saveUser(user);` (async)
- Good: `await saveUser(user);`

### TS-002 · No `any` in exported signatures — medium
Use precise types or `unknown` plus narrowing.

### TS-003 · Strict equality — medium
Use `===`/`!==`. `== null` is allowed only to check for both null and undefined.

### TS-004 · No unsanitised HTML injection — critical
No `innerHTML`, `dangerouslySetInnerHTML` or `eval` with data that is not a
trusted constant.

### TS-005 · Handle null/undefined explicitly — high
Use optional chaining / guards instead of non-null assertions (`!`) on values
that can actually be absent.

## Java / Kotlin

### JVM-001 · Try-with-resources / `use` for closeables — high
- Bad: `Connection c = ds.getConnection(); ... c.close();`
- Good: `try (Connection c = ds.getConnection()) { ... }`

### JVM-002 · Never catch `Exception`/`Throwable` to ignore it — high
See GEN-003. Kotlin: never `catch (e: Exception) {}`.

### JVM-003 · Null safety — high
Java: return `Optional` instead of `null` from lookups; Kotlin: avoid `!!` on
values that can be null.

### JVM-004 · Prepared statements only — critical
JDBC queries use `PreparedStatement` with bind parameters. See GEN-002.

### JVM-005 · Immutable data by default — low
Prefer `final` fields / `val`, records / data classes, and unmodifiable
collections for data that should not change.
