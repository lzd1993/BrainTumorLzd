import numpy as np
import random
import json
import h5py
from patch_library import PatchLibrary
from glob import glob
import matplotlib.pyplot as plt
from skimage import io, color, img_as_float
from skimage.exposure import adjust_gamma
from skimage.segmentation import mark_boundaries
from sklearn.feature_extraction.image import extract_patches_2d
from sklearn.metrics import classification_report
from keras.models import Sequential, model_from_json, load_model, Model
from keras.layers.convolutional import Convolution2D, MaxPooling2D,Conv2D
from keras.layers.core import Dense, Dropout, Activation, Flatten, Reshape
from keras.layers import Merge, MaxoutDense
from keras.layers.normalization import BatchNormalization
from keras.regularizers import L1L2 as l1l2
from keras.optimizers import SGD
from keras.constraints import maxnorm
from keras.callbacks import EarlyStopping, ModelCheckpoint

from keras.layers import Input
from keras.layers.merge import concatenate

from keras.utils import np_utils

from keras.utils import plot_model

import os

class SegmentationModel(object):
    def __init__(self, n_epoch=10, n_chan=4, batch_size=128, loaded_model=False, architecture='single', w_reg=0.01, n_filters=[64,128,128,128], k_dims = [7,5,5,3], activation = 'relu'):
        '''
        A class for compiling/loading, fitting and saving various models, viewing segmented images and analyzing results
        INPUT   (1) int 'n_epoch': number of eopchs to train on. defaults to 10
                (2) int 'n_chan': number of channels being assessed. defaults to 4
                (3) int 'batch_size': number of images to train on for each batch. defaults to 128
                (4) bool 'loaded_model': True if loading a pre-existing model. defaults to False
                (5) str 'architecture': type of model to use, options = single, dual, or two_path. defaults to single (only currently optimized version)
                (6) float 'w_reg': value for l1 and l2 regularization. defaults to 0.01
                (7) list 'n_filters': number of filters for each convolutional layer (4 total)
                (8) list 'k_dims': dimension of kernel at each layer (will be a k_dim[n] x k_dim[n] square). Four total.
                (9) string 'activation': activation to use at each convolutional layer. defaults to relu.
        '''
        self.n_epoch = n_epoch
        self.n_chan = n_chan
        self.batch_size = batch_size
        self.architecture = architecture
        self.loaded_model = loaded_model
        self.w_reg = w_reg
        self.n_filters = n_filters
        self.k_dims = k_dims
        self.activation = activation
        if not self.loaded_model:
            if self.architecture == 'two_path':
                self.model_comp = self.comp_two_path()
            elif self.architecture == 'dual':
                self.model_comp = self.comp_double()
            else:
                self.model_comp = self.compile_model()
        else:
            #model = str(input('Which model should I load? '))
            self.model_comp = self.load_model_weights('../models/dual_example')

    def compile_model(self):
        '''
        compiles standard single model with 4 convolitional/max-pooling layers.
        '''
        print( 'Compiling single model...')
        single = Sequential()

        single.add(Convolution2D(filters=self.n_filters[0],kernel_size=(self.k_dims[0], self.k_dims[0]), padding='valid', kernel_regularizer=l1l2(l1=self.w_reg, l2=self.w_reg), input_shape=(self.n_chan,33,33)))
        single.add(Activation(self.activation))
        single.add(BatchNormalization(axis=1))
        single.add(MaxPooling2D(pool_size=(2,2), strides=(1,1)))
        single.add(Dropout(0.5))
        single.add(Convolution2D(filters=self.n_filters[1], kernel_size=(self.k_dims[1], self.k_dims[1]), activation=self.activation, padding='valid', kernel_regularizer=l1l2(l1=self.w_reg, l2=self.w_reg)))
        single.add(BatchNormalization(axis=1))
        single.add(MaxPooling2D(pool_size=(2,2), strides=(1,1)))
        single.add(Dropout(0.5))
        single.add(Convolution2D(filters=self.n_filters[2], kernel_size=(self.k_dims[2], self.k_dims[2]), activation=self.activation, padding='valid', kernel_regularizer=l1l2(l1=self.w_reg, l2=self.w_reg)))
        single.add(BatchNormalization(axis=1))
        single.add(MaxPooling2D(pool_size=(2,2), strides=(1,1)))
        single.add(Dropout(0.5))
        single.add(Convolution2D(filters=self.n_filters[3], kernel_size=(self.k_dims[3], self.k_dims[3]), activation=self.activation, padding='valid', kernel_regularizer=l1l2(l1=self.w_reg, l2=self.w_reg)))
        single.add(Dropout(0.25))

        single.add(Flatten())
        single.add(Dense(5))
        single.add(Activation('softmax'))

        sgd = SGD(lr=0.001, decay=0.01, momentum=0.9)
        single.compile(loss='categorical_crossentropy', optimizer= sgd,metrics=['accuracy'])
        single.summary()
        plot_model(single,to_file='model.png')
        print( 'Done.')
        return single

    def comp_two_path(self):
        '''
        compiles two-path model, takes in a 4x33x33 patch and assesses global and local paths, then merges the results.
        '''
        print( 'Compiling two-path model...')
        #model = Graph()
        model.add_input(name='input', input_shape=(self.n_chan, 33, 33))

        # local pathway, first convolution/pooling
        model.add_node(Convolution2D(64, 7, 7, border_mode='valid', activation='relu', W_regularizer=l1l2(l1=0.01, l2=0.01)), name='local_c1', input= 'input')
        model.add_node(MaxPooling2D(pool_size=(4,4), strides=(1,1), border_mode='valid'), name='local_p1', input='local_c1')

        # local pathway, second convolution/pooling
        model.add_node(Dropout(0.5), name='drop_lp1', input='local_p1')
        model.add_node(Convolution2D(64, 3, 3, border_mode='valid', activation='relu', W_regularizer=l1l2(l1=0.01, l2=0.01)), name='local_c2', input='drop_lp1')
        model.add_node(MaxPooling2D(pool_size=(2,2), strides=(1,1), border_mode='valid'), name='local_p2', input='local_c2')

        # global pathway
        model.add_node(Convolution2D(160, 13, 13, border_mode='valid', activation='relu', W_regularizer=l1l2(l1=0.01, l2=0.01)), name='global', input='input')

        # merge local and global pathways
        model.add_node(Dropout(0.5), name='drop_lp2', input='local_p2')
        model.add_node(Dropout(0.5), name='drop_g', input='global')
        model.add_node(Convolution2D(5, 21, 21, border_mode='valid', activation='relu',  W_regularizer=l1l2(l1=0.01, l2=0.01)), name='merge', inputs=['drop_lp2', 'drop_g'], merge_mode='concat', concat_axis=1)

        # Flatten output of 5x1x1 to 1x5, perform softmax
        model.add_node(Flatten(), name='flatten', input='merge')
        model.add_node(Dense(5, activation='softmax'), name='dense_output', input='flatten')
        model.add_output(name='output', input='dense_output')

        sgd = SGD(lr=0.005, decay=0.1, momentum=0.9)
        model.compile('sgd', loss={'output':'categorical_crossentropy'})
        print( 'Done.')
        return model

    def comp_double(self):
        '''
        double model. Simialar to two-pathway, except takes in a 4x33x33 patch and it's center 4x5x5 patch. merges paths at flatten layer.
        '''
        print( 'Compiling double model...')
	#'''
        input1 = Input(shape=(4,33,33),name='input1')
        single = Conv2D(filters=64, kernel_size=(7, 7), padding='valid', kernel_regularizer=l1l2(l1=0.01, l2=0.01),activation='relu')(input1)
        #'''
        single = BatchNormalization(axis=1)(single)
        single = MaxPooling2D(pool_size=(4,4), strides=(1,1))(single)
        single = Dropout(0.5)(single)
        #'''
        single = Conv2D(filters=64, kernel_size=(3, 3), activation='relu', padding='valid', kernel_regularizer=l1l2(l1=0.01, l2=0.01))(single)
        single = MaxPooling2D(pool_size=(2,2), strides=(1,1))(single)
        single = Dropout(0.25)(single)

        five_input=Input(shape=(4,33,33),name='five_input')
        double_model = Conv2D(filters=160,kernel_size=(13,13))(five_input)

        double_model_add = concatenate([single,double_model],axis=1)
        double_model_add = Conv2D(filters=5,kernel_size=(21,21))(double_model_add)
        double_model_add = Flatten()(double_model_add)
        #double_model_add = Dropout(0.5)(double_model_add)
        #main_output = Dense(5,activation='sigmoid',name='main_output')(double_model_add)
        main_output = Activation('softmax')(double_model_add)
        model = Model(inputs=[input1,five_input],outputs=main_output)

        sgd = SGD(lr=0.001, decay=0.01, momentum=0.9)
        model.compile(loss='categorical_crossentropy', optimizer=sgd,metrics=['accuracy'])

        model.summary()
        #plot_model(model,to_file='double_path.png')

        '''
        SVG(model_to_dot(model).create(prog='dot',format='svg'))
        '''
        print( 'Done.')
        #sgd = SGD(lr=0.001,decay=0.01,momentum=0.9)
        
        return model

    def load_model_weights(self, model_name):
        '''
        INPUT  (1) string 'model_name': filepath to model and weights, not including extension
        OUTPUT: Model with loaded weights. can fit on model using loaded_model=True in fit_model method
        '''
        print( 'Loading model {}'.format(model_name))
        model = '{}.json'.format(model_name)
        weights = '{}.hdf5'.format(model_name)
        '''
        with open(model) as f:
            m = f.next()
        model_comp = model_from_json(json.loads(m))
        '''
        model_comp = model_from_json(open(model).read())
        model_comp.load_weights(weights)
        print( 'Done.')
        return model_comp

    def fit_model(self, X_train, y_train, X5_train = None, save=True):
        '''
        INPUT   (1) numpy array 'X_train': list of patches to train on in form (n_sample, n_channel, h, w)
                (2) numpy vector 'y_train': list of labels corresponding to X_train patches in form (n_sample,)
                (3) numpy array 'X5_train': center 5x5 patch in corresponding X_train patch. if None, uses single-path architecture
        OUTPUT  (1) Fits specified model
        '''
        Y_train = np_utils.to_categorical(y_train, 5)

        shuffle =list(zip(X_train, Y_train))
        np.random.shuffle(shuffle)

        X_train = np.array([shuffle[i][0] for i in range(len(shuffle))])
        Y_train = np.array([shuffle[i][1] for i in range(len(shuffle))])
        es = EarlyStopping(monitor='val_loss', patience=2, verbose=1, mode='auto')

        # Save model after each epoch to check/bm_epoch#-val_loss
        checkpointer = ModelCheckpoint(filepath="../models/dual_example.hdf5", monitor='val_acc', save_best_only=True, mode='max',verbose=1)

        if self.architecture == 'dual':
            #self.model_comp.fit([X5_train, X_train], Y_train, batch_size=self.batch_size, epochs=self.n_epoch, validation_split=0.1, verbose=1, callbacks=[checkpointer])
            self.model_comp.fit([X_train, X_train], Y_train, batch_size=self.batch_size, epochs=self.n_epoch, validation_split=0.1, verbose=1, callbacks=[checkpointer])
        elif self.architecture == 'two_path':
            data = {'input': X_train, 'output': Y_train}
            self.model_comp.fit(data, batch_size=self.batch_size, nb_epoch=self.n_epoch, validation_split=0.1, show_accuracy=True, verbose=1, callbacks=[checkpointer])
        else:
            self.model_comp.fit(X_train, Y_train, batch_size=self.batch_size, epochs=self.n_epoch, validation_split=0.1, verbose=1, callbacks=[checkpointer])
            #self.model_comp.fit(X_train, Y_train, batch_size=self.batch_size, n_epoch=self.n_epoch,
                                #validation_split=0.1,  verbose=1, callbacks=[checkpointer])
    def save_model(self, model_name):
        '''
        INPUT string 'model_name': name to save model and weigths under, including filepath but not extension
        Saves current model as json and weigts as h5df file
        '''
        model = '{}.json'.format(model_name)
        weights = '{}.hdf5'.format(model_name)
        json_string = self.model_comp.to_json()

        #self.model_comp.save_weights(weights)
        '''
        with open(model, 'w') as f:
            json.dump(json_string, f)
        '''
        open(model, 'w').write(json_string)

    def class_report(self, X_test, y_test):
        '''
        returns skilearns test report (precision, recall, f1-score)
        INPUT   (1) list 'X_test': test data of 4x33x33 patches
                (2) list 'y_test': labels for X_test
        OUTPUT  (1) confusion matrix of precision, recall and f1 score
        '''
        y_pred = self.model_load.predict_class(X_test)
        print( classification_report(y_pred, y_test))

    def predict_image(self, test_img, show=False):
        '''
        predicts classes of input image
        INPUT   (1) str 'test_image': filepath to image to predict on
                (2) bool 'show': True to show the results of prediction, False to return prediction
        OUTPUT  (1) if show == False: array of predicted pixel classes for the center 208 x 208 pixels
                (2) if show == True: displays segmentation results
        '''
        imgs = io.imread(test_img).astype('float').reshape(5,240,240)
        plist = []

        # create patches from an entire slice
        for img in imgs[:-1]:
            if np.max(img) != 0:
                img /= np.max(img)
            p = extract_patches_2d(img, (33,33))
            plist.append(p)
        patches = np.array(list(zip(np.array(plist[0]), np.array(plist[1]), np.array(plist[2]), np.array(plist[3]))))

        # predict classes of each pixel based on models
        full_pred = self.model_comp.predict_classes(patches)

        print( full_pred)
        print( max(full_pred))
        fp1 = full_pred.reshape(208,208)
        if show:
            io.imshow(fp1)
            plt.show
        else:
            return fp1

    def show_segmented_image(self, test_img,i = 0, modality='t1c', show = False):
        '''
        Creates an image of original brain with segmentation overlay
        INPUT   (1) str 'test_img': filepath to test image for segmentation, including file extension
                (2) str 'modality': imaging modelity to use as background. defaults to t1c. options: (flair, t1, t1c, t2)
                (3) bool 'show': If true, shows output image. defaults to False.
        OUTPUT  (1) if show is True, shows image of segmentation results
                (2) if show is false, returns segmented image.
        '''
        modes = {'flair':0, 't1':1, 't1c':2, 't2':3}

        segmentation = self.predict_image(test_img)
        img_mask = np.pad(segmentation, (16,16), mode='edge')
        ones = np.argwhere(img_mask == 1)
        twos = np.argwhere(img_mask == 2)
        threes = np.argwhere(img_mask == 3)
        fours = np.argwhere(img_mask == 4)

        test_im = io.imread(test_img)
        test_back = test_im.reshape(5,240,240)[-2]
        # overlay = mark_boundaries(test_back, img_mask)
        gray_img = img_as_float(test_back)

        # adjust gamma of image
        image = adjust_gamma(color.gray2rgb(gray_img), 0.65)
        sliced_image = image.copy()
        red_multiplier = [1, 0.2, 0.2]
        yellow_multiplier = [1,1,0.25]
        green_multiplier = [0.35,0.75,0.25]
        blue_multiplier = [0,0.25,0.9]

        # change colors of segmented classes
        for i in range(len(ones)):
            sliced_image[ones[i][0]][ones[i][1]] = red_multiplier
        for i in range(len(twos)):
            sliced_image[twos[i][0]][twos[i][1]] = green_multiplier
        for i in range(len(threes)):
            sliced_image[threes[i][0]][threes[i][1]] = blue_multiplier
        for i in range(len(fours)):
            sliced_image[fours[i][0]][fours[i][1]] = yellow_multiplier

        #plt.imsave('../result/' + str(i) + '.png', sliced_image, format('png'))

        if show:
            io.imshow(sliced_image)
            plt.show()

        else:
            return sliced_image

    def get_dice_coef(self, test_img, label):
        '''
        Calculate dice coefficient for total slice, tumor-associated slice, advancing tumor and core tumor
        INPUT   (1) str 'test_img': filepath to slice to predict on
                (2) str 'label': filepath to ground truth label for test_img
        OUTPUT: Summary of dice scores for the following classes:
                    - all classes
                    - all classes excluding background (ground truth and segmentation)
                    - all classes excluding background (only ground truth-based)
                    - advancing tumor
                    - core tumor (1,3 and 4)
        '''
        segmentation = self.predict_image(test_img)
        seg_full = np.pad(segmentation, (16,16), mode='edge')
        gt = io.imread(label).astype(int)
        # dice coef of total image
        total = (len(np.argwhere(seg_full == gt)) * 2.) / (2 * 240 * 240)

        def unique_rows(a):
            '''
            helper function to get unique rows from 2D numpy array
            '''
            a = np.ascontiguousarray(a)
            unique_a = np.unique(a.view([('', a.dtype)]*a.shape[1]))
            return unique_a.view(a.dtype).reshape((unique_a.shape[0], a.shape[1]))

        # dice coef of entire non-background image
        gt_tumor = np.argwhere(gt != 0)
        seg_tumor = np.argwhere(seg_full != 0)
        combo = np.append(pred_core, core, axis = 0)
        core_edema = unique_rows(combo) # intersection of locations defined as tumor_assoc in gt and segmentation
        gt_c, seg_c = [], [] # predicted class of each
        for i in core_edema:
            gt_c.append(gt[i[0]][i[1]])
            seg_c.append(seg_full[i[0]][i[1]])
        tumor_assoc = len(np.argwhere(np.array(gt_c) == np.array(seg_c))) / float(len(core))
        tumor_assoc_gt = len(np.argwhere(np.array(gt_c) == np.array(seg_c))) / float(len(gt_tumor))

        # dice coef advancing tumor
        adv_gt = np.argwhere(gt == 4)
        gt_a, seg_a = [], [] # classification of
        for i in adv_gt:
            gt_a.append(gt[i[0]][i[1]])
            seg_a.append(fp[i[0]][i[1]])
        gta = np.array(gt_a)
        sega = np.array(seg_a)
        adv = float(len(np.argwhere(gta == sega))) / len(adv_gt)

        # dice coef core tumor
        noadv_gt = np.argwhere(gt == 3)
        necrosis_gt = np.argwhere(gt == 1)
        live_tumor_gt = np.append(adv_gt, noadv_gt, axis = 0)
        core_gt = np.append(live_tumor_gt, necrosis_gt, axis = 0)
        gt_core, seg_core = [],[]
        for i in core_gt:
            gt_core.append(gt[i[0]][i[1]])
            seg_core.append(seg_full[i[0]][i[1]])
        gtcore, segcore = np.array(gt_core), np.array(seg_core)
        core = len(np.argwhere(gtcore == segcore)) / float(len(core_gt))

        print( ' ')
        print( 'Region_______________________| Dice Coefficient')
        print( 'Total Slice__________________| {0:.2f}'.format(total))
        print( 'No Background gt_____________| {0:.2f}'.format(tumor_assoc_gt))
        print( 'No Background both___________| {0:.2f}'.format(tumor_assoc))
        print( 'Advancing Tumor______________| {0:.2f}'.format(adv))
        print( 'Core Tumor___________________| {0:.2f}'.format(core))

if __name__ == '__main__':
    #'''
    train_data = glob('/vdb1/ImageData/n4_PNG/**')
    patches = PatchLibrary((33,33), train_data, 50000)
    X,y = patches.make_training_patches()
    
    model = SegmentationModel(architecture='dual')
    model.fit_model(X, y)
    model.save_model('../models/dual_example')
    '''
    # test
    model = SegmentationModel(loaded_model=True)
    tests = glob('/vdb1/ImageData/n4_PNG/0_*')
    len_of_str = len('/vdb1/ImageData/n4_png/0_')
    test_sort = sorted(tests, key=lambda x: int(x[len_of_str:-4]))
    segmented_images = []

    i = 15

    for slice in test_sort[95:96]:
        print(slice)
        img = model.show_segmented_image(slice,i)
        print('----------------------------------')
        filename = os.path.basename(slice)
        print('../result/' + filename[:-4] + '_seg.png')
        plt.imsave('../result/test/' + filename[:-4] + 'seg.png', img, format('png'))
        #segmented_images.append(img)
        i=i+1
    #'''
