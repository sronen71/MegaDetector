import os
import csv
from collections import defaultdict
import datetime

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
    csv_filename="sequence_max_detections.csv",
    confidence_threshold=0.0,
    include_all=False,
):
    """
    For each sequence (seq_id), find the image with the largest number of detections.
    Write a CSV with columns: file_name, date, time, seq_id, species, max_count, start_time, end_time, duration.
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
        # Skip this sequence if the top detection in any image is a person
        discard_sequence = False
        for im in group:
            detections = im.get("detections", [])
            if detections:
                top_det = max(detections, key=lambda d: d.get("conf", 0.0))
                if top_det.get("category") == "2":
                    discard_sequence = True
                    break
        if discard_sequence:
            continue
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
        excluding = {"human", "blank"}
        if species in excluding and not include_all:
            continue

        # --- New: Compute start_time, end_time, duration for the sequence ---
        datetimes = []
        for im in group:
            dt_str = im.get("datetime", "")
            if dt_str and "T" in dt_str:
                dt_base = dt_str.split(".")[0]  # Remove microseconds if present
                try:
                    dt_obj = datetime.datetime.strptime(dt_base, "%Y-%m-%dT%H:%M:%S")
                    datetimes.append(dt_obj)
                except Exception:
                    pass
        if datetimes:
            start_time = min(datetimes)
            end_time = max(datetimes)
            duration_td = end_time - start_time
            duration_seconds = int(duration_td.total_seconds())
            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S")
        else:
            start_time_str = end_time_str = ""
            duration_seconds = ""
        # ---------------------------------------------------------------

        rows.append(
            [
                file_name,
                date,
                time,
                seq_id,
                species,
                max_count,
                start_time_str,
                end_time_str,
                duration_seconds,
            ]
        )
    # Write CSV
    csv_path = os.path.join(output_dir, csv_filename)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "file_name",
                "date",
                "time",
                "seq_id",
                "species",
                "max_count",
                "start_time",
                "end_time",
                "duration_seconds",
            ]
        )
        writer.writerows(rows)
    print(f"Wrote sequence max detection CSV to {csv_path}")


def sequence_max_csv_to_html_table(csv_path, image_base_dir=None):
    """
    Reads the sequence max detection CSV and returns an HTML table string.
    Returns an empty string if the file does not exist or is empty.
    If image_base_dir is provided, makes file names clickable links.
    """
    if not os.path.exists(csv_path):
        return ""
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return ""
    table_html = (
        "<h3>Sequence Max Detection Table</h3>"
        '<div class="contentdiv">'
        '<table border="1" style="border-collapse:collapse;">'
        "<tr>" + "".join(f"<th>{cell}</th>" for cell in rows[0]) + "</tr>"
    )
    # Find the file_name column index
    file_col_idx = 0
    for i, col in enumerate(rows[0]):
        if col.strip().lower() == "file_name":
            file_col_idx = i
            break
    for row in rows[1:]:
        table_html += "<tr>"
        for j, cell in enumerate(row):
            if j == file_col_idx and image_base_dir is not None:
                # Build the link
                file_name = cell
                link = None
                if is_sas_url(image_base_dir):
                    link = relative_sas_url(image_base_dir, file_name)
                else:
                    link = os.path.join(image_base_dir, file_name)
                cell_html = f'<a href="{link}">{file_name}</a>'
            else:
                cell_html = cell
            table_html += f"<td>{cell_html}</td>"
        table_html += "</tr>"
    table_html += "</table></div>"
    return table_html
