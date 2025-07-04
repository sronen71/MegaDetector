import os
import csv
from collections import defaultdict

# Copied from postprocess_batch_results.py


def is_sas_url(s) -> bool:
    """
    Placeholder for a more robust way to verify that a link is a SAS URL.
    99.999% of the time this will suffice for what we're using it for right now.
    """
    return (
        s.startswith(("http://", "https://"))
        and ("core.windows.net" in s)
        and ("?" in s)
    )


def relative_sas_url(folder_url, relative_path):
    """
    Given a container-level or folder-level SAS URL, create a SAS URL to the
    specified relative path.
    """
    relative_path = relative_path.replace("%", "%25")
    relative_path = relative_path.replace("#", "%23")
    relative_path = relative_path.replace(" ", "%20")
    if not is_sas_url(folder_url):
        return None
    tokens = folder_url.split("?")
    assert len(tokens) == 2
    if not tokens[0].endswith("/"):
        tokens[0] = tokens[0] + "/"
    if relative_path.startswith("/"):
        relative_path = relative_path[1:]
    return tokens[0] + relative_path + "?" + tokens[1]


def write_sequence_max_detection_csv(
    md_results,
    output_dir,
    image_base_dir,
    csv_filename="sequence_max_detections.csv",
    confidence_threshold=0.0,
):
    """
    For each sequence (seq_id), find the image with the largest number of detections.
    Write a CSV with columns: file_name, date, time, seq_id, species, max_count.
    file_name is a clickable link to the original image (HTML <a> tag).
    """
    images = md_results["images"]
    # Group images by seq_id
    seq_to_images = defaultdict(list)
    for im in images:
        seq_id = im.get("seq_id", None)
        if seq_id is not None:
            seq_to_images[seq_id].append(im)

    rows = []
    for seq_id, group in seq_to_images.items():
        # Find image with max detections (using all detections, but count only those above threshold)
        max_img = max(group, key=lambda im: len(im.get("detections", [])))
        detections = max_img.get("detections", [])
        # Only count animal detections above threshold
        animal_detections = [
            det
            for det in detections
            if det.get("category") == "1"
            and det.get("conf", 0.0) >= confidence_threshold
        ]
        # Exclude if there are any human detections in this image
        if not animal_detections:
            continue
        file_name = max_img["file"]
        max_count = len(animal_detections)
        # Date/time extraction
        dt = max_img.get("datetime", "")
        date, time = "", ""
        if dt:
            if "T" in dt:
                date, time = dt.split("T", 1)
                time = time.split(".")[0]  # Remove microseconds if present
            else:
                date = dt
        # Get species from 'prediction' field (smoothed, preferred)
        pred = max_img.get("smoothed_class", "")
        species = pred.split(";")[-1]
        # Exclude if the species is 'human' (case-insensitive)
        if species in ["human", "blank"]:
            continue

        # Build clickable link (HTML <a> tag)
        # For CSV, just use the plain file name
        # if is_sas_url(image_base_dir):
        #     link = relative_sas_url(image_base_dir, file_name)
        # else:
        #     link = os.path.join(image_base_dir, file_name)
        # file_link = f'<a href="{link}">{file_name}</a>'
        rows.append([file_name, date, time, seq_id, species, max_count])
    # Write CSV
    csv_path = os.path.join(output_dir, csv_filename)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "date", "time", "seq_id", "species", "max_count"])
        writer.writerows(rows)
    print(f"Wrote sequence max detection CSV to {csv_path}")
