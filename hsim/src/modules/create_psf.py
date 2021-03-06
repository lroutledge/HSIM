'''
Module to create PSF from PSD
'''
import os
import logging

import numpy as np
from astropy.io import fits
from scipy.interpolate import interp2d
from astropy.convolution import Gaussian2DKernel

try:
	from ..config import *
except:
	from config import *

from misc_utils import path_setup
from rebin import *

psf_path = path_setup('../../' + config_data["data_dir"] + 'PSF/')


# Thierry FUSCO 18/12/17 17:42
# SIMUL_PSF_DataPackage.zip
#
#; $Id: eclat.pro,v 1.2 2002-10-25 11:26:32+02 conan Exp $
def eclat(imag, inverse = False):
	if inverse:
		sens = 1
	else:
		sens = -1
		
	sszz = imag.shape
	
	gami = np.roll(imag, sens*sszz[0]/2, axis=0)
	gami = np.roll(gami, sens*sszz[1]/2, axis=1)
	
	return gami


#Programme pour prendre en compte la multi-analyse les geometries
#d'etoiles et la postion de la galaxie
def psd_to_psf(psd, pup, D, phase_static = None, samp = None, fov = None, lamb = 2.2*1.e-6, jitter=0.):
	#;FUNCTION psd_to_psf, dsp, pup, local_L, osamp
	#;; computation of a PSF from a residual phase PSD and a pupil shape 
	#;;PSD: 2D array with PSD values (in nm2 per freq at the PSF wavelength)  
	#;;pup: 2D array representing the pupill 
	#;;Samp: final PSF sampling (number of pixel in the diffraction). Min = 2 ! 
	#;;FoV  : PSF FoV (in arcsec) 
	#;;lambda : PSF wavelength in m 
	#;;D = pupil diameter  
	#;;phase_static in nm 
	#;-
	
	dim       = psd.shape[0]
	npup      = pup.shape[0]
	
	sampnum   = float(dim)/npup   #;numerical sampling related to PSD vs pup dimension 
	L         = D*sampnum #;Physical size of the PSD
	
	if dim < 2*npup:
		raise HSIMError("the PSD horizon must at least two time larger than the pupil diameter")
	

	convnm = (2*np.pi/(lamb*1e9)) # nm to rad 

	#;; from PSD to structure function 
	Bg        = np.fft.fft2(psd*convnm**2)/L**2
	##;;creation of the structure function 
	Dphi      = np.real(2*(Bg[0, 0]-Bg))
	Dphi      = eclat(Dphi)

	if samp is not None:
		sampin = samp
	else:
		sampin = sampnum
	

	if float(sampin) <= sampnum:
		dimnum   =  float(int(dim*(sampin/sampnum)/2)*2) #; even dimension of the num psd
		sampout =  dimnum/npup                  #;real sampling
		Dphi2     = Dphi[int(dim/2-sampout*npup/2):int(dim/2+sampout*npup/2),int(dim/2-sampout*npup/2):int(dim/2+sampout*npup/2)]
		#print 'input sampling = ', str(sampin) , ' ---  output sampling = ', str(sampout),' --- max num sampling = ', str(sampnum)
	else:
		dimnum   =  float(int(dim*(sampin/sampnum)/2)*2) #; even dimension of the num psd
		sampout =  dimnum/npup
		Dphi2 = np.zeros((int(dimnum), int(dimnum)))+(Dphi[0,0]+Dphi[int(dim)-1, int(dim)-1]+Dphi[0, int(dim)-1]+Dphi[int(dim-1), 0])/4.
		Dphi2[int(dimnum/2-dim/2):int(dimnum/2+dim/2),int(dimnum/2-dim/2):int(dimnum/2+dim/2)]     = Dphi
		#print 'WARNING : Samplig > Dim DSP / Dim pup => extrapolation !!! We rceommmend to increase the PSD size'
		#print 'input sampling = ', str(sampin) , ' ---  output sampling = ', str(sampout),' --- max num sampling = ', str(sampnum)

	
	#;increasing the FoV PSF means oversampling the pupil 
	FoVnum    =  1./2.*(lamb/(sampnum*D))*dim/(4.85*1.e-6)
	if fov is None:
		fov = FoVnum
	
	overFoV = fov/FoVnum

	if overFoV != 1:
		raise HSIMError("overFoV != 1 not fully tested")
		dimover = float(int(dimnum*overFoV/2)*2)
		npupover =  float(int(npup*overFoV/2)*2)
		xxover  = np.arange(dimover)/dimover*dimnum
		xxpupover  = np.arange(npupover)/npupover*npup
		
		fDphi2 = interp2d(np.arange(Dphi2.shape[0]), np.arange(Dphi2.shape[0]), Dphi2, kind='cubic')
		Dphi2 = fDphi2(xxover, xxover)
		Dphi2[Dphi2 < 0] = 0.
		
		fpup = interp2d(np.arange(pup.shape[0]), np.arange(pup.shape[0]), pup, kind='cubic')
		pupover = fpup(xxpupover, xxpupover)
		pupover[pupover < 0] = 0.
	else:
		dimover = dimnum
		npupover = npup
		pupover = pup
	
	#print "dimover = ", dimover
	
	if phase_static is not None:
		npups    = phase_static.shape[0]
		if npups != npup:
			raise HSIMError("pup and static phase must have the same number of pixels")

		if overFoV != 1:
			fphase_static = interp2d(np.arange(phase_static.shape[0]), np.arange(phase_static.shape[0]), phase_static, kind='cubic')
			phase_static_o = fphase_static(xxpupover, xxpupover)
			#phase_static_o[phase_static_o < 0] = 0.
			
		else:
			phase_static_o = phase_static

	#print 'input FoV = ', str(fov) , ' ---  output FoV = ', str(FoVnum*float(dimover)/dimnum), ' ---  Num FoV = ', str(FoVnum)

	#if fov > 2*FoVnum:
		#print 'Warning : Potential alisiang issue .. I recommend to create initial PSD and pupil with a larger numbert of pixel' 


	##;creation of a diff limited OTF (pupil autocorrelation)
	tab = np.zeros((int(dimover), int(dimover)), dtype=np.complex)
	if phase_static is None:
		tab[0:pupover.shape[0], 0:pupover.shape[1]] = pupover
	else:
		tab[0:pupover.shape[0], 0:pupover.shape[1]] = pupover*np.exp(1j*phase_static_o*2*np.pi/lamb)
	

	dlFTO     = np.real(np.fft.ifft2(np.abs(np.fft.fft2(tab))**2))
	dlFTO     = eclat(np.abs(dlFTO)/np.sum(pup))
	
	##;creation of AO OTF 
	aoFTO     = np.exp(-Dphi2/2.)
	
	##;;Computation of final OTF 
	sysFTO = aoFTO*dlFTO
	sysFTO = eclat(sysFTO)

	## add Gaussian jitter
	if jitter > 0:
		sigma = 1./(2.*np.pi*jitter)*sysFTO.shape[0]
		
		Gauss2D = lambda x, y: 1./(2.*np.pi*sigma**2)*np.exp(-(x**2 + y**2)/(2.*sigma**2))
		xgrid = np.linspace(1, sysFTO.shape[0], sysFTO.shape[0]) - sysFTO.shape[0]*0.5 - 0.5
		ygrid = np.linspace(1, sysFTO.shape[1], sysFTO.shape[1]) - sysFTO.shape[1]*0.5 - 0.5
		xx, yy = np.meshgrid(xgrid, ygrid)
		kernel = eclat(Gauss2D(xx, yy))
		sysFTO = sysFTO*kernel

	
	##;;Computation of final PSF
	sysPSF = np.real(eclat((np.fft.fft2(sysFTO))))
	sysPSF = sysPSF/np.sum(sysPSF) #normalisation to 1 

	return sysPSF

