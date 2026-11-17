# Portfolio Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repo presentable to data/AI hiring managers: clean root, licence, green CI, a reproducible diagnosis-accuracy number, and a real LLM provider interface.

**Architecture:** Four user-facing steps, executed in order, with a stop and a diff review after each: (1) repo hygiene, (2) strict typing, licence and CI, (3) an offline-testable evaluation script that scores `forensics.engine.diagnose` against docgen's injected corruptions, (4) `LLMProvider` protocol plus a provider factory, so call sites no longer hard-code Gemini.

**Tech Stack:** Python 3.12, Pydantic v2, OpenTelemetry SDK, FastAPI, pytest, ruff, mypy; React/Vite/vitest; GitHub Actions.

**Spec:** the user brief of 2026-11-17 (in conversation) plus the decisions below. No separate spec file.

## Global Constraints

- Stop after each user step (Task 1 | Tasks 2–3 | Task 4 | Task 5), show the diff, and wait for approval.
- One Conventional Commit per task. End each commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Tests stay offline: mock every LLM call (`tests.conftest.MockLLM`). CI has no `GEMINI_API_KEY`.
- `ruff check .`, `mypy .` (strict, set in config) and `pytest` must pass from `backend/` at the end of every task, from Task 2 onwards.
- No runtime dependencies added. Dev extras gain `ruff` and `mypy` only; the brief asks for both tools.
- Behaviour must not change: the existing 43 backend tests keep passing, with edits limited to type annotations.
- **Corruption → expected diagnosis mapping (decided by Sasha, verbatim):**
  - `strip_dates` → step `extract`, category `extraction_hallucination`
  - `currency_mismatch` → step `extract`, category `extraction_hallucination`
  - `ambiguous_category` → step `classify`, category `misclassification`
- Evaluation batch: `n=50`, `seed=42`. "Time from flag to diagnosis" is the wall-clock duration of the `diagnose(trace_doc, llm)` call.

## Review Focus

1. **The typing pass silently changes runtime behaviour.** For example, guarding `resp.usage_metadata is None` must give `0` tokens, not raise. The test goes in Task 2.
2. **A pipeline step errors during the evaluation run** (for example, a 429 after all retries). The doc must still get a diagnosis: the errored step scores 1 and becomes the root cause. The test goes in Task 4.
3. **The batch contains no corrupted docs, or none of one type.** The summary table must still render, with `–` where there is nothing to measure, and not crash on an empty median. The test goes in Task 4.
4. **`docs/design/` stays git-ignored after the move.** The old `.gitignore` line `docs/superpowers/` must go, and new design docs must be trackable. The check goes in Task 1.
5. **Frontend `npm ci` on Linux CI.** The local `node_modules` is missing the darwin rolldown binding, so `vitest` cannot start locally. Verify the job in a clean scratch copy (Task 3); do not touch the user's `node_modules`.

---

### Task 1: Repo hygiene (user step 1)

**Files:**
- Delete: `input.md`
- Move: `docs/superpowers/` → `docs/design/` (contains `plans/`, `specs/`, this plan)
- Modify: `.gitignore` (drop the line `docs/superpowers/`)

**Interfaces:** none.

- [ ] **Step 1:** `git rm input.md`
- [ ] **Step 2:** `git mv docs/superpowers docs/design`. `docs/design` must not exist beforehand, or git nests the folder.
- [ ] **Step 3:** Remove `docs/superpowers/` from `.gitignore`, then `git add -f docs/design/plans/2026-11-17-portfolio-readiness.md .gitignore`.
- [ ] **Step 4: Verify**
  Run: `git status --short && git check-ignore docs/design/plans/x.md; echo $? && grep -rn "docs/superpowers\|input\.md" README.md backend frontend/src .gitignore`
  Expected: renames to `docs/design/...`, `D input.md`, exit code `1` from check-ignore, no grep hits.
- [ ] **Step 5: Commit** `chore: remove project brief, move design docs to docs/design`

**STOP: show `git show --stat HEAD` and the diff.**

---

### Task 2: Strict typing and lint config (user step 2a)

**Files:**
- Modify: `backend/pyproject.toml`: dev extras and tool config
- Modify: every `backend/**/*.py` flagged by `mypy --strict` and the pinned ruff rules (24 files, mostly annotations)
- Test: `backend/tests/test_llm.py` (one new test)

