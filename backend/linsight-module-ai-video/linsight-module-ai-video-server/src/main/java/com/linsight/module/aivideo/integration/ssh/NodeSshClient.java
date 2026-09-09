package com.linsight.module.aivideo.integration.ssh;

import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentConnectionReqVO;

import java.util.function.Consumer;

public interface NodeSshClient {
    Connection connect(NodeDeploymentConnectionReqVO request, String trustedHostKey) throws Exception;

    interface Connection extends AutoCloseable {
        String execute(String command, String stdin) throws Exception;
        default String execute(String command, String stdin, Consumer<String> outputConsumer) throws Exception {
            String output = execute(command, stdin);
            if (outputConsumer != null && !output.isEmpty()) {
                outputConsumer.accept(output);
            }
            return output;
        }
        void upload(byte[] content, String remotePath) throws Exception;
        String hostKey();
        String hostKeyType();
        String hostKeyFingerprint();
        @Override void close();
    }
}
