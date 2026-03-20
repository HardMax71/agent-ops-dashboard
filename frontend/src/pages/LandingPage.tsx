import React from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

function GitHubIcon({ className }: { className?: string }): React.ReactElement {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
    </svg>
  )
}

function handleLogin(): void {
  window.location.href = '/api/auth/login'
}

const AGENTS = [
  {
    name: 'investigator',
    color: 'text-blue-600',
    border: 'border-l-blue-400',
    desc: 'Reads the issue, searches for related bugs and prior discussions.',
    tools: ['search_issues', 'read_file', 'read_issue'],
  },
  {
    name: 'codebase_search',
    color: 'text-purple-600',
    border: 'border-l-purple-400',
    desc: 'Greps the codebase for relevant patterns, symbols, and file structures.',
    tools: ['grep', 'find_symbol', 'read_file'],
  },
  {
    name: 'web_search',
    color: 'text-cyan-600',
    border: 'border-l-cyan-400',
    desc: 'Searches documentation, Stack Overflow, and external references for context.',
    tools: ['web_search'],
  },
  {
    name: 'critic',
    color: 'text-orange-600',
    border: 'border-l-orange-400',
    desc: 'Cross-checks all findings, identifies contradictions, and rates confidence.',
    tools: ['evaluate_findings'],
  },
  {
    name: 'human_input',
    color: 'text-amber-600',
    border: 'border-l-amber-400',
    desc: 'Surfaces clarifying questions when the agents need your context to continue.',
    tools: ['ask_human'],
  },
  {
    name: 'writer',
    color: 'text-emerald-600',
    border: 'border-l-emerald-400',
    desc: 'Compiles everything into a structured triage report and a GitHub comment draft.',
    tools: ['generate_report'],
  },
]

