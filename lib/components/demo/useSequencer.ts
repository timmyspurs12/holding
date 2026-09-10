"use client";

import { useCallback, useEffect, useState } from "react";

export function useSequencer(
  count: number,
  opts: {
    auto?: boolean;
    durations?: number[];
    /** Pause automatically when reaching this index (waiting for user input). */
    gate?: (index: number) => boolean;
  } = {},
) {
  const { auto = true, durations = [], gate } = opts;
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(auto);
  const atEnd = index >= count - 1;

  useEffect(() => {
    if (!playing) return;
    if (atEnd) {
      setPlaying(false);
      return;
    }
    const d = durations[index] ?? 2200;
    const t = setTimeout(() => setIndex((i) => i + 1), d);
    return () => clearTimeout(t);
  }, [playing, index, atEnd, durations]);

  useEffect(() => {
    if (gate && gate(index) && !atEnd) setPlaying(false);
  }, [index, gate, atEnd]);

  const next = useCallback(() => {
    setIndex((i) => Math.min(count - 1, i + 1));
    setPlaying(true);
  }, [count]);

  const prev = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  const goTo = useCallback(
    (i: number) => {
      setIndex(Math.max(0, Math.min(count - 1, i)));
      setPlaying(true);
    },
    [count],
  );

  const reset = useCallback(() => {
    setIndex(0);
    setPlaying(true);
  }, []);

  const toggle = useCallback(() => {
    if (atEnd && !playing) {
      reset();
      return;
    }
    setPlaying((p) => !p);
  }, [atEnd, playing, reset]);

  return { index, playing, atEnd, next, prev, goTo, reset, toggle, setPlaying };
}
