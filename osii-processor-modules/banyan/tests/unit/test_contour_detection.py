"""
Test cases for the evaluate extraction (contour detection) capabilities.
These tests verify if the extraction processor correctly identifies missed 
content percentages and triggers reruns based on specific thresholds.
"""

import os
import re
import json
import pytest

from banyan_extract.utils.evaluate_extraction import evaluate_extraction

# Directory Paths
DATA_DIR_NO_BBOX = "tests/data/contour_detection/without_bbox"
DATA_DIR_WITH_BBOX = "tests/data/contour_detection/with_bbox"

# Evaluation Logic Thresholds
# Reruns are triggered if the missed percentage is between these two bounds
RERUN_THRESHOLD_MIN = 8.0
RERUN_THRESHOLD_MAX = 85.0

# LLM Configuration, temperature is only used for text output here
DEFAULT_TEMPERATURE = 0.0

# Validation Tolerances
# The allowable absolute difference between expected and actual missed percentages
PERCENTAGE_TOLERANCE = 5.0


def get_test_images_no_bbox():
    """
    Scans the directory for standalone PNG images used for testing.
    The expected missed percentage is parsed directly from the filename 
    format (e.g., '15_percent.png').
    """
    test_cases = []
    if not os.path.exists(DATA_DIR_NO_BBOX):
        return test_cases
    for filename in os.listdir(DATA_DIR_NO_BBOX):
        if filename.endswith(".png"):
            match = re.search(r"(\d+)_percent\.png$", filename)
            if match:
                expected_pct = float(match.group(1))
                test_cases.append((filename, expected_pct))
    return test_cases


def get_test_images_with_bbox():
    """
    Scans for image and JSON pairs where bounding box data is present.
    Each PNG must have a matching .json file containing the bbox coordinates.
    The expected percentage is extracted from the image filename.
    """
    test_cases = []
    if not os.path.exists(DATA_DIR_WITH_BBOX):
        return test_cases
    for filename in os.listdir(DATA_DIR_WITH_BBOX):
        if filename.endswith(".png"):
            match = re.search(r"(\d+)_percent\.png$", filename)
            if match:
                expected_pct = float(match.group(1))
                json_filename = filename.replace(".png", ".json")
                test_cases.append((filename, json_filename, expected_pct))
    return test_cases


@pytest.mark.parametrize("filename, expected_pct", get_test_images_no_bbox())
def test_evaluate_no_bbox(filename, expected_pct):
    """
    Validates extraction logic when no bounding boxes are provided.
    Tests if the 'should_rerun' flag correctly triggers for moderate 
    error rates and verifies the accuracy of the calculated missed percentage.
    """
    path = os.path.join(DATA_DIR_NO_BBOX, filename)
    with open(path, "rb") as f:
        img_bytes = f.read()

    should_rerun, missed_pct = evaluate_extraction(
        image_bytes=img_bytes,
        bbox_data=[],
        temperature=DEFAULT_TEMPERATURE,
        input_filename=filename
    )

    # Check if the system correctly identifies the need for a rerun
    if RERUN_THRESHOLD_MIN < expected_pct < RERUN_THRESHOLD_MAX:
        assert should_rerun
    else:
        assert not should_rerun

    # Ensure the calculated percentage is within the defined tolerance
    assert missed_pct == pytest.approx(expected_pct, abs=PERCENTAGE_TOLERANCE)


@pytest.mark.parametrize("img_file, json_file, expected_pct", get_test_images_with_bbox())
def test_evaluate_with_bbox(img_file, json_file, expected_pct):
    """
    Validates extraction logic using image and ground-truth bounding box data.
    This ensures that known bounding boxes are properly excluded or processed 
    during the contour detection evaluation.
    """
    img_path = os.path.join(DATA_DIR_WITH_BBOX, img_file)
    json_path = os.path.join(DATA_DIR_WITH_BBOX, json_file)

    with open(img_path, "rb") as f:
        img_bytes = f.read()
    
    with open(json_path, "r") as f:
        bbox_data = json.load(f)

    should_rerun, missed_pct = evaluate_extraction(
        image_bytes=img_bytes,
        bbox_data=bbox_data,
        temperature=DEFAULT_TEMPERATURE,
        input_filename=img_file
    )

    # Validate rerun logic against global thresholds
    if RERUN_THRESHOLD_MIN < expected_pct < RERUN_THRESHOLD_MAX:
        assert should_rerun
    else:
        assert not should_rerun

    # Validate percentage accuracy
    assert missed_pct == pytest.approx(expected_pct, abs=PERCENTAGE_TOLERANCE)