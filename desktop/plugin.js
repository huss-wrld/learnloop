// learnloop Desktop half: the question card (::learnloop-question{id="q_…"}).
// Copyright (C) 2026 Hussein Al-Amodi. AGPL-3.0-only.
import * as sdk from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const LETTERS = 'ABCDEFGH'
const STOPS = ['0', '30', '50', '70', '90', '100']
const QID = /^q_[0-9a-f]{12}$/
const VERDICT = {
  correct: { label: 'Correct', tone: 'var(--ui-success, #2e7d32)' },
  partial: { label: 'Partly right', tone: 'var(--ui-warning, #f9a825)' },
  wrong: { label: 'Not quite', tone: 'var(--ui-danger, #c62828)' },
  dont_know: { label: "You didn't know yet", tone: 'var(--ui-text-tertiary)' }
}

const cn = (...a) => (sdk.cn ? sdk.cn(...a) : a.filter(Boolean).join(' '))
const Md = ({ text }) => (sdk.MessageTextContent ? jsx(sdk.MessageTextContent, { text, media: false }) : jsx('span', { children: text }))
const Label = ({ children }) => jsx('div', { className: 'text-[0.7rem] font-medium uppercase tracking-wide text-(--ui-text-tertiary)', children })

function Field({ label, value, onChange, placeholder, rows = 2 }) {
  const Area = sdk.Textarea || 'textarea'
  return jsxs('label', {
    className: 'flex flex-col gap-1',
    children: [
      jsx(Label, { children: label }),
      jsx(Area, { value, rows, placeholder, onChange: e => onChange(e.target.value), className: 'min-h-0 text-sm' })
    ]
  })
}

function Option({ i, text, selected, multi, onClick, mark }) {
  return jsxs('button', {
    type: 'button',
    onClick,
    disabled: !onClick,
    className: cn(
      'flex w-full items-start gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors',
      selected ? 'border-(--ui-accent) bg-(--ui-accent)/10' : 'border-(--ui-stroke-secondary)',
      onClick ? 'hover:border-(--ui-accent)' : 'cursor-default'
    ),
    style: mark ? { borderColor: mark } : undefined,
    children: [
      jsx('span', {
        className: cn('mt-0.5 inline-flex size-5 shrink-0 items-center justify-center text-xs font-semibold',
          multi ? 'rounded-sm' : 'rounded-full', 'border border-(--ui-stroke-secondary)'),
        style: selected ? { background: 'var(--ui-accent)', color: 'var(--background, #fff)', borderColor: 'var(--ui-accent)' } : undefined,
        children: LETTERS[i]
      }),
      jsx('div', { className: 'min-w-0 flex-1 [&_p]:my-0', children: jsx(Md, { text }) })
    ]
  })
}

function Result({ q }) {
  // The explanation is tucked behind "Why", viewable but never centre stage (as LearnHarness's answered card).
  const [whyOpen, setWhyOpen] = useState(false)
  const sub = q.submission || {}
  const res = q.result
  const v = res && VERDICT[res.verdict]
  return jsxs('div', {
    className: 'flex flex-col gap-3',
    children: [
      q.kind === 'mc' && jsx('div', {
        className: 'flex flex-col gap-1.5',
        children: q.options.map((o, i) => {
          const chosen = (sub.choices || []).includes(i)
          const right = res && res.correct.includes(i)
          const mark = right ? VERDICT.correct.tone : chosen ? VERDICT.wrong.tone : undefined
          return jsx(Option, { i, text: o, selected: chosen, multi: q.multi, mark }, i)
        })
      }),
      q.kind === 'free' && jsxs('div', {
        className: 'flex flex-col gap-1',
        children: [jsx(Label, { children: 'Your answer' }),
          jsx('div', { className: 'text-sm', children: sub.dont_know ? "I don't know" : sub.text })]
      }),
      jsxs('div', {
        className: 'flex flex-wrap items-center gap-2 text-sm',
        children: [
          v ? jsx('span', { className: 'font-semibold', style: { color: v.tone }, children: v.label })
            : jsx('span', { className: 'text-(--ui-text-tertiary)', children: 'Submitted. Waiting for grading…' }),
          sub.confidence != null && jsx('span', { className: 'text-(--ui-text-tertiary)', children: `· confidence ${sub.confidence}%` })
        ]
      }),
      res && res.explanation && jsx('button', {
        type: 'button',
        onClick: () => setWhyOpen(!whyOpen),
        className: 'self-start text-xs font-medium text-(--ui-text-tertiary) hover:text-(--ui-text-primary)',
        children: whyOpen ? 'Hide why' : 'Why'
      }),
      res && res.explanation && whyOpen && jsx('div', {
        className: 'rounded-md bg-(--ui-stroke-secondary)/30 px-3 py-2 text-sm text-(--ui-text-secondary)',
        children: jsx(Md, { text: res.explanation })
      }),
      res && res.expected && jsxs('div', {
        className: 'flex flex-col gap-1 rounded-md bg-(--ui-stroke-secondary)/30 px-3 py-2 text-sm',
        children: [jsx(Label, { children: 'Model answer' }), jsx(Md, { text: res.expected })]
      }),
      sub.thinking && jsxs('div', {
        className: 'text-xs text-(--ui-text-tertiary)',
        children: [jsx('span', { className: 'font-medium', children: 'Your thinking: ' }), sub.thinking]
      })
    ]
  })
}

