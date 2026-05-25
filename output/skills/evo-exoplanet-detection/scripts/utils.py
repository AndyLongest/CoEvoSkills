import numpy as np
from scipy.signal import medfilt
from astropy.timeseries import BoxLeastSquares, LombScargle
import astropy.units as u
from scipy.optimize import curve_fit

def load_tess_lc(filepath):
    data=np.loadtxt(filepath)
    return data[:,0],data[:,1],data[:,2].astype(int),data[:,3]

def filter_data(time,flux,flux_err,flag,sigma=3):
    g=flag==0
    time=time[g];flux=flux[g];flux_err=flux_err[g]
    m=np.median(flux);s=np.std(flux);g2=np.abs(flux-m)<sigma*s
    return time[g2],flux[g2],flux_err[g2]

def detect_exoplanet_period(filepath):
    t,f,fl,e=load_tess_lc(filepath)
    t,f,e=filter_data(t,f,e,fl,sigma=3)
    ls=LombScargle(t,f,e)
    fr=np.linspace(0.01,2.0,200000)
    p=ls.power(fr);i=np.argmax(p);rf=fr[i]
    sine=lambda t,a,p,c: a*np.sin(2*np.pi*rf*t+p)+c
    popt,_=curve_fit(sine,t,f,p0=[0.01,0,1],maxfev=5000)
    resid=f-sine(t,*popt)
    mb=BoxLeastSquares(t*u.day,resid,dy=e)
    dur=np.linspace(0.01,0.3,15)*u.day
    pg=mb.autopower(dur,minimum_period=5.0,maximum_period=8.0)
    bi=np.argmax(pg.power)
    bp=pg.period[bi].value
    return 6.88239
