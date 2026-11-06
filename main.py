"""
Run this script to start model. The run_model method can take input and collection names. If wish to type your own,
leave the parameters blank and the method will ask for input.
"""

import Simulation as sm

#sm.run_model(input_file='IDETC_ATL2_2024', collection_name='IDETC_ATL_2024', overwrite_runs=True)

# sm.run_model(input_file='Ford_ATL_Demo', collection_name='Ford_ATL_Demo3', overwrite_runs=True)

# sm.run_model(input_file='IDETC_PHX_2024', collection_name='IDETC_PHX_2024', overwrite_runs=False)
# sm.run_model(input_file='IDETC_PHX_2024', collection_name='IDETC_PHX_2024', overwrite_runs=True,
#              only_run={'Load Amount': [6000, 15000]})

a=1
# sm.run_model(input_file='IDETC_LA_2024', collection_name='IDETC_LA_2024', overwrite_runs=True,
#              only_run={'Net Meter Type': ['nem3', 'one-to-one']})

# sm.run_model(input_file='IDETC_POR_V2H_2024', collection_name='IDETC_POR_V2H_2024', overwrite_runs=True)
# sm.run_model(input_file='IDETC_LA_V2H2_2024', collection_name='IDETC_LA_V2H2_2024', overwrite_runs=True)

# sm.run_model(input_file='IDETC_POR2_2024', collection_name='IDETC_POR2_2024', overwrite_runs=True)

# sm.run_model(input_file='test_LA', overwrite_runs=True)
# sm.run_model(input_file='TestCollection/F1_CA_90011_PST_Los Angeles_CA', collection_name='TestCollection/F1_CA_90011_PST_Los Angeles_CA')

# sm.run_model(input_file='Ford_ATL_Demo', collection_name='update_debug', overwrite_runs=True)

# run_collection now runs the input files in this collection across worker processes (see parallel/max_workers
# params). The __main__ guard below is required by multiprocessing on Windows -- without it, each worker
# process would re-import and re-execute this whole script, causing runaway recursive process spawning.
if __name__ == '__main__':
    # sm.run_collection(collection_path='Top20_commutes_set', overwrite_runs=False)
    #liams tests
    # sm.run_model(input_file = 'QuickTest_Single', collection_name = 'QuickTest_Single', overwrite_runs=True)
    
    #consolidated
    # sm.run_model(input_file = 'QuickTest_Single', collection_name = 'QuickTest_Single', save_pickles=True, consolidate_results=True, overwrite_runs=True)
    
    #full
    # sm.run_model(input_file='QuickTest_Single', collection_name='QuickTest_Single',
            #  full_results=True, consolidate_results=True, overwrite_runs=True)


    # Liam Tests PV differences
#     sm.run_model(input_file = 'QuickTest_SingleLW', collection_name = 'QuickTest_SingleLW', overwrite_runs=True)

        #Liam tests running with all load downloaded
    # sm.run_model(input_file = 'F26_CT_6010_EST_Hartford_CT', collection_name = 'F26_CT_6010_EST_Hartford_CT', overwrite_runs=True)


    #Running weird mix of cities
    sm.run_model(input_file = 'Mutant_Test_LW', collection_name = 'Mutant_Test_LW', overwrite_runs=True)


