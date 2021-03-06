import argparse
import logging
import os

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms
import torch.nn.functional as F

from unet import UNet
from utils import plot_img_and_mask
from utils import resize_and_crop, normalize, hwc_to_chw # dense_crf


def predict_img(net,
                full_img,
                device,
                scale_factor=1,
                out_threshold=0.5,
                use_dense_crf=False):
    net.eval()
    img_width = full_img.size[1]
    img_height = full_img.size[1]

    img = resize_and_crop(full_img, scale=scale_factor)
    img = normalize(img)
    img = hwc_to_chw(img)

    X = torch.from_numpy(img).unsqueeze(0)

    X = X.to(device=device)

    with torch.no_grad():
        output = net(X)
        

        if net.n_classes > 1:
            probs = F.softmax(output, dim=1)
            probs = probs.cpu()
            argmax_result = np.argmax(probs, axis=1).reshape(1024, 1024)
            # print(argmax_result.shape)
            # print(f"probs shape : {probs.shape}")
            # np.save("./output.jpg",np.array(probs))

        else:
            argmax_result = np.zeros(output.shape)
            probs = torch.sigmoid(output)
            probs = probs.cpu()
            # print(f"argmax_result.shape:{argmax_result.shape}")
            # print(f"probs.shape:{probs.shape}")
            argmax_result[np.where(probs>out_threshold)]=1
            argmax_result = argmax_result.reshape(output.shape[2:])
              

        evaluate_image = evaluate_img(argmax_result,img_width,img_height)
    return evaluate_image, argmax_result, probs

    #     evaluate_image = evaluate_img(max_result)
    #
    #     probs = probs.squeeze(0)
    #
    #     tf = transforms.Compose(
    #         [
    #             transforms.ToPILImage(),
    #             transforms.Resize(img_height),
    #             transforms.ToTensor()
    #         ]
    #     )
    #
    #     probs = tf(probs.cpu())
    #
    #     full_mask = probs.squeeze().cpu().numpy()
    #
    # if use_dense_crf:
    #     full_mask = dense_crf(np.array(full_img).astype(np.uint8), full_mask)
    #
    # return full_mask > out_threshold


def get_args():
    parser = argparse.ArgumentParser(description='Predict masks from input images',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--model', '-m', default='MODEL.pth',
                        metavar='FILE',
                        help="Specify the file in which the model is stored")
    parser.add_argument('--input', '-i', metavar='INPUT',
                        help='filenames of input images', required=True)

    parser.add_argument('--output', '-o', metavar='INPUT',
                        help='Filenames of ouput images')
    parser.add_argument('--viz', '-v', action='store_true',
                        help="Visualize the images as they are processed",
                        default=False)
    parser.add_argument('--no-save', '-n', action='store_true',
                        help="Do not save the output masks",
                        default=False)
    parser.add_argument('--mask-threshold', '-t', type=float,
                        help="Minimum probability value to consider a mask pixel white",
                        default=0.5)
    parser.add_argument('--scale', '-s', type=float,
                        help="Scale factor for the input images",
                        default=0.5)

    return parser.parse_args()


def get_output_filenames(args):
    in_files = args.input
    out_files = []

    if not args.output:
        for f in in_files:
            pathsplit = os.path.splitext(f)
            out_files.append("{}_OUT{}".format(pathsplit[0], pathsplit[1]))
    elif len(in_files) != len(args.output):
        logging.error("Input files and output files are not of the same length")
        raise SystemExit()
    else:
        out_files = args.output

    return out_files


def mask_to_image(mask):
    return Image.fromarray((mask * 255).astype(np.uint8))


color_dic = {1: [255, 255, 255], 2: [255, 255, 0], 3: [255, 0, 255], 4: [0, 255, 255], 5: [255, 0, 0]}


def evaluate_img(total_mask,width,height):
    mask = np.zeros((width, height, 3), dtype=np.uint8)
    for i in color_dic:
        mask[np.where(total_mask == i)] = np.array(color_dic[i])
    return mask


if __name__ == "__main__":
    args = get_args()
    in_files = args.input
    out_files = args.output
    
    net = UNet(n_channels=3, n_classes=6, bilinear=False)

    logging.info("Loading model {}".format(args.model))

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logging.info(f'Using device {device}')
    net.to(device=device)
    net.load_state_dict(torch.load(args.model, map_location=device))

    logging.info("Model loaded !")

    for i, fn in enumerate(os.listdir(in_files)):
        if not ".jpg" in fn: continue
        logging.info("\nPredicting image {} ...".format(fn))

        img = Image.open(os.path.join(in_files,fn))

        evaluate_image, argmax_result, probs = predict_img(net=net,
                                                           full_img=img,
                                                           scale_factor=args.scale,
                                                           out_threshold=args.mask_threshold,
                                                           use_dense_crf=False,
                                                           device=device)
        np.save(os.path.join(out_files,fn.split(".jpg")[0]), probs)
        cv2.imwrite(os.path.join(out_files,fn.split(".jpg")[0]+"_prediction.jpg"), evaluate_image)
        # print(mask.shape)
        # print(np.max(mask))
        # if not args.no_save:
        #     out_fn = out_files[i]
        #
        #     result = evaluate_img(mask)
        #
        #     cv2.imwrite(out_files[i],result)
        #
        #     logging.info("Mask saved to {}".format(out_files[i]))
        #
        # if args.viz:
        #     logging.info("Visualizing results for image {}, close to continue ...".format(fn))
        #     plot_img_and_mask(img, mask)
