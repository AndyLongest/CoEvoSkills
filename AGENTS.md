# CoEvoSkills - Repository Architecture

Repository for reproducing the CoEvoSkills paper and serving as a development platform for downstream agent work.

## Directory Structure

```
CoEvo/
├── utils/                          # Infrastructure layer
│   ├── llm/                        #   LLM connection protocol
│   │   ├── client.py               #     Abstract client interface
│   │   ├── anthropic.py            #     Claude adapter
│   │   ├── openai.py               #     GPT adapter
│   │   └── types.py                #     Message, Response types
│   ├── executor/                   #   Code execution engine
│   │   ├── sandbox.py              #     Sandboxed env (proot/bare/docker)
│   │   ├── executor.py             #     Skill Executor Φ(S,E) (Algorithm 1)
│   │   ├── environment.py          #     Env setup/teardown/rollout
│   │   └── filesystem.py           #     File I/O inside container
│   ├── agent/                      #   Agent interaction
│   │   ├── loop.py                 #     JSON protocol agent loop
│   │   └── prompts.py              #     All system prompts
│   ├── config.py                   #   Global config loading
│   └── logger.py                   #   Structured logging
│
├── layers/                         # Model components (paper core)
│   ├── skill_generator/            #   Skill Generator (§3.3 Eq.7)
│   │   ├── generator.py            #     Iterative skill generation/refinement
│   │   ├── prompts.py              #     System & evolution prompts
│   │   └── skill_manager.py        #     Skill file CRUD
│   ├── surrogate_verifier/         #   Surrogate Verifier (§3.3 Eq.4,8)
│   │   ├── verifier.py             #     Independent LLM session for testing
│   │   ├── test_generator.py       #     Test assertion generation e_k
│   │   ├── test_runner.py          #     Run assertions, compute R̃
│   │   └── feedback.py             #     Structured failure diagnostic F(i,j)
│   └── oracle/                     #   Ground-Truth Oracle (§3.3)
│       └── oracle.py               #     Independent re-exec, pass/fail signal
│
├── engine/                         # Orchestration layer
│   ├── evolution.py                #   Algorithm 1 main co-evolution loop
│   ├── context.py                  #   Conversation context mgmt (cap β)
│   └── scheduler.py                #   Parallel worker scheduling
│
├── repository/                     # Persistence layer
│   ├── task.py                     #   Task data model + SkillsBench loader
│   ├── skill.py                    #   Skill bundle data model + SKILL.md parser
│   └── store.py                    #   Artifact storage (skills, traces, logs)
│
├── eval/                           # Evaluation layer
│   ├── metrics.py                  #   Pass rate computation
│   ├── transfer.py                 #   Cross-model transfer evaluation
│   └── reporter.py                 #   Results aggregation & reporting
│
├── configs/                        # Configuration files
│   ├── default.yaml                #   Default params (N=5, M=15, β=0.7, ...)
│   └── models.yaml                 #   Model configs
│
├── scripts/                        # CLI entry points
│   ├── evolve.py                   #   Run evolution on tasks
│   ├── evaluate.py                 #   Evaluate with pre-evolved skills
│   └── transfer.py                 #   Cross-model transfer eval
│
├── tests/                          # Unit tests
├── pyproject.toml
└── README.md
```

## Layer Responsibilities

| Layer | Role | Depends On |
|-------|------|------------|
| `utils/` | Infrastructure: LLM communication, sandbox execution, config, logging | nothing |
| `layers/` | Model components: Skill Generator, Surrogate Verifier, Oracle | `utils/llm/`, `utils/executor/` |
| `engine/` | Orchestration: Algorithm 1 loop, context mgmt, parallel scheduling | `layers/`, `repository/`, `utils/` |
| `repository/` | Data: task loading, skill serialization, artifact storage | nothing |
| `eval/` | Evaluation: metrics, cross-model transfer, reporting | `engine/`, `repository/` |

## Data Flow

```
scripts/evolve.py
  └─→ engine/evolution.py (Algorithm 1)
        ├─→ repository/task.py        (load task)
        ├─→ layers/skill_generator/    → S(i), x(i) = Φ(S(i),E) (AgentLoop, unified)
        ├─→ layers/surrogate_verifier/ → R̃, F(i,j)
        ├─→ layers/oracle/            → R (pass/fail)
        └─→ layers/surrogate_verifier/ → V(j+1) (if R̃=1 ∧ R<1)
```

