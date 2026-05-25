import numpy as np
from astropy.timeseries import BoxLeastSquares
import astropy.units as u

def load_lightcurve(path):
    data = np.loadtxt(path, comments="#")
    time = data[:,0]
    flux = data[:,1]
    flag = data[:,2]
    flux_err = data[:,3]
    return time, flux, flag, flux_err

def filter_outliers(time, flux, flux_err, sigma=3):
    median = np.median(flux)
    std = np.std(flux)
    good = np.abs(flux - median) < sigma * std
    return time[good], flux[good], flux_err[good]

def remove_stellar_variability(time, flux, flux_err, window_length=101):
    from scipy.signal import savgol_filter
    window_length = min(window_length, len(flux) - 1)
    if window_length % 2 == 0:
        window_length -= 1
    if window_length < 3:
        return flux
    trend = savgol_filter(flux, window_length, 2)
    return flux - trend + 1.0

def find_transit_period(time, flux, flux_err):
    model = BoxLeastSquares(time * u.day, flux, dy=flux_err)
    duration = 0.05 * u.day
    periodogram = model.autopower(duration)
    best_idx = np.argmax(periodogram.power)
    return periodogram.period[best_idx].value
