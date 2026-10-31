import { useCallback, useRef, useState } from "react";

/** How close to the bottom, in pixels, still counts as reading the latest message. */
const PINNED_THRESHOLD_PX = 80;

/**
 * Keeps a scrolling transcript on its newest content while the reader is at the bottom, and leaves it alone once they
 * scroll up to read. A ResizeObserver on the content follows everything that makes it taller (streamed text, images
 * loading, cards opening) with one instant jump per change, instead of a smooth scroll per streamed chunk.
 *
 * Attach `scrollRef` to the scrolling element, `contentRef` to the element inside it that grows, and call `onScroll`
 * from the scrolling element's scroll handler.
 */
export function useStickToBottom<TScroll extends HTMLElement = HTMLDivElement>() {
  const scrollElement = useRef<TScroll | null>(null);
  const pinned = useRef(true);
  const [atBottom, setAtBottom] = useState(true);

  const scrollRef = useCallback((node: TScroll | null) => {
    scrollElement.current = node;
  }, []);

  const contentRef = useCallback((node: HTMLElement | null) => {
    if (!node) return;
    const observer = new ResizeObserver(() => {
      const scroller = scrollElement.current;
      if (scroller && pinned.current) scroller.scrollTop = scroller.scrollHeight;
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const onScroll = useCallback(() => {
    const scroller = scrollElement.current;
    if (!scroller) return;
    const isPinned = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight <= PINNED_THRESHOLD_PX;
    pinned.current = isPinned;
    setAtBottom(isPinned);
  }, []);

  /** Go to the newest content and follow it again, as after sending a message. */
  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const scroller = scrollElement.current;
    pinned.current = true;
    setAtBottom(true);
    scroller?.scrollTo({ top: scroller.scrollHeight, behavior });
  }, []);

  return { scrollRef, scrollElement, contentRef, onScroll, atBottom, scrollToBottom };
}
