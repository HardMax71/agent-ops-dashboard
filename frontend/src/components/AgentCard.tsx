import React from 'react'
import clsx from 'clsx'
import type { AgentFinding, AgentCardState } from '../types'

interface AgentCardProps {
  finding: AgentFinding
  state: AgentCardState
  streamedTokens?: string
}

const AGENT_COLORS: Record<string, string> = {
  investigator: 'border-blue-600 bg-blue-950/30',
  codebase_search: 'border-purple-600 bg-purple-950/30',
  web_search: 'border-cyan-600 bg-cyan-950/30',
  critic: 'border-orange-600 bg-orange-950/30',
  writer: 'border-green-600 bg-green-950/30',
  supervisor: 'border-gray-600 bg-gray-800/30',
}

export function AgentCard({ finding, state, streamedTokens }: AgentCardProps): React.ReactElement {
  const colorClass = AGENT_COLORS[finding.agent_name] || 'border-gray-600 bg-gray-800/30'

  return (
    <div
      className={clsx('rounded-lg border p-4 transition-all', colorClass)}
      role="article"
      aria-label={`${finding.agent_name} agent finding`}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-200 capitalize">
          {finding.agent_name.replace('_', ' ')}
        </h3>
        <div className="flex items-center gap-2">
          {state === 'running' && (
            <span
              className="text-xs text-blue-300 animate-pulse"
              aria-live="polite"
            >
              processing...
            </span>
          )}
          <span className="text-xs text-gray-400">
            {Math.round(finding.confidence * 100)}% confidence
          </span>
        </div>
      </div>

      <p className="text-sm text-gray-300 mb-2">{finding.summary}</p>

      {finding.hypothesis && (
        <div className="mt-2">
          <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Hypothesis</p>
          <p className="text-sm text-gray-300 font-mono text-xs bg-gray-900 rounded p-2">
            {finding.hypothesis}
          </p>
        </div>
      )}

      {finding.affected_areas && finding.affected_areas.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {finding.affected_areas.map((area) => (
            <span key={area} className="text-xs bg-gray-700 text-gray-300 rounded px-2 py-0.5">
              {area}
            </span>
          ))}
        </div>
      )}

      {streamedTokens && (
        <div
          className="mt-3 text-xs text-gray-400 font-mono bg-gray-900 rounded p-2 max-h-24 overflow-y-auto"
          aria-live="polite"
          aria-label="Streamed output"
        >
          {streamedTokens}
        </div>
      )}
    </div>
  )
}
