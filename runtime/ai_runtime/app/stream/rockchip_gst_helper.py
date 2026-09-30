"""System-Python GStreamer worker for Rockchip MPP decode and RGA conversion.

This file intentionally uses only the standard library and distro PyGObject.  The
application venv stays isolated while the vendor GStreamer plugin remains owned by
the board image.  H.264 access units arrive on stdin; JPEG frames and their source
PTS leave on stdout.  Camera credentials never enter this process.
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import threading
from fractions import Fraction

PACKET_HEADER = struct.Struct(">4sIqqqB")
FRAME_HEADER = struct.Struct(">4sIq")
PACKET_MAGIC = b"LPKT"
FRAME_MAGIC = b"LFRM"
MAX_PACKET_BYTES = 32 * 1024 * 1024


def _read_exact(stream, size: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < size:
        value = stream.read(size - len(chunks))
        if not value:
            raise EOFError
        chunks.extend(value)
    return bytes(chunks)


def _write_all(descriptor: int, value: bytes) -> None:
    view = memoryview(value)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise BrokenPipeError
        view = view[written:]


def _gstreamer():
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import GLib, Gst

    Gst.init(None)
    return GLib, Gst


def probe() -> int:
    try:
        _, Gst = _gstreamer()
        required = (
            "appsrc",
            "h264parse",
            "mppvideodec",
            "videorate",
            "jpegenc",
            "appsink",
        )
        if not all(Gst.ElementFactory.find(name) for name in required):
            return 1
        if not os.access("/dev/mpp_service", os.R_OK | os.W_OK):
            return 1
        if not os.access("/dev/rga", os.R_OK | os.W_OK):
            return 1
        print("ROCKCHIP_MPP_RGA", flush=True)
        return 0
    except Exception as error:  # noqa: BLE001 - isolated capability probe
        print(f"probe failed: {type(error).__name__}", file=sys.stderr, flush=True)
        return 1


def run(width: int, height: int, fps: Fraction, source_fps: Fraction | None,
        jpeg_quality: int) -> int:
    # Vendor MPP/RGA libraries sometimes print version text to stdout.  Preserve a
    # private protocol descriptor, then redirect process stdout to diagnostics so
    # those native messages can never corrupt the binary frame stream.
    protocol_fd = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    GLib, Gst = _gstreamer()
    pipeline = Gst.Pipeline.new("linsight-rockchip-capture")
    names = (
        "appsrc",
        "h264parse",
        "mppvideodec",
        "videorate",
        "capsfilter",
        "jpegenc",
        "appsink",
    )
    elements = {name: Gst.ElementFactory.make(name, name) for name in names}
    if not pipeline or not all(elements.values()):
        print("required GStreamer element is unavailable", file=sys.stderr, flush=True)
        os.close(protocol_fd)
        return 2

    source = elements["appsrc"]
    decoder = elements["mppvideodec"]
    rate = elements["videorate"]
    capsfilter = elements["capsfilter"]
    jpeg = elements["jpegenc"]
    sink = elements["appsink"]

    source.set_property("is-live", True)
    source.set_property("block", True)
    source.set_property("format", Gst.Format.TIME)
    source_caps = "video/x-h264,stream-format=byte-stream,alignment=au"
    if source_fps is not None:
        source_caps += f",framerate={source_fps.numerator}/{source_fps.denominator}"
    source.set_property("caps", Gst.Caps.from_string(source_caps))
    decoder.set_property("fast-mode", True)
    # Keep decoded frames in NV12 until videorate has discarded the frames that
    # analysis will not use.  Converting every full-resolution frame to RGB
    # before sampling overwhelmed the four-camera capture pipeline.
    decoder.set_property("format", 23)
    if width > 0:
        decoder.set_property("width", width)
    if height > 0:
        decoder.set_property("height", height)
    rate.set_property("drop-only", True)
    rate.set_property("max-rate", max(1, (fps.numerator + fps.denominator - 1) // fps.denominator))
    capsfilter.set_property(
        "caps",
        Gst.Caps.from_string(
            f"video/x-raw,format=NV12,framerate={fps.numerator}/{fps.denominator}"
        ),
    )
    # The vendor MPP JPEG encoder can spin in gst_mpp_enc_convert under four
    # concurrent streams.  jpegenc accepts NV12 directly, so color conversion is
    # not needed and JPEG encoding only touches sampled frames.
    jpeg.set_property("quality", jpeg_quality)
    sink.set_property("emit-signals", True)
    sink.set_property("sync", False)
    sink.set_property("max-buffers", 2)
    sink.set_property("drop", True)

    for element in elements.values():
        pipeline.add(element)
    ordered = [elements[name] for name in names]
    if not all(left.link(right) for left, right in zip(ordered, ordered[1:], strict=False)):
        print("GStreamer MPP/RGA pipeline could not be linked", file=sys.stderr, flush=True)
        os.close(protocol_fd)
        return 2

    output_lock = threading.Lock()

    def emit_frame(appsink):
        sample = appsink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR
        buffer = sample.get_buffer()
        ok, mapped = buffer.map(Gst.MapFlags.READ)
        if not ok:
            return Gst.FlowReturn.ERROR
        try:
            payload = bytes(mapped.data)
            pts = (
                -1
                if buffer.pts == Gst.CLOCK_TIME_NONE
                else round(buffer.pts * 90_000 / Gst.SECOND)
            )
            header = FRAME_HEADER.pack(FRAME_MAGIC, len(payload), pts)
            with output_lock:
                _write_all(protocol_fd, header)
                _write_all(protocol_fd, payload)
        except (BrokenPipeError, OSError):
            return Gst.FlowReturn.ERROR
        finally:
            buffer.unmap(mapped)
        return Gst.FlowReturn.OK

    sink.connect("new-sample", emit_frame)
    loop = GLib.MainLoop()
    failed = threading.Event()
    bus = pipeline.get_bus()
    bus.add_signal_watch()

    def bus_message(_bus, message):
        if message.type == Gst.MessageType.ERROR:
            error, _debug = message.parse_error()
            print(f"GStreamer MPP/RGA error: {error.message}", file=sys.stderr, flush=True)
            failed.set()
            loop.quit()
        elif message.type == Gst.MessageType.EOS:
            loop.quit()

    bus.connect("message", bus_message)

    def feed_packets() -> None:
        try:
            while True:
                header = _read_exact(sys.stdin.buffer, PACKET_HEADER.size)
                magic, length, pts, dts, _timestamp_millis, _keyframe = PACKET_HEADER.unpack(header)
                if magic != PACKET_MAGIC or length > MAX_PACKET_BYTES:
                    raise ValueError("invalid packet envelope")
                payload = _read_exact(sys.stdin.buffer, length)
                buffer = Gst.Buffer.new_allocate(None, length, None)
                buffer.fill(0, payload)
                buffer.pts = Gst.util_uint64_scale(pts, Gst.SECOND, 90_000)
                if dts >= 0:
                    buffer.dts = Gst.util_uint64_scale(dts, Gst.SECOND, 90_000)
                result = source.emit("push-buffer", buffer)
                if result != Gst.FlowReturn.OK:
                    raise RuntimeError(f"appsrc rejected packet: {result.value_nick}")
        except EOFError:
            source.emit("end-of-stream")
        except Exception as error:  # noqa: BLE001 - isolated worker reports then exits
            print(f"packet feed failed: {type(error).__name__}", file=sys.stderr, flush=True)
            failed.set()
            GLib.idle_add(loop.quit)

    state = pipeline.set_state(Gst.State.PLAYING)
    if state == Gst.StateChangeReturn.FAILURE:
        print("GStreamer MPP/RGA pipeline failed to start", file=sys.stderr, flush=True)
        os.close(protocol_fd)
        return 2
    feeder = threading.Thread(target=feed_packets, name="h264-packet-feed", daemon=True)
    feeder.start()
    print(
        f"captureBackend=ROCKCHIP_MPP_RGA output={width or 'source'}x{height or 'source'} "
        f"fps={fps.numerator}/{fps.denominator}",
        file=sys.stderr,
        flush=True,
    )
    try:
        loop.run()
    finally:
        pipeline.set_state(Gst.State.NULL)
        bus.remove_signal_watch()
        os.close(protocol_fd)
    return 2 if failed.is_set() else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--width", type=int, default=0)
    parser.add_argument("--height", type=int, default=0)
    parser.add_argument("--fps", default="4")
    parser.add_argument("--source-fps")
    parser.add_argument("--jpeg-quality", type=int, default=95)
    args = parser.parse_args()
    if args.probe:
        return probe()
    fps = Fraction(args.fps).limit_denominator(1000)
    source_fps = (
        Fraction(args.source_fps).limit_denominator(1000)
        if args.source_fps is not None else None
    )
    if (not 0 < fps <= 25 or (source_fps is not None and not 0 < source_fps <= 120)
            or not 1 <= args.jpeg_quality <= 100):
        return 64
    return run(max(0, args.width), max(0, args.height), fps, source_fps,
               args.jpeg_quality)


if __name__ == "__main__":
    raise SystemExit(main())
