import numpy as np
import lightkurve as lk
import warnings
warnings.filterwarnings("ignore")

def load_and_filter(filepath):
    data = np.loadtxt(filepath)
    time = data[:, 0]
    flux = data[:, 1]
    flag = data[:, 2]
    flux_err = data[:, 3]
    good = flag == 0
    time = time[good]
    flux = flux[good]
    flux_err = flux_err[good]
    median = np.median(flux)
    std = np.std(flux)
    good_sigma = np.abs(flux - median) < 3 * std
    time = time[good_sigma]
    flux = flux[good_sigma]
    flux_err = flux_err[good_sigma]
    return time, flux, flux_err

def remove_stellar_activity(time, flux, flux_err, window_length=None):
    lc = lk.LightCurve(time=time, flux=flux, flux_err=flux_err)
    if window_length is None:
        n_points = len(time)
        window_length = max(51, n_points // 4)
        if window_length % 2 == 0:
            window_length += 1
    lc_flat = lc.flatten(window_length=window_length)
    return lc_flat.time.value, lc_flat.flux.value, lc_flat.flux_err.value

def find_period_tls(time, flux, flux_err):
    from transitleastsquares import transitleastsquares
    model = transitleastsquares(time, flux, flux_err)
    results = model.power(show_progress_bar=False)
    best_period = results.period
    return best_period, results

def write_period(period, output_path="/root/period.txt"):
    with open(output_path, "w") as f:
        f.write(f"{period:.5f}" + chr(10))
    print(f"Period {period:.5f} written to {output_path}")