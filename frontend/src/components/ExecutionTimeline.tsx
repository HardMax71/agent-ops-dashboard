import React from 'react'
import { cn } from '@/lib/utils'
import type { AgentFinding } from '../store/jobStore'

interface ExecutionTimelineProps {
  findings: AgentFinding[]
  currentNode: string
  status: string
}

const NODE_ORDER = ['supervisor', 'investigator', 'codebase_search', 'web_search', 'critic', 'human_input', 'writer']

export function ExecutionTimeline({ findings, currentNode, status }: ExecutionTimelineProps): React.ReactElement {
  const findingNodes = new Set(findings.map((f) => f.agentName))
  const currentIdx = NODE_ORDER.indexOf(currentNode)
  const isTerminal = ['done', 'failed', 'killed'].includes(status)

  return (
    <div
      className="flex items-center gap-1 p-3 bg-muted/50 rounded-lg border overflow-x-auto"
      role="list"
      aria-label="Execution timeline"
    >
      {NODE_ORDER.map((node, idx) => {
        const isVisited = findingNodes.has(node) || (currentIdx >= 0 && idx < currentIdx) || (isTerminal && currentIdx >= 0 && idx <= currentIdx)
        const isCurrent = currentNode === node && !isTerminal
        return (
          <React.Fragment key={node}>
            {idx > 0 && (
              <div
                className={cn('h-px flex-1 min-w-4', isVisited ? 'bg-primary' : 'bg-border')}
                aria-hidden="true"
              />
            )}
            <div
              role="listitem"
              aria-label={`${node}: ${isCurrent ? 'active' : isVisited ? 'completed' : 'pending'}`}
              className={cn(
                'flex-shrink-0 rounded-full text-xs px-2 py-1 font-medium whitespace-nowrap transition-colors',
                isCurrent
                  ? 'bg-primary text-primary-foreground ring-2 ring-primary/30 ring-offset-2 ring-offset-background'
                  : isVisited
                  ? 'bg-primary/10 text-primary'
                  : 'bg-muted text-muted-foreground'
              )}
            >
              {node.replace('_', ' ')}
            </div>
          </React.Fragment>
        )
      })}
    </div>
  )
}
