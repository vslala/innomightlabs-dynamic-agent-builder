import { useCallback, useState, type FormEvent } from 'react'
import { EnquiryError, sendEnquiry, type Enquiry } from '@/services/contact/contactService'

type Status =
  | { state: 'idle' }
  | { state: 'sending' }
  | { state: 'sent'; message: string }
  | { state: 'failed'; message: string }

const emptyEnquiry: Enquiry = {
  name: '',
  email: '',
  organisation: '',
  topic: 'project',
  message: '',
  website: '',
}

export function useContactForm() {
  const [enquiry, setEnquiry] = useState<Enquiry>(emptyEnquiry)
  const [status, setStatus] = useState<Status>({ state: 'idle' })

  const update = useCallback(<K extends keyof Enquiry>(field: K, value: Enquiry[K]) => {
    setEnquiry((current) => ({ ...current, [field]: value }))
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setStatus({ state: 'sending' })
    try {
      const message = await sendEnquiry(enquiry)
      setStatus({ state: 'sent', message })
      setEnquiry(emptyEnquiry)
    } catch (error) {
      const message = error instanceof EnquiryError ? error.message : 'Something went wrong. Please try again.'
      setStatus({ state: 'failed', message })
    }
  }

  return { enquiry, status, update, submit }
}
