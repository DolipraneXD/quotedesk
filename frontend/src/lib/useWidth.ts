import { useEffect, useRef, useState } from 'react'

/** Track an element's rendered width so SVG can be drawn at 1:1 pixel scale. */
export function useWidth<T extends HTMLElement>(initial = 640) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(initial)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => {
      setWidth(Math.max(240, Math.floor(entry.contentRect.width)))
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}