**Interfaces:**
- Produces, in `pipeline/llm.py`: `LLMClient.generate_structured[T: BaseModel](self, prompt: str, schema: type[T]) -> tuple[T, LLMCall]` (PEP 695 generic). `GeminiClient.generate_structured` has the same signature. This removes the three `steps.py` return-value errors without casts.
- Produces, in `pipeline/docgen.py`: `class BatchDoc(TypedDict)` with `doc_id: str`, `doc_type: str`, `corruption: str | None`, `text: str`. `generate_batch(...) -> list[BatchDoc]`. Task 4 uses this.
- Produces, in `tests/conftest.py`: `MockLLM(responses: list[BaseModel | Exception] | None = None)` with the same generic `generate_structured` signature. It returns `cast(T, obj)`.

- [ ] **Step 1: Config in `backend/pyproject.toml`**
  - dev extras: `["pytest>=8", "httpx>=0.27", "ruff>=0.17", "mypy>=2.4"]`
  - `[tool.ruff]`: `line-length = 100`, `target-version = "py312"`
  - `[tool.ruff.lint]`: `select = ["E", "F", "I", "UP", "B", "SIM"]`, `ignore = ["UP042"]`. UP042 would turn `(str, Enum)` into `StrEnum` and change `str()` output.
  - `[tool.mypy]`: `strict = true`, `python_version = "3.12"`, `plugins = ["pydantic.mypy"]` (ships with pydantic, so no new dependency)
- [ ] **Step 2: Write the failing test** in `tests/test_llm.py`:
  ```python
  def test_missing_usage_metadata_counts_zero_tokens():
      resp = FakeResponse('{"answer": "x"}')
      resp.usage_metadata = None
      client, _ = make_client([resp])
      _, call = client.generate_structured("q?", Out)
      assert (call.tokens_in, call.tokens_out) == (0, 0)
  ```
  Run: `pytest tests/test_llm.py -v`. Expected: FAIL with `AttributeError: 'NoneType' object has no attribute 'prompt_token_count'`.
- [ ] **Step 3:** In `GeminiClient.generate_structured`, read the tokens as `0` when `resp.usage_metadata is None`, and use `resp.text or ""`. Annotate `_generate` with the return type from `google.genai.types`.
- [ ] **Step 4:** Run `ruff check --fix .`, then fix the remaining ruff findings by hand (E501, SIM115, SIM117). Annotate until `mypy .` is clean. Rules:
  - Trace and span docs are `dict[str, Any]`.
  - `_rerun_step` returns `BaseModel`.
  - In `test_llm.make_client`, keep `client._generate = fake_generate` with `# type: ignore[method-assign]`; no rewrite.
  - Add `[[tool.mypy.overrides]] ignore_missing_imports` only for a third-party module without stubs, and name the module.
- [ ] **Step 5: Verify**
  Run: `ruff check . && mypy . && pytest -q`. Expected: `All checks passed!`, `Success: no issues found`, `44 passed`.
- [ ] **Step 6: Commit** `chore: type backend for mypy --strict and pin ruff rules`

---

### Task 3: MIT licence and CI (user step 2b)

**Files:**
- Create: `LICENSE`: standard MIT text, `Copyright (c) 2026 Sasha Risoluti`
- Create: `.github/workflows/ci.yml`

**Interfaces:** consumes the Task 2 config. CI runs plain `ruff check .`, `mypy .` and `pytest`.

- [ ] **Step 1:** Write `ci.yml`: `on: [push, pull_request]`, two jobs on `ubuntu-latest`.
  - `backend`: `defaults.run.working-directory: backend`. Steps: `actions/checkout@v4`, `actions/setup-python@v5` with `python-version: "3.12"` and `cache: pip`, `pip install -e ".[dev]"`, then `ruff check .`, `mypy .`, `pytest -q`. No secrets referenced.
  - `frontend`: `working-directory: frontend`. Steps: `actions/checkout@v4`, `actions/setup-node@v4` with `node-version: 22`, `cache: npm` and `cache-dependency-path: frontend/package-lock.json`, `npm ci`, `npm test`.
- [ ] **Step 2: Verify the YAML parses**
  Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"` (use the scratch venv; pyyaml comes in through the dev deps if present, otherwise `pip install pyyaml` in scratch only). Expected: no output.
