# -*- coding:utf-8 -*-
"""Classifier model verifier"""
import sys, logging

logger = logging.getLogger("log")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())
fh = logging.FileHandler("logging.log", encoding="utf-8")
logger.addHandler(fh)
try:
    from screen_processor import MapleScreenCapturer
    import cv2, time, os
    import numpy as np
    from keras.models import load_model
    from tensorflow import device
    from keystate_manager import KeyboardInputManager
    from directinput_constants import DIK_UP, DIK_DOWN, DIK_LEFT, DIK_RIGHT, DIK_NUMLOCK, DIK_SPACE
    from win32con import VK_NUMLOCK
    from win32api import GetKeyState
except:
    logger.exception("EXCEPTION FROM IMPORTS")

class RuneDetector:
    def __init__(self, model_path, labels=None, screen_capturer=None, key_mgr=None):
        """
        Run just Once to initialize
        :param model_path: Path to trained keras model
        :param labels: dictionary with class names as keys, integer as values
        example: {'down': 0, 'left': 1, 'right': 2, 'up': 3}
        """
        self.logger = logging.getLogger("RuneDetector")
        self.logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        fh = logging.FileHandler("logging.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        self.labels = labels or {'down': 0, 'left': 1, 'right': 2, 'up': 3}
        self.model_path = model_path
        with device("/cpu:0"):  # Use cpu for evaluation
            model = load_model(self.model_path)
            #model.compile(optimizer="adam", loss='categorical_crossentropy', metrics=['accuracy'])
            model.load_weights(self.model_path)

        self.model = model

        self.rune_roi_1366 = [450, 180, 500, 130]  # x, y, w, h
        self.rune_roi_1024 = [295, 180, 500, 133]
        self.rune_roi_800 = [170,200, 440, 135]
        self.rune_roi = self.rune_roi_800  # set as default rune roi
        self.screen_processor = screen_capturer or MapleScreenCapturer()
        self.key_mgr = key_mgr or KeyboardInputManager()

    def capture_roi(self):
        screen_rect = self.screen_processor.ms_get_screen_rect(self.screen_processor.ms_get_screen_hwnd())
        screen_width = screen_rect[2]-screen_rect[0]

        if screen_width > 1300:
            self.rune_roi = self.rune_roi_1366
        elif screen_width > 1000:
            self.rune_roi = self.rune_roi_1024
        elif screen_width > 800:
            self.rune_roi = self.rune_roi_800

        captured_image = self.screen_processor.capture(set_focus=False, rect=screen_rect)

        captured_roi = cv2.cvtColor(np.array(captured_image), cv2.COLOR_RGB2BGR)

        captured_roi = captured_roi[self.rune_roi[1]:self.rune_roi[1]+self.rune_roi[3], self.rune_roi[0]:self.rune_roi[0]+self.rune_roi[2]]

        return captured_roi

    def preprocess(self, img):
        """
        finds and returns sorted list of 60 by 60 grayscale images of circles, centered
        :param img: BGR image of roi containing circle
        :return: list of grayscale images each containing a circle
        """
        hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hsv_img[:, :, 1] = 255
        hsv_img[:, :, 2] = 255
        bgr_img = cv2.cvtColor(hsv_img, cv2.COLOR_HSV2BGR)
        gray_img = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)

        circles = cv2.HoughCircles(gray_img, cv2.HOUGH_GRADIENT, 1, gray_img.shape[0] / 8, param1=100, param2=30, minRadius=18, maxRadius=30)
        temp_list = []
        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")
            for img_index, (x, y, r) in enumerate(circles, start=1):

                cropped = gray_img[max(0, int(y - 60 / 2)):int(y + 60 / 2), max(0, int(x - 60 / 2)):int(x + 60 / 2)].astype(np.float32)

                temp_list.append((cropped, (x, y)))
        temp_list = sorted(temp_list, key= lambda x: x[1][0])
        return [image[0] for image in temp_list]

    def images2tensor(self, img_list):
        """
        Creates a tf compliant tensor by stacking images in img_list
        :param img_list:
        :return: np.array of shape [1, 60, 60, 1]
        """
        return np.vstack([np.reshape(x, [1, 60, 60, 1]) for x in img_list])

    def classify(self, tensor, batch_size = 4):
        """
        Runs tensor through model and returns list of direction in string.
        :param tensor: input tensor
        :param batch_size: batch size
        :return: size of strings "up", "down", "left", "right"
        """
        return_list = []
        result = self.model.predict(tensor, batch_size=batch_size)
        for res in result:
            final_class = np.argmax(res, axis=-1)
            return_list.extend(
                key for key, val in self.labels.items() if final_class == val
            )

        return return_list

    def solve_auto(self):
        """
        Solves rune if present and sends key presses.
        :return: -1 if rune not detected, result of classify() if successful
        """
        img = self.capture_roi()
        processed_imgs = self.preprocess(img)
        if len(processed_imgs) != 4:
            self.logger.debug("Failed to extract 4 ROI from processed image")
            return -1
        #cv2.imwrite("roi.png", img)
        tensor = self.images2tensor(processed_imgs)
        result = self.classify(tensor)
        if GetKeyState(VK_NUMLOCK):
            self.key_mgr.single_press(DIK_NUMLOCK)
            time.sleep(0.2)
        self.logger.debug(f"Solved rune with solution {str(result)}")
        for inp in result:
            if inp == "down":
                self.key_mgr.single_press(DIK_DOWN)
            elif inp == "left":
                self.key_mgr.single_press(DIK_LEFT)
            elif inp == "right":
                self.key_mgr.single_press(DIK_RIGHT)
            elif inp == "up":
                self.key_mgr.single_press(DIK_UP)
            time.sleep(0.1)
        return len(processed_imgs)

    def press_space(self):
        self.key_mgr.single_press(DIK_SPACE)

    def solve(self):
        """
        Solves rune if present and just returns solution.
        :return: -1 if rune not detected, result of classify() if successful
        """
        img = self.capture_roi()
        processed_imgs = self.preprocess(img)
        if len(processed_imgs) != 4:
            return -1
        tensor = self.images2tensor(processed_imgs)
        return self.classify(tensor)

if __name__ == "__main__":
    try:
        label = {'down': 0, 'left': 1, 'right': 2, 'up': 3}

        solver = RuneDetector("arrow_classifier_keras_gray.h5", label, logger=logger)
        logger.debug("Log start")
        logger.debug(
            f"screen handle: {str(solver.screen_processor.ms_get_screen_hwnd())}"
        )

        logger.debug(
            f"screen rect: {str(solver.screen_processor.ms_get_screen_rect(solver.screen_processor.ms_get_screen_hwnd()))}"
        )

        # solver.scrp.screen_capture(800,600, save=True, save_name="dta.png")
        while True:
            img = solver.capture_roi()
            cv2.imshow("Solver", img)

            return_val = solver.solve_auto()
            if return_val == -1:
                print("no rune detected")
            else:
                logger.debug("Finished solving runes.")
            k = cv2.waitKey(1)
            if k == ord("q"):
                break
            if cv2.getWindowProperty("Solver", 0) < 0:
                logger.debug("Program Exit")
                break
    except:
        logger.exception("EXCEPTION")



