import React, { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { useJobStore } from '../store/jobStore'
import type { LogEntry } from '../store/jobStore'
import { QuestionCard } from './QuestionCard'

// ── Style config ─────────────────────────────────────────────────────

const NODE_STYLE: Record<string, { text: string; border: string; bg: string }> = {
  investigator:    { text: 'text-blue-300',   border: 'border-blue-700',   bg: 'bg-blue-950/20' },
  codebase_search: { text: 'text-purple-300', border: 'border-purple-700', bg: 'bg-purple-950/20' },
  web_search:      { text: 'text-cyan-300',   border: 'border-cyan-700',   bg: 'bg-cyan-950/20' },
  critic:          { text: 'text-orange-300',  border: 'border-orange-700', bg: 'bg-orange-950/20' },
  human_input:     { text: 'text-amber-300',   border: 'border-amber-700',  bg: 'bg-amber-950/20' },
  writer:          { text: 'text-green-300',   border: 'border-green-700',  bg: 'bg-green-950/20' },
}
const DEFAULT_STYLE = { text: 'text-gray-300', border: 'border-gray-700', bg: 'bg-gray-800/30' }

function label(node: string): string { return node.replace(/_/g, ' ') }
function colors(node: string) { return NODE_STYLE[node] || DEFAULT_STYLE }

// ── Standalone event config (icon + text + style — no branching) ─────

interface EventDisplay {
  icon: string
  text: (e: Record<string, string>) => string
  className: string
}

const EVENT_DISPLAY: Record<string, EventDisplay> = {
  JobDoneEvent:     { icon: '\u2713', text: () => 'Job completed',                                     className: 'border border-green-800 bg-green-950/30 text-green-300 font-medium' },
  JobFailedEvent:   { icon: '\u2717', text: (e) => `Job failed${e.error ? `: ${e.error}` : ''}`,       className: 'border border-red-800 bg-red-950/30 text-red-300' },
  JobKilledEvent:   { icon: '\u2715', text: () => 'Job killed',                                        className: 'border border-gray-700 bg-gray-800/50 text-gray-400' },
  JobTimedOutEvent: { icon: '\u23f1', text: () => 'Job timed out',                                     className: 'border border-red-800 bg-red-950/30 text-red-300' },
  JobSnapshotEvent: { icon: '\u21bb', text: (e) => `Reconnected \u2014 ${e.status}${e.currentNode ? `, at ${label(e.currentNode)}` : ''}`, className: 'text-gray-500 text-xs py-0' },
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
    // Agent spawned (non-supervisor) → start a new run
    if (e.__typename === 'AgentSpawnedEvent' && e.node !== 'supervisor') {
      flushRun()
      run = { node: e.node, children: [], done: false }
      continue
    }
    // Agent done (non-supervisor) → close current run
    if (e.__typename === 'AgentDoneEvent' && e.node !== 'supervisor') {
      if (run?.node === e.node) run.done = true
      flushRun()
      continue
    }
    // Tool events → nest inside current run
    if (run && (e.__typename === 'AgentToolCallEvent' || e.__typename === 'AgentToolResultEvent')) {
      run.children.push(e)
      continue
    }
    // Question → attach to current run (human_input node) or standalone
    if (e.__typename === 'GraphInterruptEvent') {
      if (run) {
        run.question = { text: e.question, context: e.context, index: qIdx++ }
      } else {
        // Shouldn't happen, but handle gracefully — make a synthetic run
        run = { node: 'human_input', children: [], done: false, question: { text: e.question, context: e.context, index: qIdx++ } }
      }
      continue
    }
    // Everything else → standalone
    flushRun()
    blocks.push({ kind: 'event', entry: e })
  }
  flushRun()
  return blocks
}

// ── Agent run component (collapsible) ────────────────────────────────

function RunBlock({ run, jobId }: { run: AgentRun; jobId: string }): React.ReactElement {
  const hasQuestion = !!run.question
  // Default open only if there's a pending question (user needs to interact)
  const job = useJobStore((s) => s.jobs[jobId])
  const isPending = hasQuestion && run.question!.index === (job?.humanExchanges?.length ?? 0) - 1 && job?.awaitingHuman
  const [open, setOpen] = useState(isPending)
  const c = colors(run.node)
  const calls = run.children.filter((e) => e.__typename === 'AgentToolCallEvent').length

  // Auto-open when a question arrives
  useEffect(() => { if (isPending) setOpen(true) }, [isPending])

  const statusLabel = hasQuestion && isPending
    ? <span className="text-amber-400 text-xs ml-auto">awaiting input</span>
    : run.done
      ? <span className="text-green-500 text-xs ml-auto">&#10003; done</span>
      : <span className="text-blue-400 text-xs ml-auto animate-pulse">running...</span>

  return (
    <div className={clsx('rounded-lg border', c.border, c.bg)}>
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 px-3 py-2 text-left">
        <span className={clsx('text-xs transition-transform', open && 'rotate-90')}>&#9654;</span>
        <span className={clsx('text-sm font-medium', c.text)}>{label(run.node)}</span>
        {statusLabel}
        {calls > 0 && <span className="text-gray-500 text-xs">{calls} tool call{calls !== 1 ? 's' : ''}</span>}
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-1 border-t border-gray-700/50 pt-2 ml-5">
          {run.children.map((ev, i) =>
            ev.__typename === 'AgentToolCallEvent' ? (
              <div key={i} className="text-xs">
                <span className="text-gray-500">&#9881; </span>
                <span className="text-gray-300 font-mono">{ev.toolName}</span>
                {ev.inputPreview && <span className="text-gray-500 font-mono ml-1">({ev.inputPreview})</span>}
              </div>
            ) : ev.__typename === 'AgentToolResultEvent' ? (
              <div key={i} className="text-xs text-gray-500 font-mono pl-3 break-all">&#8592; {ev.resultSummary}</div>
            ) : null,
          )}
          {hasQuestion && (
            <QuestionInRun question={run.question!.text} index={run.question!.index} jobId={jobId} />
          )}
        </div>
      )}
    </div>
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
        <span className="text-amber-400 font-medium">Question: </span>
        <span className="text-gray-300">{question}</span>
      </div>
      {exchange?.answer && (
        <div className="text-sm">
          <span className="text-amber-300 font-medium">Your answer: </span>
          <span className="text-gray-300">{exchange.answer}</span>
        </div>
      )}
    </div>
  )
}

// ── Standalone event banner (config-driven) ──────────────────────────

function EventBanner({ entry }: { entry: LogEntry }): React.ReactElement | null {
  const cfg = EVENT_DISPLAY[entry.__typename]
  if (!cfg) return null
  const text = cfg.text(entry as unknown as Record<string, string>)
  return (
    <div className={clsx('rounded px-3 py-2 text-sm', cfg.className)}>
      {cfg.icon} {entry.__typename === 'HumanAnswerEntry'
        ? <><span className="font-medium">Your answer: </span>{text}</>
        : text}
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
        <div className="text-center text-gray-500 text-sm py-8">Job queued. Waiting for worker...</div>
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
