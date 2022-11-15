import cv2, json, os
import numpy as np

class MonsterTemplateDetector:
    """
    Match specific images on screen using cv MatchTemplate.
    """
    def __init__(self, mob_data_path):
        """
        Class Variables:
        self.template: cv image object for template
        self.template_flipped: self.templated flipped on Y axis
        :param mob_data_path: path to mob data file.
        """
        self.template = None
        self.template_flipped = None
        self.template_calibrated_xcoords = None
        self.template_calibrated_ycoords = None
        self.mob_data = json.loads(open(mob_data_path, "r", encoding="utf-8").read())

    def create_template(self, template_img_filename):
        """Save reference image to memory, both original and vertically flipped"""
        template_img = cv2.imread(os.path.join(self.mob_data["imgdir"], template_img_filename), 0)
        self.template = template_img
        self.template_flipped = cv2.flip(self.template, 1)
        self.template_calibrated_xcoords = self.mob_data[template_img_filename]["offset_x"]
        self.template_calibrated_ycoords = self.mob_data[template_img_filename]["offset_y"]

    def find(self, src_gray_img_arr, search_threshold=0.8, override_error=True):
        if override_error:
            if src_gray_img_arr.shape[0] < self.template.shape[0] or src_gray_img_arr.shape[1] < self.template.shape[1]:
                return 0
        else:
            assert src_gray_img_arr.shape[0] > self.template.shape[0] and src_gray_img_arr.shape[1] > self.template.shape[1], "Search image is smaller than template!"
        template_matcher = cv2.matchTemplate(src_gray_img_arr, self.template, cv2.TM_CCOEFF_NORMED)
        loc = np.where(template_matcher >= search_threshold)
        detected_points = [
            (
                point[0] + self.template_calibrated_xcoords,
                point[1] + self.template_calibrated_ycoords,
            )
            for point in zip(*loc[::-1])
        ]

        template_matcher = cv2.matchTemplate(src_gray_img_arr, self.template_flipped, cv2.TM_CCOEFF_NORMED)
        loc = np.where(template_matcher >= search_threshold)
        detected_points.extend(
            (
                point[0] + self.template_calibrated_xcoords,
                point[1] + self.template_calibrated_ycoords,
            )
            for point in zip(*loc[::-1])
        )

        return detected_points

