import { type RefObject, useEffect } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Keeps keyboard focus inside `container` while a dialog is open, closes it on
 * Escape, and returns focus to the element that opened it.
 */
export function useFocusTrap(
  container: RefObject<HTMLElement | null>,
  onEscape: () => void,
): void {
  useEffect(() => {
    const node = container.current;
    if (!node) return;
    const opener = document.activeElement as HTMLElement | null;
    node.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.stopPropagation();
        onEscape();
        return;
      }
      if (event.key !== "Tab" || !node) return;
      const focusable = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE));
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      const active = document.activeElement;
      if (event.shiftKey && (active === first || active === node)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }

    node.addEventListener("keydown", onKeyDown);
    return () => {
      node.removeEventListener("keydown", onKeyDown);
      opener?.focus();
    };
  }, [container, onEscape]);
}
