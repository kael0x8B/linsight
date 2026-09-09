/** Match video to observed result delivery latency; never move boxes onto newer frames. */
export class OverlayDelay {
  delayMs = 800;
  private samples: number[] = [];
  private identity?: string;
  private lastAdjustment = 0;

  reset() { this.delayMs = 800; this.samples = []; this.identity = undefined; this.lastAdjustment = 0; }

  observe(identity: string, resultPts: number, displayedPts: number, actualBufferMs: number, now: number) {
    if (identity !== this.identity) { this.reset(); this.identity = identity; }
    if (![resultPts, displayedPts, actualBufferMs, now].every(Number.isFinite)) return this.delayMs;
    // Both PTS values come from the same source stream. Add the next tracking
    // anchor's delivery margin; wall clocks on the camera, node and browser may differ.
    const lag = actualBufferMs + (displayedPts - resultPts) / 90;
    if (lag < -100 || lag > 10_000) return this.delayMs;
    this.samples.push(Math.max(0, lag) + 250);
    if (this.samples.length > 24) this.samples.shift();
    const sorted = [...this.samples].sort((a, b) => a - b);
    const target = Math.max(600, Math.min(1800, Math.ceil(sorted[Math.floor((sorted.length - 1) * .9)]! / 100) * 100));
    if (now - this.lastAdjustment < 1000) return this.delayMs;
    if (target > this.delayMs || (this.samples.length >= 12 && target < this.delayMs - 200)) {
      this.delayMs = target > this.delayMs ? target : this.delayMs - 100;
      this.lastAdjustment = now;
    }
    return this.delayMs;
  }
}