export function LandingPage(): React.ReactElement {
  return (
    <div className="min-h-screen bg-background">
      {/* ── Nav ──────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-50 border-b bg-background/80 backdrop-blur-sm">
        <div className="max-w-5xl mx-auto flex items-center justify-between px-6 h-14">
          <span className="font-bold tracking-tight">AgentOps</span>
          <Button
            onClick={handleLogin}
            size="sm"
            className="gap-2"
            aria-label="Sign in with GitHub"
          >
            <GitHubIcon className="h-4 w-4" />
            Sign in with GitHub
          </Button>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pt-20 pb-24 lg:pt-28 lg:pb-32">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-start">
          {/* Copy */}
          <div className="lg:pt-6">
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight leading-[1.1]">
              Paste an issue.
              <br />
              Get a root cause.
            </h1>
            <p className="text-muted-foreground leading-relaxed mt-6 max-w-md">
              You give it a GitHub issue URL. It dispatches AI agents to
              investigate — they search your codebase, read related issues,
              and ask you questions when they get stuck. You get back a
              triage report with severity, root cause, and the files that matter.
            </p>
            <div className="mt-8">
              <Button onClick={handleLogin} size="lg" className="gap-2 h-11">
                <GitHubIcon className="h-5 w-5" />
                Sign in with GitHub
              </Button>
            </div>
            <p className="text-xs text-muted-foreground mt-4">
              Open source &middot; bring your own LLM keys
            </p>
          </div>

          {/* Agent run log */}
          <div className="rounded-xl border bg-muted/30 p-5 font-mono text-[13px] leading-[1.7] space-y-3 overflow-x-auto">
            <div className="text-xs text-muted-foreground pb-2.5 border-b">
              acme/api-gateway#847
            </div>

            <div>
              <div className="flex justify-between items-baseline">
                <span className="text-blue-600 font-semibold">&#9656; investigator</span>
                <span className="text-emerald-600 text-[11px]">done</span>
              </div>
              <div className="pl-4 text-muted-foreground">
                search_issues <span className="opacity-50">&quot;auth middleware crash&quot;</span>
              </div>
              <div className="pl-4 text-muted-foreground/50">&larr; 3 related issues</div>
              <div className="pl-4 text-muted-foreground">
                read_file <span className="opacity-50">src/auth/middleware.ts</span>
              </div>
              <div className="pl-4 text-muted-foreground/50">&larr; token validation at L42</div>
            </div>

            <div>
              <div className="flex justify-between items-baseline">
                <span className="text-purple-600 font-semibold">&#9656; codebase_search</span>
                <span className="text-emerald-600 text-[11px]">done</span>
              </div>
              <div className="pl-4 text-muted-foreground">
                grep <span className="opacity-50">&quot;token.verify&quot; --include *.ts</span>
              </div>
              <div className="pl-4 text-muted-foreground/50">&larr; 4 matches in 2 files</div>
            </div>

            <div>
              <div className="flex justify-between items-baseline">
                <span className="text-orange-600 font-semibold">&#9656; critic</span>
                <span className="text-emerald-600 text-[11px]">done</span>
              </div>
              <div className="pl-4 text-muted-foreground">evaluate_findings</div>
              <div className="pl-4 text-muted-foreground/50">&larr; 91% confidence &mdash; null deref on expired token</div>
            </div>

            <div>
              <div className="flex justify-between items-baseline">
                <span className="text-amber-600 font-semibold">&#9656; human_input</span>
                <span className="text-amber-500 text-[11px]">answered</span>
              </div>
              <div className="pl-4 text-amber-600/70">? Which auth provider is in production?</div>
              <div className="pl-4 text-amber-600/50">&rarr; Auth0, JWT with 15-min rotation</div>
            </div>

            <div>
              <div className="flex justify-between items-baseline">
                <span className="text-emerald-600 font-semibold">&#9656; writer</span>
                <span className="text-emerald-600 text-[11px]">done</span>
              </div>
              <div className="pl-4 text-muted-foreground/50">&larr; severity: critical</div>
              <div className="pl-4 text-muted-foreground/50">&larr; root cause: token expiry not checked</div>
              <div className="pl-4 text-muted-foreground/50">&larr; files: middleware.ts, token.ts</div>
            </div>

            <div className="pt-1.5 border-t text-emerald-600 font-semibold text-[11px]">
              &#10003; report posted to acme/api-gateway#847
            </div>
          </div>
        </div>
      </section>

      <Separator className="max-w-5xl mx-auto" />

      {/* ── Agent roster ─────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-6 py-20">
        <p className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-8">
          the agents
        </p>
        <div>
          {AGENTS.map((agent, i) => (
            <div
              key={agent.name}
              className={`border-l-2 ${agent.border} pl-4 py-4 ${i > 0 ? 'mt-1' : ''}`}
            >
              <div className="flex items-baseline gap-3 flex-wrap">
                <span className={`font-semibold font-mono text-sm ${agent.color}`}>
                  {agent.name}
                </span>
                <span className="text-[11px] text-muted-foreground font-mono">
                  {agent.tools.join(' &middot; ')}
                </span>
              </div>
              <p className="text-sm text-muted-foreground mt-1">{agent.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-xs text-muted-foreground mt-8">
          A LangGraph supervisor orchestrates the flow. Not every agent runs every time —
          the supervisor decides what&apos;s needed based on the issue.
        </p>
      </section>

      <Separator className="max-w-5xl mx-auto" />

      {/* ── Output preview ───────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-6 py-20">
        <p className="text-xs font-mono text-muted-foreground uppercase tracking-wider mb-8">
          the output
        </p>
        <div className="grid md:grid-cols-2 gap-6 items-start">
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold">Triage Report</CardTitle>
                <Badge
                  variant="outline"
                  className="bg-red-50 text-red-700 border-red-200 text-[11px]"
                >
                  critical
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-[11px] text-muted-foreground uppercase tracking-wide mb-1">Root Cause</p>
                <p className="text-sm leading-relaxed">
                  Token expiry not checked in auth middleware. When the JWT
                  expires mid-request, <code className="text-xs bg-muted px-1 py-0.5 rounded">token.verify()</code> returns
                  null instead of throwing, causing a null deref at L42.
                </p>
              </div>
              <div>
                <p className="text-[11px] text-muted-foreground uppercase tracking-wide mb-1">Relevant Files</p>
                <div className="font-mono text-xs text-blue-600 space-y-0.5">
                  <div>src/auth/middleware.ts:42</div>
                  <div>src/auth/token.ts:18</div>
                </div>
              </div>
              <div className="flex items-baseline justify-between">
                <div>
                  <p className="text-[11px] text-muted-foreground uppercase tracking-wide mb-1">Confidence</p>
                  <p className="text-sm font-medium">91%</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="space-y-3">
            <p className="text-[11px] text-muted-foreground uppercase tracking-wide">
              Posts to the issue as
            </p>
            <div className="rounded-lg border bg-muted/30 p-4 font-mono text-xs leading-relaxed text-muted-foreground">
              <div className="text-foreground font-semibold text-sm font-sans mb-2">Triage Report</div>
              <div><span className="font-semibold text-foreground">Severity:</span> Critical</div>
              <div className="mt-1.5"><span className="font-semibold text-foreground">Root cause:</span> Token expiry not checked in auth middleware. <code>token.verify()</code> returns null on expiry.</div>
              <div className="mt-1.5"><span className="font-semibold text-foreground">Files:</span></div>
              <div className="pl-2">- <code>src/auth/middleware.ts:42</code></div>
              <div className="pl-2">- <code>src/auth/token.ts:18</code></div>
              <div className="mt-1.5"><span className="font-semibold text-foreground">Confidence:</span> 91%</div>
              <div className="mt-3 pt-3 border-t text-[10px] text-muted-foreground/60">
                Generated by AgentOps
              </div>
            </div>
            <Button className="w-full" disabled>
              Post to GitHub
            </Button>
          </div>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────── */}
      <footer className="border-t py-8 px-6">
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <span className="text-sm text-muted-foreground">AgentOps</span>
          <Button
            onClick={handleLogin}
            variant="ghost"
            size="sm"
            className="gap-2 text-muted-foreground"
          >
            <GitHubIcon className="h-4 w-4" />
            Sign in
          </Button>
        </div>
      </footer>
    </div>
  )
}
