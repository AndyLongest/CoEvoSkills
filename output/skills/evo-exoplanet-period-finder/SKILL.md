---
name: evo-exoplanet-period-finder
---

---
name: evo-exoplanet-period-finder
description: Find exoplanet orbital periods from TESS light curves by removing stellar variability.
---

# Exoplanet Period Finder

Utility functions for exoplanet transit period detection.

# Workflow
1. Load data
2. Filter by quality flags, sigma-clip outliers
3. Remove stellar variability via Savitzky’Golay
4. Find period using BLS

# Scripts

Functions in scripts/utils.py:
- load_lightcurve
- filter_data
- remove_variability
- find_exoplanet_period