- [ ] **Step 3: Verify the frontend job in a clean copy.** Copy `frontend/` without `node_modules` to the scratchpad, then run `npm ci && npm test`.
  Expected: vitest reports `traceFlow.test.ts` passing. If the darwin binding still fails, report it. Linux CI is then the source of truth.
- [ ] **Step 4: Commit** `ci: add MIT licence and GitHub Actions for ruff, mypy, pytest, vitest`

**STOP: show the diff for Tasks 2 and 3.**

---

### Task 4: Diagnosis evaluation script (user step 3)

**Files:**
- Create: `backend/scripts/evaluate_diagnosis.py`. It lives next to `run_batch.py`, because `backend/scripts` is the existing scripts package. Run it from `backend/` with `python -m scripts.evaluate_diagnosis`.
- Test: `backend/tests/test_evaluate_diagnosis.py`

**Interfaces:**
- Consumes: `generate_batch(n, seed) -> list[BatchDoc]`, `CORRUPTORS` (docgen), `run_pipeline(text, doc_id, llm, tracer, recorder) -> str`, `diagnose(trace_doc, llm) -> Diagnosis`, `connect`, `ForensicsExporter`, `PayloadRecorder`, `build_tracer`.
- Produces:
  - `EXPECTED: dict[str, tuple[str, FailureCategory]]`: the Global Constraints mapping, verbatim.
  - `@dataclass(frozen=True) class Outcome` with fields `doc_id: str`, `corruption: str`, `root_cause_step: str`, `category: FailureCategory`, `seconds: float`.
  - `evaluate(batch: list[BatchDoc], llm: LLMClient, conn: sqlite3.Connection, tracer: Tracer, recorder: PayloadRecorder, clock: Callable[[], float] = time.perf_counter, pause: float = 0.0) -> list[Outcome]`.
    Run the pipeline on every doc, because clean docs are part of a realistic batch. Then, for docs with `corruption is not None` only, load the trace JSON via `SELECT json_path FROM traces WHERE trace_id=?` and time `diagnose()` with `clock()` before and after.
  - `render_table(outcomes: list[Outcome]) -> str`: the markdown table.
  - `main() -> None`: argparse `--n 50 --seed 42 --pause 2.0 --data-dir <repo>/data/evaluation`. Build the tracer like `run_batch.py`, use `llm = GeminiClient()` (Task 5 swaps this to `make_provider()`), print `render_table(...)`.

**Table format (exact):**
```
| Corruption | n | Root-cause step correct | Category correct | Median flag→diagnosis (s) |
|---|---|---|---|---|
| ambiguous_category | 3 | 2/3 (67%) | 1/3 (33%) | 4.1 |
| ...one row per corruption in sorted(EXPECTED)... |
| **all** | 10 | 7/10 (70%) | 5/10 (50%) | 3.8 |
```
Percentages are rounded to whole numbers. The median comes from `statistics.median` with 1 decimal. A row with `n = 0` shows `0 | – | – | –`.

- [ ] **Step 1: Write the failing tests**
  ```python
  def test_mapping_covers_every_corruptor():
      assert set(EXPECTED) == set(CORRUPTORS)

  def test_render_table_scores_and_median():
      outs = [Outcome("d0", "strip_dates", "extract", FailureCategory.extraction_hallucination, 1.0),
              Outcome("d1", "strip_dates", "summarize", FailureCategory.context_loss, 3.0),
              Outcome("d2", "ambiguous_category", "classify", FailureCategory.propagation_error, 2.0)]
      table = render_table(outs)
      assert "| strip_dates | 2 | 1/2 (50%) | 1/2 (50%) | 2.0 |" in table
      assert "| ambiguous_category | 1 | 1/1 (100%) | 0/1 (0%) | 2.0 |" in table
      assert "| currency_mismatch | 0 | – | – | – |" in table
      assert "| **all** | 3 | 2/3 (67%) | 1/3 (33%) | 2.0 |" in table

  def test_render_table_empty_batch():
      assert "| **all** | 0 | – | – | – |" in render_table([])

  def test_evaluate_diagnoses_only_corrupted_docs_and_times_them(tmp_env): ...
      # batch: one clean BatchDoc + one corruption="strip_dates"
      # MockLLM queue: 3 pipeline outputs (clean), 3 pipeline outputs (corrupted),
      #   4 JudgeVerdicts (5,2,2,2) + CategoryVerdict(extraction_hallucination)
      # clock = iter([10.0, 12.5]).__next__
      # assert one Outcome: doc_id of corrupted doc, root_cause_step "extract", seconds == 2.5

  def test_evaluate_still_diagnoses_when_a_step_errors(tmp_env): ...
      # one corrupted doc; MockLLM queue: RateLimitError("429") for extract,
      #   then JudgeVerdict(score=5) for intake, CategoryVerdict(prompt_failure)
      # assert outcome.root_cause_step == "extract"
  ```
  Build tracer, recorder and conn the same way as `build_env` in `tests/test_orchestrator.py`.
  Run: `pytest tests/test_evaluate_diagnosis.py -v`. Expected: FAIL with `ModuleNotFoundError: scripts.evaluate_diagnosis`.
