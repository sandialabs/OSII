import cv2
import json
import os
import numpy as np

def shift_clip_to_uint8(arr, quantile=5):
    arr = np.asarray(arr)

    # Shift so that roughly 25% of values become negative
    shift_value = np.percentile(arr, quantile)
    if shift_value <= 0:
        return out
    shifted = arr - shift_value

    # Clip negative values to zero
    clipped = np.clip(shifted, 0, None)

    # Clip to valid uint8 range before converting
    clipped = np.clip(clipped, 0, 255)

    # Convert to uint8
    out = clipped.astype(np.uint8)

    return out



def expand_keep_region_cv2(mask, iterations=1, neighbors=8):
    """
    mask: [H, W, 1] array
          1 = keep
          0 = discard

    iterations: number of pixels to expand the keep region
    neighbors: 4 or 8

    returns:
          [H, W, 1] array with same convention:
          1 = keep
          0 = discard
    """

    # Convert [H, W, 1] -> [H, W]
    keep_mask = mask[..., 0].astype(np.uint8)

    if neighbors == 4:
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    elif neighbors == 8:
        kernel = np.ones((3, 3), dtype=np.uint8)
    else:
        raise ValueError("neighbors must be 4 or 8")

    # Expand keep region
    expanded_keep = cv2.dilate(
        keep_mask,
        kernel,
        iterations=iterations,
    )

    # Restore shape [H, W, 1]
    return expanded_keep[..., None].astype(mask.dtype)


def apply_kmeans(image_bytes, num_clusters=2, input_filename="filtered_image", save_fig=False, output_dir=None,
                 debug=False, darken=False, sharpen=False):
    nparr = np.frombuffer(image_bytes, np.uint8)

    original_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    image_rgb = cv2.cvtColor(original_img,cv2.COLOR_BGR2RGB)
    
    if original_img is None:
        print(f"[Evaluation] Failed to decode image: {input_filename}")

    original_shape = image_rgb.shape
    
    pixel_values = image_rgb.reshape((-1,3))
    pixel_values = np.float32(pixel_values) / 255.0

    num_attempts = 2

    max_iterations = 100
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, max_iterations, 0.2)

    #Apply the K-Means clustering
    retval, _labels, centers = cv2.kmeans(pixel_values, num_clusters, None, criteria, num_attempts, cv2.KMEANS_PP_CENTERS)

    # Ensure the label with the most pixels is assigned to 'white' for background color
    label_0_count = np.sum(_labels == 0)
    label_1_count = np.sum(_labels == 1)
    labels = np.zeros(_labels.shape)
    if label_0_count < label_1_count:
        labels[_labels == 0] = 0
        labels[_labels == 1] = 255
    else:
        labels[_labels == 0] = 255
        labels[_labels == 1] = 0

    #construct the segmented image from labels back to image dimensions
    segmented_data = np.reshape(labels, [original_shape[0], original_shape[1], 1])
    segmented_data = np.concatenate([segmented_data,segmented_data,segmented_data], axis=-1).astype(np.uint8)

    # Replace text with original image pixel values (try darkening if possible)
    mask = (segmented_data == 0)
    mask = mask[:,:,0,None]
    original_count = np.sum(mask)
    mask = expand_keep_region_cv2(mask, iterations=1, neighbors=8)
    expanded_count = np.sum(mask)
    mask = np.concatenate([mask, mask, mask], axis=-1)

    # Optionally, try darkening values to increase contrast
    values_from_original_image = image_rgb[mask]
    if darken:
        values_from_original_image = shift_clip_to_uint8(values_from_original_image, quantile=5)
    segmented_data[mask] = values_from_original_image


    # Optionally, try to sharpen image with 3x4 kernel
    if sharpen:
        #kernel = np.array([[-1, -1, -1],
        #                   [-1,  9, -1],
        #                   [-1, -1, -1]])

        #kernel = np.array([[0,  -1,  0],
        #                   [-1,  5, -1],
        #                   [0,  -1,  0]])

        kernel = np.array([[-0.2, -1, -0.2],
                           [-1,  6.5, -1],
                           [-0.2, -1, -0.2]])

        segmented_data = cv2.filter2D(segmented_data, -1, kernel)

    
    # Avoid compression when converting to ".png"
    png_compression_params = [cv2.IMWRITE_PNG_COMPRESSION, 0]

    # Try Gaussian blur...
    #segmented_data = cv2.GaussianBlur(segmented_data, (5, 5), 0)
    
    if save_fig:
        base_filename = os.path.split(os.path.splitext(input_filename)[0])[-1]
        outpath = f"filtered_{base_filename}.png"
        if output_dir is not None:
            outpath = os.path.join(output_dir, outpath)
        cv2.imwrite(outpath, segmented_data, png_compression_params)

    if debug:
        plt.imshow(segmented_data)
        plt.show()
        
    success, encoded_img = cv2.imencode(".png", cv2.cvtColor(segmented_data, cv2.COLOR_RGB2BGR), png_compression_params)
    if not success:
        raise ValueError("Failed to encode image")

    image_bytes = encoded_img.tobytes()

    if debug:
        with open("tmp.png", "wb") as f:
            f.write(image_bytes)
    
    return image_bytes

