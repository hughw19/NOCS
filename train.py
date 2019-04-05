"""
Normalized Object Coordinate Space for Category-Level 6D Object Pose and Size Estimation
Jointly training for CAMERA, COCO, and REAL datasets 

Modified based on Mask R-CNN(https://github.com/matterport/Mask_RCNN)
Written by He Wang
------------------------------------------------------------
"""
import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument('--mode', default='train', type=str, help="train/finetune")
parser.add_argument('--gpu',  default='0', type=str)
args = parser.parse_args()

os.environ['CUDA_VISIBLE_DEVICES']=args.gpu
print('Using GPU {}.'.format(args.gpu))
mode = args.mode

import sys
import datetime
import re
import time
import numpy as np
from config import Config
import utils
import model as modellib
import visualize
from dataset import TOICOCODataset


# Root directory of the project
ROOT_DIR = os.getcwd()

# Directory to save logs and trained model
MODEL_DIR = os.path.join(ROOT_DIR, "logs")

# Path to COCO trained weights
COCO_MODEL_PATH = os.path.join(MODEL_DIR, "mask_rcnn_coco.h5")

class ScenesConfig(Config):
    """Configuration for training on the toy shapes dataset.
    Derives from the base Config class and overrides values specific
    to the toy shapes dataset.
    """
    # Give the configuration a recognizable name
    NAME = "ShapeNetTOI"
    OBJ_MODEL_DIR = os.path.join(ROOT_DIR, 'data', 'ShapeNetTOIModels', 'ShapeNetTOIFinalModels')
    # Train on 1 GPU and 8 images per GPU. We can put multiple images on each
    # GPU because the images are small. Batch size is 8 (GPUs * images/GPU).
    GPU_COUNT = 1
    IMAGES_PER_GPU = 2

    # Number of classes (including background)
    NUM_CLASSES = 1 + 6  # background + 6 object categories
    MEAN_PIXEL = np.array([[ 120.66209412, 114.70348358, 105.81269836]])

    IMAGE_MIN_DIM = 480
    IMAGE_MAX_DIM = 640

    if IMAGE_MIN_DIM == 480 and IMAGE_MAX_DIM == 640:
        USE_SMALL_IMAGE = False
    elif IMAGE_MIN_DIM == 240 and IMAGE_MAX_DIM == 320:
        USE_SMALL_IMAGE = True
    else:
        print('Image resolution is wrong.')
        exit()

    RPN_ANCHOR_SCALES = (16, 32, 48, 64, 128)  # anchor side in pixels

    # Reduce training ROIs per image because the images are small and have
    # few objects. Aim to allow ROI sampling to pick 33% positive ROIs.
    TRAIN_ROIS_PER_IMAGE = 64

    # Use a small epoch since the data is simple
    STEPS_PER_EPOCH = 1000

    # use small validation steps since the epoch is small
    VALIDATION_STEPS = 50

    WEIGHT_DECAY = 0.0001
    LEARNING_RATE = 0.001
    LEARNING_MOMENTUM = 0.9

    COORD_LOSS_SCALE = 1
    COORD_REGRESS_LOSS   = 'Soft_L1'
    JOINT_MASK_COORDS = False
    USE_DEEPER_NET = False

#     COORD_USE_BINS = False
#     COORD_NUM_BINS = 32
#     COORD_SHARE_WEIGHTS = False
#     COORD_USE_DELTA = False
#     COORD_USE_UNET = False
#     COORD_USE_CASCADE_L1 = False
    COORD_SECOND_NORM = False

    COORD_POOL_SIZE = 14
#     if COORD_USE_UNET:
#         COORD_POOL_SIZE = 28
    COORD_SHAPE = [28, 28]

    USE_BN = True
#     if COORD_SHARE_WEIGHTS:
#         USE_BN = False

    USE_RNN = False
    USE_SYMMETRY_LOSS = True
#     if USE_RNN:
#         IMAGES_PER_GPU = 1

    RESNET = "resnet50"
    TRAINING_AUGMENTATION = True
    SOURCE_WEIGHT = [3, 1, 1] #'ShapeNetTOI', 'Real', 'coco'



class InferenceConfig(ScenesConfig):
    GPU_COUNT = 1
    IMAGES_PER_GPU = 1



