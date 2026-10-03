import { useCallback, useEffect, useState, type RefObject } from 'react'
import { useLocation } from 'react-router-dom'

// Open/closed state for menus and drawers. They close on Escape, whenever the page changes and,
// when given the menu's container, on any click outside it.
export function useDisclosure(container?: RefObject<HTMLElement | null>) {
  const [isOpen, setIsOpen] = useState(false)
  const { pathname } = useLocation()

  const close = useCallback(() => setIsOpen(false), [])
  const toggle = useCallback(() => setIsOpen((value) => !value), [])

  useEffect(close, [pathname, close])

  useEffect(() => {
    if (!isOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (container?.current && !container.current.contains(event.target as Node)) close()
    }
    document.addEventListener('keydown', closeOnEscape)
    document.addEventListener('pointerdown', closeOnOutsideClick)
    return () => {
      document.removeEventListener('keydown', closeOnEscape)
      document.removeEventListener('pointerdown', closeOnOutsideClick)
    }
  }, [isOpen, close, container])

  return { isOpen, close, toggle }
}
