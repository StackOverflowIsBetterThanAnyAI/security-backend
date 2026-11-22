import struct

# rpicam-jpeg embeds a small preview in the EXIF data of every image
# (--thumb in capture_images.py). Reading it needs only the first few kilobytes
# of the file and no image library, which matters on the Pi Zero.
EXIF_READ_LIMIT = 128 * 1024

TAG_THUMBNAIL_OFFSET = 0x0201
TAG_THUMBNAIL_LENGTH = 0x0202


def _find_exif_segment(data):
    if data[:2] != b"\xff\xd8":
        return None
    position = 2
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            return None
        marker = data[position + 1]
        if marker == 0xDA:
            return None
        length = struct.unpack(">H", data[position + 2 : position + 4])[0]
        segment_start = position + 4
        segment_end = position + 2 + length
        if (
            marker == 0xE1
            and data[segment_start : segment_start + 6] == b"Exif\x00\x00"
        ):
            return data[segment_start + 6 : segment_end]
        position = segment_end
    return None


def _thumbnail_from_tiff(tiff):
    byte_order = tiff[:2]
    if byte_order == b"II":
        prefix = "<"
    elif byte_order == b"MM":
        prefix = ">"
    else:
        return None

    def read(fmt, offset):
        return struct.unpack_from(prefix + fmt, tiff, offset)[0]

    ifd0 = read("I", 4)
    ifd0_entries = read("H", ifd0)
    ifd1 = read("I", ifd0 + 2 + ifd0_entries * 12)
    if ifd1 == 0:
        return None

    offset = length = None
    for index in range(read("H", ifd1)):
        entry = ifd1 + 2 + index * 12
        tag = read("H", entry)
        if tag == TAG_THUMBNAIL_OFFSET:
            offset = read("I", entry + 8)
        elif tag == TAG_THUMBNAIL_LENGTH:
            length = read("I", entry + 8)

    if not offset or not length:
        return None
    thumbnail = tiff[offset : offset + length]
    if len(thumbnail) != length or thumbnail[:2] != b"\xff\xd8":
        return None
    return thumbnail


def read_thumbnail(path):
    """Return the embedded JPEG preview of an image, or None if it has none."""
    try:
        with open(path, "rb") as f:
            data = f.read(EXIF_READ_LIMIT)
        tiff = _find_exif_segment(data)
        return _thumbnail_from_tiff(tiff) if tiff else None
    except (OSError, struct.error):
        return None
