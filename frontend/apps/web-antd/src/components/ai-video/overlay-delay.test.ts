import { describe, expect, it } from 'vitest';
import { OverlayDelay } from './overlay-delay';
describe('adaptive video delay',()=>{
  it('accommodates late metadata using the shared source clock',()=>{
    const delay=new OverlayDelay();
    expect(delay.observe('run1',90_000,126_000,800,1000)).toBe(1500);
    delay.observe('run1',90_000,900_000,800,2000);
    expect(delay.observe('run1',90_000,900_000,800,3000)).toBe(1800);
  });
  it('does not grow repeatedly from the video delay it just added',()=>{
    const delay=new OverlayDelay();
    delay.observe('run1',90_000,126_000,800,1000);
    // At the same 1200 ms pipeline latency, a 1500 ms video delay puts video
    // 300 ms behind the incoming result rather than adding another 1500 ms.
    expect(delay.observe('run1',117_000,90_000,1500,2000)).toBe(1500);
  });
  it('resets on a new run and rejects invalid clocks',()=>{
    const delay=new OverlayDelay();delay.observe('run1',0,180_000,800,1000);
    expect(delay.observe('run2',NaN,0,800,2000)).toBe(800);
    expect(delay.observe('run2',0,1e9,800,3000)).toBe(800);
  });
});