function QuestionCard({ ctx, id, sessionId }) {
  const [q, setQ] = useState(null)
  const [error, setError] = useState('')
  const [choices, setChoices] = useState([])
  const [text, setText] = useState('')
  const [confidence, setConfidence] = useState('')
  const [thinking, setThinking] = useState('')
  const [reading, setReading] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    ctx.rest(`/question/${id}`).then(setQ, e => setError(String(e && e.message ? e.message : e)))
  }, [ctx, id])
  useEffect(load, [load])
  // A free answer waits for the model's verdict: poll until it's graded.
  useEffect(() => {
    if (!q || q.status !== 'open' || !q.submission) return undefined
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [q, load])

  const send = async dontKnow => {
    setBusy(true)
    try {
      const body = { dont_know: dontKnow, thinking, reading_thinking: reading,
        confidence: !dontKnow && confidence !== '' ? Number(confidence) : null }
      if (!dontKnow) Object.assign(body, q.kind === 'mc' ? { choices } : { text })
      const r = await ctx.rest(`/question/${id}/submit`, { method: 'POST', body })
      setQ(r.question)
      const sent = sdk.host.composer.submit(sessionId ?? null, r.line)
      if (!sent) sdk.host.notify({ kind: 'info', message: 'Answer saved. Open this chat and send any message to continue the lesson.' })
    } catch (e) {
      sdk.host.notify({ kind: 'warning', message: `learnloop: ${e && e.message ? e.message : e}` })
    } finally {
      setBusy(false)
    }
  }

  const shell = children => jsxs('div', {
    className: 'my-2 flex max-w-2xl flex-col gap-3 rounded-lg border border-(--ui-stroke-secondary) p-4 text-(--ui-text-primary)',
    'data-slot': 'learnloop-question',
    children: Array.isArray(children) ? children : [children]
  })

  if (!QID.test(id || '') || error) {
    return shell(jsx('div', { className: 'text-sm text-(--ui-text-tertiary)',
      children: "This question wasn't created properly, so it can't be answered here. Ask for it again in the chat." }))
  }
  if (!q) return shell(jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children: 'Loading question…' }))

  const header = jsxs('div', {
    className: 'flex items-center gap-2',
    children: [jsx(Label, { children: 'Question' }),
      q.qtype && jsx('span', { className: 'rounded-full border border-(--ui-stroke-secondary) px-2 text-[0.65rem] text-(--ui-text-tertiary)',
        children: q.qtype === 'predict' ? 'predict' : 'check' })]
  })
  const prompt = jsx('div', { className: 'text-sm [&_p:first-child]:mt-0 [&_p:last-child]:mb-0', children: jsx(Md, { text: q.prompt }) })

  if (q.status === 'abandoned') {
    return shell([header, prompt, jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children: 'The lesson ended before this was answered.' })])
  }
  if (q.submission || q.status === 'answered') return shell([header, prompt, jsx(Result, { q })])

  const toggle = i => setChoices(q.multi ? (choices.includes(i) ? choices.filter(c => c !== i) : [...choices, i]) : [i])
  const ready = q.kind === 'mc' ? choices.length > 0 : text.trim().length > 0
  const Btn = sdk.Button || 'button'
  return shell([
    header,
    prompt,
    jsx(Field, { label: 'Thoughts while reading (optional)', value: reading, onChange: setReading, rows: 1 }),
    q.kind === 'mc'
      ? jsxs('div', { className: 'flex flex-col gap-1.5', children: [
        q.multi && jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: 'More than one is right: select all that apply.' }),
        ...q.options.map((o, i) => jsx(Option, { i, text: o, multi: q.multi, selected: choices.includes(i), onClick: () => toggle(i) }, i))
      ] })
      : jsx(Field, { label: 'Your answer', value: text, onChange: setText, rows: 3 }),
    jsxs('div', { className: 'flex flex-col gap-1', children: [
      jsx(Label, { children: 'Confidence' }),
      sdk.SegmentedControl
        ? jsx(sdk.SegmentedControl, { value: confidence, onChange: setConfidence, sizing: 'equal',
          options: STOPS.map(s => ({ id: s, label: `${s}%` })) })
        : jsx('div', { className: 'flex gap-1', children: STOPS.map(s => jsx('button', { type: 'button', onClick: () => setConfidence(s), children: `${s}%` }, s)) })
    ] }),
    jsx(Field, { label: 'Your thinking', value: thinking, onChange: setThinking, rows: 2 }),
    jsxs('div', { className: 'flex justify-end gap-2', children: [
      jsx(Btn, { type: 'button', variant: 'ghost', disabled: busy, onClick: () => send(true), children: "I don't know" }),
      jsx(Btn, { type: 'button', disabled: busy || !ready, onClick: () => send(false), children: busy ? 'Sending…' : 'Submit' })
    ] })
  ])
}


