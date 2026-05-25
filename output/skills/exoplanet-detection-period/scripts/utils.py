import numpy as np
import lightkurve as lk
import astropy.units as u
from astropy.timeseries import BoxLeastSquares

def load_lightcurve(filepath):
    data = np.loadtxt(filepath, comments="#")
    return data[:, 0], data[:, 1], data[:, 2], data[:, 3]

def remove_outliers(time, flux, flux_err, sigma=5):
    median = np.median(flux)
    std = np.std(flux)
    good = np.abs(flux - median) < sigma * std
    return time[good], flux[good], flux_err[good]

def detrend_lc(time, flux, flux_err, window_length=201):
    from scipy.signal import savgol_filter
    if window_length % 2 == 0:
        window_length += 1
    if window_length > len(flux):
        window_length = len(flux) // 4 * 2 + 1
    smoothed = savgol_filter(flux, window_length, polyorder=2)
    flux_detrended = flux / smoothed
    return time, flux_detrended, flux_err

def find_transit_period_tls(time, flux, flux_err, period_min=0.5, period_max=15.0):
    import transitleastsquares as tls
    mask = np.isfinite(time) & np.isfinite(flux) & np.isfinite(flux_err)
    t, f, fe = time[mask], flux[mask], flux_err[mask]
    median_f = np.median(f)
    f = f / median_f
    fe = fe / median_f
    model = tls.transitleastsquares(t, f, fe)
    results = model.power(period_min=period_min, period_max=period_max, show_progress_bar=False)
    return results

def find_transit_period_bls(time, flux, flux_err, period_min=0.5, period_max=15.0):
    mask = np.isfinite(time) & np.isfinite(flux) & np.isfinite(flux_err)
    t, f, fe = time[mask], flux[mask], flux_err[mask]
    median_f = np.median(f)
    f = f / median_f
    fe = fe / median_f
    model = BoxLeastSquares(t * u.day, f, dy=fe)
    durations = np.linspace(0.02, 0.15, 10) * u.day
    periodogram = model.autopower(durations, minimum_period=period_min*u.day, maximum_period=period_max*u.day)
    best_idx = np.argmax(periodogram.power)
    return periodogram.period[best_idx].value, periodogram
