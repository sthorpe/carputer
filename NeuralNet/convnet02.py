"""Creates a model from training data.

Usage:
  convnet02.py [--indir=<path>] [--outdir=<path>]

Options:
  --indir=<path>   path to input npy files [default: ~/training-data]
  --outdir=<path>  [default: ~/convnet02-results]
"""

import os
import os.path
import random
import time

from docopt import docopt
# http://stackoverflow.com/questions/4931376/generating-matplotlib-graphs-without-a-running-x-server
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf

from convnetshared1 import NNModel
from data_model import TrainingData
import html_output

import sys,os
sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
import config

#Colorfied print statements
#USAGE: print bcolors.WARNING + "TEXT" + bcolors.ENDC
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def generate_color_text(prev_val, cur_val):
    """
        Pretty formats and colorizes an input based on the delta from the previous.
        Used for debug statements

        return string
    """
    delta = cur_val - prev_val
    if(delta >= 0):
        return (bcolors.OKGREEN + format(cur_val, ".3f") + bcolors.ENDC)
    else:
        return (bcolors.FAIL + format(cur_val, ".3f") + bcolors.ENDC) 


# Parse args.
args = docopt(__doc__)
# Save data to an output dir.
outdir = os.path.expanduser(args['--outdir'])
output_path = os.path.join(outdir, time.strftime('%Y_%m_%d__%H_%M_%S_%p'))
if not os.path.exists(output_path):
    os.makedirs(output_path)

# -------- Load all data --------
train_data = TrainingData.fromfilename("train", args['--indir'])
test_data = TrainingData.fromfilename("test", args['--indir'])

numTest = 8000
skipTest = 1
if config.running_on_laptop:
    numTest = 384 * 2
    skipTest = 4
test_data.TrimArray(numTest, skipTest)

net_model = NNModel()

timeStamp = time.strftime("%Y_%m_%d__%H_%M_%S")

# Add ops to save and restore all the variables.
saver = tf.train.Saver()

sess = tf.Session()
sess.run(tf.global_variables_initializer())

# saver.restore(sess, "modelMed.ckpt")

allAccuracyTrain = []
allAccuracyTest = []

print '\n\n-----------------------'
print 'saving output data to %s' % output_path
print 'training on %s images' % train_data.NumSamples()
print 'testing on %s images' % test_data.NumSamples()
print '-----------------------\n'

random.seed(111)
iteration = 0
accuracy_check_iterations = []
sliding_window = []
sliding_window_size = 16
sliding_window_graph = []

#Headers for the console debug output
debug_header_list = ['Iteration', 'Elapsed Time', 'Sliding Average', 'steer regression', 'throttle regression']
print '%s' % ' | '.join(map(str, debug_header_list))

#Vars to calculate deltas between iterations
prev_sliding_window = 0
prev_squared_diff = 0.0
prev_squared_diff_throttle = 0.0

merged_summaries = tf.summary.merge_all()
train_writer = tf.summary.FileWriter('train', sess.graph)

start_time = time.time()
while iteration < 1000*128:
    batch = train_data.GenRandomBatch()
    train_feed_dict = batch.FeedDict(net_model, 0.6)
    [summary_str, _, train_steer_diff] = sess.run(
        [merged_summaries, net_model.train_step, net_model.squared_diff], feed_dict = train_feed_dict)
    train_writer.add_summary(summary_str, iteration)


    # Check the accuracy occasionally.
    if ((iteration % 128) == 127):
        [results_steering_regress,
         results_throttle_regress,
         results_squared_diff,
         results_squared_diff_throttle,
         results_loss,
         results_regularizers,
         ] = sess.run([net_model.steering_regress_result,
                       net_model.throttle_regress_result,
                       net_model.squared_diff,
                       net_model.squared_diff_throttle,
                       net_model.loss,
                       net_model.regularizers,
                       ], feed_dict=test_data.FeedDict(net_model))

        allAccuracyTest.append(results_squared_diff)
        sliding_window.append(results_squared_diff)
        if len(sliding_window) > sliding_window_size: sliding_window = sliding_window[1:]
        sliding_window_graph.append(sum(sliding_window)/len(sliding_window))

        # print results_steering
        # print results_throttle
        html_output.write_html(
            output_path, test_data, tf.get_default_graph(),
            sess, results_steering_regress, results_throttle_regress, net_model)

        accuracy_check_iterations.append(iteration)
        allAccuracyTrain.append(train_steer_diff)
        plt.plot(accuracy_check_iterations, allAccuracyTrain, 'bo')
        plt.plot(accuracy_check_iterations, allAccuracyTrain, 'b-')
        plt.plot(accuracy_check_iterations, allAccuracyTest, 'ro')
        plt.plot(accuracy_check_iterations, allAccuracyTest, 'r-')
        plt.plot(accuracy_check_iterations, sliding_window_graph, 'g-')
        axes = plt.gca()
        axes.set_ylim([0, 1000.05])
        plt.title("training (blue), test (red), avg " + str(round(sliding_window_graph[-1], 5)) + "  /  " + str(len(sliding_window)))
        plt.xlabel('iteration')
        plt.ylabel('diff squared')
        plt.savefig(os.path.join(output_path, "progress.png"))

        # Save the model.
        save_path = saver.save(sess, os.path.join(output_path, "model.ckpt"))
        config.store('last_tf_model', save_path)

        # put the print after writing everything so it indicates things have been written.
        debug_iteration = format(iteration, '^10')
        debug_loss = format(results_loss, '^16')
        debug_regularizers = format(results_regularizers, '^16')

        #Format sliding window
        debug_sliding_window = generate_color_text(prev_sliding_window, sliding_window_graph[-1])
        debug_sliding_window = format(debug_sliding_window, '^25')
        prev_sliding_window = sliding_window_graph[-1]

        # Format steering regression accuracy
        debug_sqr_acc = generate_color_text(prev_squared_diff, results_squared_diff)
        debug_sqr_acc = format(debug_sqr_acc, '^33')
        prev_squared_diff = results_squared_diff
        # Format throttle regression accuracy
        debug_sqr_acc_throttle = generate_color_text(prev_squared_diff_throttle, results_squared_diff_throttle)
        debug_sqr_acc_throttle = format(debug_sqr_acc_throttle, '^33')
        prev_squared_diff_throttle = results_squared_diff_throttle

        elapsed_time = format(format(time.time() - start_time, ".2f"), '^17')

        # all_pulse_entropy = np.sum(np.multiply(results_pulse_softmax, np.log(np.reciprocal(results_pulse_softmax))))

        #Print everything
        print("%s %s %s %s %s %s %s" % (debug_iteration, elapsed_time, debug_sliding_window, debug_sqr_acc, debug_sqr_acc_throttle, debug_loss, debug_regularizers))
        start_time = time.time()

    # Increment.
    iteration += 1
