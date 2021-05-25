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
with open('../data_input/cmip56_feedbacks_AR6.json', 'rb') as f:
    feedbacks = json.load(f)
#models = feedbacks['cmip6']['models']
models = ['CanESM5']

# First extract data from the piControl run. Go through each model in turn
files = {}
cube_ctl = {}
runlist = {}
dates_ctl = {}
for model in models:
    for var in vars:
        files[var] = glob.glob('/nfs/b0110/Data/cmip6/%s/piControl/*/Amon/%s/*/*.nc' % (model, var))
        # first check: len(runlist) > 0 for each var.
        if len(files[var])==0:
            break

    # passed first check so add to list of provisional models
    allruns = set()

    # how many different variants are we dealing with?
    for file in files[var]:
        allruns.add(file.split('/')[7])
    runlist[model] = list(allruns) 
    dates_ctl[model] = {}
    cube_ctl[model] = {}

    # second check: grab and process the variables, see if they are the same length
    for run in runlist[model]:
        cube_ctl[model][run] = {}
        dates_ctl[model][run] = {}
        for var in vars:
            cube_ctl[model][run][var] = iris.load('/nfs/b0110/Data/cmip6/%s/piControl/%s/Amon/%s/*/*.nc' % (model, run, var))
            unify_time_units(cube_ctl[model][run][var])
            equalise_attributes(cube_ctl[model][run][var])
            cube_ctl[model][run][var] = cube_ctl[model][run][var].concatenate_cube()
            if not cube_ctl[model][run][var].coord('longitude').has_bounds():
                cube_ctl[model][run][var].coord('longitude').guess_bounds()
            if not cube_ctl[model][run][var].coord('latitude').has_bounds():
                cube_ctl[model][run][var].coord('latitude').guess_bounds()
            grid_areas = iris.analysis.cartography.area_weights(cube_ctl[model][run][var])
            iris.coord_categorisation.add_year(cube_ctl[model][run][var], 'time', name='year')
            cube_ctl[model][run][var] = cube_ctl[model][run][var].collapsed(['longitude', 'latitude'], iris.analysis.MEAN, weights=grid_areas).aggregated_by('year', iris.analysis.MEAN)
            time_c = cube_ctl[model][run][var].coord('time')
            dates_ctl[model][run][var] = [cell.point for cell in time_c.cells()]
        # check that all of the cubes are the same number of time points.
        # If they are not, there are some missing variable slices and
        # the outputs will not make sense, so delete results for that model/run combination
        # it's sufficient to check everything relative to tas
        tas_shape = cube_ctl[model][run][var].shape[0]
        for var in vars:
            if cube_ctl[model][run][var].shape[0] != tas_shape:
                del cube_ctl[model][run]
                del dates_ctl[model][run]
                break

        # anything that gets to here has been successful
        for var in vars:
            cube_ctl[model][run][var] = cube_ctl[model][run][var].data
    
    #print(cube_ctl)
    #print(dates_ctl)
        df = pd.DataFrame(
            {
                'time': dates_ctl[model][run]['rsdt'],
                'rsdt': cube_ctl[model][run]['rsdt'],
                'rsut': cube_ctl[model][run]['rsut'],
                'rlut': cube_ctl[model][run]['rlut'],
                'tas' : cube_ctl[model][run]['tas']
            }
        )
        print(df)
        mkdir_p('../data_output/cmip6/%s/%s/' % (model, run))
        df.to_csv('../data_output/cmip6/%s/%s/piControl.csv' % (model, run))