// ---------- shared ----------
const PHASES = ['probe', 'plan', 'teach', 'done']
const PHASE_LABEL = { probe: 'Probe', plan: 'Plan', teach: 'Teach', done: 'Done' }
const STATE_MARK = { done: '✓', current: '●', todo: '○' }

function usePoll(ctx, path, ms) {
  const [data, setData] = useState(null)
  useEffect(() => {
    if (!path) { setData(null); return undefined }
    let live = true
    const tick = () => ctx.rest(path).then(d => live && setData(d), () => {})
    tick()
    const t = setInterval(tick, ms)
    return () => { live = false; clearInterval(t) }
  }, [ctx, path, ms])
  return data
}

// Store timestamps are ISO strings; sdk.relativeTime wants epoch ms (an ISO string made it throw).
function when(iso) {
  const ms = Date.parse(iso)
  if (!Number.isFinite(ms)) return ''
  try { return sdk.relativeTime ? sdk.relativeTime(ms) : new Date(ms).toLocaleDateString() } catch { return new Date(ms).toLocaleDateString() }
}

function startLesson(topic) {
  const t = topic.trim()
  if (!t) return
  // A lesson belongs to its own chat: open a fresh one, then send the start command into it.
  if (typeof sdk.host.newChat === 'function') sdk.host.newChat()
  setTimeout(() => {
    const sent = sdk.host.composer.submit(null, `/learnloop:study ${t}`)
    if (!sent) sdk.host.notify({ kind: 'warning', message: `Type /learnloop:study ${t} in a chat to start.` })
  }, 400)
}

function StartBox({ compact }) {
  const [topic, setTopic] = useState('')
  const Btn = sdk.Button || 'button'
  const In = sdk.Input || 'input'
  return jsxs('form', {
    className: cn('flex gap-2', compact ? 'flex-col' : 'items-center'),
    onSubmit: e => { e.preventDefault(); startLesson(topic); setTopic('') },
    children: [
      jsx(In, { value: topic, onChange: e => setTopic(e.target.value), placeholder: 'What do you want to understand?',
        className: 'min-w-0 flex-1 text-sm' }),
      jsx(Btn, { type: 'submit', disabled: !topic.trim(), children: 'Start a lesson' })
    ]
  })
}

