import type { SourceStamp } from './frame-stamp';

interface TimelineMessage extends SourceStamp { rtpTimestamp: number; bufferMs: number }
type ClockReceiver = RTCRtpReceiver & {
  createEncodedStreams?: () => { readable: ReadableStream; writable: WritableStream };
  transform?: unknown;
};
type ScriptTransformConstructor = new (worker: Worker) => RTCRtpScriptTransform;

export class SourceClock {
  readonly stamps = new Map<number, SourceStamp & { bufferMs: number }>();
  streamId?: string;
  supported = false;
  private delayMs = 0;
  private frameKeys = new Map<string, SourceStamp | undefined>();
  private worker?: Worker;

  close() { this.worker?.terminate(); this.stamps.clear(); this.frameKeys.clear(); this.supported = false; }
  connect(receiver: RTCRtpReceiver) {
    const target = receiver as ClockReceiver;
    const Transform = (globalThis as unknown as { RTCRtpScriptTransform?: ScriptTransformConstructor }).RTCRtpScriptTransform;
    if (!Transform && !target.createEncodedStreams) return;
    const worker = new Worker(new URL('./source-clock.worker.ts', import.meta.url), { type: 'module' });
    worker.onmessage = ({ data }: MessageEvent<TimelineMessage>) => {
      if (!data.streamId || !Number.isSafeInteger(data.sourcePts) || !Number.isFinite(data.rtpTimestamp)) return;
      if (this.streamId !== data.streamId) { this.stamps.clear(); this.frameKeys.clear(); this.streamId = data.streamId; }
      if (data.frameKey) {
        const existing = this.frameKeys.get(data.frameKey);
        this.frameKeys.set(data.frameKey, this.frameKeys.has(data.frameKey) && existing?.sourcePts !== data.sourcePts ? undefined : data);
        if (this.frameKeys.size > 600) this.frameKeys.delete(this.frameKeys.keys().next().value!);
      }
      this.stamps.set(data.rtpTimestamp, { frameKey: data.frameKey, streamId: data.streamId,
        sourcePts: data.sourcePts, bufferMs: data.bufferMs });
      if (this.stamps.size > 300) this.stamps.delete(this.stamps.keys().next().value!);
    };
    if (Transform) target.transform = new Transform(worker);
    else {
      const streams = target.createEncodedStreams!();
      worker.postMessage(streams, [streams.readable, streams.writable]);
    }
    this.worker = worker; this.supported = true;
    worker.postMessage({ delayMs: this.delayMs });
  }

  locate(frameKey: string) { return this.frameKeys.get(frameKey); }
  read(rtpTimestamp: number) { return this.stamps.get(rtpTimestamp); }
  setDelay(delayMs: number) {
    this.delayMs = delayMs;
    this.worker?.postMessage({ delayMs });
  }
}
