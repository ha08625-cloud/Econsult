import { useEffect, useRef } from "react";

/**
 * Generalises the SelectConditionScreen / FreeTextScreen loading-transition
 * focus pattern to every screen. Returns a ref to attach to the screen's
 * <h1> (with tabIndex={-1} so it is focusable without entering the tab
 * order). Screens that render synchronously call this with no argument and
 * focus on mount. Screens with an async loading -> ready transition pass a
 * value that is falsy while loading and truthy once the heading's final
 * content is in place, so focus is deferred until then.
 */
export function useFocusHeading(ready: unknown = true) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (ready) headingRef.current?.focus();
  }, [ready]);
  return headingRef;
}
