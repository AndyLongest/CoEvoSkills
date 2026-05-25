---
name: evo-tess-exoplanet-period
---

---
name: evo-tess-exoplanet-period
description: Detect exoplanet periods from TESS light curves with stellar activity removal.
---
 
# EVO TESS Exoplanet Period Detection
 
Pipeline:
1. Load and filter TESS light curve
2. Remove stellar variability via Savitzky-Golay filter
3. Run Transit Least Squares to find orbital period
 
See scripts/utils.py for full implementation.
