---
name: evo-tess-exoplanet-detection
---

---
name: evo-tess-exoplanet-detection
description: Process TESS light curve data to detect exoplanet transit signals. Handles data loading, quality filtering, outlier removal, stellar variability removal (flattening), and period searching using Transit Least Squares (TLS). Use when given a TESS light curve file with columns time, flux, flag, flux_err and asked to find exoplanet orbital period.
---

# TESS Exoplanet Detection Pipeline

## Functions in scripts/pipeline.py

- load_tess_lc(filename): returns time, flux, flag, flux_err
- filter_good_data(time, flux, flag, flux_err): keeps flag==0
- sigma_clip_outliers(time, flux, flux_err, sigma=3): removes >3 sigma from median
- flatten_lc(time, flux, flux_err, window_length=21): lightkurve flatten to remove stellar variability
- period_search_tls(time, flux, flux_err): Transit Least Squares periodogram, returns period and other params
- process_tess_lc(filename, window_length=21, sigma=3): full pipeline, returns period,duration,T0,depth,snr,SDE

## Usage

import sys
sys.path.insert(0, '/app/environment/skills/evo-tess-exoplanet-detection/scripts')
from pipeline import process_tess_lc
period, duration, T0, depth, snr, SDE = process_tess_lc(filename)
