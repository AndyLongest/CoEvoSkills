# CoEvoSkills

Reproduction of [CoEvoSkills: Self-Evolving Agent Skills via Co-Evolutionary Verification](https://arxiv.org/abs/2604.01687) (arXiv: 2604.01687v2).

Agent skills self-evolve through a co-evolutionary loop: a **Skill Generator** creates multi-file skill bundles, a **Surrogate Verifier** independently tests them, and a **Ground-Truth Oracle** returns pass/fail signals. Evaluated on [SkillsBench](https://github.com/benchflow-ai/skillsbench) (94 tasks across 11 domains).

> **Current config uses debug defaults (N=2, M=3). Override with `--n 5 --m 15` for paper-level budget.**

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.8+ | `tomli` fallback for <3.11; 3.11+ recommended |
| Docker | Container isolation for sandboxed execution. [Install Docker](https://docs.docker.com/engine/install/) |
| opencode CLI | Agent harness for evolution. Install: `curl -fsSL https://opencode.ai/install.sh \| bash` |
| API key | DeepSeek (default). Configure via opencode: edit `~/.local/share/opencode/auth.json` |

## Installation

```bash
# 1. Install opencode CLI (agent harness)
curl -fsSL https://opencode.ai/install.sh | bash
opencode --version   # verify installation (>= 1.2.27)

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# 3. Install core dependencies
pip install -e .

# 4. Install LLM provider of your choice
pip install -e ".[anthropic]"   # Claude
pip install -e ".[openai]"      # GPT
# DeepSeek uses openai package — included in core deps

# 5. (Optional) Dev tools
pip install -e ".[dev]"         # pytest, ruff

# 6. Configure DeepSeek API key in opencode
mkdir -p ~/.local/share/opencode
cat > ~/.local/share/opencode/auth.json << 'AUTH'
{
  "deepseek": {
    "type": "api",
    "key": "sk-your-deepseek-api-key"
  }
}
AUTH
```

## Quick Start

```bash
# Run evolution on a single task
python3 scripts/evolve.py --tasks citation-check --n 1 --m 1

# Override evolution budget (paper: N=5, M=15)
python3 scripts/evolve.py --tasks exoplanet-detection-period --n 5 --m 15

# Run all 94 tasks (requires API quota)
python3 scripts/evolve.py
```

## Available Tasks

All tasks can be run with `--tasks <name>`. The `--tasks` flag accepts a task name
(e.g., `citation-check`) or `all` for the full benchmark. See `skillsbench/tasks/` for details.

<!-- start task-table -->

<details>
<summary><strong>cybersecurity</strong> (7 tasks)</summary>

| Task | Description |
|------|-------------|
| `dapt-intrusion-detection` | Network Intrusion Detection |
| `fix-druid-loophole-cve` | Vulnerability Analysis |
| `fix-erlang-ssh-cve` | Vulnerability Analysis |
| `setup-fuzzing-py` | Fuzzing |
| `software-dependency-audit` | Vulnerability Analysis |
| `suricata-custom-exfil` | Intrusion Detection |
| `syzkaller-ppdev-syzlang` | Fuzzing |
</details>

<details>
<summary><strong>finance-economics</strong> (9 tasks)</summary>

| Task | Description |
|------|-------------|
| `econ-detrending-correlation` | Macroeconomic Time Series |
| `financial-modeling-qa` | Financial Modeling |
| `invoice-fraud-detection` | Fraud Detection |
| `reserves-at-risk-calc` | Risk Analysis |
| `sec-financial-report` | Sec Filings Analysis |
| `shock-analysis-demand` | Macroeconomic Analysis |
| `shock-analysis-supply` | Macroeconomic Analysis |
| `weighted-gdp-calc` | Macroeconomic Analysis |
| `xlsx-recover-data` | Financial Modeling |
</details>

<details>
<summary><strong>industrial-physical-systems</strong> (14 tasks)</summary>

| Task | Description |
|------|-------------|
| `3d-scan-calc` | 3D Printing Mass Calculation |
| `ada-bathroom-plan-repair` | Architectural Design |
| `adaptive-cruise-control` | Vehicle Control |
| `drone-planning-control` | Robot Control |
| `dynamic-object-aware-egomotion` | Egomotion / Dynamic Object Segmentation |
| `energy-ac-optimal-power-flow` | AC Optimal Power Flow |
| `energy-market-pricing` | Electricity Market Pricing |
| `energy-unit-commitment` | Unit Commitment |
| `grid-dispatch-operator` | Grid Dispatch |
| `hvac-control` | Control Systems |
| `manufacturing-codebook-normalization` | Defect Analysis |
| `manufacturing-equipment-maintenance` | Maintenance |
| `manufacturing-fjsp-optimization` | Production Scheduling |
| `r2r-mpc-control` | Control Systems |
</details>

<details>
<summary><strong>mathematics-or-formal-reasoning</strong> (8 tasks)</summary>

| Task | Description |
|------|-------------|
| `bike-rebalance` | Vehicle Routing |
| `civ6-adjacency-optimizer` | Combinatorial Optimization |
| `exam-block-sequencing` | Mathematical Optimization |
| `lean4-proof` | Formal Proof |
| `paratransit-routing` | Mathematical Optimization |
| `pddl-airport-planning` | Formal Planning |
| `pddl-tpp-planning` | Formal Planning |
| `travel-planning` | Calendar Scheduling |
</details>

<details>
<summary><strong>media-content-production</strong> (9 tasks)</summary>

| Task | Description |
|------|-------------|
| `mario-coin-counting` | Video Processing |
| `multilingual-video-dubbing` | Video Processing |
| `pedestrian-traffic-counting` | Video Processing |
| `pg-essay-to-audiobook` | Audio Processing |
| `threejs-structure-parser` | 3D Content |
| `threejs-to-obj` | 3D Content |
| `video-filler-word-remover` | Video Processing |
| `video-silence-remover` | Video Processing |
| `video-tutorial-indexer` | Video Processing |
</details>

<details>
<summary><strong>natural-science</strong> (15 tasks)</summary>

| Task | Description |
|------|-------------|
| `crystallographic-wyckoff-position-analysis` | Crystallography |
| `earthquake-phase-association` | Seismology |
| `earthquake-plate-calculation` | Geophysics Plate Tectonics |
| `exoplanet-detection-period` | Astronomy |
| `find-topk-similiar-chemicals` | Chemistry |
| `flood-risk-analysis` | Hydrology |
| `glm-lake-mendota` | Hydrology |
| `gravitational-wave-detection` | Astronomy |
| `lab-unit-harmonization` | Lab Unit Harmonization |
| `lake-warming-attribution` | Hydrology |
| `mars-clouds-clustering` | Astronomy |
| `protein-expression-analysis` | Protein Expression |
| `quantum-numerical-simulation` | Quantum Simulation |
| `radar-vital-signs` | Biomedical Analysis |
| `seismic-phase-picking` | Seismology |
</details>

<details>
<summary><strong>office-white-collar</strong> (15 tasks)</summary>

| Task | Description |
|------|-------------|
| `citation-check` | Academic Bibliography Verification |
| `court-form-filling` | Legal Form Filling |
| `edit-pdf` | PDF Editing |
| `enterprise-information-search` | Business Reporting |
| `exceltable-in-ppt` | Presentation Editing |
| `jpg-ocr-stat` | OCR |
| `latex-formula-extraction` | PDF Formula Extraction |
| `offer-letter-generator` | Document Editing |
| `organize-messy-files` | Document Classification |
| `paper-anonymizer` | Document Editing |
| `pdf-excel-diff` | Spreadsheet Workflow |
| `powerlifting-coef-calc` | Spreadsheet Workflow |
| `pptx-reference-formatting` | Presentation Editing |
| `sales-pivot-analysis` | Spreadsheet Workflow |
| `taxonomy-tree-merge` | Business Reporting |
</details>

<details>
<summary><strong>software-engineering</strong> (17 tasks)</summary>

| Task | Description |
|------|-------------|
| `azure-bgp-oscillation-route-leak` | Network Engineering |
| `data-to-d3` | Data Visualization Frontend |
| `debug-trl-grpo` | Debugging |
| `dialogue-parser` | Parser Implementation |
| `fix-build-agentops` | Build Repair |
| `fix-build-google-auto` | Build Repair |
| `fix-visual-stability` | Performance Optimization |
| `flink-query` | Implementation |
| `gh-repo-analytics` | Repo Analysis |
| `jax-computing-basics` | Library API Usage |
| `llm-prefix-cache-replay` | Performance Optimization |
| `parallel-tfidf-search` | Performance Optimization |
| `python-scala-translation` | Code Translation |
| `react-performance-debugging` | Performance Optimization |
| `simpo-code-reproduction` | Paper to Code Reproduction |
| `spring-boot-jakarta-migration` | Migration |
| `tictoc-unnecessary-abort-detection` | Concurrency Control |
</details>

<!-- end task-table -->

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.8+ | `tomli` fallback for <3.11; 3.11+ recommended |
| Docker | Container isolation for sandboxed execution. [Install Docker](https://docs.docker.com/engine/install/) |
| API key | Default provider: DeepSeek. Set env `DEEPSEEK_API_KEY`. Also supports Anthropic/OpenAI |

## Installation

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# 2. Install core dependencies
pip install -e .

# 3. Install LLM provider of your choice
pip install -e ".[anthropic]"   # Claude
pip install -e ".[openai]"      # GPT
# DeepSeek uses OpenAI-compatible API — install openai client
pip install openai

# 4. (Optional) Dev tools
pip install -e ".[dev]"         # pytest, ruff
```

## Project Structure

```
CoEvo/
├── utils/                    # Infrastructure
│   ├── llm/                  #   LLM clients (Anthropic, OpenAI, DeepSeek)
│   ├── agent/                #   Agent harness (opencode CLI + legacy JSON protocol)
│   │   ├── opencode_harness.py  #     opencode CLI agent harness (default)
│   │   ├── loop.py              #     Legacy JSON-protocol AgentLoop
│   │   └── prompts.py           #     System prompts
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
2. **opencode CLI harness** receives an AGENTS.md with evolution workflow (P1-P6), available skills, environment context, and task instruction.
3. Co-evolution loop (Algorithm 1):
   - **opencode execution** in Docker sandbox: reads pre-installed skills, creates evo-* skill bundle, executes task → output files.
   - **Surrogate Verifier** generates tests, runs them against outputs.
   - If tests fail → structured feedback → opencode refines the skill (--session --continue).
   - If tests pass → **Oracle** re-executes in a fresh environment.
   - If Oracle fails → Verifier escalates its tests.
   - Repeat up to N=5 Oracle rounds, M=15 surrogate retries.
4. Output: evolved skills + round-by-round metrics saved to `./output/`.

The agent harness is configurable in `configs/default.yaml`:
```yaml
agent_harness: "opencode"     # "opencode" (default) | "agentloop" (legacy JSON protocol)
opencode:
  model: "deepseek/deepseek-v4-pro"
```
opencode uses its own provider configuration (`opencode providers list`).

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
  n: 2       # Max oracle interventions (paper: 5)
  m: 3       # Max surrogate retries (paper: 15)
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

Three backends, configured via `configs/default.yaml` → `sandbox.backend`:

| Backend | Description |
|---|---|
| `docker` **(default)** | Full container isolation via Docker SDK. Spins up a `python:3.12-slim` container per task with volume mounts. Real `apt-get`/`curl` available inside. |
| `local` | proot-based path virtualization. Auto-downloads static binary on first run. Maps `/app`, `/root`, `/tests`, `/logs` to temp workspace. No root needed. |
| `bare` | Plain subprocess in temp dir (fallback if proot unavailable). No path virtualization. |

## Troubleshooting

**ImportError: tomllib / yaml not found**
```bash
pip install tomli pyyaml
```

**opencode: command not found**
opencode CLI is not installed. Install from https://opencode.ai

**opencode hangs / no output for >5 minutes**
- opencode may be in plan mode analyzing the task — normal for complex tasks
- Check: `ps aux | grep opencode` to verify it's still running (CPU > 0%)
- If opencode hangs with 0% CPU for >5 min, the DeepSeek API may be rate-limited
- Kill and retry: `pkill -f "opencode run"; pkill -f "evolve.py"`

**DeepSeek API key not found**
openCode's provider configuration is in `~/.local/share/opencode/auth.json`:
```json
{
  "deepseek": {
    "type": "api",
    "key": "sk-your-deepseek-api-key"
  }
}
```
Verify: `cat ~/.local/share/opencode/auth.json`

**Docker not available / daemon not running**
```bash
docker info   # check Docker daemon status
```
If Docker is unavailable, switch to local sandbox backend in `configs/default.yaml`:
```yaml
sandbox:
  backend: "local"   # proot-based, no Docker needed
```

**Sandbox fails on a specific task**
- Docker is the default backend; ensure Docker daemon is running (`docker ps`)
- dependencies are auto-installed from the task's Dockerfile
- for local backend: proot auto-downloads on first run; check internet connectivity if it fails

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
