# CoEvoSkills

Reproduction of [CoEvoSkills: Self-Evolving Agent Skills via Co-Evolutionary Verification](https://arxiv.org/abs/2604.01687) (arXiv: 2604.01687v2).

Agent skills self-evolve through a co-evolutionary loop: a **Skill Generator** creates multi-file skill bundles, a **Surrogate Verifier** independently tests them, and a **Ground-Truth Oracle** returns pass/fail signals. Evaluated on [SkillsBench](https://github.com/benchflow-ai/skillsbench) (94 tasks across 11 domains).

## Quick Start

```bash
# 1. Activate environment
source .venv/bin/activate

# 2. Set your API key
export DEEPSEEK_API_KEY=sk-xxx

# 3. Sanity check — hello-world with flash model (~1-2 min)
python scripts/evolve.py \
  --tasks skillsbench/experiments/sanity-tasks/hello-world \
  --model deepseek-v4-flash

# 4. Run on a real task
python scripts/evolve.py --tasks citation-check --model deepseek-v4-pro
```

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.8+ | `tomli` fallback for <3.11 |
| API key | Default provider: DeepSeek. Set env `DEEPSEEK_API_KEY`. Also supports Anthropic/OpenAI |
| proot (auto) | Static binary downloaded on first run for path virtualization |

## Installation

```bash
cd CoEvo

# Core dependencies
pip install -e .

# With specific LLM provider
pip install -e ".[anthropic]"   # Claude
pip install -e ".[openai]"      # GPT
pip install -e ".[dev]"         # pytest, ruff
pip install -e ".[anthropic,openai,dev]"  # all at once
```

## Project Structure

```
CoEvo/
├── utils/                    # Infrastructure
│   ├── llm/                  #   LLM clients (Anthropic, OpenAI, DeepSeek)
│   ├── agent/                #   Agent interaction loop (JSON protocol + prompts)
│   ├── executor/             #   Sandbox, Executor Φ(S,E), environment
│   ├── config.py             #   Configuration loading
│   └── logger.py             #   Structured logging
├── layers/                   # Core model components
│   ├── skill_generator/      #   Generator πθ: skill generation/refinement (Eq.7)
│   ├── surrogate_verifier/   #   Verifier πV_θ: test generation, R̃ computation (Eq.4)
│   └── oracle/               #   Ground-Truth Oracle: fresh env re-execution (Eq.8)
├── engine/                   # Orchestration
│   ├── evolution.py          #   Algorithm 1 main co-evolution loop
│   ├── context.py            #   Conversation context management (cap β)
│   └── scheduler.py          #   Parallel worker scheduling
├── repository/               # Data layer
│   ├── task.py               #   SkillsBench task loader
│   ├── skill.py              #   Skill bundle model + SKILL.md parser
│   └── store.py              #   Artifact persistence
├── eval/                     # Evaluation & metrics
├── configs/                  # YAML config files
├── scripts/                  # CLI entry points
├── skillsbench/              # Upstream benchmark (git submodule)
└── pyproject.toml
```

## API Key Setup

Set the environment variable for the provider you want to use:

| Provider | Env Variable | Example |
|---|---|---|
| DeepSeek (default) | `DEEPSEEK_API_KEY` | `sk-...` |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | `sk-ant-api03-...` |
| OpenAI (GPT) | `OPENAI_API_KEY` | `sk-proj-...` |

You only need ONE. The code auto-detects the model name to select the right client.

## Running Experiments

### 1. Evolution — Generate Skills (Paper §4.2, Figure 4)

```bash
# Single task quick test
python scripts/evolve.py --tasks exoplanet-detection-period

# All tasks with DeepSeek (default)
python scripts/evolve.py

# Override evolution budget (paper uses N=5, M=15)
python scripts/evolve.py --tasks citation-check --n 5 --m 15

# Switch to other providers
python scripts/evolve.py --provider anthropic --model claude-sonnet-4-20250514
python scripts/evolve.py --provider openai --model gpt-5.2

# Custom config and output dir
python scripts/evolve.py --config configs/default.yaml --output ./output/run1

# Limit parallelism (default: 4)
python scripts/evolve.py --parallel 2
```

**What happens:**
1. Loads each SkillsBench task (instruction + environment).
2. **Generator πθ** creates an initial skill bundle (SKILL.md + scripts/).
3. Co-evolution loop (Algorithm 1):
   - **Executor Φ(S,E)** runs the skill in a sandbox → output files.
   - **Surrogate Verifier** generates tests, runs them against outputs.
   - If tests fail → structured feedback → Generator refines the skill.
   - If tests pass → **Oracle** re-executes in a fresh environment.
   - If Oracle fails → Verifier escalates its tests.
   - Repeat up to N=5 Oracle rounds, M=15 surrogate retries.
4. Output: evolved skills + round-by-round metrics saved to `./output/`.

### 2. Evaluation — Test Evolved Skills (Paper §4.2)

After evolution generates skills:

```bash
python scripts/evaluate.py \
  --skills ./output/skills \
  --model claude-sonnet-4-20250514 \
  --output ./output/eval
```

### 3. Cross-Model Transfer (Paper §4.4, Figure 5)

Evolve skills with one model, test on others:

```bash
# Evolve with Claude, evaluate on multiple models
python scripts/evolve.py --provider anthropic --output ./output/claude_skills

python scripts/transfer.py \
  --skills ./output/claude_skills/skills \
  --models gpt-5.2,qwen3-coder-480b,deepseek-v3 \
  --output ./output/transfer
```

## Configuration

All key parameters from the paper are in `configs/default.yaml`:

```yaml
evolution:
  n: 5       # Max oracle interventions (N)
  m: 15      # Max surrogate retries (M)
  beta: 0.7  # Context usage cap (β)

timeout:
  evolution_multiplier: 5.0  # 5× effective 3000s/task
  evaluation: 7200           # 7200s/task oracle timeout

workers:
  evolve: 4   # Parallel evolution workers
  eval: 10    # Parallel evaluation workers

llm_model: "claude-sonnet-4-20250514"
skillsbench_path: "./skillsbench"
output_dir: "./output"
```

Override any param via CLI:
```bash
python scripts/evolve.py --model gpt-5.2 --output ./output/gpt_run
python scripts/evolve.py --n 5 --m 15  # override evolution budget
```

Model presets in `configs/models.yaml`.

## Output Structure

```
output/
├── skills/                  # Evolved skill bundles
│   └── exoplanet-detection-period/
│       ├── SKILL.md         # Procedural workflow
│       └── scripts/         # Executable utility code
├── traces/                  # Round-by-round evolution snapshots
│   └── exoplanet-detection-period/
│       ├── round_0.json     # {R̃, feedback, skill version, ...}
│       ├── round_1.json
│       └── ...
├── logs/                    # Per-task structured logs
│   └── exoplanet-detection-period.log
└── results/
    └── results.json         # Aggregated pass rates and metrics
```

## Results Format

`output/results/results.json`:
```json
[
  {
    "task": "exoplanet-detection-period",
    "converged": true,
    "reward": 1.0,
    "rounds": 6,
    "oracle_calls": 3,
    "surrogate_retries": 3,
    "history": [...]
  }
]
```

## Sandbox

| Backend | Description |
|---|---|---|
| `local` (default) | proot-based path virtualization. Auto-downloads static binary on first run. Maps `/app`, `/root`, `/tests`, `/logs` to temp workspace. No root needed. |
| `bare` | Plain subprocess in temp dir (fallback if proot unavailable). No path virtualization. |
| `docker` | Full container isolation via Docker SDK (requires docker-py + daemon). |

No manual setup — `Sandbox` auto-detects and downloads `proot` if needed.

## Troubleshooting

**ImportError: tomllib / yaml not found**
```bash
pip install tomli pyyaml
```

**Anthropic/OpenAI/DeepSeek client not connecting**
- Verify API key is set: `echo $ANTHROPIC_API_KEY`
- Check model name matches your API access tier

**Sandbox fails on a specific task**
- proot auto-downloads on first run; check internet connectivity if it fails
- dependencies are auto-installed from the task's Dockerfile
- if commands fail inside the sandbox, proot binary may need `PROOT_NO_SECCOMP=1` (already set)

**Context overflow (β exceeded)**
- Increase `beta` in `configs/default.yaml` (max 1.0)
- Or reduce `n` or `m` to limit rounds

## Development

```bash
# Lint
pip install ruff
ruff check .

# Auto-fix
ruff check --fix .
```

## References

- [CoEvoSkills Paper](CoEvoSkills.md) (arXiv: 2604.01687v2)
- [SkillsBench Benchmark](https://github.com/benchflow-ai/skillsbench)
- [Project Page](https://zhang-henry.github.io/CoEvoSkills/)
