<!-- @id:impl-skill-cli-install-update-venv -->
## install.py update refreshes venv by default

<!-- @ref:prd/global#prd-skill-cli-resolution rel:implements -->

### Implementation

#### 1. Update command contract

Change `install.py` so `update` accepts a boolean `--skip-venv` option.

- Default `python install.py update` continues to copy source files into the installed skill directory, but then refreshes the installed `.venv` package before returning.
- `python install.py update --skip-venv` keeps the old fast path: copy source files and leave `.venv` untouched.
- `--skip-venv` belongs only to the `update` subcommand. Keep `install --no-venv-warmup` unchanged for full installs.
- Help text and top-of-file usage must describe `update` as refreshing venv by default, with `--skip-venv` as the opt-out.

#### 2. Venv refresh helper

Add a helper in `install.py` that refreshes the package installed in the target skill venv after files are copied.

- If the target `.venv` already has a Python executable, run that interpreter with pip to install the target skill directory again.
- Use a reinstall/upgrade path so an existing importable old `ait` package is replaced by the newly copied code.
- If no venv Python exists, fall back to the existing wrapper warmup path so the wrapper creates the venv and installs the copied skill.
- Keep setup diagnostics on stderr, matching the current installer and wrapper behavior.
- Do not delete `.venv` during `update`; the refresh must reuse the existing environment unless the wrapper's own first-run path creates it because it was absent.

#### 3. Update flow

Change `do_update` to accept `skip_venv`.

- Preserve the current safety checks: the target must exist and look like an AIT skill before any overwrite.
- Preserve the current copy behavior and ignore list so `.venv`, caches, build outputs, and egg-info files are not copied from source.
- After copy, log whether `.venv` existed.
- If `skip_venv` is true, log that venv refresh was skipped and return.
- If `skip_venv` is false, call the refresh helper so updated code is active for the next wrapper invocation.

#### 4. Documentation

Update both `README.md` and `skill/ait/README.md`.

- The upgrade example should show `python install.py update` as the normal post-`git pull` command.
- The command table should state that `update` refreshes the installed venv by default.
- Add `python install.py update --skip-venv` or an option row explaining the fast path for copying files without touching venv.
- Remove wording that says update always preserves `.venv` without reinstalling the package.

#### 5. Tests

Add focused tests for the installer behavior.

- Cover that default update copies files and invokes the venv refresh helper.
- Cover that `update --skip-venv` copies files but does not invoke venv refresh.
- Cover parser/help wiring enough to prove `--skip-venv` is accepted only for `update`.
- Mock subprocess calls and temporary directories; do not create real external venvs or require network access.

### Validation

- Run the new installer tests.
- Run the full pytest suite.
- Manually inspect `python install.py update --help` to verify the new option and wording.

### Boundaries

- Do not change wrapper lazy-install semantics in `skill/ait/bin/ait` or `skill/ait/bin/ait.cmd`.
- Do not change `install --no-venv-warmup`.
- Do not introduce PATH installation or global `ait` commands.
- Do not make `--skip-venv` repair or validate a broken venv.
