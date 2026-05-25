---
name: evo-transit-detection
---

---
name: evo-transit-detection
description: Detects exoplanet transit periods from TESS lightcurve data by filtering quality flags, removing outliers, flattening to remove stellar variability, and searching with Transit Least Squares. Use when asked to find exoplanet period from a lightcurve file containing stellar activity oscillations and a hidden transit signal.
---

# Evo Transit Detection

Workflow for detecting an exoplanet transit period from a TESS lightcurve.

## Workflow

1. **Load data**: Use `load_data(filepath)` from `scripts/utils.py`. Reads the lightcurve file with columns: time (MJD), flux, quality flag, flux error.
2. **Filter quality**: Keep only rows where quality flag == 0 using `filter_good_data(time, flux, flux_err, flag)`.
3. **Remove outliers**: Apply sigma-clipping (default sigma=3) with `sigma_clip(time, flux, flux_err, sigma=3)`.
4. **Remove stellar variability**: Flatten the lightcurve using a Savitzy-Golay filter via lightkurve's `flatten()` method. Use `flatten_lightcurve(time, flux, flux_err, window_length=None)`. If `window_length` is None, it is automatically determined as the nearest odd number to `len(time)*0.3`, but not less than 11.
5. **Search for transits**: Use Transit Least Squares (TLS) with `run_tls(time, flux, flux_err)` to find the best period. TLS is more sensitive than BLS for transit-shaped signals.
6. **Write result**: Use `write_period(period, filepath)` to write the period rounded to 5 decimal places.

## Imports

To use the skill in a main script:
```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-transit-detection/scripts')
from utils import load_data, filter_good_data, sigma_clip, flatten_lightcurve, run_tls, write_period

# Execute pipeline
time, flux, flux_err, flag = load_data('/root/data/tess_lc.txt')
t, f, fe = filter_good_data(time, flux, flux_err, flag)
t, f, fe = sigma_clip(t, f, fe, sigma=3)
t_flat, f_flat, fe_flat = flatten_lightcurve(t, f, fe)
period = run_tls(t_flat, f_flat, fe_flat)
write_period(period, '/root/period.txt')
```

## Notes

- Always include flux_err in TLS for best results.
- The flatten window_length is automatically chosen; adjust if needed.
- TLS may return multiple candidates; the best period is the one with highest SDE (Signal Detection Efficiency).
