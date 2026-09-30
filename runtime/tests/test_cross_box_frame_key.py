from uuid import uuid4

from ai_runtime.app.stream.frame_stamp import h264_frame_key, stamp_h264


def test_content_key_ignores_transport_prefix_and_auxiliary_nals():
    vcl = b"\x65\x88\x84\x21"
    a = b"\0\0\0\1" + vcl
    b = b"\0\0\1\x67\x42\x00\x1e\0\0\1" + vcl
    c = len(vcl).to_bytes(4, "big") + vcl
    assert h264_frame_key(a) == h264_frame_key(b) == h264_frame_key(c)
    assert h264_frame_key(a) != h264_frame_key(a + b"\x12")
    key = h264_frame_key(a)
    assert key and len(key) == 32
    assert h264_frame_key(stamp_h264(a, str(uuid4()), 9000, key)) == key


def test_malformed_or_metadata_only_packets_have_no_cross_box_identity():
    assert h264_frame_key(b"\0\0\0\1\x67\x42\x01") is None
    assert h264_frame_key(b"garbage") is None
