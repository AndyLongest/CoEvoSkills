---
name: evo-tess-exoplanet
---

---
name: evo-tess-exoplanet
description: Detects exoplanet transit periods in TESS light curves obscured by stellar activity. Workflow: filter quality flags, remove outliers, subtract stellar variability (flattening), run Transit Least Squares (TLS) to find the best period. Use when the task involves finding an exoplanet period from a TESS light curve with strong stellar rotation signals.
---

# TESS Exoplanet Detection with Stellar Activity Removal

Detect exoplanet periods in TESS light curves where strong stellar activity (rotational modulation) masks the transit signal.

## Workflow

1. Load and filter: Read the data file, filter quality flag=0, remove outliers via sigma clipping.
2. Remove stellar activity: Use lightkurve flatten() with an appropriate window length.
3. Period search: Run Transit Least Squares (TLS) on the cleaned, flattened light curve.
4. Output: Write the best period to /root/period.txt rounded to 5 decimal places.

## Key Decisions

- Outlier removal: sigma=3 sigma clipping
- Stellar activity removal: lightkurve flatten() with an appropriate window length
- Period search: TLS, which is more sensitive than Lomb-Scargle for transit-shaped signals
- Always include flux_err in TLS call

## Scripts

- scripts/utils.py: Contains load_and_filter(), remove_stellar_activity(), find_period_tls(), write_period()
