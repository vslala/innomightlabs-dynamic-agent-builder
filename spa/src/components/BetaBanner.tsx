import { useState, useEffect } from 'react';
import { X, Sparkles } from 'lucide-react';

const BANNER_DISMISSED_KEY = 'beta-banner-dismissed';
const BANNER_HEIGHT = 52; // Approximate height in pixels

export default function BetaBanner() {
  const [isVisible, setIsVisible] = useState(false);
  const [isAnimatingOut, setIsAnimatingOut] = useState(false);

  useEffect(() => {
    const dismissed = localStorage.getItem(BANNER_DISMISSED_KEY);
    if (!dismissed) {
      setIsVisible(true);
      // Add CSS variable for navbar offset
      document.documentElement.style.setProperty('--banner-offset', `${BANNER_HEIGHT}px`);
    } else {
      // Ensure offset is 0 if banner was previously dismissed
      document.documentElement.style.setProperty('--banner-offset', '0px');
    }
  }, []);

  const handleDismiss = () => {
    setIsAnimatingOut(true);
    setTimeout(() => {
      setIsVisible(false);
      localStorage.setItem(BANNER_DISMISSED_KEY, 'true');
      // Remove navbar offset
      document.documentElement.style.setProperty('--banner-offset', '0px');
    }, 300);
  };

  if (!isVisible) return null;

  return (
    <div
      style={{
        position: 'relative',
        zIndex: 200,
        height: isAnimatingOut ? '0' : 'auto',
        overflow: 'hidden',
        transition: 'height 0.3s ease-out',
        background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%)',
        borderBottom: '1px solid rgba(71, 85, 105, 0.4)',
      }}
    >
      <div
        style={{
          transform: isAnimatingOut ? 'translateY(-100%)' : 'translateY(0)',
          opacity: isAnimatingOut ? 0 : 1,
          transition: 'transform 0.3s ease-out, opacity 0.3s ease-out',
        }}
      >
        <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '12px 32px' }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr auto',
            alignItems: 'center',
            gap: '16px'
          }}>
            {/* Left content */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', minWidth: 0 }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  background: 'rgba(59, 130, 246, 0.12)',
                  border: '1px solid rgba(59, 130, 246, 0.25)',
                  flexShrink: 0,
                }}
              >
                <Sparkles style={{ width: '16px', height: '16px', color: '#60a5fa' }} />
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', minWidth: 0 }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '3px 10px',
                    fontSize: '11px',
                    fontWeight: 700,
                    borderRadius: '6px',
                    background: 'rgba(96, 165, 250, 0.12)',
                    color: '#93c5fd',
                    border: '1px solid rgba(96, 165, 250, 0.2)',
                    letterSpacing: '0.8px',
                    textTransform: 'uppercase',
                  }}
                >
                  Beta
                </span>
                <span style={{ fontSize: '14px', color: '#e2e8f0', fontWeight: 500 }}>
                  We're actively improving the platform
                </span>
                <span style={{ fontSize: '13px', color: '#94a3b8' }} className="hidden sm:inline">
                  • Expect occasional updates
                </span>
              </div>
            </div>

            {/* Right - Dismiss button */}
            <button
              onClick={handleDismiss}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                padding: '7px 14px',
                fontSize: '13px',
                fontWeight: 500,
                borderRadius: '9999px',
                background: 'rgba(255, 255, 255, 0.06)',
                color: '#cbd5e1',
                border: '1px solid rgba(255, 255, 255, 0.12)',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                flexShrink: 0,
                whiteSpace: 'nowrap',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.2)';
                e.currentTarget.style.transform = 'scale(1.03)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.06)';
                e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.12)';
                e.currentTarget.style.transform = 'scale(1)';
              }}
              aria-label="Dismiss banner"
            >
              <X style={{ width: '14px', height: '14px', strokeWidth: 2.5 }} />
              <span>Dismiss</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