function PhaseSteps({ phase }) {
  const at = PHASES.indexOf(phase)
  return jsx('div', { className: 'flex items-center gap-1 text-[0.7rem]', children: PHASES.map((p, i) => jsxs('span', {
    className: cn('flex items-center gap-1', i === at ? 'font-semibold text-(--ui-text-primary)' : 'text-(--ui-text-tertiary)'),
    children: [i > 0 && jsx('span', { className: 'text-(--ui-text-quaternary)', children: '→' }), PHASE_LABEL[p]]
  }, p)) })
}

// ---------- lesson pane (right of the chat) ----------
function LessonPane({ ctx }) {
  const sid = sdk.useValue && sdk.host.state ? sdk.useValue(sdk.host.state.focusedStoredSessionId) : null
  const data = usePoll(ctx, sid ? `/lesson?session=${encodeURIComponent(sid)}` : null, 3000)
  const les = data && data.lesson
  const body = []
  if (!les) {
    body.push(jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children:
      'No lesson in this chat. Start one here, or type /learnloop:study <topic> in a chat.' }, 'e'))
    body.push(jsx(StartBox, { compact: true }, 's'))
  } else {
    body.push(jsx('div', { className: 'text-sm font-semibold leading-snug', children: les.goal }, 'g'))
    body.push(jsx(PhaseSteps, { phase: les.phase }, 'p'))
    const plan = les.plan
    const reached = plan ? plan.nodes.filter(n => n.state !== 'todo').length : 0
    body.push(jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: [
      plan ? `${reached}/${plan.nodes.length} steps` : 'Measuring what you already know',
      `${les.answered} answered (${les.correct} correct)`
    ].join(' · ') }, 'st'))
    if (plan) {
      body.push(jsx('div', { className: 'learnloop-map overflow-x-auto [&_p]:my-0', children:
        jsx(Md, { text: '```mermaid\n' + plan.mermaid + '\n```' }) }, 'm'))
      body.push(jsx('ol', { className: 'flex flex-col gap-1 text-sm', children: plan.nodes.map(n => jsxs('li', {
        className: cn('flex gap-2', n.state === 'current' ? 'font-semibold' : n.state === 'todo' ? 'text-(--ui-text-tertiary)' : ''),
        children: [jsx('span', { className: 'w-3 shrink-0', style: n.state === 'done' ? { color: VERDICT.correct.tone } : undefined,
          children: STATE_MARK[n.state] }), n.title]
      }, n.id)) }, 'n'))
    } else if (les.phase === 'probe') {
      body.push(jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children:
        'The plan appears here once the probe has found where your understanding ends.' }, 'pp'))
    }
    if (les.open_question) {
      body.push(jsxs('div', { className: 'rounded-md border border-(--ui-stroke-secondary) px-2 py-1.5 text-xs', children: [
        jsx(Label, { children: 'Open question' }), jsx('div', { className: 'line-clamp-3 [&_p]:my-0', children: jsx(Md, { text: les.open_question.prompt }) })
      ] }, 'q'))
    }
    if (les.facts.length) {
      body.push(jsxs('div', { className: 'flex flex-col gap-1', children: [
        jsx(Label, { children: 'Learned in this lesson' }),
        ...les.facts.map((f, i) => jsx('div', { className: 'text-xs', title: f.statement, children: `• ${f.name}` }, i))
      ] }, 'f'))
    }
  }
  return jsx('div', { className: 'flex h-full flex-col gap-3 overflow-y-auto p-3 text-(--ui-text-primary)', children: body })
}

