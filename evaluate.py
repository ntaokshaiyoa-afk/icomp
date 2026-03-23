import cv2
import numpy as np
import math
from skimage.metrics import structural_similarity as ssim

def imread_any(path):
    img = cv2.imread(str(path))
    if img is not None:
        return img

    try:
        with open(path, "rb") as f:
            data = np.frombuffer(f.read(), np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except:
        return None

def evaluate_quality(original, target):
    img1 = imread_any(original)
    img2 = imread_any(target)

    if img1 is None or img2 is None:
        raise Exception("image decode failed")

    img1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    img2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    score, _ = ssim(img1, img2, full=True)

    mse = ((img1 - img2) ** 2).mean()
    psnr = 100 if mse == 0 else 20 * math.log10(255.0 / (mse ** 0.5))

    return {"ssim": score, "psnr": psnr}
