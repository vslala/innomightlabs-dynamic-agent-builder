import { DocsLayout } from '../../components/docs/DocsLayout';
import { ReleaseNotes } from './ReleaseNotes';
import { releaseMonths } from './whatsNewData';

const navItems = releaseMonths.map((month) => ({ ...month, href: `#${month.id}` }));

export function WhatsNew() {
  return (
    <DocsLayout
      navItems={navItems}
      title="What's New"
      description="New features, improvements, and fixes across InnoMight Labs, newest first."
    >
      {/* The release cards carry their own styles, so the docs prose styles stay out. */}
      <div data-docs-embed>
        <ReleaseNotes />
      </div>
    </DocsLayout>
  );
}
