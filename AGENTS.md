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
│   │   ├── sandbox.py              #     Sandboxed env (Docker)
│   │   ├── environment.py          #     Env setup/teardown/rollout Φ(S,E)
│   │   └── filesystem.py           #     File I/O inside container
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
        ├─→ repository/task.py       (load task)
        ├─→ engine/context.py        (init context C)
        └─→ loop while n<N and r<M:
              ├─→ layers/skill_generator/  → S(i)
              ├─→ utils/executor/          → x(i) = Φ(S(i), E)
              ├─→ layers/surrogate_verifier/ → R̃, F(i,j)
              ├─→ layers/oracle/           → R (pass/fail)
              └─→ layers/surrogate_verifier/ → V(j+1) (if R̃=1 ∧ R<1)
```

## Key Design Decisions

1. **`engine/` separate from `layers/`**: orchestration is pure logic, no LLM calls; layers are decoupled via engine
2. **`repository/` as standalone layer**: Task/Skill data models and serialization are reusable across components
3. **Abstract LLM interface in `utils/llm/`**: enables hot-swapping Claude/GPT/open-source backends
4. **Sandboxed executor in `utils/executor/`**: rollout Φ requires isolated Docker environments, independent of LLM
5. **`eval/` separated from `engine/`**: evolution and evaluation are distinct phases, no circular deps

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
S(0) ~ πθ(·|C)                                      ✅ LLM generates initial skill bundle
V(0) ← ∅                                            ✅
n←0; r←0; Rbest←0; S*←S(0)                         ✅

while n<N and r<M:
    x(i) ← Φ(S(i), E)                               ✅ proot path virtualization works;
                                                        dependencies installed via pip
    context > β check                                — (not yet triggered)
    R̃(i,j) ← evaluate(x, V)                         ⚠️ partially tested
    if R̃ < 1:
        C ← C ⊕ F                                   ✅
        S(i+1) ← refine                             ?
        r++; continue
    x̂(i) ← Φ(S(i), E')   fresh env                  — unreachable
    R(i) ← oracle                                     — unreachable (never called)
    V(j+1) ← escalate                                — unreachable
```

### Current State (2026-05-24)

The core infrastructure is working:
- **Sandbox**: proot-based path virtualization (no `-r`, bind mounts only) gives host access + path remapping. `pip install` runs in host Python venv.
- **LLM**: DeepSeek V4 Pro connectivity confirmed.
- **Agent Loop**: JSON protocol (Appendix F.1) works end-to-end.
- **Skill Generator**: generates and refines skills.
- **Surrogate Verifier**: generates tests, computes R̃, produces F(i,j) diagnostics.
- **Engine**: Algorithm 1 main loop, context mgmt, scheduler all functional.
- **Tasks**: 94 SkillsBench tasks load correctly.

### What's Not Yet Verified
- End-to-end evolution on a non-trivial task (oracle path never reached)
- Dependency installation for heavy tasks (numpy, scipy, lightkurve, etc.)
- Full convergence to R=1 on any task
- Cross-model transfer evaluation

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
