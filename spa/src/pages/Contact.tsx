import { useState } from 'react';
import { Send, CheckCircle, AlertCircle } from 'lucide-react';
import { Navbar } from '../components/Navbar';
import { Footer } from '../components/Footer';
import { httpClient } from '../services/http';

interface ContactFormData {
  type: string;
  subject: string;
  email: string;
  description: string;
}

interface SubmissionResponse {
  success: boolean;
  message: string;
  issue_number?: number;
  issue_url?: string;
}

export function Contact() {
  const [formData, setFormData] = useState<ContactFormData>({
    type: 'support',
    subject: '',
    email: '',
    description: '',
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitStatus, setSubmitStatus] = useState<{
    type: 'success' | 'error' | null;
    message: string;
  }>({ type: null, message: '' });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitStatus({ type: null, message: '' });

    try {
      const response = await httpClient.post<SubmissionResponse>(
        '/contact/submit',
        formData,
        { skipAuth: true }
      );

      setSubmitStatus({
        type: 'success',
        message: response.message,
      });

      // Reset form
      setFormData({
        type: 'support',
        subject: '',
        email: '',
        description: '',
      });
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.detail ||
        'Failed to submit. Please try again later.';
      setSubmitStatus({
        type: 'error',
        message: errorMessage,
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleChange = (
    e: React.ChangeEvent<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  return (
    <>
      <Navbar />
      <div style={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #0a0a1a 0%, #1a1a2e 50%, #16213e 100%)',
        paddingTop: '120px',
        paddingBottom: '80px',
      }}>
        <div style={{ maxWidth: '900px', margin: '0 auto', padding: '0 24px' }}>
          {/* Header */}
          <div style={{ textAlign: 'center', marginBottom: '48px' }}>
            <h1 style={{
              fontSize: '3rem',
              fontWeight: 800,
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              marginBottom: '16px',
            }}>
              Get in Touch
            </h1>
            <p style={{ fontSize: '1.125rem', color: '#94a3b8', lineHeight: 1.6 }}>
              Have questions, feedback, or found a bug? We'd love to hear from you!
            </p>
          </div>

          {/* Success Message */}
          {submitStatus.type === 'success' && (
            <div style={{
              marginBottom: '24px',
              background: 'rgba(34, 197, 94, 0.1)',
              border: '1px solid rgba(34, 197, 94, 0.3)',
              borderRadius: '12px',
              padding: '16px',
              display: 'flex',
              alignItems: 'flex-start',
            }}>
              <CheckCircle style={{ width: '20px', height: '20px', color: '#22c55e', marginTop: '2px', marginRight: '12px', flexShrink: 0 }} />
              <div>
                <p style={{ color: '#86efac', fontWeight: 600, marginBottom: '4px' }}>
                  Thank you for your submission!
                </p>
                <p style={{ color: '#bbf7d0', fontSize: '0.875rem' }}>
                  {submitStatus.message}
                </p>
              </div>
            </div>
          )}

          {/* Error Message */}
          {submitStatus.type === 'error' && (
            <div style={{
              marginBottom: '24px',
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: '12px',
              padding: '16px',
              display: 'flex',
              alignItems: 'flex-start',
            }}>
              <AlertCircle style={{ width: '20px', height: '20px', color: '#ef4444', marginTop: '2px', marginRight: '12px', flexShrink: 0 }} />
              <div>
                <p style={{ color: '#fca5a5', fontWeight: 600, marginBottom: '4px' }}>
                  Submission failed
                </p>
                <p style={{ color: '#fecaca', fontSize: '0.875rem' }}>
                  {submitStatus.message}
                </p>
              </div>
            </div>
          )}

          {/* Contact Form */}
          <div style={{
            background: 'rgba(30, 41, 59, 0.5)',
            backdropFilter: 'blur(20px)',
            border: '1px solid rgba(148, 163, 184, 0.1)',
            borderRadius: '16px',
            padding: '40px',
            boxShadow: '0 20px 60px rgba(0, 0, 0, 0.3)',
          }}>
            <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
              {/* Type Selection */}
              <div>
                <label htmlFor="type" style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '8px' }}>
                  What can we help you with?
                </label>
                <select
                  id="type"
                  name="type"
                  value={formData.type}
                  onChange={handleChange}
                  required
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    borderRadius: '10px',
                    color: '#e2e8f0',
                    fontSize: '0.9375rem',
                    transition: 'all 0.2s ease',
                    cursor: 'pointer',
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'rgba(102, 126, 234, 0.5)';
                    e.target.style.outline = 'none';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'rgba(148, 163, 184, 0.2)';
                  }}
                >
                  <option value="support">Support Question</option>
                  <option value="feedback">Product Feedback</option>
                  <option value="bug-report">Bug Report</option>
                  <option value="feature-request">Feature Request</option>
                </select>
              </div>

              {/* Email */}
              <div>
                <label htmlFor="email" style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '8px' }}>
                  Your Email
                </label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  required
                  placeholder="you@example.com"
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    borderRadius: '10px',
                    color: '#e2e8f0',
                    fontSize: '0.9375rem',
                    transition: 'all 0.2s ease',
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'rgba(102, 126, 234, 0.5)';
                    e.target.style.outline = 'none';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'rgba(148, 163, 184, 0.2)';
                  }}
                />
              </div>

              {/* Subject */}
              <div>
                <label htmlFor="subject" style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '8px' }}>
                  Subject
                </label>
                <input
                  type="text"
                  id="subject"
                  name="subject"
                  value={formData.subject}
                  onChange={handleChange}
                  required
                  minLength={5}
                  maxLength={200}
                  placeholder="Brief summary of your message"
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    borderRadius: '10px',
                    color: '#e2e8f0',
                    fontSize: '0.9375rem',
                    transition: 'all 0.2s ease',
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'rgba(102, 126, 234, 0.5)';
                    e.target.style.outline = 'none';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'rgba(148, 163, 184, 0.2)';
                  }}
                />
                <p style={{ marginTop: '4px', fontSize: '0.75rem', color: '#64748b' }}>
                  {formData.subject.length}/200 characters
                </p>
              </div>

              {/* Description */}
              <div>
                <label htmlFor="description" style={{ display: 'block', fontSize: '0.875rem', fontWeight: 600, color: '#e2e8f0', marginBottom: '8px' }}>
                  Description
                </label>
                <textarea
                  id="description"
                  name="description"
                  value={formData.description}
                  onChange={handleChange}
                  required
                  minLength={20}
                  maxLength={5000}
                  rows={8}
                  placeholder="Please provide as much detail as possible..."
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.2)',
                    borderRadius: '10px',
                    color: '#e2e8f0',
                    fontSize: '0.9375rem',
                    transition: 'all 0.2s ease',
                    resize: 'vertical',
                    fontFamily: 'inherit',
                  }}
                  onFocus={(e) => {
                    e.target.style.borderColor = 'rgba(102, 126, 234, 0.5)';
                    e.target.style.outline = 'none';
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = 'rgba(148, 163, 184, 0.2)';
                  }}
                />
                <p style={{ marginTop: '4px', fontSize: '0.75rem', color: '#64748b' }}>
                  {formData.description.length}/5000 characters (min 20)
                </p>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isSubmitting}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '14px 24px',
                  background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                  color: 'white',
                  fontSize: '1rem',
                  fontWeight: 600,
                  borderRadius: '10px',
                  border: 'none',
                  cursor: isSubmitting ? 'not-allowed' : 'pointer',
                  opacity: isSubmitting ? 0.6 : 1,
                  transition: 'all 0.3s ease',
                  boxShadow: '0 4px 15px rgba(102, 126, 234, 0.3)',
                }}
                onMouseEnter={(e) => {
                  if (!isSubmitting) {
                    e.currentTarget.style.transform = 'translateY(-2px)';
                    e.currentTarget.style.boxShadow = '0 6px 20px rgba(102, 126, 234, 0.4)';
                  }
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = '0 4px 15px rgba(102, 126, 234, 0.3)';
                }}
              >
                {isSubmitting ? (
                  <>
                    <svg
                      className="animate-spin"
                      style={{ marginRight: '12px', width: '20px', height: '20px' }}
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        style={{ opacity: 0.25 }}
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      />
                      <path
                        style={{ opacity: 0.75 }}
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      />
                    </svg>
                    Submitting...
                  </>
                ) : (
                  <>
                    <Send style={{ width: '20px', height: '20px', marginRight: '8px' }} />
                    Submit
                  </>
                )}
              </button>
            </form>

            {/* Rate Limit Notice */}
            <div style={{
              marginTop: '24px',
              padding: '14px 16px',
              background: 'rgba(59, 130, 246, 0.1)',
              border: '1px solid rgba(59, 130, 246, 0.2)',
              borderRadius: '10px',
            }}>
              <p style={{ fontSize: '0.8125rem', color: '#93c5fd' }}>
                <strong>Note:</strong> To prevent spam, submissions are limited to one every 5 minutes per device.
              </p>
            </div>
          </div>
        </div>
      </div>
      <Footer />
    </>
  );
}
