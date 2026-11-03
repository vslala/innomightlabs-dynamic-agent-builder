import { Children, isValidElement, type MouseEvent } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { RateLimitBanner } from './RateLimitBanner';
import { type ButtonProps } from './ui/button';

const hooks = vi.hoisted(() => ({
  detail: null as unknown,
  setDetail: vi.fn((value: unknown) => { hooks.detail = value; }),
  useEffect: vi.fn<(effect: () => void | (() => void), deps: unknown[]) => void>(),
}));
const commerce = vi.hoisted(() => ({ canSellSubscriptions: true }));

// SSR does not run effects or retain state; drive those explicitly without a DOM.
vi.mock('react', async (importOriginal) => ({
  ...await importOriginal<typeof import('react')>(),
  useState: () => [hooks.detail, hooks.setDetail],
  useEffect: hooks.useEffect,
}));
vi.mock('../platform', () => ({ platform: () => ({ commerce }) }));

let events: EventTarget;
let cleanup: (() => void) | undefined;

function markup() {
  return renderToStaticMarkup(RateLimitBanner());
}

function notify(detail?: unknown) {
  events.dispatchEvent(Object.assign(new Event('rate-limit'), { detail }));
}

beforeEach(() => {
  vi.clearAllMocks();
  hooks.detail = null;
  commerce.canSellSubscriptions = true;
  events = new EventTarget();
  vi.stubGlobal('window', events);
  cleanup = undefined;
  RateLimitBanner();
  cleanup = hooks.useEffect.mock.calls[0][0]() || undefined;
});

afterEach(() => {
  cleanup?.();
  vi.unstubAllGlobals();
});

describe('RateLimitBanner (controlled hooks and static markup)', () => {
  it('renders nothing before a rate-limit notification', () => {
    expect(markup()).toBe('');
  });

  it.each([undefined, null, {}, { message: '' }])('ignores an event without a nonempty message: %j', (detail) => {
    notify(detail);
    expect(hooks.setDetail).not.toHaveBeenCalled();
    expect(markup()).toBe('');
  });

  it('shows the event message and replaces it with the latest notification', () => {
    notify({ message: 'Hourly limit reached' });
    expect(markup()).toContain('Hourly limit reached');

    notify({ message: 'Daily limit reached', upgradeUrl: '/pricing?plan=pro' });
    const html = markup();
    expect(html).toContain('Daily limit reached');
    expect(html).not.toContain('Hourly limit reached');
    expect(html).toContain('href="/pricing?plan=pro"');
  });

  it('does not clear an existing notification when an invalid event arrives', () => {
    notify({ message: 'Limit reached' });
    hooks.setDetail.mockClear();
    notify({ message: '' });
    notify();
    expect(hooks.setDetail).not.toHaveBeenCalled();
    expect(markup()).toContain('Limit reached');
  });

  it.each([
    [undefined, '/pricing'],
    ['', '/pricing'],
    ['/dashboard/billing', '/dashboard/billing'],
  ])('offers the web upgrade link for upgradeUrl=%j', (upgradeUrl, expectedUrl) => {
    notify({ message: 'Limit reached', upgradeUrl });
    expect(markup()).toContain(`href="${expectedUrl}"`);
    expect(markup()).toContain('Upgrade plan</a>');
  });

  it('keeps the notification and dismiss control but hides upgrades on a commerce-restricted platform', () => {
    commerce.canSellSubscriptions = false;
    notify({ message: 'Limit reached', upgradeUrl: '/dashboard/billing' });
    const html = markup();
    expect(html).toContain('Limit reached');
    expect(html).toContain('aria-label="Dismiss notification"');
    expect(html).not.toContain('Upgrade plan');
    expect(html).not.toContain('<a');
    expect(html).not.toContain('/dashboard/billing');
  });

  it('dismisses the notification and can display a later event', () => {
    notify({ message: 'Limit reached' });
    const tree = RateLimitBanner();
    const dismiss = Children.toArray(tree?.props.children).find(
      (child) => isValidElement<ButtonProps>(child) && child.props['aria-label'] === 'Dismiss notification',
    );
    expect(markup()).toContain('type="button"');
    expect(isValidElement<ButtonProps>(dismiss)).toBe(true);
    if (!isValidElement<ButtonProps>(dismiss)) throw new Error('Missing dismiss button');
    dismiss.props.onClick?.({} as MouseEvent<HTMLButtonElement>);

    expect(hooks.setDetail).toHaveBeenLastCalledWith(null);
    expect(markup()).toBe('');
    notify({ message: 'Another limit reached' });
    expect(markup()).toContain('Another limit reached');
  });

  it('removes the registered rate-limit listener on cleanup', () => {
    notify({ message: 'Before cleanup' });
    expect(markup()).toContain('Before cleanup');
    expect(cleanup).toBeTypeOf('function');

    cleanup?.();
    cleanup = undefined;
    hooks.setDetail.mockClear();
    notify({ message: 'After cleanup' });

    expect(hooks.setDetail).not.toHaveBeenCalled();
    expect(markup()).toContain('Before cleanup');
    expect(markup()).not.toContain('After cleanup');
  });
});
