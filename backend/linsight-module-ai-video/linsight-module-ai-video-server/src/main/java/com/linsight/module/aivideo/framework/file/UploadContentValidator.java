package com.linsight.module.aivideo.framework.file;

/** Content-based checks for untrusted files before they reach object storage. */
public final class UploadContentValidator {
    private static final byte[] PNG = {(byte) 0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a};
    private static final byte[] ELF = {0x7f, 0x45, 0x4c, 0x46};

    private UploadContentValidator() {}

    public static String safeFileName(String candidate, String fallback) {
        String value = candidate == null || candidate.isBlank() ? fallback : candidate.trim();
        if (value.length() > 255 || value.contains("/") || value.contains("\\")
                || value.contains("..") || value.chars().anyMatch(character -> character < 32 || character == 127)) {
            throw new IllegalArgumentException("unsafe file name");
        }
        return value;
    }

    public static String detectImageContentType(byte[] content) {
        if (content.length >= 3 && unsigned(content[0]) == 0xff && unsigned(content[1]) == 0xd8
                && unsigned(content[2]) == 0xff) return "image/jpeg";
        if (startsWith(content, PNG)) return "image/png";
        if (content.length >= 12 && ascii(content, 0, "RIFF") && ascii(content, 8, "WEBP")) {
            return "image/webp";
        }
        return null;
    }

    public static boolean isMp4(byte[] content) {
        return content.length >= 12 && ascii(content, 4, "ftyp");
    }

    public static boolean isGzip(byte[] content) {
        return content.length >= 10 && unsigned(content[0]) == 0x1f
                && unsigned(content[1]) == 0x8b && unsigned(content[2]) == 0x08;
    }

    public static boolean matchesModelFormat(String format, byte[] content) {
        if (content.length < 4 || looksExecutableOrScript(content)) return false;
        return switch (format) {
            case "ONNX" -> isOnnxModelProto(content);
            case "TORCHSCRIPT", "ARCHIVE" -> isZip(content);
            case "PYTORCH" -> isZip(content) || unsigned(content[0]) == 0x80;
            case "RKNN" -> ascii(content, 0, "RKNN");
            case "TENSORRT" -> content.length >= 32 && !isZip(content) && !isGzip(content);
            default -> false;
        };
    }

    private static boolean looksExecutableOrScript(byte[] content) {
        return ascii(content, 0, "MZ") || startsWith(content, ELF)
                || ascii(content, 0, "#!")
                || (content.length >= 4 && SetOfMachOMagic.matches(content));
    }

    private static boolean isZip(byte[] content) {
        return content.length >= 4 && unsigned(content[0]) == 0x50 && unsigned(content[1]) == 0x4b
                && SetOfZipSignatures.matches(content);
    }

    /** Minimal top-level protobuf scan: ONNX ModelProto requires ir_version(1) and graph(7). */
    private static boolean isOnnxModelProto(byte[] content) {
        int[] offset = {0};
        boolean irVersion = false;
        boolean graph = false;
        try {
            while (offset[0] < content.length) {
                long tag = readVarint(content, offset);
                int field = (int) (tag >>> 3);
                int wire = (int) (tag & 7);
                if (field <= 0) return false;
                if (field == 1 && wire == 0) irVersion = true;
                if (field == 7 && wire == 2) graph = true;
                skipField(content, offset, wire);
            }
            return irVersion && graph;
        } catch (IllegalArgumentException ignored) {
            return false;
        }
    }

    private static void skipField(byte[] content, int[] offset, int wire) {
        switch (wire) {
            case 0 -> readVarint(content, offset);
            case 1 -> advance(content, offset, 8);
            case 2 -> {
                long length = readVarint(content, offset);
                if (length > Integer.MAX_VALUE) throw new IllegalArgumentException("field too large");
                advance(content, offset, (int) length);
            }
            case 5 -> advance(content, offset, 4);
            default -> throw new IllegalArgumentException("unsupported protobuf wire type");
        }
    }

    private static long readVarint(byte[] content, int[] offset) {
        long value = 0;
        for (int shift = 0; shift < 64; shift += 7) {
            if (offset[0] >= content.length) throw new IllegalArgumentException("truncated varint");
            int current = unsigned(content[offset[0]++]);
            value |= (long) (current & 0x7f) << shift;
            if ((current & 0x80) == 0) return value;
        }
        throw new IllegalArgumentException("varint too long");
    }

    private static void advance(byte[] content, int[] offset, int length) {
        if (length < 0 || offset[0] > content.length - length) {
            throw new IllegalArgumentException("truncated field");
        }
        offset[0] += length;
    }

    private static boolean startsWith(byte[] content, byte[] prefix) {
        if (content.length < prefix.length) return false;
        for (int index = 0; index < prefix.length; index++) {
            if (content[index] != prefix[index]) return false;
        }
        return true;
    }

    private static boolean ascii(byte[] content, int offset, String expected) {
        if (content.length < offset + expected.length()) return false;
        for (int index = 0; index < expected.length(); index++) {
            if (unsigned(content[offset + index]) != expected.charAt(index)) return false;
        }
        return true;
    }

    private static int unsigned(byte value) {
        return value & 0xff;
    }

    private enum SetOfZipSignatures {
        INSTANCE;

        static boolean matches(byte[] content) {
            int third = unsigned(content[2]);
            int fourth = unsigned(content[3]);
            return (third == 0x03 && fourth == 0x04) || (third == 0x05 && fourth == 0x06)
                    || (third == 0x07 && fourth == 0x08);
        }
    }

    private enum SetOfMachOMagic {
        INSTANCE;

        static boolean matches(byte[] content) {
            long magic = ((long) unsigned(content[0]) << 24) | ((long) unsigned(content[1]) << 16)
                    | ((long) unsigned(content[2]) << 8) | unsigned(content[3]);
            return magic == 0xfeedfaceL || magic == 0xcefaedfeL || magic == 0xfeedfacfL
                    || magic == 0xcffaedfeL || magic == 0xcafebabeL || magic == 0xbebafecaL;
        }
    }
}
