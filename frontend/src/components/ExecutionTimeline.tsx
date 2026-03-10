import React from 'react'
import clsx from 'clsx'
import type { AgentFinding } from '../types'

interface ExecutionTimelineProps {
  findings: AgentFinding[]
  currentNode: string
}

const NODE_ORDER = ['supervisor', 'investigator', 'codebase_search', 'web_search', 'critic', 'human_input', 'writer']

export function ExecutionTimeline({ findings, currentNode }: ExecutionTimelineProps): React.ReactElement {
  const visitedNodes = new Set(findings.map((f) => f.agent_name))

  return (
    <div
      className="flex items-center gap-1 p-3 bg-gray-800 rounded-lg border border-gray-700 overflow-x-auto"
      role="list"
      aria-label="Execution timeline"
    >
      {NODE_ORDER.map((node, idx) => {
        const isVisited = visitedNodes.has(node)
        const isCurrent = currentNode === node
        return (
          <React.Fragment key={node}>
            {idx > 0 && (
              <div
                className={clsx('h-px flex-1 min-w-4', isVisited ? 'bg-blue-500' : 'bg-gray-600')}
                aria-hidden="true"
              />
            )}
            <div
              role="listitem"
              aria-label={`${node}: ${isCurrent ? 'active' : isVisited ? 'completed' : 'pending'}`}
              className={clsx(
                'flex-shrink-0 rounded-full text-xs px-2 py-1 font-medium whitespace-nowrap transition-colors',
                isCurrent
                  ? 'bg-blue-600 text-white ring-2 ring-blue-400 ring-offset-2 ring-offset-gray-800'
                  : isVisited
                  ? 'bg-blue-900 text-blue-200'
                  : 'bg-gray-700 text-gray-400'
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
