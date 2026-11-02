// The facts about the company. Everything that renders the company name, contact details or legal
// disclosures reads them from here.
export const site = {
  name: 'Innomight',
  legalName: 'Innomight Labs Ltd',
  url: 'https://innomight.com',
  email: 'hello@innomight.com',
  location: 'United Kingdom',
  description:
    'Innomight Labs is a UK digital agency. We design, build and run software for businesses and the public sector, bid for and deliver public contracts, and build products of our own.',

  // UK company disclosures. The footer shows them once they're filled in.
  jurisdiction: 'England and Wales',
  companyNumber: '17491874',
  registeredOffice: '47 Hallgarth, Consett, England, DH8 8BL',
  dunsNumber: '235201313',
  vatNumber: '',
  // Where legal and privacy requests (including from public authorities) are sent
  legalEmail: 'hello@innomightlabs.com',

  // Certifications and procurement frameworks (e.g. "Cyber Essentials", "G-Cloud 14"). The
  // credentials strip on the home and public sector pages appears once this has entries.
  credentials: [] as string[],
}

export type Accent = 'blue' | 'purple' | 'teal' | 'magenta'
