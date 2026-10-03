import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/Button/Button'
import { Icon } from '@/components/Icon/Icon'
import { useContactForm } from '@/hooks/useContactForm'
import { enquiryTopics, type EnquiryTopic } from '@/services/contact/contactService'
import styles from './style.module.css'

export function ContactForm({ topic }: { topic?: EnquiryTopic }) {
  const { enquiry, status, update, submit } = useContactForm()

  // Applied after hydration: the prerendered page can't know the visitor's ?topic= link.
  useEffect(() => {
    if (topic) update('topic', topic)
  }, [topic, update])

  if (status.state === 'sent') {
    return (
      <div className={styles.sent} role="status">
        <span className={styles.sentIcon}>
          <Icon name="check" size={28} />
        </span>
        <h2 className={styles.sentTitle}>Message sent</h2>
        <p>{status.message}</p>
      </div>
    )
  }

  return (
    <form className={styles.form} onSubmit={submit}>
      <div className={styles.row}>
        <label className={styles.field}>
          <span className={styles.label}>Your name</span>
          <input
            className={styles.input}
            name="name"
            autoComplete="name"
            required
            minLength={2}
            maxLength={120}
            value={enquiry.name}
            onChange={(event) => update('name', event.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>Work email</span>
          <input
            className={styles.input}
            type="email"
            name="email"
            autoComplete="email"
            required
            value={enquiry.email}
            onChange={(event) => update('email', event.target.value)}
          />
        </label>
      </div>

      <div className={styles.row}>
        <label className={styles.field}>
          <span className={styles.label}>
            Organisation <span className={styles.optional}>(optional)</span>
          </span>
          <input
            className={styles.input}
            name="organisation"
            autoComplete="organization"
            maxLength={160}
            value={enquiry.organisation}
            onChange={(event) => update('organisation', event.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>What is it about?</span>
          <select
            className={styles.input}
            name="topic"
            value={enquiry.topic}
            onChange={(event) => update('topic', event.target.value as EnquiryTopic)}
          >
            {Object.entries(enquiryTopics).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className={styles.field}>
        <span className={styles.label}>How can we help?</span>
        <textarea
          className={`${styles.input} ${styles.message}`}
          name="message"
          required
          minLength={20}
          maxLength={5000}
          rows={6}
          placeholder="A few lines about your project, tender or question: goals, timescales and anything we should know."
          value={enquiry.message}
          onChange={(event) => update('message', event.target.value)}
        />
      </label>

      {/* Honeypot: hidden from people and assistive technology; bots that fill it in are dropped. */}
      <label className={styles.honeypot} aria-hidden="true">
        Website
        <input
          name="website"
          tabIndex={-1}
          autoComplete="off"
          value={enquiry.website}
          onChange={(event) => update('website', event.target.value)}
        />
      </label>

      {status.state === 'failed' && (
        <p className={styles.error} role="alert">
          {status.message}
        </p>
      )}

      <div className={styles.footer}>
        <p className={styles.privacy}>
          We only use your details to reply to you. See our <Link to="/privacy">privacy notice</Link>.
        </p>
        <Button type="submit" size="lg" icon="arrow-right" disabled={status.state === 'sending'}>
          {status.state === 'sending' ? 'Sending…' : 'Send message'}
        </Button>
      </div>
    </form>
  )
}
