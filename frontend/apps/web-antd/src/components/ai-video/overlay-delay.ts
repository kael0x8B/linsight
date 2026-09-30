/** Match video to observed result delivery latency; never move boxes onto newer frames. */
export class OverlayDelay {
  cadenceMs = 250;
  delayMs = 800;
  deliveryLagMs = 0;
  private identity?: string;
  private intervals: number[] = [];
  private lastAdjustment = 0;
  private lastPts?: number;
  private samples: number[] = [];

  observe(
    identity: string,
    resultPts: number,
    displayedPts: number,
    actualBufferMs: number,
    now: number,
  ) {
    if (identity !== this.identity) {
      this.reset();
      this.identity = identity;
    }
    if (
      ![resultPts, displayedPts, actualBufferMs, now].every((value) =>
        Number.isFinite(value),
      )
    )
      return this.delayMs;
    // Both PTS values come from the same source stream. Add the next tracking
    // anchor's delivery margin; wall clocks on the camera, node and browser may differ.
    const lag = actualBufferMs + (displayedPts - resultPts) / 90;
    if (lag < -100 || lag > 10_000) return this.delayMs;
    if (this.lastPts !== undefined && resultPts <= this.lastPts)
      return this.delayMs;
    const interval =
      this.lastPts === undefined ? undefined : (resultPts - this.lastPts) / 90;
    this.lastPts = resultPts;
    if (interval !== undefined && interval <= 2000) {
      this.intervals.push(interval);
      if (this.intervals.length > 24) this.intervals.shift();
      const cadence = [...this.intervals].toSorted((a, b) => a - b);
      this.cadenceMs = Math.max(
        250,
        Math.min(1000, cadence[Math.ceil((cadence.length - 1) * 0.9)]!),
      );
    }
    this.deliveryLagMs = Math.max(0, lag);
    this.samples.push(this.deliveryLagMs);
    if (this.samples.length > 24) this.samples.shift();
    const sorted = [...this.samples].toSorted((a, b) => a - b);
    const target = Math.max(
      600,
      Math.min(
        1800,
        Math.ceil(
          (sorted[Math.floor((sorted.length - 1) * 0.9)]! + this.cadenceMs) /
            100,
        ) * 100,
      ),
    );
    if (now - this.lastAdjustment < 1000) return this.delayMs;
    if (
      target > this.delayMs ||
      (this.samples.length >= 12 && target < this.delayMs - 200)
    ) {
      this.delayMs = target > this.delayMs ? target : this.delayMs - 100;
      this.lastAdjustment = now;
    }
    return this.delayMs;
  }

  reset() {
    this.delayMs = 800;
    this.samples = [];
    this.identity = undefined;
    this.lastAdjustment = 0;
    this.lastPts = undefined;
    this.intervals = [];
    this.cadenceMs = 250;
    this.deliveryLagMs = 0;
  }
}
