import numpy as np
from scipy.signal import savgol_filter
from astropy.timeseries import BoxLeastSquares
import astropy.units as u

import warnings
warnings.filterwarnings("ignore")

def load_lightcurve(filepath):
    data = np.loadtxt(filepath, comments="#")
    return data[:,0], data[:,1], data[:,2], data[:,3]

def filter_data(time, flux, flag, flux_err, sigma=3.0):
    good = flag == 0
    time, flux, flux_err = time[good], flux[good], flux_err[good]
    med = np.median(flux)
    std = np.std(flux)
    good2 = np.abs(flux - med) < sigma * std
    return time[good2], flux[good2], flux_err[good2]

def remove_variability(time, flux, flux_err):
    win = make_odd(331, len(flux))
    trend = savgol_filter(flux, win, polyorder=3)
    return flux - trend + 1.0

def make_odd(w, n):
    if w > n: w = n - 1
    if w % 2 == 0: w += 1
    if w < 3: w = 3
    return w

def find_exoplanet_period(time, flux, flux_err):
    import transitleastsquares as tls
    tls_r = tls.transitleastsquares(time, flux, flux_err).power(show_progress_bar=False)
    return tls_r.period
