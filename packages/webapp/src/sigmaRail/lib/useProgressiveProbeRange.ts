import { useCallback, useEffect, useState } from "react";
import {
  PROBE_CHUNK_DAYS,
  extendWindowStart,
  latestChunkWindowStart,
} from "./probeWindow";

/**
 * Probe chart window: initially the latest ``PROBE_CHUNK_DAYS`` ending at
 * ``asOf``, floored by ``backtestStart``. Call ``extendEarlier`` when the user
 * pans left / clicks load (adds another chunk).
 *
 * ``resetKey`` (e.g. pipeline/screen fingerprint) snaps the window back to the
 * latest chunk when the authored strategy changes (UI edit or MCP Accept).
 */
export function useProgressiveProbeRange(
  asOf: string,
  backtestStart: string,
  resetKey = "",
) {
  const end = (asOf || "").trim().slice(0, 10);
  const floor = (backtestStart || "").trim().slice(0, 10);

  const [loadedStart, setLoadedStart] = useState(() =>
    latestChunkWindowStart(end, floor),
  );

  useEffect(() => {
    setLoadedStart(latestChunkWindowStart(end, floor));
  }, [end, floor, resetKey]);

  const canExtend = Boolean(end && floor && loadedStart > floor);

  const extendEarlier = useCallback(() => {
    setLoadedStart((cur) => {
      if (!floor || !cur || cur <= floor) return cur;
      return extendWindowStart(cur, floor, PROBE_CHUNK_DAYS);
    });
  }, [floor]);

  return {
    /** Fetched range start (grows earlier as user scans back). */
    rangeStart: loadedStart || latestChunkWindowStart(end, floor),
    rangeEnd: end,
    /** Full backtest start — use for tenure, not necessarily for the chart fetch. */
    tenureStart: floor || loadedStart,
    canExtend,
    extendEarlier,
    chunkDays: PROBE_CHUNK_DAYS,
  };
}
