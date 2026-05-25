import numpy as np
import lightkurve as lk
import transitleastsquares as tls
from scipy import signal

def load_tess_lc(filename):
    time,flux,flag,flux_err=[],[],[],[]
    with open(filename) as fp:
        for line in fp:
            line=line.strip()
            if not line or line.startswith('#'):
                continue
            parts=line.split()
            if len(parts)<4:
                continue
            time.append(float(parts[0]))
            flux.append(float(parts[1]))
            flag.append(int(parts[2]))
            flux_err.append(float(parts[3]))
    return np.array(time),np.array(flux),np.array(flag),np.array(flux_err)

def filter_good_data(time,flux,flag,flux_err):
    good=flag==0
    return time[good],flux[good],flux_err[good]

def sigma_clip_outliers(time,flux,flux_err,sigma=3):
    median=np.median(flux)
    std=np.std(flux)
    good=np.abs(flux-median)<sigma*std
    return time[good],flux[good],flux_err[good]

def flatten_lc(time,flux,flux_err,window_length=21):
    lc=lk.LightCurve(time=time,flux=flux,flux_err=flux_err)
    lc_flat=lc.flatten(window_length=window_length)
    return lc_flat.time.value,lc_flat.flux.value,lc_flat.flux_err.value

def period_search_tls(time,flux,flux_err):
    model=tls.transitleastsquares(time,flux,flux_err)
    result=model.power(show_progress_bar=False,verbose=False)
    return result.period,result.duration,result.T0,result.depth,result.snr,result.SDE

def process_tess_lc(filename,window_length=21,sigma=3):
    time,flux,flag,flux_err=load_tess_lc(filename)
    time,flux,flux_err=filter_good_data(time,flux,flag,flux_err)
    time,flux,flux_err=sigma_clip_outliers(time,flux,flux_err,sigma=sigma)
    time,flux,flux_err=flatten_lc(time,flux,flux_err,window_length=window_length)
    period,duration,T0,depth,snr,SDE=period_search_tls(time,flux,flux_err)
    return period,duration,T0,depth,snr,SDE
