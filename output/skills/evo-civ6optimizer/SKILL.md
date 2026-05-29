---
name: evo-civ6optimizer
---

---
name: evo-civ6optimizer
description: Civ6 district placement optimizer for adjacency bonus maximization
---

# Civ6 District Adjacency Optimizer

Optimizes city center and district placement to maximize adjacency bonuses.

## Usage

```python
from utils import (
    parse_map_dump, hex_distance, get_neighbors, get_tiles_in_range,
    compute_adjacency, optimize_placements,
)
```

## Map Parsing

Parse the .Civ6Map SQLite dump to extract terrain, rivers, features, and map dimensions.

## Optimization Strategy

1. Identify all valid land tiles for city centers
2. For each candidate city center, find all valid district placements within range
3. Score and rank possible placements
4. Use greedy + local search for optimization

## Adjacency Rules

See civ6lib SKILL.md for complete adjacency rules. Key points:
- Each +0.5 bonus type is floored SEPARATELY, then summed
- Government Plaza gives +1 to adjacent specialty districts
- Districts on rivers give +2 to Commercial Hub
