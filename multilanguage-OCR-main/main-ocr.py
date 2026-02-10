# pip install paddleocr paddlepaddle

from paddleocr import PaddleOCR
import cv2
from matplotlib import pyplot as plt

ocr = PaddleOCR(use_angle_cls=True, lang='en' )
image_path = 'test.jpg'
img = cv2.imread(image_path)

plt.figure()
plt.imshow(img)
plt.show()
result = ocr.ocr(img, cls=True)
print(result[0] [1] [1])
