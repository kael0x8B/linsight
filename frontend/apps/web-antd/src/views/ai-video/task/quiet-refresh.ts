/** A single visible-page refresh loop. Stale responses never update a new view. */
export function createQuietRefresh<T>(options: {
  active: () => boolean;
  apply: (value: T) => Promise<void> | void;
  fetch: () => Promise<T>;
  interval?: number;
  onError: (error: unknown) => void;
}) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let generation = 0;
  let inFlight = false;
  function stop() {
    generation++;
    clearTimeout(timer);
    timer = undefined;
  }
  function schedule() {
    clearTimeout(timer);
    timer = undefined;
    if (!options.active()) return;
    timer = setTimeout(async () => {
      timer = undefined;
      if (!options.active()) return;
      if (inFlight) {
        schedule();
        return;
      }
      inFlight = true;
      const current = generation;
      try {
        const value = await options.fetch();
        if (current === generation && options.active())
          await options.apply(value);
      } catch (error) {
        if (current === generation && options.active()) options.onError(error);
      } finally {
        inFlight = false;
        schedule();
      }
    }, options.interval ?? 5000);
  }
  return { schedule, stop };
}
