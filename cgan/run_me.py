"""Ryu: main experiments script"""
import tensorflow as tf

# Options
opt = {}

# Network:
opt['method'] = 'cnn_simple'
opt['valid'] = False  # validation metric
opt['n_h1'] = 50
opt['n_h2'] = 2*opt['n_h1']
opt['n_h3'] = 10

# Training
opt['overwrite'] = False  # restart the training completely.
opt['continue'] = False  # set True if you want to continue training from the previous experiment
if opt['continue']: opt['overwrite'] = False

opt['optimizer'] = 'adam'
opt['dropout_rate'] = 0.0
opt['learning_rate'] = 1e-3
opt['L1_reg'] = 0.00
opt['L2_reg'] = 1e-5

opt['train_size'] = 17431 #72000  #17431 # 9000  # 100  # total number of patch pairs (train + valid set)
opt['n_epochs'] = 200
opt['batch_size'] = 12
opt['validation_fraction'] = 0.5
opt['patch_sampling_opt']='separate'  # by default, train and valid sets are separated.
opt['shuffle'] = True


# Data (new):
opt['background_value'] = 0  # background value in the images
#opt['train_subjects']=['117324', '904044']
opt['train_subjects'] = ['992774', '125525', '205119', '133928', # first 8 are the original Diverse  dataset
                         '570243', '448347', '654754', '153025']
                         # '101915', '106016', '120111', '122317', # original 8 training subjects
                         # '130316', '148335', '153025', '159340',
                         # '162733', '163129', '178950', '188347', # original 8 test subjects
                         # '189450', '199655', '211720', '280739',
                         # '106319', '117122', '133827', '140824', # random 8 subjects
                         # '158540', '196750', '205826', '366446']
                         # '351938', '390645', '545345', '586460',
                         # '705341', '749361', '765056', '951457']
opt['test_subjects'] = ['904044', '165840', '889579', '713239',
                        '899885', '117324', '214423', '857263']


# Data/task:
opt['cohort'] ='Diverse'
opt['no_subjects'] = len(opt['train_subjects'])
opt['b_value'] = 1000
opt['patchlib_idx'] = 1
opt['no_randomisation'] = 1
opt['shuffle_data'] = True
opt['chunks'] = True  # set True if you want to chunk the HDF5 file.

opt['subsampling_rate'] = 343
opt['upsampling_rate'] = 2
opt['input_radius'] = 5
opt['receptive_field_radius'] = 2
output_radius = ((2*opt['input_radius']-2*opt['receptive_field_radius']+1)//2)
opt['output_radius'] = output_radius
opt['no_channels'] = 6
opt['transform_opt'] = 'standard'  #'standard'  # preprocessing of input/output variables

# # Local dir:
# opt['data_dir'] = '/Users/ryutarotanno/tmp/iqt_DL/auro/TrainingData/'
# opt['save_dir'] = '/Users/ryutarotanno/tmp/iqt_DL/auro/TrainingData/'
# opt['log_dir'] = '/Users/ryutarotanno/tmp/iqt_DL/auro/log/'
# opt['save_train_dir'] = '/Users/ryutarotanno/tmp/iqt_DL/auro/TrainingData/'
#
# opt['gt_dir'] = '/Users/ryutarotanno/DeepLearning/nsampler/data/HCP/'  # ground truth dir
# opt['subpath'] = ''
#
# opt['input_file_name'] = 'dt_b1000_lowres_' + str(opt['upsampling_rate']) + '_'


# Cluster directories:
base_dir = '/SAN/vision/hcp/Ryu/miccai2017/25Apr2017/'
opt['data_dir'] = base_dir + 'data/'
opt['save_dir'] = base_dir + 'models/'
opt['log_dir'] = base_dir + 'log/'
opt['recon_dir'] = base_dir + 'recon/'

opt['mask_dir'] = '/SAN/vision/hcp/Ryu/miccai2017/recon/'
opt['gt_dir'] = '/SAN/vision/hcp/DCA_HCP.2013.3_Proc/'  # ground truth dir
opt['subpath'] = '/T1w/Diffusion/'

opt['input_file_name'] = 'dt_b1000_lowres_' + str(opt['upsampling_rate']) + '_'


# Train:
from largesc.train_v2 import train_cnn
tf.reset_default_graph()
train_cnn(opt)

# Reconstruct:
import largesc.reconstruct_v2 as reconstruct
subjects_list = ['904044', '165840', '889579', '713239',
                 '899885', '117324', '214423', '857263']
rmse_average = 0
for subject in subjects_list:
    opt['subject'] = subject
    rmse, _ = reconstruct.sr_reconstruct(opt)
    rmse_average += rmse
print('\n Average RMSE on Diverse dataset is %.15f.'
      % (rmse_average / len(subjects_list),))
