import { normalizePreviewBuffer } from './preview-buffer';

/** Bounded receiver delay. Keep coded frames in order and recover a broken chain. */
export class EncodedVideoDelay<T extends { type: string }> {
  get size() {
    return this.queue.length;
  }
  private arrivalOrigin = 0;
  private closed = false;
  private delayMs = 0;
  private draining = false;
  private queue: Array<{ frame: T; received: number; timelineAt: number }> = [];
  private sourceOrigin?: number;
  private timer?: ReturnType<typeof setTimeout>;

  private waitingKeyframe = false;

  constructor(
    private forward: (frame: T, delayMs: number) => Promise<void>,
    private recover: () => void,
    private failed: () => void,
  ) {}

  close() {
    this.closed = true;
    this.reset();
  }

  offer(frame: T, sourceTimeMs?: number) {
    if (this.closed) return;
    if (this.queue.length >= 128) {
      this.reset();
      this.recover();
    }
    if (this.waitingKeyframe && frame.type !== 'key') return;
    this.waitingKeyframe = false;
    const received = performance.now();
    if (sourceTimeMs !== undefined && this.sourceOrigin === undefined) {
      this.sourceOrigin = sourceTimeMs;
      this.arrivalOrigin = received;
    }
    let timelineAt =
      sourceTimeMs === undefined
        ? received
        : this.arrivalOrigin + sourceTimeMs - this.sourceOrigin!;
    if (sourceTimeMs !== undefined && timelineAt > received) {
      // A late first frame must not leave a permanent extra delay after the
      // source catches up. Move the whole pending timeline together to retain
      // frame order and source cadence, capped by the viewer's selected delay.
      const adjustment = timelineAt - received;
      this.arrivalOrigin -= adjustment;
      for (const item of this.queue) item.timelineAt -= adjustment;
      timelineAt = received;
    }
    this.queue.push({ frame, received, timelineAt });
    this.schedule();
  }

  reset() {
    this.queue = [];
    this.sourceOrigin = undefined;
    this.waitingKeyframe = true;
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
  }

  setDelay(delayMs: number) {
    this.delayMs = normalizePreviewBuffer(delayMs);
    this.schedule();
  }

  private deadline(item: { received: number; timelineAt: number }) {
    // Pace buffered frames by source PTS, not by possibly bursty network arrivals.
    return this.delayMs ? item.timelineAt + this.delayMs : item.received;
  }

  private async drain() {
    this.draining = true;
    try {
      while (
        !this.closed &&
        this.queue[0] &&
        performance.now() >= this.deadline(this.queue[0])
      ) {
        const item = this.queue.shift()!;
        await this.forward(item.frame, performance.now() - item.received);
      }
    } catch {
      this.close();
      this.failed();
    } finally {
      this.draining = false;
      this.schedule();
    }
  }

  private schedule() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
    if (this.closed || this.draining || !this.queue[0]) return;
    const wait = Math.max(0, this.deadline(this.queue[0]) - performance.now());
    this.timer = setTimeout(() => {
      this.timer = undefined;
      void this.drain();
    }, wait);
  }
}
