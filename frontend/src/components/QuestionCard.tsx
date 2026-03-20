import React, { useState, useRef, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { gql } from '../api/graphqlClient'

interface QuestionCardProps {
  jobId: string
  question: string
  onAnswered: (answer: string) => void
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
    try {
      await gql.mutation({ answerJob: { __args: { jobId, answer }, __scalar: true } })
      const submitted = answer
      setAnswer('')
      onAnswered(submitted)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card
      className="border-amber-200 bg-amber-50/50"
      role="alertdialog"
      aria-live="assertive"
      aria-labelledby="question-heading"
    >
      <CardHeader className="pb-2">
        <CardTitle id="question-heading" className="text-sm font-semibold text-amber-800">
          Human Input Required
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-foreground mb-4">{question}</p>
        <form onSubmit={handleSubmit}>
          <Textarea
            ref={textareaRef}
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="Type your answer..."
            rows={3}
            aria-label="Answer to agent question"
          />
          <div className="flex justify-end mt-2">
            <Button
              type="submit"
              disabled={!answer.trim() || isSubmitting}
              size="sm"
              className="bg-amber-600 hover:bg-amber-700 text-white"
            >
              {isSubmitting ? 'Submitting...' : 'Submit Answer'}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
