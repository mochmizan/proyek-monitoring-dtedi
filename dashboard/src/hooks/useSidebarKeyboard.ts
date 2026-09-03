import { useEffect } from 'react'
import { useSidebarStore } from '@/lib/sidebarStore'

export function useSidebarKeyboard() {
  const toggleCollapsed = useSidebarStore((s) => s.toggleCollapsed)
  const toggleMobile = useSidebarStore((s) => s.toggleMobile)

  useEffect(() => {
    let resizeTimer: ReturnType<typeof setTimeout> | undefined

    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        const target = e.target as HTMLElement | null
        if (
          target &&
          (target.tagName === 'INPUT' ||
            target.tagName === 'TEXTAREA' ||
            target.tagName === 'SELECT' ||
            target.isContentEditable)
        ) {
          return
        }

        e.preventDefault()

        const isDesktop =
          typeof window !== 'undefined' &&
          typeof window.matchMedia === 'function' &&
          window.matchMedia('(min-width: 768px)').matches

        if (isDesktop) {
          toggleCollapsed()
          clearTimeout(resizeTimer)
          resizeTimer = setTimeout(() => {
            window.dispatchEvent(new Event('resize'))
          }, 300)
        } else {
          toggleMobile()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      clearTimeout(resizeTimer)
    }
  }, [toggleCollapsed, toggleMobile])
}
