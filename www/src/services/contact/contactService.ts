export const enquiryTopics = {
  project: 'A new software project',
  'public-sector': 'A public-sector tender or contract',
  product: 'One of our products',
  partnership: 'Partnering with us',
  other: 'Something else',
} as const

export type EnquiryTopic = keyof typeof enquiryTopics

export interface Enquiry {
  name: string
  email: string
  organisation: string
  topic: EnquiryTopic
  message: string
  // Honeypot field. People never see it; bots fill it in and are quietly dropped by the API.
  website: string
}

export class EnquiryError extends Error {}

// Sends an enquiry to the Innomight inbox and returns the confirmation message to show.
export async function sendEnquiry(enquiry: Enquiry): Promise<string> {
  let response: Response
  try {
    response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/contact/enquiry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(enquiry),
    })
  } catch {
    throw new EnquiryError('We couldn’t reach our server. Please check your connection and try again.')
  }

  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : 'Something went wrong. Please try again.'
    throw new EnquiryError(detail)
  }
  return body.message
}