psfscale = None
fov = None
AO_mode = None

# AO variables
pup = None
stats = None
psd = None
xgrid_out = None
ygrid_out = None
jitter = None
diameter = None

# no AO variables
seeing = None
air_mass = None


def define_psf(_air_mass, _seeing, _jitter, D, _fov, _psfscale, _aoMode):
	'''
	Define parameters used for the PSF generation
	Inputs:
		air_mass: Air mass of the observation
		seeing: Atmospheric seeing FWHM [arcsec]
		jitter: Residual telescope jitter [mas]
		D: telescope diameter [m]
		fov: number of pixels of the PSF
		psfscale: pixel size for the PSF [mas]
		aoMode: LTAO/SCAO/NOAO
	Outputs:
		None
	'''
	global pup, stats, psd, xgrid_out, ygrid_out, jitter, psfscale, fov, diameter, AO_mode
	global seeing, air_mass
	
	AO_mode = _aoMode
	
	fov = _fov
	psfscale = _psfscale
	xgrid_out = (np.linspace(0, fov-1, fov) - fov*0.5)*psfscale
	ygrid_out = (np.linspace(0, fov-1, fov) - fov*0.5)*psfscale

	seeing = _seeing
	air_mass = _air_mass
	
	if AO_mode in ["LTAO", "SCAO"]:
		jitter = _jitter
		diameter = D
		logging.info("define AO PSF - " + AO_mode)
		if os.path.isfile(os.path.join(psf_path,"ELT_pup.fits")):
			# Check that we have the actual files and not the git LFS links
			if os.path.getsize(os.path.join(psf_path,"ELT_pup.fits")) < 1024:
				raise HSIMError("The sim_data/PSF/*fits files are git LFS links. These FITS files are needed to run HSIM.")
			
			
			# PSD cubes
			pup = fits.getdata(os.path.join(psf_path,"ELT_pup.fits"))
			stats = fits.getdata(os.path.join(psf_path, "ELT_statics.fits"))
			
			# Select PSD based on air_mass and seeing
			try:
				index_airmass = config_data["PSD_cube"]["air_masses"].index(air_mass)
			except:
				raise HSIMError(str(air_mass) + ' is not a valid air mass. Valid options are: ' + ", ".join(map(str, sorted(config_data["PSD_cube"]["air_masses"]))))
			
			try:
				index_seeing = config_data["PSD_cube"]["seeings"].index(seeing)
			except:
				raise HSIMError(str(seeing) + ' is not a valid seeing. Valid options are: ' + ", ".join(map(str, sorted(config_data["PSD_cube"]["seeings"]))))
			
			
			logging.info("Using PSD file: " + config_data["PSD_file"][AO_mode])
			
			psd_cube = fits.getdata(os.path.join(psf_path, config_data["PSD_file"][AO_mode]))
			psd = psd_cube[index_airmass, index_seeing,:,:]
			psd = eclat(psd)

		else:
			#Test PSF
			logging.warning("Using test PSD files")
			pup = fits.getdata(os.path.join(psf_path,"demo_pup.fits"))
			stats = fits.getdata(os.path.join(psf_path, "demo_static_phase.fits"))	
			psd = fits.getdata(os.path.join(psf_path, "PSD_HARMONI_test_D=37_L=148_6LGS_LGSFOV=60arcmin_median_Cn2_Zenith=30.fits"))
	
	else: # no AO Gaussian 
		logging.info("define noAO Gaussian PSF")
		
	
	return


