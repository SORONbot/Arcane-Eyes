import time

import cv2

cap = cv2.VideoCapture("rtsp://admin:admin@192.168.100.25:554")

time.sleep(2)

while (True):

    ret, frame = cap.read()
    print(ret)
    if ret == 1:
        cv2.imshow('frame', frame)
    else:
        print("No video")

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
