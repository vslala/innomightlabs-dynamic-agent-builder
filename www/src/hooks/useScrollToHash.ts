import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

// React Router restores scroll position but ignores #fragments, so links like /services#cloud-devops
// would land at the top of the page without this.
export function useScrollToHash() {
  const { pathname, hash } = useLocation()

  useEffect(() => {
    if (!hash) return
    document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView()
  }, [pathname, hash])
}
