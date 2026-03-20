import React, { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'
import { useJobStore } from '../store/jobStore'
import type { LogEntry } from '../store/jobStore'
import { QuestionCard } from './QuestionCard'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import { ChevronRight, Check, Loader2, MessageSquare, XCircle, X, Clock, Wrench, ArrowLeft } from 'lucide-react'

// ── Style config ─────────────────────────────────────────────────────

const NODE_STYLE: Record<string, { text: string; border: string; bg: string }> = {
  investigator:    { text: 'text-blue-700',    border: 'border-blue-200',    bg: 'bg-blue-50/50' },
  codebase_search: { text: 'text-purple-700',  border: 'border-purple-200',  bg: 'bg-purple-50/50' },
  web_search:      { text: 'text-cyan-700',    border: 'border-cyan-200',    bg: 'bg-cyan-50/50' },
  critic:          { text: 'text-orange-700',   border: 'border-orange-200',  bg: 'bg-orange-50/50' },
  human_input:     { text: 'text-amber-700',    border: 'border-amber-200',   bg: 'bg-amber-50/50' },
  writer:          { text: 'text-green-700',    border: 'border-green-200',   bg: 'bg-green-50/50' },
}
const DEFAULT_STYLE = { text: 'text-foreground', border: 'border-border', bg: 'bg-muted/30' }

function label(node: string): string { return node.replace(/_/g, ' ') }
function colors(node: string) { return NODE_STYLE[node] || DEFAULT_STYLE }

// ── Standalone event config ──────────────────────────────────────────

interface EventDisplay {
  icon: React.ReactElement
  text: (e: Record<string, string>) => string
  className: string
}

const EVENT_DISPLAY: Record<string, EventDisplay> = {
  JobDoneEvent:     { icon: <Check className="h-3.5 w-3.5" />,    text: () => 'Job completed',                                className: 'border border-emerald-200 bg-emerald-50 text-emerald-700 font-medium' },
  JobFailedEvent:   { icon: <XCircle className="h-3.5 w-3.5" />,  text: (e) => `Job failed${e.error ? `: ${e.error}` : ''}`,  className: 'border border-red-200 bg-red-50 text-red-700' },
  JobKilledEvent:   { icon: <X className="h-3.5 w-3.5" />,        text: () => 'Job killed',                                   className: 'border border-border bg-muted text-muted-foreground' },
  JobTimedOutEvent: { icon: <Clock className="h-3.5 w-3.5" />,    text: () => 'Job timed out',                                className: 'border border-red-200 bg-red-50 text-red-700' },
}

// ── Block types for grouping ─────────────────────────────────────────

interface AgentRun {
  node: string
  children: LogEntry[]
  done: boolean
  question?: { text: string; context: string; index: number }
}

type Block =
  | { kind: 'run'; run: AgentRun }
  | { kind: 'event'; entry: LogEntry }

function buildBlocks(events: LogEntry[]): Block[] {
  const blocks: Block[] = []
  let run: AgentRun | null = null
  let qIdx = 0

  const flushRun = () => { if (run) { blocks.push({ kind: 'run', run }); run = null } }

  for (const e of events) {
    // Skip snapshot/reconnect events entirely
    if (e.__typename === 'JobSnapshotEvent') continue

    if (e.__typename === 'AgentSpawnedEvent' && e.node !== 'supervisor') {
      flushRun()
      run = { node: e.node, children: [], done: false }
      continue
    }
    if (e.__typename === 'AgentDoneEvent' && e.node !== 'supervisor') {
      if (run?.node === e.node) run.done = true
      flushRun()
      continue
    }
    if (run && (e.__typename === 'AgentToolCallEvent' || e.__typename === 'AgentToolResultEvent')) {
      run.children.push(e)
      continue
    }
    if (e.__typename === 'GraphInterruptEvent') {
      if (run) {
        run.question = { text: e.question, context: e.context, index: qIdx++ }
      } else {
        run = { node: 'human_input', children: [], done: false, question: { text: e.question, context: e.context, index: qIdx++ } }
      }
      continue
    }
    flushRun()
    blocks.push({ kind: 'event', entry: e })
  }
  flushRun()
  return blocks
}

// ── Agent run component (collapsible) ────────────────────────────────

function RunBlock({ run, jobId }: { run: AgentRun; jobId: string }): React.ReactElement {
  const hasQuestion = !!run.question
  const job = useJobStore((s) => s.jobs[jobId])
  const isPending = hasQuestion && run.question!.index === (job?.humanExchanges?.length ?? 0) - 1 && job?.awaitingHuman
  const [open, setOpen] = useState(isPending)
  const c = colors(run.node)
  const calls = run.children.filter((e) => e.__typename === 'AgentToolCallEvent').length

  useEffect(() => { if (isPending) setOpen(true) }, [isPending])

  const statusIcon = hasQuestion && isPending
    ? <MessageSquare className="h-3.5 w-3.5 text-amber-600 ml-auto" />
    : run.done
      ? <Check className="h-3.5 w-3.5 text-emerald-600 ml-auto" />
      : <Loader2 className="h-3.5 w-3.5 text-blue-600 ml-auto animate-spin" />

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className={cn('rounded-lg border', c.border, c.bg)}>
        <CollapsibleTrigger className="w-full flex items-center gap-2 px-3 py-2 text-left">
          <ChevronRight className={cn('h-3 w-3 transition-transform text-muted-foreground', open && 'rotate-90')} />
          <span className={cn('text-sm font-medium', c.text)}>{label(run.node)}</span>
          {calls > 0 && <span className="text-muted-foreground text-xs">{calls} tool call{calls !== 1 ? 's' : ''}</span>}
          {statusIcon}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-3 pb-3 space-y-1 border-t pt-2 ml-5">
            {run.children.map((ev, i) =>
              ev.__typename === 'AgentToolCallEvent' ? (
                <div key={i} className="text-xs flex items-center gap-1">
                  <Wrench className="h-3 w-3 text-muted-foreground shrink-0" />
                  <span className="text-foreground font-mono">{ev.toolName}</span>
                  {ev.inputPreview && <span className="text-muted-foreground font-mono">({ev.inputPreview})</span>}
                </div>
              ) : ev.__typename === 'AgentToolResultEvent' ? (
                <div key={i} className="text-xs text-muted-foreground font-mono pl-4 break-all flex items-start gap-1">
                  <ArrowLeft className="h-3 w-3 shrink-0 mt-0.5" />
                  <span>{ev.resultSummary}</span>
                </div>
              ) : null,
            )}
            {hasQuestion && (
              <QuestionInRun question={run.question!.text} index={run.question!.index} jobId={jobId} />
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

// ── Question inside a run ─────────────────────────────────────────────

function QuestionInRun({ question, index, jobId }: { question: string; index: number; jobId: string }): React.ReactElement {
  const job = useJobStore((s) => s.jobs[jobId])
  const updateJob = useJobStore((s) => s.updateJob)
  const pushEvent = useJobStore((s) => s.pushEvent)

  const exchange = job?.humanExchanges?.[index]
  const isLast = index === (job?.humanExchanges?.length ?? 0) - 1
  const isPending = isLast && job?.awaitingHuman

  if (isPending) {
    return (
      <QuestionCard
        jobId={jobId}
        question={question}
        onAnswered={(answerText) => {
          const exchanges = [...(job?.humanExchanges || [])]
          if (exchanges[index]) exchanges[index] = { ...exchanges[index], answer: answerText }
          updateJob(jobId, { awaitingHuman: false, pendingQuestion: '', humanExchanges: exchanges })
          pushEvent(jobId, { __typename: 'HumanAnswerEntry', answer: answerText })
        }}
      />
    )
  }

  return (
    <div className="space-y-1 mt-1">
      <div className="text-sm">
        <span className="text-amber-700 font-medium">Question: </span>
        <span className="text-foreground">{question}</span>
      </div>
      {exchange?.answer && (
        <div className="text-sm">
          <span className="text-amber-600 font-medium">Your answer: </span>
          <span className="text-foreground">{exchange.answer}</span>
        </div>
      )}
    </div>
  )
}

// ── Standalone event banner ──────────────────────────────────────────

function EventBanner({ entry }: { entry: LogEntry }): React.ReactElement | null {
  const cfg = EVENT_DISPLAY[entry.__typename]
  if (!cfg) return null
  const text = cfg.text(entry as unknown as Record<string, string>)
  return (
    <div className={cn('rounded px-3 py-2 text-sm flex items-center gap-2', cfg.className)}>
      {cfg.icon}
      {text}
    </div>
  )
}

// ── Main component ───────────────────────────────────────────────────

export function ActivityLog({ jobId }: { jobId: string }): React.ReactElement {
  const eventLog = useJobStore((s) => s.eventLog[jobId] || [])
  const job = useJobStore((s) => s.jobs[jobId])
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [eventLog.length])

  if (!job) return <div />

  const blocks = buildBlocks(eventLog)

  return (
    <div className="space-y-2">
      {blocks.length === 0 && job.status === 'queued' && (
        <div className="text-center text-muted-foreground text-sm py-8">Job queued. Waiting for worker...</div>
      )}
      {blocks.map((block, i) =>
        block.kind === 'run'
          ? <RunBlock key={i} run={block.run} jobId={jobId} />
          : <EventBanner key={i} entry={block.entry} />,
      )}
      <div ref={bottomRef} />
    </div>
  )
}
