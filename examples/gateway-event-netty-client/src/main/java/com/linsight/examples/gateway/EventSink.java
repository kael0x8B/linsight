package com.linsight.examples.gateway;

/**
 * 事件处理扩展点。生产实现应使用 {@link GatewayEvent#sourceEventId()} 做幂等去重，
 * 并在业务事务完成后才正常返回；失败必须抛出异常，让客户端停止处理当前事件。
 */
@FunctionalInterface
public interface EventSink {
    /** 处理一条事件，包括识别结果和图片；方法返回表示本地处理已成功完成。 */
    void accept(GatewayEvent event) throws Exception;
}
