"""Hardware-free output sink and model/runtime diagnostics."""
from config import ROOT

class FakeMouse:
    def __init__(self):
        self.events = []
        self.xy = (960, 540)
    def position(self): return self.xy
    def size(self): return (1920, 1080)
    def move(self,x,y):
        self.xy = (x,y)
        self.events.append(('move',x,y))
        if len(self.events)>1000: self.events=self.events[-500:]
    def click(self): self.events.append(('click',))
    def down(self): self.events.append(('down',))
    def up(self): self.events.append(('up',))
    def scroll(self,n): self.events.append(('scroll',n))

def main():
    import cv2
    import mediapipe as mp
    import numpy as np
    import pyautogui
    import tkinter as tk
    import ctypes
    from config import load
    load()
    print(f'OpenCV {cv2.__version__}; MediaPipe {mp.__version__}; screen {pyautogui.size()}')
    root = tk.Tk()
    root.withdraw()
    root.update()
    root.destroy()
    ctypes.windll.user32.GetAsyncKeyState(0x77)
    model = ROOT/'models'/'hand_landmarker.task'
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=2)
    with mp.tasks.vision.HandLandmarker.create_from_options(options) as detector:
        blank = np.zeros((480,640,3),dtype=np.uint8)
        for t in (1,34,67):
            result=detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB,data=blank),t)
            assert not result.hand_landmarks
    cv2.namedWindow('GestureControl self-test',cv2.WINDOW_AUTOSIZE)
    cv2.imshow('GestureControl self-test',blank)
    cv2.waitKey(50)
    cv2.destroyAllWindows()
    print('PASS: configuration, Tk, OpenCV preview, global-key polling, model load and blank-frame inference.')
    print('No mouse movement, clicks, camera capture or network requests were performed.')

if __name__=='__main__': main()
