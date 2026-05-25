import numpy as np
from scipy.signal import savgol_filter
import transitleastsquares as tls

def load_and_filter_data(filename, sigma=4):
    data = np.loadtxt(filename)
    time = data[:, 0]
    flux = data[:, 1]
    flag = data[:, 2]
    flux_err = data[:, 3]
    good = flag == 0
    time = time[good]
    flux = flux[good]
    flux_err = flux_err[good]
    median = np.median(flux)
    mad = np.median(np.abs(flux - median))
    non_outlier = np.abs(flux - median) < sigma * mad
    return time[non_outlier], flux[non_outlier], flux_err[non_outlier]

def remove_stellar_variability(flux, window_length=51, polyorder=3):
    if window_length % 2 == 0:
        window_length += 1
    trend = savgol_filter(flux, window_length, polyorder)
    return flux / trend

def find_exoplanet_period(time, flux, flux_err):
    model = tls.transitleastsquares(time, flux, flux_err)
    results = model.power(show_progress_bar=False, verbose=False)
    return round(float(results.period), 5)
