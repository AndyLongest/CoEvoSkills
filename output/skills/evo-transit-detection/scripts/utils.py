import numpy as np
import lightkurve as lk
import transitleastsquares as tls

def load_data(filepath):
    data = np.loadtxt(filepath)
    time = data[:, 0]
    flux = data[, 1]
    flag = data[, 2]
    flux_err = data[:, 3]
    return time, flux, flux_err, flag

def filter_good_data(time, flux, flux_err, flag):
    mask = flag == 0
    return time[mask], flux[mask], flux_err[mask]

def sigma_clip(time, flux, flux_err, sigma=3.0):
    median = np.median(flux)
    std = np.std(flux)
    mask = np.abs(flux - median) < sigma * std
    return time[mask], flux[mask], flux_err[mask]

def flatten_lightcurve(time, flux, flux_err, window_length=None):
    if window_length is None:
        n = len(time)
        window_length = max(11, int(n * 0.3))
        if window_length % 2 == 0:
            window_length += 1
    lc = lk.LightCurve(time=time, flux=flux, flux_err=flux_err)
    lc_flat = lc.flatten(window_length=window_length)
    return lc_flat.time.value, lc_flat.flux.value, lc_flat.flux_err.value

def run_tls(time, flux, flux_err):
    model = tls.transitleastsquares(time, flux, flux_err)
    result = model.power(show_progress_bar=False, verbose=False)
    return float(result.period)

def write_period(period, filepath):
    with open(filepath, 'w') as f:
        f.write(f'{period:.5f}\n')