// ---------- Learn page (sidebar) ----------
function LearnPage({ ctx }) {
  const data = usePoll(ctx, '/lessons', 5000)
  const graph = usePoll(ctx, '/graph', 15000)
  const [q, setQ] = useState('')
  const lessons = (data && data.lessons) || []
  const stats = data && data.stats
  const facts = ((graph && graph.propositions) || []).filter(p => !q.trim() ||
    (p.name + ' ' + p.statement).toLowerCase().includes(q.trim().toLowerCase()))
  const byId = new Map(((graph && graph.propositions) || []).map(p => [p.id, p.name]))
  const premisesOf = new Map()
  for (const c of (graph && graph.chains) || []) premisesOf.set(c.conclusion, [...(premisesOf.get(c.conclusion) || []), ...c.premises])
  const open = l => typeof sdk.host.openSession === 'function' ? sdk.host.openSession(l.session_id) : null
  const In = sdk.Input || 'input'
  return jsxs('div', { className: 'mx-auto flex h-full w-full max-w-3xl flex-col gap-6 overflow-y-auto p-6 text-(--ui-text-primary)', children: [
    jsxs('div', { className: 'flex flex-col gap-1', children: [
      jsx('h1', { className: 'text-xl font-semibold', children: 'Learn' }),
      jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children: stats
        ? `${stats.propositions} facts and ${stats.chains} reasoning links in your knowledge graph · ${stats.lessons} lessons`
        : 'Structured lessons: probe what you know, plan a path, learn it step by step.' })
    ] }),
    jsx(StartBox, {}),
    jsxs('section', { className: 'flex flex-col gap-2', children: [
      jsx(Label, { children: 'Lessons' }),
      lessons.length === 0 && jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children: 'No lessons yet.' }),
      ...lessons.map(l => jsxs('button', {
        type: 'button', onClick: () => open(l),
        className: 'flex flex-col gap-0.5 rounded-md border border-(--ui-stroke-secondary) px-3 py-2 text-left hover:border-(--ui-accent)',
        children: [
          jsx('div', { className: 'text-sm font-medium', children: l.goal }),
          jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: [
            PHASE_LABEL[l.phase] || l.phase,
            l.steps ? `${l.reached}/${l.steps} steps` : null,
            `${l.answered} answered`, `${l.facts} facts`,
            when(l.updated_at)
          ].filter(Boolean).join(' · ') })
        ]
      }, l.id))
    ] }),
    jsxs('section', { className: 'flex flex-col gap-2', children: [
      jsx(Label, { children: 'What you know' }),
      jsx(In, { value: q, onChange: e => setQ(e.target.value), placeholder: 'Search your knowledge graph', className: 'text-sm' }),
      ...facts.slice(0, 200).map(p => jsxs('div', { className: 'flex flex-col gap-0.5 border-b border-(--ui-stroke-secondary) py-2 text-sm', children: [
        jsx('div', { className: 'font-medium', children: p.name }),
        jsx('div', { className: 'text-(--ui-text-secondary) [&_p]:my-0', children: jsx(Md, { text: p.statement }) }),
        premisesOf.has(p.id) && jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children:
          'from: ' + [...new Set(premisesOf.get(p.id))].map(id => byId.get(id)).filter(Boolean).join(', ') })
      ] }, p.id))
    ] })
  ] })
}

export default {
  id: 'learnloop',
  name: 'learnloop',
  register(ctx) {
    // Tell the backend the Desktop half is live: learnloop only emits cards once it has (KI-7).
    ctx.rest('/hello', { method: 'POST' }).catch(() => {})
    if (typeof sdk.TRANSCRIPT_DIRECTIVE_AREA !== 'string') return
    ctx.registerMany([
      {
        id: 'lesson',
        area: 'panes',
        title: 'Lesson',
        // hideOnly: closing hides the pane instead of disabling learnloop (Desktop's own flag for standing chrome).
        data: { placement: 'right', width: '320px', hideOnly: true },
        render: () => jsx(LessonPane, { ctx })
      },
      ...(typeof sdk.ROUTES_AREA === 'string' ? [
        { id: 'learn-page', area: sdk.ROUTES_AREA, data: { path: '/learnloop' }, render: () => jsx(LearnPage, { ctx }) },
        { id: 'learn-nav', area: sdk.SIDEBAR_NAV_AREA, data: { path: '/learnloop', label: 'Learn', codicon: 'mortar-board' } }
      ] : [])
    ])
    ctx.register({
      id: 'question-card',
      area: sdk.TRANSCRIPT_DIRECTIVE_AREA,
      data: {
        name: 'learnloop-question',
        render: ({ attrs, sessionId }) => jsx(QuestionCard, { ctx, id: attrs && attrs.id, sessionId })
      }
    })
  }
}
