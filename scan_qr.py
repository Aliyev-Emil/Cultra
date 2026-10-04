import cv2
from pyzbar.pyzbar import decode

image = cv2.imread("pizza_qr.png")

result = decode(image)

for qr in result:
    data = qr.data.decode("utf-8")
    print(data)