- [ ] **Step 2:** Implement `evaluate_diagnosis.py` per the Interfaces block. Add a module docstring with the usage line and the note `Requires GEMINI_API_KEY`.
- [ ] **Step 3: Verify**
  Run: `ruff check . && mypy . && pytest -q`. Expected: all clean, `49 passed`.
- [ ] **Step 4: Commit** `feat: add diagnosis accuracy evaluation script`

**STOP: show the diff.** A real run with `--n 50 --seed 42` calls the Gemini API with the key in `.env`. Ask Sasha before running it.

---

### Task 5: LLMProvider protocol (user step 4)

**Files:**
- Modify: `backend/pipeline/llm.py`
- Modify: every importer of `LLMClient` (`steps.py`, plus annotations added in Task 2: `orchestrator.py`, `forensics/engine.py`, `evals/runner.py`, `api/app.py`, `scripts/*.py`, `tests/conftest.py`). Find them with `grep -rn "LLMClient\|GeminiClient()" backend`.
- Test: `backend/tests/test_llm.py`

**Interfaces:**
- Produces:
  - `class LLMProvider(Protocol)`: the renamed `LLMClient`, with the same generic `generate_structured`. No alias is kept for the old name.
  - `PROVIDERS: dict[str, Callable[[], LLMProvider]] = {"gemini": GeminiClient}`.
  - `make_provider(name: str | None = None) -> LLMProvider`. The name resolves as `name or os.environ.get("LLM_PROVIDER", "gemini")`. An unknown name raises `ValueError` with a message containing the unknown name and `sorted(PROVIDERS)`.
- Call sites: `create_app` (`llm is None` branch), `run_batch.main` and `evaluate_diagnosis.main` use `make_provider()` instead of `GeminiClient()`.

- [ ] **Step 1: Write the failing tests** in `tests/test_llm.py`:
  ```python
  def test_make_provider_defaults_to_gemini(monkeypatch):
      monkeypatch.delenv("LLM_PROVIDER", raising=False)
      sentinel = MockLLM([])
      monkeypatch.setitem(PROVIDERS, "gemini", lambda: sentinel)
      assert make_provider() is sentinel

  def test_make_provider_reads_env(monkeypatch):
      sentinel = MockLLM([])
      monkeypatch.setitem(PROVIDERS, "fake", lambda: sentinel)
      monkeypatch.setenv("LLM_PROVIDER", "fake")
      assert make_provider() is sentinel

  def test_make_provider_unknown_name_raises():
      with pytest.raises(ValueError, match="nope.*gemini"):
          make_provider("nope")

  def test_implementations_satisfy_protocol():
      providers: list[LLMProvider] = [MockLLM([]), GeminiClient.__new__(GeminiClient)]  # mypy is the gate
      assert len(providers) == 2
  ```
  Run: `pytest tests/test_llm.py -v`. Expected: FAIL with `ImportError: cannot import name 'LLMProvider'`.
- [ ] **Step 2:** Rename the protocol, add `PROVIDERS` and `make_provider`, and switch the three call sites.
- [ ] **Step 3: Verify**
  Run: `ruff check . && mypy . && pytest -q && grep -rn "LLMClient\|GeminiClient()" . ; true`. Expected: all clean, `53 passed`, no grep hits outside `PROVIDERS`.
- [ ] **Step 4: Commit** `refactor: introduce LLMProvider protocol with provider factory`

**STOP: show the diff.**
