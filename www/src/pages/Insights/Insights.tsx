import { Button } from '@/components/Button/Button'
import { FeatureGrid, type Feature } from '@/components/FeatureGrid/FeatureGrid'
import { PageHero } from '@/components/PageHero/PageHero'
import { Section } from '@/components/Section/Section'
import { Seo } from '@/components/Seo/Seo'

const topics: Feature[] = [
  { title: 'Engineering notes', body: 'How we design, build and operate reliable software, with the trade-offs explained.', icon: 'code' },
  { title: 'AI in practice', body: 'What works when putting AI agents and automation into real organisations, and what does not.', icon: 'spark' },
  { title: 'Public sector delivery', body: 'Lessons from tenders, service assessments and delivering digital public services.', icon: 'building' },
  { title: 'Product launches', body: 'Release notes, launch videos and the stories behind the products we build.', icon: 'play' },
]

export function Insights() {
  return (
    <>
      <Seo
        title="Insights"
        description="Articles, research and launch notes from the Innomight Labs team on software engineering, AI and public-sector delivery."
      />
      <PageHero
        eyebrow="Insights"
        title="Articles, research and launch notes"
        intro="Practical writing from the Innomight team on building software, applying AI and delivering for the public sector. Our first articles are on their way."
        actions={
          <Button to="/contact" variant="secondary" icon="arrow-right">
            Suggest a topic
          </Button>
        }
      />
      <Section id="topics" eyebrow="Coming soon" title="What we'll be writing about">
        <FeatureGrid features={topics} columns={4} />
      </Section>
    </>
  )
}