## Key Design Decisions

1. **`engine/` separate from `layers/`**: orchestration is pure logic, no LLM calls; layers are decoupled via engine
2. **`repository/` as standalone layer**: Task/Skill data models and serialization are reusable across components
3. **Abstract LLM interface in `utils/llm/`**: enables hot-swapping Claude/GPT/open-source backends
4. **Sandboxed executor in `utils/executor/`**: rollout Φ requires isolated Docker environments, independent of LLM
5. **`eval/` separated from `engine/`**: evolution and evaluation are distinct phases, no circular deps
6. **Generator πθ as AgentLoop (unified with Executor Φ)**: The SkillGenerator uses an AgentLoop with `EVOLUTION_AGENT_SYSTEM_PROMPT` (P1-P6 workflow). The Generator creates skills, executes them, and SEES the terminal output (including import errors, API timeouts, runtime failures) — matching the paper's unified Evolution Agent design. Previously, Generator was a single text-only LLM call and Executor was a separate AgentLoop; this split prevented the Generator from seeing execution failures. Oracle still uses an independent AgentLoop in a fresh environment (E′).
7. **V persistence across evaluate calls**: `SurrogateVerifier.evaluate()` returns the test suite as its third return value so `engine/evolution.py` can persist it as `V`. This ensures V(j) is fixed across surrogate retry rounds (matching Alg. 1 line 18: "V(j) locked") and only grows via `escalate()` when R̃=1 ∧ R<1.
8. **Environment context injected into Generator**: The Generator πθ receives a dense summary of task environment files (`test.bib`, reference docs, pre-installed skill SKILL.md, pip dependencies, installed tools). See `_build_environment_context()` in `engine/evolution.py`.
9. **Test runner namespace includes common modules**: `TestRunner._run_single_assertion()` injects `json`, `re`, `Path` into the exec namespace alongside `os` and `open`. The namespace is shared across all assertions in a single evaluate call. Both the generate and escalate prompts tell the LLM which modules are pre-available.
10. **Verifier feedback constrained to visible evidence**: The `VERIFIER_SYSTEM_PROMPT` and `_generate_feedback()` prompt explicitly forbid speculating about invisible causes (file permissions, symlinks, sandbox, network). Root-cause analysis is limited to what can be directly observed from the test failures and output files.
11. **Environment root files copied to sandbox**: `Environment` collects root-level input files (e.g., `test.bib`) into `root_files` and `prepare_sandbox()` copies them to `/root/` in the sandbox. Previously only `data/`, `doc/`, and `skills/` subdirectories were copied; files at the environment root were silently dropped, causing skills to fail with FileNotFoundError.
12. **Surrogate Verifier generates content-level tests**: The Verifier's test generator prompt instructs the LLM to read input data files (e.g., `test.bib`), independently compute expected answers, and compare against the agent's output. This matches the paper's exoplanet case study where the Verifier "independently ran its own BLS analysis on the raw lightcurve" (§E). Examples of content-driven assertions (suspicious DOI detection, expected value comparison) are included in the prompt to guide the Verifier LLM.

## Key Parameters (from paper §4.1, Table A1)

| Param | Value | Description |
|-------|-------|-------------|
| N | 5 | Max oracle interventions (evolution rounds) |
| M | 15 | Max surrogate retries |
| β | 0.7 | Context usage cap (LLM context overflow prevention) |
| Evolution timeout | 5× (effective 3000s/task) | Per-task timeout multiplier |
| Evaluation timeout | 7200s/task | Oracle evaluation timeout |
| Parallel workers | 4 (evolve), 10 (eval) | Concurrent task workers |

## References

- Paper: CoEvoSkills.md (arXiv: 2604.01687v2)
- Benchmark: SkillsBench (Li et al., 2026b) - `skillsbench/` directory (upstream, do not modify)
- Meta-skill S_meta: Anthropic official skill-creator (see paper Appendix F.3)
- Paper project page: https://zhang-henry.github.io/CoEvoSkills/

## Code Modification Rules

- **DO NOT modify any code without explicit user request.** Do not proactively fix bugs, refactor, or add features unless asked.
- If you spot an issue, report it and wait for the user to decide.

## Experiment Status (2026-05-24)

### Current State

The full Algorithm 1 co-evolution loop runs end-to-end. Progress through the loop:

