import React, { useState, useRef, useEffect } from 'react'
import { jobsApi } from '../api/endpoints'

interface QuestionCardProps {
  jobId: string
  question: string
  onAnswered: () => void
}

export function QuestionCard({ jobId, question, onAnswered }: QuestionCardProps): React.ReactElement {
  const [answer, setAnswer] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault()
    if (!answer.trim()) return
    setIsSubmitting(true)
    await jobsApi.answer(jobId, answer)
    setIsSubmitting(false)
    setAnswer('')
    onAnswered()
  }

  return (
    <div
      role="alertdialog"
      aria-live="assertive"
      aria-labelledby="question-heading"
      className="border border-amber-600 bg-amber-950/30 rounded-lg p-4 mb-4"
    >
      <h3 id="question-heading" className="text-sm font-semibold text-amber-300 mb-2">
        Human Input Required
      </h3>
      <p className="text-sm text-gray-300 mb-4">{question}</p>
      <form onSubmit={handleSubmit}>
        <textarea
          ref={textareaRef}
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="Type your answer..."
          className="w-full bg-gray-900 border border-gray-600 rounded p-3 text-sm text-gray-200 placeholder-gray-500 resize-none focus:outline-none focus:border-amber-500"
          rows={3}
          aria-label="Answer to agent question"
        />
        <div className="flex justify-end mt-2">
          <button
            type="submit"
            disabled={!answer.trim() || isSubmitting}
            className="bg-amber-600 hover:bg-amber-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-medium px-4 py-2 rounded transition-colors"
          >
            {isSubmitting ? 'Submitting...' : 'Submit Answer'}
          </button>
        </div>
      </form>
    </div>
  )
}