def create_psf(lamb, Airy=False):
	'''
	Returns a cube with the PSF for the given lambs generated from the PSD
	Inputs:
		lamb: lambda  [um]
		Airy: calculate Airy pattern
	Outputs:
		cube: PSF
	'''
		
	global pup, stats, psd, xgrid_out, ygrid_out, jitter, psfscale, fov, diameter, AO_mode
	global seeing, air_mass

	if AO_mode in ["LTAO", "SCAO"]:
		# size of a pixel returned by psd_to_psf
		pix_psf = lamb*1e-6/(2.*diameter)*1/(4.85*1e-9) # mas
		
		if not Airy:
			psf = psd_to_psf(psd, pup, diameter, phase_static = stats, lamb=lamb*1e-6, samp=2., jitter=jitter/pix_psf)
		else:
			psf = psd_to_psf(psd*0., pup, diameter, phase_static = None, lamb=lamb*1e-6, samp=2., jitter=0.)
		
		area_scale = (pix_psf/psfscale)**2
		#print area_scale
		if area_scale > 1:
			# interpolate PSF
			xgrid_in = (np.linspace(0, psf.shape[0]-1, psf.shape[0]) - psf.shape[0]*0.5)*pix_psf
			ygrid_in = (np.linspace(0, psf.shape[1]-1, psf.shape[1]) - psf.shape[1]*0.5)*pix_psf
			image = interp2d(xgrid_in, ygrid_in, psf, kind='cubic', fill_value=0.)
			finalpsf = image(xgrid_out, ygrid_out)/area_scale
		else:
			# rebin PSF
			side = int(psf.shape[0]*pix_psf/psfscale/2)*2
			rebin_psf = frebin2d(psf, (side, side))/area_scale
			center = side/2
			finalpsf = rebin_psf[center-fov/2:center+fov/2, center-fov/2:center+fov/2]
			
		finalpsf[finalpsf < 0] = 0.
		#fits.writeto("psf_orig.fits", psf, overwrite=True)
		#print np.sum(finalpsf)
		return finalpsf
	
	else: # noAO Gaussian PSF
		# Beckers 1993 ARAA
		zenit_angle = np.arccos(1./air_mass)
		seeing_lambda = seeing/((lamb/0.5)**(1./5)*np.cos(zenit_angle)**(3./5))*1000. # mas
		sigma = seeing_lambda/2.35482
		
		Gauss2D = lambda x, y: 1./(2.*np.pi*sigma**2)*np.exp(-(x**2 + y**2)/(2.*sigma**2))*psfscale**2
		
		xx, yy = np.meshgrid(xgrid_out, ygrid_out)
		finalpsf = Gauss2D(xx, yy)
		#fits.writeto("psf.fits", Gauss2D(xx, yy), overwrite=True)
		return finalpsf
	

