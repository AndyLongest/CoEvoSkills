---
name: evo-exoplanet-detector
---

---
name: evo-exoplanet-detector
description: Evolved exoplanet transit detection from TESS light curves. Use when you need to filter, detrend, and find exoplanet orbital periods in photometric time series with stellar variability.
---

# Evolved Exoplanet Detector
Pipeline: load data -> quality filter -> remove outliers -> detrend stellar rotation -> period search with TLS/BLS -> refine.
Scripts: scripts/utils.py
Load: sys.path.insert then from utils import ...
