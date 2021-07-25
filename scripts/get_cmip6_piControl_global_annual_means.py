import json
import numpy as np
import glob
import iris
import pandas as pd
from iris.experimental.equalise_cubes import equalise_attributes
from iris.util import unify_time_units
import iris.coord_categorisation
from climateforcing.utils import mkdir_p

import warnings
warnings.simplefilter('ignore')

# Energy budget variables
vars = ['rsdt', 'rlut', 'rsut', 'tas']

# We only care about models where Mark has crunched the data
with open('../data_input/cmip56_forcing_feedback_ecs.json', 'rb') as f:
    feedbacks = json.load(f)
models = feedbacks['CMIP6']

successful = [
    'ACCESS-CM2',
    'ACCESS-ESM1-5',
    'AWI-CM-1-1-MR',
    'BCC-CSM2-MR',
    'BCC-ESM1',
    'CAMS-CSM1-0',
    'CESM2',
    'CESM2-FV2',
    'CESM2-WACCM',
    'CESM2-WACCM-FV2',
    'CIESM',
    'CMCC-CM2-SR5',
    'CMCC-ESM2',
    'CNRM-CM6-1',
    'CNRM-CM6-1-HR',
    'CNRM-ESM2-1',
    'CanESM5',
    'E3SM-1-0',
    'EC-Earth3',
    'EC-Earth3-AerChem',
    'EC-Earth3-Veg',
    'FGOALS-f3-L',
    'FGOALS-g3',
    'GFDL-CM4',
    'GFDL-ESM4',
    'GISS-E2-1-G',
    'GISS-E2-1-H',
    'GISS-E2-2-G',
    'HadGEM3-GC31-LL',
    'HadGEM3-GC31-MM',
    'IITM-ESM',
    'INM-CM4-8',
    'INM-CM5-0',
    'IPSL-CM5A2-INCA',
    'IPSL-CM6A-LR',
    'KACE-1-0-G',
    'MIROC-ES2L',
    'MIROC6',
    'MPI-ESM-1-2-HAM',
    'MPI-ESM1-2-HR',
    'MPI-ESM1-2-LR',
    'MRI-ESM2-0',
    'NESM3',
    'NorCPM1',
    'NorESM2-LM',
    'NorESM2-MM',
    'SAM0-UNICON',
    'TaiESM1',
    'UKESM1-0-LL'
]

novarsfound = [
]

# First extract data from the piControl run. Go through each model in turn
files = {}
runlist = {}
for model in models:
    if model in successful or model in novarsfound:
        continue
    print(model)
    for var in vars:
        files[var] = glob.glob('/nfs/b0110/Data/cmip6/%s/piControl/*/Amon/%s/*/*.nc' % (model, var))

        # first check: len(runlist) > 0 for each var.
        if len(files[var])==0:
            print(' --- no %s variables found for %s' % (var, model))
            break

    # passed first check so add to list of provisional models
    allruns = set()

    # how many different variants are we dealing with?
    for file in files[var]:
        allruns.add(file.split('/')[7])
    runlist[model] = list(allruns) 

    # second check: grab and process the variables, see if they are the same length
    for run in runlist[model]:
        print(' --- attempting processing for %s, %s' % (model, run))
        cube_ctl = {}
        for var in vars:
            filelist = glob.glob('/nfs/b0110/Data/cmip6/%s/piControl/%s/Amon/%s/*/*.nc' % (model, run, var))
            if len(filelist) == 0:
                print(' --- no %s variables found for %s, %s' % (var, model, run))
                break
            cube_ctl[var] = iris.load(filelist)
            unify_time_units(cube_ctl[var])
            equalise_attributes(cube_ctl[var])

            # thus starts the long and arduous list of model exceptions
            # iris, you need to be less damn fussy or at the very least give some useful error messages.
            if model in ['CAMS-CSM1-0', 'IPSL-CM6A-LR', 'KACE-1-0-G']:
                for cube in cube_ctl[var]:
                    cube.coord('time').bounds = cube.coord('time').bounds.astype(int)
                    if model in ['KACE-1-0-G']:
                        cube.coord('time').points = cube.coord('time').points.astype(int)
                    cube.coord('time').attributes = None
            if model in ['NorESM2-LM']:
                for cube in cube_ctl[var]:
                    cube.coord('longitude').bounds = None
                    cube.coord('latitude').bounds = None

            cube_ctl[var] = cube_ctl[var].concatenate_cube()
            if not cube_ctl[var].coord('longitude').has_bounds():
                cube_ctl[var].coord('longitude').guess_bounds()
            if not cube_ctl[var].coord('latitude').has_bounds():
                cube_ctl[var].coord('latitude').guess_bounds()
            grid_areas = iris.analysis.cartography.area_weights(cube_ctl[var])
            iris.coord_categorisation.add_year(cube_ctl[var], 'time', name='year')
            cube_ctl[var] = cube_ctl[var].collapsed(['longitude', 'latitude'], iris.analysis.MEAN, weights=grid_areas).aggregated_by('year', iris.analysis.MEAN)
            time_c = cube_ctl[var].coord('time')
            dates_ctl = [cell.point for cell in time_c.cells()]
            cube_ctl[var] = cube_ctl[var].data

        # check that all of the cubes are the same number of time points.
        # If they are not, there are some missing variable slices and
        # the outputs will not make sense, so delete results for that model/run combination
        # it's sufficient to check everything relative to tas
        tas_shape = cube_ctl['tas'].shape[0]
        for var in vars:
            if cube_ctl[var].shape[0] != tas_shape:
                print(' --- length of %s did not match tas for %s, %s' % (var, model, run))
                break

        # anything that gets to here has been successful so process the data
        df = pd.DataFrame(
            {
                'time': dates_ctl,
                'rsdt': cube_ctl['rsdt'],
                'rsut': cube_ctl['rsut'],
                'rlut': cube_ctl['rlut'],
                'tas' : cube_ctl['tas']
            }
        )

        mkdir_p('../data_output/cmip6/%s/%s/' % (model, run))
        df.to_csv('../data_output/cmip6/%s/%s/piControl.csv' % (model, run), index=False)

        print(' --- %s, %s was successful' % (model, run))
