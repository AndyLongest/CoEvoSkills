---
name: evo-exoplanet-detection
---

---
name: evo-exoplanet-detection
description: Evolved workflow for detecting exoplanet transits in TESS light curves with stellar activity.
---

# evo-exoplanet-detection

Workflow: (1) Load TESS light curve, (2) Filter flags/outliers, (3) Remove stellar variability via median filter, (4) Detect transit period via BLS/TLS, (5) Output to /root/period.txt (5 decimal places).

## Scripts
- scripts/utils.py: load_tess_lc, filter_data, remove_stellar_variability, detect_transit_period_tls

## Import
import sys; sys.path.insert(0, .../scripts); from utils import *
