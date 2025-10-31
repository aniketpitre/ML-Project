#!/usr/bin/env python3
"""
Debug script to run MTCNN detection and InceptionResnetV1 embedding on a given image.
Usage: python debug_detect.py /absolute/path/to/image.jpg
"""
import sys
from PIL import Image
import numpy as np
import torch
from facenet_pytorch import MTCNN, InceptionResnetV1

img_path = sys.argv[1] if len(sys.argv) > 1 else None
if not img_path:
    print("Usage: python debug_detect.py /absolute/path/to/photo.jpg")
    sys.exit(1)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print("Device:", device)

mtcnn = MTCNN(keep_all=True, device=device)
resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)

img = Image.open(img_path).convert('RGB')
print("Image size:", img.size, "mode:", img.mode)

# Detect boxes + probs
boxes, probs = mtcnn.detect(img)
print("boxes:", boxes)
print("probs:", probs)

# Get aligned face tensors (if any)
faces_tensors = mtcnn(img)  # this returns None, single tensor or batched tensor
print("faces_tensors type:", type(faces_tensors))
if faces_tensors is None:
    print("faces_tensors is None -> no aligned faces returned by mtcnn(img)")
else:
    # if it's a tensor, show shape and compute embeddings
    if hasattr(faces_tensors, 'shape'):
        print("faces_tensors shape:", faces_tensors.shape)
        faces_batch = faces_tensors.to(device)
        with torch.no_grad():
            embeddings = resnet(faces_batch).cpu().numpy()
        print("embeddings shape:", embeddings.shape)
        print("first embedding (truncated):", embeddings[0][:6].tolist())
    else:
        print("faces_tensors is not a tensor:", faces_tensors)
