import { EncodedVideoDelay } from './encoded-video-delay';
import { readSourceStamp } from './frame-stamp';

interface EncodedFrame {
  data: ArrayBuffer;
  getMetadata: () => { rtpTimestamp?: number };
  timestamp: number;
  type: string;
}
interface FrameStreams {
  readable: ReadableStream<EncodedFrame>;
  writable: WritableStream<EncodedFrame>;
  sendKeyFrameRequest?: () => Promise<void>;
}
const worker = globalThis as unknown as {
  onmessage: (event: MessageEvent<FrameStreams | { delayMs: number }>) => void;
  onrtctransform: (event: { transformer: FrameStreams }) => void;
  postMessage: (message: unknown) => void;
};
let requestedDelay = 0;
let activeDelay: EncodedVideoDelay<EncodedFrame> | undefined;

function forward(streams: FrameStreams) {
  const writer = streams.writable.getWriter();
  let streamId: string | undefined;
  const delay = new EncodedVideoDelay<EncodedFrame>(async (frame, bufferMs) => {
    const stamp = readSourceStamp(frame.data);
    if (stamp) worker.postMessage({ ...stamp, bufferMs,
      rtpTimestamp: frame.getMetadata().rtpTimestamp ?? frame.timestamp });
    await writer.write(frame);
  }, () => { void streams.sendKeyFrameRequest?.().catch(() => undefined); },
  () => worker.postMessage({ closed: true }));
  activeDelay?.close(); activeDelay = delay; delay.setDelay(requestedDelay);
  void streams.readable.pipeTo(new WritableStream<EncodedFrame>({
    write(frame) {
      try {
        const stamp = readSourceStamp(frame.data);
        if (stamp && stamp.streamId !== streamId) {
          if (streamId) delay.reset();
          streamId = stamp.streamId;
        }
        delay.offer(frame, stamp ? stamp.sourcePts / 90 : undefined);
      } catch {
        worker.postMessage({ error: 'CLOCK_FRAME_INVALID' });
      }
    },
    close() { delay.close(); void writer.close().catch(() => undefined); },
    abort() { delay.close(); void writer.abort().catch(() => undefined); },
  })).catch(() => { delay.close(); worker.postMessage({ closed: true }); });
}
worker.onrtctransform = event => forward(event.transformer);
worker.onmessage = event => {
  if ('delayMs' in event.data) {
    requestedDelay = event.data.delayMs;
    activeDelay?.setDelay(requestedDelay);
  } else forward(event.data);
};
