---
name: evo-exoplanet-search
---

---
name: evo-exoplanet-search
description: Detect exoplanet transit periods in light curves with strong stellar activity. Use for TESS/Kepler light curves where stellar rotation masks transit signals. Workflow: filter outliers, remove stellar variability via Savitzky-Golay detrending, then search with BLS.
---

# Evo Exoplanet Search
Skill for finding exoplanet transit periods in light curves dominated by stellar activity.

## Functions
- load_lightcurve(path) -> time, flux, flag, flux_err
- filter_outliers(time, flux, flux_err, sigma=3) -> filtered arrays
- remove_stellar_variability(time, flux, flux_err, window_length=101) -> detrended flux
- find_transit_period(time, flux, flux_err) -> best period in days
