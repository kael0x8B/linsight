import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EncodedVideoDelay } from './encoded-video-delay';

describe('bounded native video receiver delay', () => {
  beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] }));
  afterEach(() => vi.useRealTimers());

  it('retains frame identity, cadence and order while delaying 600 ms', async () => {
    const seen: unknown[] = [];
    const delay = new EncodedVideoDelay(async frame => { seen.push(frame); }, vi.fn(), vi.fn());
    delay.setDelay(600);
    const key = { type: 'key', pts: 100 }; const delta = { type: 'delta', pts: 3700 };
    delay.offer(key); await vi.advanceTimersByTimeAsync(40); delay.offer(delta);
    await vi.advanceTimersByTimeAsync(559); expect(seen).toEqual([]);
    await vi.advanceTimersByTimeAsync(1); expect(seen[0]).toBe(key);
    await vi.advanceTimersByTimeAsync(40); expect(seen[1]).toBe(delta);
    expect(delay.size).toBe(0); delay.close();
  });

  it('raw video mode releases the pending delay without reordering frames', async () => {
    const seen: string[] = [];
    const delay = new EncodedVideoDelay(async frame => { seen.push(frame.type); }, vi.fn(), vi.fn());
    delay.setDelay(600); delay.offer({ type: 'key' }); delay.offer({ type: 'delta' });
    delay.setDelay(0); await vi.advanceTimersByTimeAsync(1);
    expect(seen).toEqual(['key', 'delta']); delay.close();
  });

  it('absorbs arrival jitter while preserving the source video cadence', async () => {
    const seen: number[] = [];
    const delay = new EncodedVideoDelay(async () => { seen.push(performance.now()); }, vi.fn(), vi.fn());
    delay.setDelay(600); delay.offer({ type: 'key' }, 0);
    await vi.advanceTimersByTimeAsync(100); delay.offer({ type: 'delta' }, 40);
    await vi.advanceTimersByTimeAsync(500); expect(seen).toEqual([600]);
    await vi.advanceTimersByTimeAsync(40); expect(seen).toEqual([600, 640]); delay.close();
  });

  it('bounds overload to 128 coded frames and resumes only at a keyframe', async () => {
    const seen: string[] = []; const recover = vi.fn();
    const delay = new EncodedVideoDelay(async frame => { seen.push(frame.type); }, recover, vi.fn());
    delay.setDelay(600); delay.offer({ type: 'key' });
    for (let i = 0; i < 128; i++) delay.offer({ type: 'delta' });
    expect(delay.size).toBe(0); expect(recover).toHaveBeenCalledOnce();
    delay.offer({ type: 'delta' }); expect(delay.size).toBe(0);
    delay.offer({ type: 'key' }); await vi.advanceTimersByTimeAsync(601);
    expect(seen).toEqual(['key']); delay.close();
  });

  it('discards old stream frames on reconnect and releases timers on close', async () => {
    const forward = vi.fn(async () => undefined);
    const delay = new EncodedVideoDelay(forward, vi.fn(), vi.fn());
    delay.setDelay(600); delay.offer({ type: 'key' }); delay.reset();
    delay.offer({ type: 'delta' }); await vi.advanceTimersByTimeAsync(1000);
    expect(forward).not.toHaveBeenCalled(); delay.offer({ type: 'key' }); delay.close();
    await vi.advanceTimersByTimeAsync(1000); expect(forward).not.toHaveBeenCalled();
  });

  it('stops retaining frames if the browser decoder sink closes', async () => {
    const failed = vi.fn();
    const delay = new EncodedVideoDelay(async () => { throw new Error('closed'); }, vi.fn(), failed);
    delay.offer({ type: 'key' }); await vi.advanceTimersByTimeAsync(1);
    delay.offer({ type: 'delta' }); expect(delay.size).toBe(0); expect(failed).toHaveBeenCalledOnce();
  });
});

it('allows the bounded 1800 ms analysis buffer at 25 FPS without losing the codec chain', async ()=>{
  vi.useFakeTimers({toFake:['setTimeout','clearTimeout','performance']});
  const seen:number[]=[];const recover=vi.fn();
  const delay=new EncodedVideoDelay(async (frame:{type:string;pts:number})=>{seen.push(frame.pts);},recover,vi.fn());
  try{
    delay.setDelay(1800);
    for(let i=0;i<60;i++){delay.offer({type:i===0?'key':'delta',pts:i*40},i*40);await vi.advanceTimersByTimeAsync(40);}
    await vi.advanceTimersByTimeAsync(1800);
    expect(seen).toEqual(Array.from({length:60},(_,i)=>i*40));expect(recover).not.toHaveBeenCalled();
  }finally{delay.close();vi.useRealTimers();}
});
