"""Metadata inspection for images and PDFs.

Values are returned to the uploader (it is their own file) but only the keys
and labels are persisted.
"""

from __future__ import annotations

from PIL import ExifTags, Image

from app.detection.masking import mask_generic
from app.detection.types import MetadataFinding

_GPS_IFD = 0x8825
_EXIF_IFD = 0x8769


def _ratio(v) -> float:
    try:
        return float(v)
    except Exception:
        num, den = v
        return num / den if den else 0.0


def _dms_to_deg(dms, ref) -> float:
    d, m, s = (_ratio(x) for x in dms)
    deg = d + m / 60 + s / 3600
    return -deg if ref in ("S", "W", b"S", b"W") else deg


def inspect_image(img: Image.Image) -> list[MetadataFinding]:
    out: list[MetadataFinding] = []
    exif = img.getexif()
    base = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()}
    try:
        sub = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.get_ifd(_EXIF_IFD).items()}
    except Exception:
        sub = {}
    try:
        gps = {ExifTags.GPSTAGS.get(k, str(k)): v for k, v in exif.get_ifd(_GPS_IFD).items()}
    except Exception:
        gps = {}

    if gps:
        try:
            lat = _dms_to_deg(gps["GPSLatitude"], gps.get("GPSLatitudeRef", "N"))
            lon = _dms_to_deg(gps["GPSLongitude"], gps.get("GPSLongitudeRef", "E"))
            out.append(MetadataFinding("gps", "GPS location", f"{lat:.4f}, {lon:.4f}"))
        except Exception:
            out.append(MetadataFinding("gps", "GPS data", "present"))

    device = " ".join(str(base[k]).strip("\x00 ") for k in ("Make", "Model") if base.get(k))
    if device:
        out.append(MetadataFinding("device", "Device", device[:60]))
    if base.get("Software"):
        out.append(MetadataFinding("software", "Software", str(base["Software"]).strip("\x00 ")[:60]))
    if base.get("HostComputer"):
        out.append(MetadataFinding("host", "Computer name", str(base["HostComputer"]).strip("\x00 ")[:60]))
    taken = sub.get("DateTimeOriginal") or sub.get("DateTimeDigitized") or base.get("DateTime")
    if taken:
        out.append(MetadataFinding("timestamp", "Capture time", str(taken).strip("\x00 ")))
    for key, label in (("BodySerialNumber", "Camera serial number"), ("LensSerialNumber", "Lens serial number")):
        if sub.get(key):
            out.append(MetadataFinding("serial", label, mask_generic(str(sub[key]))))
    if sub.get("CameraOwnerName") or base.get("Artist"):
        out.append(MetadataFinding("owner", "Owner name", "present"))
    if sub.get("LensModel"):
        out.append(MetadataFinding("lens", "Lens", str(sub["LensModel"]).strip("\x00 ")[:60]))

    info = img.info or {}
    if any(k in info for k in ("xmp", "XML:com.adobe.xmp")):
        out.append(MetadataFinding("xmp", "XMP metadata", "present"))
    text_chunks = [k for k in getattr(img, "text", {}) or {} if k not in ("XML:com.adobe.xmp",)]
    if text_chunks:
        out.append(MetadataFinding("text", "Embedded text fields", f"{len(text_chunks)} field(s)"))
    if info.get("comment"):
        out.append(MetadataFinding("comment", "Comment", "present"))
    if exif and not out:
        out.append(MetadataFinding("exif", "EXIF data", f"{len(exif)} tag(s)"))
    return out


def inspect_pdf(doc) -> list[MetadataFinding]:
    out: list[MetadataFinding] = []
    meta = doc.metadata or {}
    for key, label in (
        ("author", "Author"), ("creator", "Creator application"), ("producer", "Producer"),
        ("title", "Title"), ("subject", "Subject"), ("keywords", "Keywords"),
    ):
        if meta.get(key):
            out.append(MetadataFinding(key, label, str(meta[key])[:60]))
    if meta.get("creationDate") or meta.get("modDate"):
        out.append(MetadataFinding("timestamp", "Created / modified dates", "present"))
    if doc.get_xml_metadata():
        out.append(MetadataFinding("xmp", "XMP metadata", "present"))

    annots = sum(len(list(p.annots() or [])) for p in doc)
    widgets = sum(len(list(p.widgets() or [])) for p in doc)
    links = sum(len(p.get_links()) for p in doc)
    if annots:
        out.append(MetadataFinding("annotations", "Comments and annotations", f"{annots}"))
    if widgets:
        out.append(MetadataFinding("forms", "Form fields", f"{widgets}"))
    if links:
        out.append(MetadataFinding("links", "Links", f"{links}"))
    if doc.embfile_count():
        out.append(MetadataFinding("attachments", "Embedded files", f"{doc.embfile_count()}"))
    return out
