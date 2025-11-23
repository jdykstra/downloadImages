import os
import stat
import sys
import shutil
from progressbar import ProgressBar, GranularBar, AdaptiveTransferSpeed, AbsoluteETA
from .sourceimages import STILL_FILE_TYPES, SourceImage


# Tweak the AbsoluteETA widget to only show the time part of the time and date.
class _CustomAbsoluteEta(AbsoluteETA):

    def __call__(self, progress, data, format=None):
        eta = super().__call__(progress, data, format)
        eta = str(data['eta'])
        return 'ETA: %s' % eta[-8:]


class _ProgressTracker():

    def __init__(self, total):
        self.already_copied = 0
        self.bar = ProgressBar(max_value=total, widgets=[AdaptiveTransferSpeed(), " ", GranularBar(), " ",
                        _CustomAbsoluteEta(format='ETA: %(eta)s', format_finished='ETA: %(ow)s', format_not_started='ETA: --:--')])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def update(self, copied):
        self.already_copied += copied
        self.bar.update(self.already_copied)


# Copy a file while updating progress on the screen.
# We originally used shutil.copy2(), which takes advantage of OS-specific optimizations,
# but doesn't provide progress feedback.
# Tests of this version on Mac OS with an external flash drive showed equivalent performance.
def _copy_with_progress(src_file: str, dst_file: str, image_name: str, tracker) -> None:
    try:
        with open(src_file, 'rb') as src, open(dst_file, 'wb') as dst:
            while True:
                buf = src.read(1024 * 1024)  # Read file in chunks of 1MB
                if not buf:
                    break
                dst.write(buf)
                tracker.update(len(buf))
        shutil.copystat(src_file, dst_file)
    except Exception as e:
        print(f"Deleting suspect destination file {dst_file} due to error.")
        try:
            os.remove(dst_file)
        except Exception:
            pass  # Ignore exceptions from os.remove()
        raise e


# Copy the image files from the source to the destination and create a XMP sidecar file for each.
def copy_image_files(
    images: dict[str, 'SourceImage'],
    destination_dirs: list[str],
    description: str,
    total_to_transfer: int,
    download_locked_only: bool = False,
    delete_src: bool = False
) -> int:

    already_copied = 0
    skipped_count = 0
    with _ProgressTracker(len(destination_dirs) * total_to_transfer) as tracker:
        for image_name in iter(images):
            image = images[image_name]
            for dest in destination_dirs:
                for extension in image.extensions:
                    src_full_path = os.path.join(
                        image.src_path, image.src_filename + "." + extension)
                    dst_full_path = os.path.join(dest, image.dst_filename + "." + extension)

                    # Check if destination file already exists and has the same size
                    skip_copy = False
                    if os.path.exists(dst_full_path):
                        dst_size = os.stat(dst_full_path).st_size
                        if image.size == dst_size:
                            skip_copy = True
                            skipped_count += 1

                    # Copy the image file unless it's a duplicate.  If we're only copying locked files, skip unlocked files.
                    if not skip_copy and (not download_locked_only or image.file_locked):
                        _copy_with_progress(
                            src_full_path, dst_full_path, image_name, tracker)

                    # If write protect was set on the source file, clear it on the destination.  We'll
                    # treat it specially below when we create the XMP sidecar file.  If we're going
                    # to delete the source file, also clear write protect on it.
                    # ?? This is slightly unsafe, since we'll lose the locked indication on the source
                    # ?? if we crash before deleting it.
                    if image.file_locked and not skip_copy:
                        if 'darwin' in sys.platform:
                            os.chflags(dst_full_path, os.stat(
                                dst_full_path).st_flags & ~stat.UF_IMMUTABLE)
                            if delete_src:
                                os.chflags(src_full_path, os.stat(
                                    src_full_path).st_flags & ~stat.UF_IMMUTABLE)
                        else:
                            os.chmod(dst_full_path, stat.S_IWRITE)
                            if delete_src:
                                os.chmod(src_full_path, stat.S_IWRITE)

                    # Create the sidecar file for stills only.
                    if extension.upper() in STILL_FILE_TYPES and not skip_copy:
                        xmp_label = "     xmp:Label=\"Purple\"\n" if image.file_locked else ""
                        xmp_content = f"""<x:xmpmeta xmlns:x=\"adobe:ns:meta/\">
<rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">

<rdf:Description rdf:about=\"\"
    xmlns:xmp=\"http://ns.adobe.com/xap/1.0/\"
    xmlns:dc=\"http://purl.org/dc/elements/1.1/\"
{xmp_label}     >
    <dc:description>
    <rdf:Alt>
    <rdf:li xml:lang=\"x-default\">{description}&#xA;</rdf:li>
    </rdf:Alt>
</dc:description>
</rdf:Description>

</rdf:RDF>
</x:xmpmeta>
"""
                        with open(os.path.join(dest, image.dst_filename + ".xmp"), "w") as sidecar:
                            sidecar.write(xmp_content)
            already_copied += image.size

    sys.stdout.write("\n")      # Needed after progress bar output
    sys.stdout.flush()

    return skipped_count