if __name__ == '__main__':

    config = ScenesConfig()
    config.display()


    # Training dataset
    toi_dir = os.path.join('data', 'shapenet_toi_330K')
    coco_dir = os.path.join('data', 'coco')
    #  real classes
    coco_names = ['BG', 'person', 'bicycle', 'car', 'motorcycle', 'airplane',
                  'bus', 'train', 'truck', 'boat', 'traffic light',
                  'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird',
                  'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear',
                  'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie',
                  'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball',
                  'kite', 'baseball bat', 'baseball glove', 'skateboard',
                  'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup',
                  'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
                  'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza',
                  'donut', 'cake', 'chair', 'couch', 'potted plant', 'bed',
                  'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote',
                  'keyboard', 'cell phone', 'microwave', 'oven', 'toaster',
                  'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors',
                  'teddy bear', 'hair drier', 'toothbrush']

    
    synset_names = ['BG', #0
                    'bottle', #1
                    'bowl', #2
                    'camera', #3
                    'can',  #4
                    'laptop',#5
                    'mug'#6
                    ]


    class_map = {
        'bottle': 'bottle',
        'bowl':'bowl',
        'cup':'mug',
        'laptop': 'laptop',
    }


    coco_cls_ids = []
    for coco_cls in class_map:
        ind = coco_names.index(coco_cls)
        coco_cls_ids.append(ind)
    config.display()

    if mode == 'train':

        # Create model in training mode
        model = modellib.MaskRCNN(mode="training", config=config,
                              model_dir=MODEL_DIR)

        # Which weights to start with?
        init_with = "coco"  # imagenet, coco, or last

        if init_with == "imagenet":
            model.load_weights(model.get_imagenet_weights(), by_name=True)
        elif init_with == "coco":
            # Load weights trained on MS COCO, but skip layers that
            # are different due to the different number of classes
            # See README for instructions to download the COCO weights
            model.load_weights(COCO_MODEL_PATH, by_name=True,
                               exclude=["mrcnn_class_logits", "mrcnn_bbox_fc",
                                        "mrcnn_bbox", "mrcnn_mask"])
        elif init_with == "last":
            # Load the last model you trained and continue training
            #model.load_weights(model.find_last()[1], by_name=True)
            model.load_weights('logs/shapenettoi20180605T1718/mask_rcnn_shapenettoi_0120.h5',
                               by_name=True)

        elif init_with == "rnn":
            # Load the last model you trained and continue training
            #model.load_weights(model.find_last()[1], by_name=True)
            model.load_weights('/orions4-zfs/projects/hewang/Mask_RCNN/logs/mask_rcnn_scenes_softl1bn.h5',
                               by_name=True)

        # Train the head branches
        # Passing layers="heads" freezes all layers except the head
        # layers. You can also pass a regular expression to select
        # which layers to train by name pattern.
        dataset_train = TOICOCODataset(synset_names, 'train', config)
        dataset_train.load_scenes(toi_dir)
        dataset_train.load_real_scenes(toi_dir)
        dataset_train.load_coco(coco_dir, "train", class_names=class_map.keys())
        dataset_train.prepare(class_map)

        # Validation dataset
        dataset_val = TOICOCODataset(synset_names, 'val', config)
        # dataset_val.load_scenes(toi_dir)
        dataset_val.load_real_scenes(toi_dir)
        # dataset_val.load_coco(coco_dir, "val", class_names=class_map.keys())
        dataset_val.prepare(class_map)

        
        #print("Training network heads")
        model.train(dataset_train, dataset_val,
                    learning_rate=config.LEARNING_RATE,
                    epochs=100,
                    layers_name='heads')

        # Training - Stage 2
        # Finetune layers from ResNet stage 4 and up
        print("Training Resnet layer 4+")
        model.train(dataset_train, dataset_val,
                    learning_rate=config.LEARNING_RATE/10,
                    epochs=130,
                    layers_name='4+')

        # Training - Stage 3
        # Finetune layers from ResNet stage 3 and up
        print("Training Resnet layer 3+")
        model.train(dataset_train, dataset_val,
                    learning_rate=config.LEARNING_RATE/100,
                    epochs=400,
                    layers_name='all')


    if mode == 'finetune':

        # Create model in training mode
        model = modellib.MaskRCNN(mode="training", config=config,
                              model_dir=MODEL_DIR)

 
            # Load the last model you trained and continue training
            #model.load_weights(model.find_last()[1], by_name=True)
        model_name = 'TOICOCO_resnet50_softl1_640*480_batch2_lr1e-3'
        checkpoint_name = 'mask_rcnn_shapenettoi_0120.h5'
        checkpoint_folder = checkpoint_name.split('.')[0]

        model_dir = './logs/'
        model_path = os.path.join(model_dir, model_name, checkpoint_name)

        # Load trained weights (fill in path to trained weights here)
        assert model_path != "", "Provide path to trained weights"
        print("Loading weights from ", model_path)
        model.load_weights(model_path, by_name=True)


       
        # Train the head branches
        # Passing layers="heads" freezes all layers except the head
        # layers. You can also pass a regular expression to select
        # which layers to train by name pattern.
        dataset_real_train = TOICOCODataset(synset_names, 'train', config)
        dataset_real_train.load_real_scenes(toi_dir)
        dataset_real_train.prepare(class_map)
        
        dataset_real_val = TOICOCODataset(synset_names, 'val', config)
        dataset_real_val.load_real_scenes(toi_dir)
        dataset_real_val.prepare(class_map)

        #print("Training network heads")
        model.train(dataset_real_train, dataset_real_val,
                    learning_rate=config.LEARNING_RATE/100,
                    epochs=40,
                    layers_name='heads')

        # Training - Stage 2
        # Finetune layers from ResNet stage 4 and up
        print("Training Resnet layer 4+")
        model.train(dataset_real_train, dataset_test,
                    learning_rate=config.LEARNING_RATE/100,
                    epochs=70,
                    layers_name='4+')

        # Training - Stage 3
        # Finetune layers from ResNet stage 3 and up
        print("Training Resnet layer 3+")
        model.train(dataset_real_train, dataset_test,
                    learning_rate=config.LEARNING_RATE/100,
                    epochs=110,
                    layers_name='all')

            

    else:
        assert False

