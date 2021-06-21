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

# ta https://stackoverflow.com/questions/11942364/typeerror-integer-is-not-json-serializable-when-serializing-json-in-python
def convert(obj):
    if isinstance(obj, np.int64): return int(obj)

# Energy budget variables
vars = ['rsdt', 'rlut', 'rsut', 'tas']

# We only care about models where Mark has crunched the data
with open('../data_input/cmip56_feedbacks_AR6.json', 'rb') as f:
    feedbacks = json.load(f)
models = feedbacks['cmip6']['models']

successful = [
    'ACCESS-CM2',
    'ACCESS-ESM1-5',
    'CanESM5',
    'CESM2',
    'CNRM-CM6-1',
    'FGOALS-g3',
    'GISS-E2-1-G',
    'HadGEM3-GC31-LL',
    'IPSL-CM6A-LR',
    'MIROC6',
    'MRI-ESM2-0',
    'NorESM2-LM',
]

novarsfound = [
    'BCC-CSM2-MR',
]

# Extract data from the historical run. Go through each model in turn
files = {}
runlist = {}
for model in models:
    if model in successful + novarsfound:
        continue
    print(model)
    for var in vars:
        files[var] = glob.glob('/nfs/b0110/Data/cmip6/%s/hist-nat/*/Amon/%s/*/*.nc' % (model, var))

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
        cube_hist = {}
        nvars = 0
        for var in vars:
            # check any files exist before we try and open them else iris throws error
            filelist = glob.glob('/nfs/b0110/Data/cmip6/%s/hist-nat/%s/Amon/%s/*/*.nc' % (model, run, var))
            if len(filelist) == 0:
                print(' --- no %s variables found for %s, %s' % (var, model, run))
                break
            nvars = nvars + 1
            cube_hist[var] = iris.load(filelist)
            unify_time_units(cube_hist[var])
            equalise_attributes(cube_hist[var])
            # A problem first identified in AWI but good to turn off in all models
            for cube in cube_hist[var]:
                cube.coord('latitude').long_name='latitude'
                cube.coord('time').attributes=None  # only causes headaches
            cube_hist[var] = cube_hist[var].concatenate_cube()
            if not cube_hist[var].coord('longitude').has_bounds():
                cube_hist[var].coord('longitude').guess_bounds()
            if not cube_hist[var].coord('latitude').has_bounds():
                cube_hist[var].coord('latitude').guess_bounds()
            grid_areas = iris.analysis.cartography.area_weights(cube_hist[var])
            iris.coord_categorisation.add_year(cube_hist[var], 'time', name='year')
            cube_hist[var] = cube_hist[var].collapsed(['longitude', 'latitude'], iris.analysis.MEAN, weights=grid_areas).aggregated_by('year', iris.analysis.MEAN)
            time_c = cube_hist[var].coord('time')
            dates_hist = [cell.point for cell in time_c.cells()]

        # don't bother comparing owt if we don't have four entries - move to next run or model
        if nvars < 4:
            continue

        # check that all of the cubes are the same number of time points.
        # If they are not, there are some missing variable slices and
        # the outputs will not make sense, so delete results for that model/run combination
        # it's sufficient to check everything relative to tas
        tas_shape = cube_hist[var].shape[0]
        for var in vars:
            if cube_hist[var].shape[0] != tas_shape:
                print(' --- length of %s did not match tas for %s, %s' % (var, model, run))
                break

        # The one thing we do need from the historical is the branch time from the piControl.
        # this is not always consistently reported, so basically dump all of the attributes and
        # try and make sense of it manually in the data analysis stage :)
        global_attributes = cube_hist['tas'].attributes

        # anything that gets to here has been successful so process the data
        for var in vars:
            cube_hist[var] = cube_hist[var].data
    
        df = pd.DataFrame(
            {
                'time': dates_hist,
                'rsdt': cube_hist['rsdt'],
                'rsut': cube_hist['rsut'],
                'rlut': cube_hist['rlut'],
                'tas' : cube_hist['tas']
            }
        )

        mkdir_p('../data_output/cmip6/%s/%s/' % (model, run))
        df.to_csv('../data_output/cmip6/%s/%s/hist-nat.csv' % (model, run), index=False)
        with open('../data_output/cmip6/%s/%s/meta_hist-nat.json' % (model, run), 'w') as f:
            json.dump(global_attributes, f, default=convert)

        print(' --- %s, %s was successful' % (model, run))
