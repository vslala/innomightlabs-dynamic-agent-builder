import styles from './StoryPage.module.css';

// Shared and page-specific selectors both apply when a mockup refines a shared component.
export function storyClasses(local: Readonly<Record<string, string>> = {}) {
  return (...names: (string | false | undefined)[]) => names.filter((name): name is string => Boolean(name))
    .flatMap(name => name.split(/\s+/))
    .flatMap(name => [styles[name], local[name]])
    .filter(Boolean).join(' ');
}

