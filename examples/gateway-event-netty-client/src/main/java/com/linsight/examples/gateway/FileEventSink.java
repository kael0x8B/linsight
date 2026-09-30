package com.linsight.examples.gateway;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;

/**
 * 示例事件处理器：按 sourceEventId 保存 JPG 图片和 JSON 元数据。
 * 同一事件重复出现时复用已有文件；生产系统可将此类替换为数据库或消息队列处理器。
 */
public final class FileEventSink implements EventSink {
    private final Path directory;
    private final ObjectMapper mapper;

    public FileEventSink(Path directory, ObjectMapper mapper) throws IOException {
        this.directory = directory.toAbsolutePath().normalize();
        this.mapper = mapper;
        Files.createDirectories(this.directory);
        try {
            // 图片和识别内容可能包含敏感数据，支持 POSIX 权限的系统仅允许当前用户访问。
            Files.setPosixFilePermissions(this.directory, PosixFilePermissions.fromString("rwx------"));
        } catch (UnsupportedOperationException ignored) {
            // Windows 等文件系统没有 POSIX 权限接口。
        }
    }

    @Override
    public void accept(GatewayEvent event) throws IOException {
        Path image = directory.resolve(event.sourceEventId() + ".jpg");
        Path metadata = directory.resolve(event.sourceEventId() + ".json");
        if (Files.isRegularFile(image) && Files.isRegularFile(metadata)) {
            return; // 两个文件都存在时视为已经处理，避免重复写入。
        }
        // 先写图片再写元数据；中途失败时可重新处理相同 sourceEventId。
        atomicWrite(image, event.jpeg());
        atomicWrite(metadata, mapper.writerWithDefaultPrettyPrinter()
                .writeValueAsString(event.metadata()).getBytes(StandardCharsets.UTF_8));
    }

    /** 同目录临时文件写入并强制刷盘，再重命名为目标文件，避免留下半写入内容。 */
    static void atomicWrite(Path target, byte[] bytes) throws IOException {
        Path temporary = Files.createTempFile(target.getParent(), ".event-", ".tmp");
        try {
            try {
                Files.setPosixFilePermissions(temporary, PosixFilePermissions.fromString("rw-------"));
            } catch (UnsupportedOperationException ignored) {
                // Windows 等文件系统没有 POSIX 权限接口。
            }
            try (FileChannel channel = FileChannel.open(temporary, StandardOpenOption.WRITE)) {
                ByteBuffer buffer = ByteBuffer.wrap(bytes);
                while (buffer.hasRemaining()) {
                    channel.write(buffer);
                }
                channel.force(true);
            }
            try {
                Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException error) {
                // 文件系统不支持原子重命名时回退。
                Files.move(temporary, target, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }
}