```
Algorithm 1 progress (key: ✅ working, ⚠️ partial, ❌ blocked, — unreachable):

C ← (I, Smeta)                                      ✅
S(0) ~ πθ(·|C)                                      ✅ SkillGenerator returns SkillBundle
V(0) ← ∅                                            ✅
n←0; r←0; Rbest←0; S*←S(0)                         ✅

while n<N and r<M:
    x(i) ← Φ(S(i), E)                               ✅ Executor class (AgentLoop
                                                        with EXECUTION prompt)
    context > β check                                — (not yet triggered)
    R̃(i,j) ← evaluate(x, V)                         ✅ SurrogateVerifier works
    if R̃ < 1:
        C ← C ⊕ F                                   ✅
        S(i+1) ← refine                             ✅ SkillGenerator refines with feedback
        r++; continue
    x̂(i) ← Φ(S(i), E')   fresh env                  ✅ Oracle sandbox with deps
    R(i) ← oracle                                     ✅ Oracle returns R
    V(j+1) ← escalate                                ✅
```

### Current State (2026-05-24)

The full Algorithm 1 loop is operational:
- **Sandbox**: proot-based path virtualization (no `-r`, bind mounts only). `pip install` in host venv.
- **LLM**: DeepSeek V4 Pro/Flash confirmed.
- **SkillGenerator πθ**: generates/refines SkillBundle (SKILL.md + scripts/) via single LLM call. Environment context (input files, reference docs, available skills, pip deps) injected into conversation context C.
- **Executor Φ(S,E)**: writes skill to sandbox → AgentLoop with `EXECUTION_AGENT_SYSTEM_PROMPT` → collects outputs. Injects full SKILL.md into the agent prompt.
- **SurrogateVerifier πV_θ**: generates deterministic tests, computes R̃, produces F(i,j) diagnostics. Test suite V is persisted across rounds and escalated only on oracle mismatch. Test runner namespace includes `json`, `re`, `Path` to prevent NameError from Verifier LLM's generated assertions.
- **Oracle**: fresh sandbox with deps, runs ground-truth tests via test.sh stubs (apt-get/curl stubbed).
- **Engine**: Algorithm 1 main loop with Generator→Executor→Verifier→Oracle separation. V now correctly returned by evaluate() for persistent test suites.
- **Tasks**: 94 SkillsBench tasks load correctly.

### Verified ✅
- hello-world converged to R=1 (both with unified AgentLoop and Generator+Executor split)
- proot path virtualization with bind mounts (v5.3.0 static binary)
- Oracle sandbox dependency installation
- Agent JSON protocol parsing with clear error messages
- Skill refinement loop (R̃ < 1 → feedback → regenerate)
- V persistence across evaluate calls (generated tests no longer discarded)
- Environment context injection into Generator (test.bib, ref docs, skill info)
- Test runner namespace includes common modules (json, re, Path) to prevent verifier assertion NameError

### Not Yet Verified
- Non-trivial task convergence (citation-check R̃=1 but Oracle R=0 — needs N>2)
- Heavy dependency tasks (numpy, scipy, lightkurve on exoplanet)
- Cross-model transfer evaluation
- Context overflow β cap

### Environment
- Python: 3.11.15 venv (`source .venv/bin/activate`)
- LLM: DeepSeek V4 Pro (default), API key in `DEEPSEEK_API_KEY`
- Docker: NOT available on this machine
- Sandbox: proot-based path virtualization (`utils/executor/proot` auto-downloaded on first run)
- Config: `configs/default.yaml` (N=2, M=3 for debug; paper uses N=5, M=15)

## Sandbox Architecture

Three backends, auto-detected:

```
Sandbox(backend="local")      # default
  → _ensure_proot()           # auto-downloads proot static binary if missing
  → _run_local()              # proot -b bind-mount wraps subprocess
    proot -b {ws}/app:/app -b {ws}/root:/root ...
    → absolute paths (/app/hello.txt) resolve to workspace
    → read_file/write_file use same {ws}/path mapping → all layers aligned

Sandbox(backend="bare")       # fallback, no path virtualization
  → plain subprocess in temp dir

Sandbox(backend="docker")     # requires docker-py + daemon
  → volume mount -v {ws}:/app
```

proot provides filesystem path virtualization without root, matching Docker's volume mount semantics. All three layers (write_file/read_file, subprocess, verifier tests) see the same path namespace.

## Plan B: Docker Sandbox (future)

Once Docker is available, switch with `Sandbox(backend="docker", dockerfile=...)` for full isolation + reproducible builds.
