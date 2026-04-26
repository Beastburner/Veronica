"use client";

import { useCallback, useState } from "react";

export function useMemoryEfficientState<T>(initial: T[] = [], maxSize = 100) {
  const [items, setItems] = useState<T[]>(initial);

  const add = useCallback(
    (item: T) => {
      setItems((prev) => [...prev, item].slice(-maxSize));
    },
    [maxSize]
  );

  const replace = useCallback(
    (next: T[]) => {
      setItems(next.slice(-maxSize));
    },
    [maxSize]
  );

  const clear = useCallback(() => setItems([]), []);

  const estimateKB = useCallback(() => Math.round(JSON.stringify(items).length / 1024), [items]);

  return { items, add, replace, clear, estimateKB };
}
