"""Builds the specified model:
1. inference() - Builds the model as far as is required for running the network
forward to make predictions.
2. cost() - Adds to the inference model the layers required to generate the cost function.
3. training() - Adds to the loss model the Ops required to generate and apply gradients.

This file is used by sr_nn.py and not meant to be run.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import tensorflow as tf
from largesc.ops import *


def get_weights(filter_shape, W_init=None, name=None):
    if W_init == None:
        # He/Xavier
        prod_length = len(filter_shape) - 1
        stddev = np.sqrt(2.0 / np.prod(filter_shape[:prod_length]))
        W_init = tf.random_normal(filter_shape, stddev=stddev)
    return tf.Variable(W_init, name=name)


def conv3d(x, w_shape, b_shape=None, layer_name='', summary=True):
    """Return the 3D convolution"""
    with tf.name_scope(layer_name):
        with tf.name_scope('weights'):
            w = get_weights(w_shape)
            variable_summaries(w, summary)

        if b_shape is not None:
            with tf.name_scope('biases'):
                b = tf.Variable(tf.constant(1e-2,dtype=tf.float32,shape=b_shape))
                variable_summaries(b, summary)

            # b = tf.get_variable('biases', dtype=tf.float32, shape=b_shape,
            #                    initializer=tf.constant_initializer(1e-2))
            with tf.name_scope('wxplusb'):
                z = tf.nn.conv3d(x, w, strides=(1, 1, 1, 1, 1), padding='VALID')
                z = tf.nn.bias_add(z, b)
                variable_summaries(z, summary)
        else:
            with tf.name_scope('wx'):
                z = tf.nn.conv3d(x, w, strides=(1, 1, 1, 1, 1), padding='VALID')
                variable_summaries(z, summary)
    return z


def normal_mult_noise(a, keep_prob, params, opt, name, summary=True):
    """Gaussian dropout, Srivastava 2014 JMLR"""
    with tf.name_scope(name):
        if params==None:
            sigma = (1.-keep_prob) / keep_prob
            a_drop = a * (1. + sigma * tf.random_normal(tf.shape(a)))
            kl = None
        elif params=='weight':
            # W_init = tf.constant(1e-4, shape=tf.shape(a)[1:])
            W_init = tf.constant(np.float32(1e-4*np.ones(get_tensor_shape(a)[1:])))
            rho = get_weights(filter_shape=None, W_init=W_init, name='rho')
            sigma = tf.minimum(tf.nn.softplus(rho), 1., name='std')
            a_drop = tf.mul(a, 1. + sigma * tf.random_normal(tf.shape(a)), name='a_drop')
            kl = kl_log_uniform_prior(sigma, name='kl')
            variable_summaries(sigma, summary)
            variable_summaries(a_drop, summary)
            # variable_summaries(kl, summary)
        elif params=='channel':
            # W_init = tf.constant(1e-4, shape=tf.shape(a)[1:])
            W_init = tf.constant(np.float32(1e-4 * np.ones(get_tensor_shape(a)[4])))
            rho = get_weights(filter_shape=None, W_init=W_init, name='rho')
            sigma = tf.minimum(tf.nn.softplus(rho), 1., name='std')
            a_drop = tf.mul(a, 1. + sigma * tf.random_normal(tf.shape(a)), name='a_drop')
            # kl = kl_log_uniform_prior(sigma, name='kl')
            kl = np.prod(get_tensor_shape(a)[1:4]) * kl_log_uniform_prior(sigma, name='kl')
            variable_summaries(a_drop, summary)
            variable_summaries(sigma, summary)
            variable_summaries(kl, summary)
        elif params=='layer':
            rho = get_weights(filter_shape=None, W_init=tf.constant(1e-4), name='rho')
            sigma = tf.minimum(tf.nn.softplus(rho), 1., name='std')
            a_drop = tf.mul(a, 1. + sigma * tf.random_normal(tf.shape(a)), name='a_drop')
            # kl = kl_log_uniform_prior(sigma, name='kl')
            kl = np.prod(get_tensor_shape(a)[1:]) * kl_log_uniform_prior(sigma, name='kl')
            variable_summaries(a_drop, summary)
            variable_summaries(kl, summary)
        elif params=='weight_average':  # use average KL across the weights instead.
            # W_init = tf.constant(1e-4, shape=tf.shape(a)[1:])
            W_init = tf.constant(np.float32(1e-4 * np.ones(get_tensor_shape(a)[1:])))
            rho = get_weights(filter_shape=None, W_init=W_init, name='rho')
            sigma = tf.minimum(tf.nn.softplus(rho), 1., name='std')
            a_drop = tf.mul(a, 1. + sigma * tf.random_normal(tf.shape(a)), name='a_drop')
            kl = kl_log_uniform_prior(sigma, name='kl_mean', average=True)
            variable_summaries(a_drop, summary)
            # variable_summaries(kl, summary)
        elif params=='no_noise': # do nothing
            a_drop = a
            kl = None
    return a_drop, kl


def kl_log_uniform_prior(varQ, name=None, average=False):
    """Compute the gaussian-log uniform KL-div from VDLRT"""
    c1 = 1.16145124
    c2 = -1.50204118
    c3 = 0.58629921
    kl_mtx = 0.5*tf.log(varQ) + c1*varQ + c2*tf.pow(varQ,2) + c3*tf.pow(varQ,3)
    if average:
        kl_div = tf.reduce_mean(kl_mtx, name=name)
    else:
        kl_div = tf.reduce_sum(kl_mtx, name=name)
    return kl_div


def residual_block(x, n_in, n_out, name):
    """A residual block of constant spatial dimensions and 1x1 convs only"""
    b = tf.get_variable(name+'_2b', dtype=tf.float32, shape=[n_out],
                        initializer=tf.constant_initializer(1e-2))
    assert n_out >= n_in

    h1 = conv3d(x, [1,1,1,n_in,n_out], [n_out], name+'1')
    h2 = conv3d(tf.nn.relu(h1), [1,1,1,n_out,n_out], None, name+'2')
    h3 = tf.pad(x, [[0,0],[0,0],[0,0],[0,0],[0,n_out-n_in]]) + h2
    return tf.nn.relu(tf.nn.bias_add(h3, b))


def discriminator(self, image, y=None, reuse=False):
    with tf.variable_scope("discriminator") as scope:

        # image is 256 x 256 x (input_c_dim + output_c_dim)
        if reuse:
            tf.get_variable_scope().reuse_variables()
        else:
            assert tf.get_variable_scope().reuse == False

        h0 = lrelu(conv2d(image, self.df_dim, name='d_h0_conv'))
        # h0 is (128 x 128 x self.df_dim)
        h1 = lrelu(self.d_bn1(conv2d(h0, self.df_dim * 2, name='d_h1_conv')))
        # h1 is (64 x 64 x self.df_dim*2)
        h2 = lrelu(self.d_bn2(conv2d(h1, self.df_dim * 4, name='d_h2_conv')))
        # h2 is (32x 32 x self.df_dim*4)
        h3 = lrelu(self.d_bn3(
            conv2d(h2, self.df_dim * 8, d_h=1, d_w=1, name='d_h3_conv')))
        # h3 is (16 x 16 x self.df_dim*8)
        h4 = linear(tf.reshape(h3, [self.batch_size, -1]), 1, 'd_h3_lin')

        return tf.nn.sigmoid(h4), h4


def Unet(self, image, y=None):
    with tf.variable_scope("generator") as scope:
        s = self.output_size
        s2, s4, s8, s16, s32, s64, s128 = int(s / 2), int(s / 4), int(
            s / 8), int(s / 16), int(s / 32), int(s / 64), int(s / 128)

        # image is (256 x 256 x input_c_dim)
        e1 = conv2d(image, self.gf_dim, name='g_e1_conv')
        # e1 is (128 x 128 x self.gf_dim)
        e2 = self.g_bn_e2(conv2d(lrelu(e1), self.gf_dim * 2, name='g_e2_conv'))
        # e2 is (64 x 64 x self.gf_dim*2)
        e3 = self.g_bn_e3(conv2d(lrelu(e2), self.gf_dim * 4, name='g_e3_conv'))
        # e3 is (32 x 32 x self.gf_dim*4)
        e4 = self.g_bn_e4(conv2d(lrelu(e3), self.gf_dim * 8, name='g_e4_conv'))
        # e4 is (16 x 16 x self.gf_dim*8)
        e5 = self.g_bn_e5(conv2d(lrelu(e4), self.gf_dim * 8, name='g_e5_conv'))
        # e5 is (8 x 8 x self.gf_dim*8)
        e6 = self.g_bn_e6(conv2d(lrelu(e5), self.gf_dim * 8, name='g_e6_conv'))
        # e6 is (4 x 4 x self.gf_dim*8)
        e7 = self.g_bn_e7(conv2d(lrelu(e6), self.gf_dim * 8, name='g_e7_conv'))
        # e7 is (2 x 2 x self.gf_dim*8)
        e8 = self.g_bn_e8(conv2d(lrelu(e7), self.gf_dim * 8, name='g_e8_conv'))
        # e8 is (1 x 1 x self.gf_dim*8)

        self.d1, self.d1_w, self.d1_b = deconv2d(tf.nn.relu(e8), [self.batch_size, s128, s128,self.gf_dim * 8], name='g_d1',with_w=True)
        d1 = tf.nn.dropout(self.g_bn_d1(self.d1), 0.5)
        d1 = tf.concat(3, [d1, e7])
        # d1 is (2 x 2 x self.gf_dim*8*2)

        self.d2, self.d2_w, self.d2_b = deconv2d(tf.nn.relu(d1),[self.batch_size, s64, s64,self.gf_dim * 8], name='g_d2',with_w=True)
        d2 = tf.nn.dropout(self.g_bn_d2(self.d2), 0.5)
        d2 = tf.concat(3, [d2, e6])
        # d2 is (4 x 4 x self.gf_dim*8*2)

        self.d3, self.d3_w, self.d3_b = deconv2d(tf.nn.relu(d2),[self.batch_size, s32, s32,self.gf_dim * 8], name='g_d3',with_w=True)
        d3 = tf.nn.dropout(self.g_bn_d3(self.d3), 0.5)
        d3 = tf.concat(3, [d3, e5])
        # d3 is (8 x 8 x self.gf_dim*8*2)

        self.d4, self.d4_w, self.d4_b = deconv2d(tf.nn.relu(d3),[self.batch_size, s16, s16,self.gf_dim * 8], name='g_d4',with_w=True)
        d4 = self.g_bn_d4(self.d4)
        d4 = tf.concat(3, [d4, e4])
        # d4 is (16 x 16 x self.gf_dim*8*2)

        self.d5, self.d5_w, self.d5_b = deconv2d(tf.nn.relu(d4),[self.batch_size, s8, s8,self.gf_dim * 4], name='g_d5',with_w=True)
        d5 = self.g_bn_d5(self.d5)
        d5 = tf.concat(3, [d5, e3])
        # d5 is (32 x 32 x self.gf_dim*4*2)

        self.d6, self.d6_w, self.d6_b = deconv2d(tf.nn.relu(d5),[self.batch_size, s4, s4,self.gf_dim * 2], name='g_d6',with_w=True)
        d6 = self.g_bn_d6(self.d6)
        d6 = tf.concat(3, [d6, e2])
        # d6 is (64 x 64 x self.gf_dim*2*2)

        self.d7, self.d7_w, self.d7_b = deconv2d(tf.nn.relu(d6),[self.batch_size, s2, s2,self.gf_dim], name='g_d7',with_w=True)
        d7 = self.g_bn_d7(self.d7)
        d7 = tf.concat(3, [d7, e1])
        # d7 is (128 x 128 x self.gf_dim*1*2)

        self.d8, self.d8_w, self.d8_b = deconv2d(tf.nn.relu(d7),[self.batch_size, s, s,self.output_c_dim],name='g_d8', with_w=True)
        # d8 is (256 x 256 x output_c_dim)
        return tf.nn.tanh(self.d8)

def inference(method, x, y, keep_prob, opt, trade_off=None):
    """ Define the model up to where it may be used for inference.
    Args:
        method (str): model type
    Returns:
        y_pred: the predicted output patch (tensor)
    """
    method = opt['method']
    n_h1 = opt['n_h1']
    n_h2 = opt['n_h2']
    n_h3 = opt['n_h3']
    upsampling_rate = opt['upsampling_rate']
    no_channels = opt['no_channels']
    y_std = None

    if method == 'cnn_simple':
        h1_1 = conv3d(x, [3,3,3,no_channels,n_h1], [n_h1], 'conv_1')

        if opt['receptive_field_radius'] == 2:
            h1_2 = conv3d(tf.nn.relu(h1_1), [1,1,1,n_h1,n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 3:
            h1_2 = conv3d(tf.nn.relu(h1_1), [3,3,3,n_h1,n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 4:
            h1_2 = conv3d(tf.nn.relu(h1_1), [3,3,3,n_h1,n_h2], [n_h2], 'conv_2')
            h1_2 = conv3d(tf.nn.relu(h1_2), [3,3,3,n_h2,n_h2], [n_h2], 'conv_3')
        elif opt['receptive_field_radius'] == 5:
            h1_2 = conv3d(tf.nn.relu(h1_1), [3,3,3,n_h1,n_h2], [n_h2], 'conv_2')
            h1_2 = conv3d(tf.nn.relu(h1_2), [3,3,3,n_h2,n_h2], [n_h2], 'conv_3')
            h1_2 = conv3d(tf.nn.relu(h1_2), [3,3,3,n_h2,n_h2], [n_h2], 'conv_4')
        elif opt['receptive_field_radius'] > 5:
            h1_2 = conv3d(tf.nn.relu(h1_1), [3, 3, 3, n_h1, n_h2], [n_h2],'conv_2')
            lyr=3
            while lyr<(opt['receptive_field_radius']):
                h1_2 = conv3d(tf.nn.relu(h1_2), [3,3,3,n_h2,n_h2], [n_h2], 'conv_'+str(lyr+1))
                lyr+=1

        y_pred = conv3d(tf.nn.relu(h1_2),
                        [3,3,3,n_h2,no_channels*(upsampling_rate**3)],
                        [no_channels*(upsampling_rate**3)],
                        'conv_last')

        with tf.name_scope('loss'):
            cost = tf.reduce_mean(tf.square(y - y_pred))

    elif method == 'baseline_transcon':
        h1_1 = conv3d(x, [3,3,3,no_channels,n_h1], [n_h1], 'conv_1')

        if opt['receptive_field_radius'] == 2:
            h1_2 = conv3d(tf.nn.relu(h1_1), [1,1,1,n_h1,n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 3:
            h1_2 = conv3d(tf.nn.relu(h1_1), [3,3,3,n_h1,n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 4:
            h1_2 = conv3d(tf.nn.relu(h1_1), [3,3,3,n_h1,n_h2], [n_h2], 'conv_2')
            h1_2 = conv3d(tf.nn.relu(h1_2), [3,3,3,n_h2,n_h2], [n_h2], 'conv_3')
        elif opt['receptive_field_radius'] == 5:
            h1_2 = conv3d(tf.nn.relu(h1_1), [3,3,3,n_h1,n_h2], [n_h2], 'conv_2')
            h1_2 = conv3d(tf.nn.relu(h1_2), [3,3,3,n_h2,n_h2], [n_h2], 'conv_3')
            h1_2 = conv3d(tf.nn.relu(h1_2), [3,3,3,n_h2,n_h2], [n_h2], 'conv_4')
        elif opt['receptive_field_radius'] > 5:
            h1_2 = conv3d(tf.nn.relu(h1_1), [3, 3, 3, n_h1, n_h2], [n_h2],'conv_2')
            lyr=3
            while lyr<(opt['receptive_field_radius']):
                h1_2 = conv3d(tf.nn.relu(h1_2), [3,3,3,n_h2,n_h2], [n_h2], 'conv_'+str(lyr+1))
                lyr+=1

        y_pred = conv3d(tf.nn.relu(h1_2),
                        [3,3,3,n_h2,no_channels*(upsampling_rate**3)],
                        [no_channels*(upsampling_rate**3)],
                        'conv_last')

        with tf.name_scope('loss'):
            cost = tf.reduce_mean(tf.square(y - y_pred))

    elif method=='cnn_simple_L1':
        h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')

        if opt['receptive_field_radius'] == 2:
            h1_2 = conv3d(tf.nn.relu(h1_1), [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 3:
            h1_2 = conv3d(tf.nn.relu(h1_1), [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 4:
            h1_2 = conv3d(tf.nn.relu(h1_1), [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            h1_2 = conv3d(tf.nn.relu(h1_2), [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
        elif opt['receptive_field_radius'] == 5:
            h1_2 = conv3d(tf.nn.relu(h1_1), [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            h1_2 = conv3d(tf.nn.relu(h1_2), [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
            h1_2 = conv3d(tf.nn.relu(h1_2), [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')

        y_pred = conv3d(tf.nn.relu(h1_2),
                        [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                        [no_channels * (upsampling_rate ** 3)],
                        'conv_last')

        with tf.name_scope('loss'):
            cost = tf.reduce_mean(tf.abs(y - y_pred))

    elif method == 'cnn_heteroscedastic':
        with tf.name_scope('mean_network'):
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')
            if opt['receptive_field_radius'] == 2:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
            elif opt['receptive_field_radius'] == 5:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')

            y_pred = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)], 'conv_last')

        with tf.name_scope('precision_network'):  # diagonality assumed
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')
            if opt['receptive_field_radius'] == 2:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
            elif opt['receptive_field_radius'] == 5:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')

            h_last = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)], 'conv_last')
            y_prec = tf.nn.softplus(h_last) + 1e-6  # precision matrix (diagonal)
            y_std = tf.sqrt(1. / y_prec, name='y_std')

        with tf.name_scope('loss'):
            cost = tf.reduce_mean(tf.square(tf.mul(y_prec, (y - y_pred)))) \
                   - tf.reduce_mean(tf.log(y_prec))

        # with tf.name_scope('covariance_network'):  # diagonality assumed
        #     h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')
        #     if opt['receptive_field_radius'] == 2:
        #         h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
        #                       [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
        #     elif opt['receptive_field_radius'] == 3:
        #         h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
        #                       [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
        #     elif opt['receptive_field_radius'] == 4:
        #         h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
        #                       [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
        #         h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
        #                       [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
        #     elif opt['receptive_field_radius'] == 5:
        #         h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
        #                       [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
        #         h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
        #                       [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
        #         h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
        #                       [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')
        #
        #     h_last = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
        #                     [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
        #                     [no_channels * (upsampling_rate ** 3)], 'conv_last')
        #     y_cov = tf.nn.softplus(h_last) + 1e-6  # precision matrix (diagonal)
        #     y_std = tf.sqrt(y_cov, name='y_std')
        #
        # with tf.name_scope('loss'):
        #     cost = tf.reduce_mean(tf.square(tf.mul(1./y_cov, (y - y_pred)))) \
        #            + tf.reduce_mean(tf.log(y_cov))

    elif method == 'cnn_dropout':
        h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')

        if opt['receptive_field_radius'] == 2:
            h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                          [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 3:
            h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                          [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 4:
            h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                          [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                          [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
        elif opt['receptive_field_radius'] == 5:
            h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                          [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                          [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
            h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                          [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')

        y_pred = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                        [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                        [no_channels * (upsampling_rate ** 3)], 'conv_last')

        with tf.name_scope('loss'):
            cost = tf.reduce_mean(tf.square(y - y_pred))

    elif method == 'cnn_gaussian_dropout':
        h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')
        params=None
        if opt['receptive_field_radius'] == 2:
            a1_2_drop, _ = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
            h1_2 = conv3d(a1_2_drop, [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 3:
            a1_2_drop, _ = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 4:
            a1_2_drop, _ = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            a1_2_drop, _ = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
        elif opt['receptive_field_radius'] == 5:
            a1_2_drop, _ = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            a1_2_drop, _ = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
            a1_2_drop, _ = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_3')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')

        a1_2_drop, _ = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_last')
        y_pred = conv3d(a1_2_drop,
                        [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                        [no_channels * (upsampling_rate ** 3)],
                        'conv_last')

        with tf.name_scope('loss'):
            cost = tf.reduce_mean(tf.square(y - y_pred))

    elif method == 'cnn_variational_dropout' or \
         method == 'cnn_variational_dropout_layerwise' or \
         method == 'cnn_variational_dropout_channelwise' or \
         method == 'cnn_variational_dropout_average':

        if method == 'cnn_variational_dropout':
            params='weight'
        elif method == 'cnn_variational_dropout_layerwise':
            params='layer'
        elif method == 'cnn_variational_dropout_channelwise':
            params='channel'
        elif method == 'cnn_variational_dropout_average':
            params = 'weight_average'
        else:
            raise ValueError('no variational parameters specified!')

        h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')

        if opt['receptive_field_radius'] == 2:
            a1_2_drop, kl = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
            h1_2 = conv3d(a1_2_drop, [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 3:
            a1_2_drop, kl = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
        elif opt['receptive_field_radius'] == 4:
            a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
            kl = kl_1 + kl_2
        elif opt['receptive_field_radius'] == 5:
            a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
            a1_2_drop, kl_3 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_3')
            h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')
            kl = kl_1 + kl_2 + kl_3
        a1_2_drop, kl_last = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_last')
        y_pred = conv3d(a1_2_drop,
                        [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                        [no_channels * (upsampling_rate ** 3)],
                        'conv_last')

        with tf.name_scope('kl_div'):
            down_sc = 1.0
            kl_div = down_sc * (kl + kl_last)
            tf.summary.scalar('kl_div_average', kl_div)

        with tf.name_scope('expected_negloglikelihood'):
            e_negloglike = tf.reduce_mean(tf.reduce_sum(tf.square(y - y_pred),[1,2,3,4]),0)
            if not(method == 'cnn_variational_dropout_average'):
                e_negloglike = opt['train_noexamples'] * e_negloglike
            tf.summary.scalar('e_negloglike', e_negloglike)

        with tf.name_scope('loss'):  # negative evidence lower bound (ELBO)
            cost = tf.add(e_negloglike, -kl_div, name='neg_ELBO')
            tf.summary.scalar('neg_ELBO', cost)

    elif method=='cnn_heteroscedastic_variational' or \
         method=='cnn_heteroscedastic_variational_layerwise' or \
         method=='cnn_heteroscedastic_variational_channelwise' or \
         method=='cnn_heteroscedastic_variational_average' :

        if method == 'cnn_heteroscedastic_variational':
            params = 'weight'
        elif method == 'cnn_heteroscedastic_variational_average':
            params = 'weight_average'
        elif method == 'cnn_heteroscedastic_variational_layerwise':
            params = 'layer'
        elif method == 'cnn_heteroscedastic_variational_channelwise':
            params = 'channel'
        else:
            raise ValueError('no variational parameters specified!')

        with tf.name_scope('mean_network'):
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')

            if opt['receptive_field_radius'] == 2:
                a1_2_drop, kl = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                a1_2_drop, kl = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt,'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                kl = kl_1 + kl_2
            elif opt['receptive_field_radius'] == 5:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                a1_2_drop, kl_3 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_3')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')
                kl = kl_1 + kl_2 + kl_3
            a1_2_drop, kl_last = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_last')
            y_pred = conv3d(a1_2_drop,
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)],
                            'conv_last')

        with tf.name_scope('kl_div'):
            down_sc = 1.0
            kl_div = down_sc*(kl + kl_last)
            tf.summary.scalar('kl_div', kl_div)

        with tf.name_scope('precision_network'):  # diagonality assumed
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')
            if opt['receptive_field_radius'] == 2:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
            elif opt['receptive_field_radius'] == 5:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')

            h_last = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)], 'conv_last')
            y_prec = tf.nn.softplus(h_last) + 1e-6  # precision matrix (diagonal)
            y_std = tf.sqrt(1. / y_prec, name='y_std')

        with tf.name_scope('expected_negloglikelihood'):
            e_negloglike = tf.reduce_mean(tf.reduce_sum(tf.square(tf.mul(y_prec, (y - y_pred))), [1,2,3,4]), 0) \
                         - tf.reduce_mean(tf.reduce_sum(tf.log(y_prec), [1,2,3,4]), 0)
            if not (method == 'cnn_heteroscedastic_variational_average'):
                e_negloglike = opt['train_noexamples'] * e_negloglike
            tf.summary.scalar('e_negloglike', e_negloglike)

        with tf.name_scope('loss'):  # negative evidence lower bound (ELBO)
            cost = tf.add(e_negloglike, -kl_div, name='neg_ELBO')
            tf.summary.scalar('cost', cost)

    elif method == 'cnn_heteroscedastic_variational_downsc' or \
         method == 'cnn_heteroscedastic_variational_upsc' or \
         method == 'cnn_heteroscedastic_variational_layerwise_downsc' or \
         method == 'cnn_heteroscedastic_variational_channelwise_downsc':

        if method == 'cnn_heteroscedastic_variational_downsc':
            params = 'weight'
            sc = 0.3
        elif method == 'cnn_heteroscedastic_variational_upsc':
            params = 'weight'
            sc = 3.0
        elif method == 'cnn_heteroscedastic_variational_layerwise_downsc':
            params = 'layer'
            sc = 0.3
        elif method == 'cnn_heteroscedastic_variational_channelwise_downsc':
            params = 'channel'
            sc = 0.3
        else:
            raise ValueError('no variational parameters specified!')

        with tf.name_scope('mean_network'):
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')

            if opt['receptive_field_radius'] == 2:
                a1_2_drop, kl = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                a1_2_drop, kl = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                kl = kl_1 + kl_2
            elif opt['receptive_field_radius'] == 5:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                a1_2_drop, kl_3 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_3')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')
                kl = kl_1 + kl_2 + kl_3
            a1_2_drop, kl_last = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_last')
            y_pred = conv3d(a1_2_drop,
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)],
                            'conv_last')

        with tf.name_scope('kl_div'):
            kl_div = sc * (kl + kl_last)
            tf.summary.scalar('kl_div', kl_div)

        with tf.name_scope('precision_network'):  # diagonality assumed
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')
            if opt['receptive_field_radius'] == 2:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
            elif opt['receptive_field_radius'] == 5:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')

            h_last = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)], 'conv_last')
            y_prec = tf.nn.softplus(h_last) + 1e-6  # precision matrix (diagonal)
            y_std = tf.sqrt(1. / y_prec, name='y_std')

        with tf.name_scope('expected_negloglikelihood'):
            e_negloglike = tf.reduce_mean(tf.reduce_sum(tf.square(tf.mul(y_prec, (y - y_pred))), [1, 2, 3, 4]), 0) \
                           - tf.reduce_mean(tf.reduce_sum(tf.log(y_prec), [1, 2, 3, 4]), 0)
            if not (method == 'cnn_heteroscedastic_variational_average'):
                e_negloglike = opt['train_noexamples'] * e_negloglike
            tf.summary.scalar('e_negloglike', e_negloglike)

        with tf.name_scope('loss'):  # negative evidence lower bound (ELBO)
            cost = tf.add(e_negloglike, -kl_div, name='neg_ELBO')
            tf.summary.scalar('cost', cost)

    elif method == 'cnn_heteroscedastic_variational_hybrid_control' or \
         method == 'cnn_heteroscedastic_variational_channelwise_hybrid_control' or \
         method == 'cnn_heteroscedastic_variational_downsc_control' or \
         method == 'cnn_heteroscedastic_variational_upsc_control':

        if method == 'cnn_heteroscedastic_variational_hybrid_control':
            params = 'weight'
        elif method == 'cnn_heteroscedastic_variational_channelwise_hybrid_control':
            params = 'channel'
        elif method == 'cnn_heteroscedastic_variational_downsc_control' or \
             method == 'cnn_heteroscedastic_variational_upsc_control':
            params = 'weight'
        else:
            raise ValueError('no variational parameters specified!')

        with tf.name_scope('mean_network'):
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')

            if opt['receptive_field_radius'] == 2:
                a1_2_drop, kl = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                a1_2_drop, kl = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                kl = kl_1 + kl_2
            elif opt['receptive_field_radius'] == 5:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                a1_2_drop, kl_3 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_3')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')
                kl = kl_1 + kl_2 + kl_3
            a1_2_drop, kl_last = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_last')
            y_pred = conv3d(a1_2_drop,
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)],
                            'conv_last')

        with tf.name_scope('kl_div'):
            down_sc = 1.0
            kl_div = down_sc * (kl + kl_last)
            tf.summary.scalar('kl_div', kl_div)

        with tf.name_scope('precision_network'):  # diagonality assumed
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')
            if opt['receptive_field_radius'] == 2:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
            elif opt['receptive_field_radius'] == 5:
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_1), keep_prob),
                              [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                h1_2 = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                              [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')

            h_last = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)], 'conv_last')
            y_prec = tf.nn.softplus(h_last) + 1e-6  # precision matrix (diagonal)
            y_std = tf.sqrt(1. / y_prec, name='y_std')

        with tf.name_scope('expected_negloglikelihood'):
            if method == 'cnn_heteroscedastic_variational_hybrid_control' or \
            method == 'cnn_heteroscedastic_variational_channelwise_hybrid_control':
                mse_sum = tf.reduce_mean(tf.reduce_sum(tf.square(y - y_pred),[1,2,3,4]),0)
                mse_sum = opt['train_noexamples'] * mse_sum
                tf.summary.scalar('mse_sum', mse_sum)

            e_negloglike = tf.reduce_mean(tf.reduce_sum(tf.square(tf.mul(y_prec, (y - y_pred))), [1, 2, 3, 4]), 0) \
                           - tf.reduce_mean(tf.reduce_sum(tf.log(y_prec), [1, 2, 3, 4]), 0)
            e_negloglike = opt['train_noexamples'] * e_negloglike
            tf.summary.scalar('e_negloglike', e_negloglike)

        with tf.name_scope('loss'):  # negative evidence lower bound (ELBO)
            if method == 'cnn_heteroscedastic_variational_hybrid_control' or \
               method == 'cnn_heteroscedastic_variational_channelwise_hybrid_control':
                cost = trade_off*(e_negloglike - kl_div) + (1.- trade_off)*(mse_sum- kl_div)
            elif method == 'cnn_heteroscedastic_variational_downsc_control':
                cost = tf.add(e_negloglike, -trade_off * kl_div, name='neg_ELBO')
            elif method == 'cnn_heteroscedastic_variational_upsc_control':
                cost = tf.add(e_negloglike, -trade_off * kl_div, name='neg_ELBO')
            tf.summary.scalar('cost', cost)

    elif method == 'cnn_heteroscedastic_variational_cov' or \
         method == 'cnn_heteroscedastic_variational_layerwise_cov' or \
         method == 'cnn_heteroscedastic_variational_channelwise_cov':

        if method == 'cnn_heteroscedastic_variational_cov':
            params = 'weight'
        elif method == 'cnn_heteroscedastic_variational_layerwise_cov':
            params = 'layer'
        elif method == 'cnn_heteroscedastic_variational_channelwise_cov':
            params = 'channel'
        else:
            raise ValueError('no variational parameters specified!')

        with tf.name_scope('mean_network'):
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')

            if opt['receptive_field_radius'] == 2:
                a1_2_drop, kl_mean = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                a1_2_drop, kl_mean = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                kl_mean = kl_1 + kl_2
            elif opt['receptive_field_radius'] == 5:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                a1_2_drop, kl_3 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_3')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')
                kl_mean = kl_1 + kl_2 + kl_3
            a1_2_drop, kl_mean_last = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_last')
            y_pred = conv3d(a1_2_drop,
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)],
                            'conv_last')

        with tf.name_scope('kl_div_mean'):
            down_sc = 1.0
            kl_div_mean = down_sc * (kl_mean + kl_mean_last)
            tf.summary.scalar('kl_div_mean', kl_div_mean)

        with tf.name_scope('precision_network'):  # diagonality assumed
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')

            if opt['receptive_field_radius'] == 2:
                a1_2_drop, kl_prec = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                a1_2_drop, kl_prec = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                kl_prec = kl_1 + kl_2
            elif opt['receptive_field_radius'] == 5:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                a1_2_drop, kl_3 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_3')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')
                kl_prec = kl_1 + kl_2 + kl_3

            a1_2_drop, kl_prec_last = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_last')
            h_last = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)], 'conv_last')
            y_prec = tf.nn.softplus(h_last) + 1e-6  # precision matrix (diagonal)
            y_std = tf.sqrt(1. / y_prec, name='y_std')

        with tf.name_scope('kl_div_prec'):
            down_sc = 1.0
            kl_div_prec = down_sc * (kl_prec + kl_prec_last)
            tf.summary.scalar('kl_div_prec', kl_div_prec)

        with tf.name_scope('expected_negloglikelihood'):
            e_negloglike = tf.reduce_mean(tf.reduce_sum(tf.square(tf.mul(y_prec, (y - y_pred))), [1, 2, 3, 4]), 0) \
                           - tf.reduce_mean(tf.reduce_sum(tf.log(y_prec), [1, 2, 3, 4]), 0)
            if not (method == 'cnn_heteroscedastic_variational_average'):
                e_negloglike = opt['train_noexamples'] * e_negloglike
            tf.summary.scalar('e_negloglike', e_negloglike)

        with tf.name_scope('loss'):  # negative evidence lower bound (ELBO)
            cost = tf.add(e_negloglike, -kl_div_mean-kl_div_prec, name='neg_ELBO')
            tf.summary.scalar('cost', cost)

    elif method == 'cnn_heteroscedastic_variational_cov_hybrid' or \
         method == 'cnn_heteroscedastic_variational_layerwise_cov_hybrid' or \
         method == 'cnn_heteroscedastic_variational_channelwise_cov_hybrid':

        if method == 'cnn_heteroscedastic_variational_cov_hybrid':
            params = 'weight'
        elif method == 'cnn_heteroscedastic_variational_layerwise_cov_hybrid':
            params = 'layer'
        elif method == 'cnn_heteroscedastic_variational_channelwise_cov_hybrid':
            params = 'channel'
        else:
            raise ValueError('no variational parameters specified!')

        with tf.name_scope('mean_network'):
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')

            if opt['receptive_field_radius'] == 2:
                a1_2_drop, kl_mean = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                a1_2_drop, kl_mean = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                kl_mean = kl_1 + kl_2
            elif opt['receptive_field_radius'] == 5:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                a1_2_drop, kl_3 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_3')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')
                kl_mean = kl_1 + kl_2 + kl_3
            a1_2_drop, kl_mean_last = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_last')
            y_pred = conv3d(a1_2_drop,
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)],
                            'conv_last')

        with tf.name_scope('kl_div_mean'):
            down_sc = 1.0
            kl_div_mean = down_sc * (kl_mean + kl_mean_last)
            tf.summary.scalar('kl_div_mean', kl_div_mean)

        with tf.name_scope('precision_network'):  # diagonality assumed
            h1_1 = conv3d(x, [3, 3, 3, no_channels, n_h1], [n_h1], 'conv_1')

            if opt['receptive_field_radius'] == 2:
                a1_2_drop, kl_prec = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [1, 1, 1, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 3:
                a1_2_drop, kl_prec = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
            elif opt['receptive_field_radius'] == 4:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                kl_prec = kl_1 + kl_2
            elif opt['receptive_field_radius'] == 5:
                a1_2_drop, kl_1 = normal_mult_noise(tf.nn.relu(h1_1), keep_prob, params, opt, 'mulnoise_1')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h1, n_h2], [n_h2], 'conv_2')
                a1_2_drop, kl_2 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_2')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_3')
                a1_2_drop, kl_3 = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_3')
                h1_2 = conv3d(a1_2_drop, [3, 3, 3, n_h2, n_h2], [n_h2], 'conv_4')
                kl_prec = kl_1 + kl_2 + kl_3

            a1_2_drop, kl_prec_last = normal_mult_noise(tf.nn.relu(h1_2), keep_prob, params, opt, 'mulnoise_last')
            h_last = conv3d(tf.nn.dropout(tf.nn.relu(h1_2), keep_prob),
                            [3, 3, 3, n_h2, no_channels * (upsampling_rate ** 3)],
                            [no_channels * (upsampling_rate ** 3)], 'conv_last')
            y_prec = tf.nn.softplus(h_last) + 1e-6  # precision matrix (diagonal)
            y_std = tf.sqrt(1. / y_prec, name='y_std')

        with tf.name_scope('kl_div_prec'):
            down_sc = 1.0
            kl_div_prec = down_sc * (kl_prec + kl_prec_last)
            tf.summary.scalar('kl_div_prec', kl_div_prec)

        with tf.name_scope('expected_negloglikelihood'):
            mse_sum = tf.reduce_mean(tf.reduce_sum(tf.square(y - y_pred), [1, 2, 3, 4]), 0)
            mse_sum = opt['train_noexamples'] * mse_sum
            tf.summary.scalar('mse_sum', mse_sum)

            e_negloglike = tf.reduce_mean(tf.reduce_sum(tf.square(tf.mul(y_prec, (y - y_pred))), [1, 2, 3, 4]), 0) \
                           - tf.reduce_mean(tf.reduce_sum(tf.log(y_prec), [1, 2, 3, 4]), 0)
            e_negloglike = opt['train_noexamples'] * e_negloglike
            tf.summary.scalar('e_negloglike', e_negloglike)

        with tf.name_scope('loss'):  # negative evidence lower bound (ELBO)
            cost = trade_off * (e_negloglike - kl_div_mean - kl_div_prec) \
                   + (1. - trade_off) * (mse_sum - kl_div_mean)
            tf.summary.scalar('cost', cost)

    elif method == 'cnn_residual':
        h1 = tf.nn.relu(conv3d(x, [3,3,3,no_channels,n_h1], [n_h1], '1'))
        # Residual blocks:
        # todo: include BN
        h2 = residual_block(h1, n_h1, n_h1, 'res2')
        h3 = residual_block(h2, n_h1, n_h1, 'res3')
        # Output
        h4 = conv3d(h3, [3,3,3,n_h1,n_h2], [n_h2], '4')
        h5 = residual_block(h4, n_h2, n_h2, 'res5')
        h6 = residual_block(h5, n_h2, n_h2, 'res6')
        y_pred = conv3d(h6, [1,1,1,n_h2,no_channels*(upsampling_rate**3)],
                            [no_channels*(upsampling_rate**3)], '7')
    else:
        raise ValueError('The chosen method not available ...')
    return y_pred, y_std, cost


def scaled_prediction(method, x, y, keep_prob, transform, opt, trade_off):
    x_mean = tf.constant(np.float32(transform['input_mean']), name='x_mean')
    x_std = tf.constant(np.float32(transform['input_std']), name='x_std')
    y_mean = tf.constant(np.float32(transform['output_mean']), name='y_mean')
    y_std = tf.constant(np.float32(transform['output_std']), name='y_std')
    # x_scaled = tf.div(tf.sub(x - transform['input_mean'), transform['input_std'])
    x_scaled = tf.div(tf.sub(x, x_mean), x_std)
    y, y_uncertainty, cost = inference(method, x_scaled, y, keep_prob, opt, trade_off)
    y_pred = tf.add(tf.mul(y_std, y), y_mean, name='y_pred')

    if opt['method']=='cnn_simple' or \
       opt['method']=='cnn_simple_L1' or \
       opt['method']=='cnn_dropout' or \
       opt['method']=='cnn_gaussian_dropout' or\
       opt['method']=='cnn_variational_dropout' or \
       opt['method']=='cnn_variational_dropout_channelwise':
        y_pred_std = 1
    else:
        y_pred_std = tf.mul(y_std, y_uncertainty, name='y_pred_std')
    return y_pred, y_pred_std


def variable_summaries(var, default=False):
    """Attach a lot of summaries to a Tensor (for TensorBoard visualization)."""
    if default:
        with tf.name_scope('summaries'):
            mean = tf.reduce_mean(var)
            tf.summary.scalar('mean', mean)
            with tf.name_scope('stddev'):
                stddev = tf.sqrt(tf.reduce_mean(tf.square(var - mean)))
            tf.summary.scalar('stddev', stddev)
            tf.summary.scalar('max', tf.reduce_max(var))
            tf.summary.scalar('min', tf.reduce_min(var))
            tf.summary.histogram('histogram', var)


def get_tensor_shape(tensor):
    """Return the shape of a tensor as a tuple"""
    s = tensor.get_shape()
    return tuple([s[i].value for i in range(0, len(s))])

def get_tradeoff_values(opt):
    n_epochs = opt['n_epochs']
    tradeoff_list = np.zeros(n_epochs)
    if opt['method'] == 'cnn_heteroscedastic_variational_hybrid_control' or \
       opt['method'] == 'cnn_heteroscedastic_variational_channelwise_hybrid_control' or \
       opt['method'] == 'cnn_heteroscedastic_variational_cov_hybrid' or \
       opt['method'] == 'cnn_heteroscedastic_variational_layerwise_cov_hybrid' or \
       opt['method'] == 'cnn_heteroscedastic_variational_channelwise_cov_hybrid':

        print('apply trade-off!')
        init_idx = n_epochs//4  # intial stable training with std variational dropout loss
        freq = 1
        counter = 0
        rate  = 1./(len(range(init_idx,3*init_idx))//freq)
        for idx in range(init_idx,3*init_idx):
            if (counter+1)%freq==0:
                tradeoff_list[idx] = tradeoff_list[idx-1] + rate
                counter=0
            else:
                tradeoff_list[idx] = tradeoff_list[idx-1]
                counter+=1
        tradeoff_list[3*init_idx:]=1.  # fine-tune with the true cost function.
    else:
        print('no trade off needed!')
    return tradeoff_list

def get_tradeoff_values_v2(method, n_epochs):
    tradeoff_list = np.zeros(n_epochs)
    if method == 'cnn_heteroscedastic_variational_hybrid_control' or \
       method== 'cnn_heteroscedastic_variational_channelwise_hybrid_control' or \
       method == 'cnn_heteroscedastic_variational_cov_hybrid' or \
       method == 'cnn_heteroscedastic_variational_layerwise_cov_hybrid' or \
       method == 'cnn_heteroscedastic_variational_channelwise_cov_hybrid':

        print('apply trade-off!')
        init_idx = n_epochs//4  # intial stable training with std variational dropout loss
        freq = 1
        counter = 0
        rate  = 1./(len(range(init_idx,3*init_idx))//freq)
        for idx in range(init_idx,3*init_idx):
            if (counter+1)%freq==0:
                tradeoff_list[idx] = tradeoff_list[idx-1] + rate
                counter=0
            else:
                tradeoff_list[idx] = tradeoff_list[idx-1]
                counter+=1
        tradeoff_list[3*init_idx:]=1.  # fine-tune with the true cost function.
    else:
        print('no trade off needed!')
    return tradeoff_list