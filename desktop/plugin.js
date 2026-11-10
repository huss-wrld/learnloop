// learnloop Desktop half: the question card (::learnloop-question{id="q_…"}).
// Copyright (C) 2026 Hussein Al-Amodi. AGPL-3.0-only.
import * as sdk from '@hermes/plugin-sdk'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
const Md = ({ text }) => jsx('div', { className: 'learnloop-md', children: sdk.MessageTextContent
  ? jsx(sdk.MessageTextContent, { text, media: false }) : jsx('span', { children: text }) })
// Desktop compiles Tailwind from its own sources only, so a class it never uses does nothing in a plugin.
// The few styles learnloop needs beyond Desktop's own classes live here and in inline styles.
const STYLE = '.learnloop-md p{margin-top:0;margin-bottom:0}.learnloop-md p+p{margin-top:.5em}'
const Style = () => jsx('style', { children: STYLE })
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
      onClick ? 'hover:border-(--ui-stroke-primary)' : 'cursor-default'
    ),
    style: mark ? { borderColor: mark } : undefined,
    children: [
      jsx('span', {
        className: cn('mt-0.5 inline-flex size-5 shrink-0 items-center justify-center text-xs font-semibold',
          multi ? 'rounded-sm' : 'rounded-full', 'border border-(--ui-stroke-secondary)'),
        style: selected ? { background: 'var(--ui-accent)', color: 'var(--background, #fff)', borderColor: 'var(--ui-accent)' } : undefined,
        children: i >= 0 ? LETTERS[i] : '?'
      }),
      jsx('div', { className: 'min-w-0 flex-1', children: jsx(Md, { text }) })
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
        className: 'rounded-md px-3 py-2 text-sm text-(--ui-text-secondary)',
        style: { background: 'color-mix(in srgb, var(--ui-stroke-secondary) 30%, transparent)' },
        children: jsx(Md, { text: res.explanation })
      }),
      res && res.expected && jsxs('div', {
        className: 'flex flex-col gap-1 rounded-md px-3 py-2 text-sm',
        style: { background: 'color-mix(in srgb, var(--ui-stroke-secondary) 30%, transparent)' },
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
  // Answered in the dock: take its result the moment it's submitted (multiple choice is graded on submit).
  useEffect(() => {
    const f = () => { if (DOCK.q && DOCK.q.id === id && DOCK.q.submission) setQ(DOCK.q) }
    DOCK.listeners.add(f)
    return () => DOCK.listeners.delete(f)
  }, [id])
  // Poll while open: a free answer waits for the model's verdict; a dock answer may come from another surface.
  useEffect(() => {
    if (!q || q.status !== 'open') return undefined
    const t = setInterval(load, q.submission ? 4000 : 3000)
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
    children: [jsx(Style, {}, 'css'), ...(Array.isArray(children) ? children : [children])]
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
  const prompt = jsx('div', { className: 'text-sm', children: jsx(Md, { text: q.prompt }) })

  if (q.status === 'abandoned') {
    return shell([header, prompt, jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children: 'The lesson ended before this was answered.' })])
  }
  if (q.submission || q.status === 'answered') return shell([header, prompt, jsx(Result, { q })])
  if (HAS_DOCK && sdk.COMPOSER_AREAS.middleware) {
    // the open question is answered in the dock above the message box (LearnHarness's question dock)
    return shell([header, prompt, jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children:
      'Answer above the message box: pick an option there and write your thinking in the box.' })])
  }

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



// ---------- practice problem card (::learnloop-problem{id="x_…"}) ----------
// LearnHarness's practice: the learner works in a thinking box; hints come one rung at a time; the committed
// solution is revealed only at the conclusion; the next problem waits for an explicit "Next problem".
const PID = /^x_[0-9a-f]{12}$/
const HAS_DOCK = !!(sdk.COMPOSER_AREAS && sdk.COMPOSER_AREAS.top)
const OUTCOME = {
  solved: { label: 'Solved', tone: 'var(--ui-success, #2e7d32)' },
  solvedWithHints: { label: 'Solved with hints', tone: 'var(--ui-warning, #f9a825)' },
  movedOn: { label: 'Moved on', tone: 'var(--ui-text-tertiary)' },
  surrendered: { label: 'Gave up', tone: 'var(--ui-text-tertiary)' },
  dismissed: { label: 'Set aside', tone: 'var(--ui-text-tertiary)' }
}

function ProblemCard({ ctx, id, sessionId }) {
  const [p, setP] = useState(null)
  const [error, setError] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => {
    ctx.rest(`/problem/${id}`).then(setP, e => setError(String(e && e.message ? e.message : e)))
  }, [ctx, id])
  useEffect(load, [load])
  // Follow the conclusion and the pause: poll while this card can still change.
  const live = p && (p.status === 'open' || (p.latest && p.lesson_open))
  useEffect(() => {
    if (!live) return undefined
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [live, load])

  const post = async (path, body, after) => {
    setBusy(true)
    try {
      const r = await ctx.rest(`/problem/${id}${path}`, { method: 'POST', body })
      setP(r.problem)
      if (after) after()
      const sent = sdk.host.composer.submit(sessionId ?? null, r.line)
      if (!sent) sdk.host.notify({ kind: 'info', message: 'Saved. Open this chat and send any message to continue.' })
    } catch (e) {
      sdk.host.notify({ kind: 'warning', message: `learnloop: ${e && e.message ? e.message : e}` })
    } finally {
      setBusy(false)
    }
  }
  const next = () => {
    const sent = sdk.host.composer.submit(sessionId ?? null, 'Next problem')
    if (!sent) sdk.host.notify({ kind: 'info', message: 'Type "Next problem" in this chat to continue.' })
    setTimeout(load, 1500)
  }

  const shell = children => jsxs('div', {
    className: 'my-2 flex max-w-2xl flex-col gap-3 rounded-lg border border-(--ui-stroke-secondary) p-4 text-(--ui-text-primary)',
    'data-slot': 'learnloop-problem',
    children: [jsx(Style, {}, 'css'), ...(Array.isArray(children) ? children : [children])]
  })
  if (!PID.test(id || '') || error) {
    return shell(jsx('div', { className: 'text-sm text-(--ui-text-tertiary)',
      children: "This problem wasn't created properly, so it can't be worked here. Ask for it again in the chat." }))
  }
  if (!p) return shell(jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children: 'Loading problem…' }))

  const Btn = sdk.Button || 'button'
  const parts = [
    jsx(Label, { children: 'Problem' }, 'h'),
    jsx('div', { className: 'text-sm', children: jsx(Md, { text: p.statement }) }, 's')
  ]
  if (p.trace.length) {
    parts.push(jsxs('div', { className: 'flex flex-col gap-1 border-l-2 border-(--ui-stroke-secondary) pl-3 text-xs text-(--ui-text-secondary)', children: [
      jsx(Label, { children: 'Your work so far' }),
      ...p.trace.map((t, i) => jsx('div', { children: t.hint ? (t.text ? `Asked for a hint: ${t.text}` : 'Asked for a hint') : t.text }, i))
    ] }, 'tr'))
  }
  if (p.status === 'abandoned') {
    parts.push(jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children: 'The session ended before this problem was concluded.' }, 'ab'))
  } else if (p.status === 'open' && HAS_DOCK) {
    // LearnHarness's practice dock: the open problem's working surface is the composer (docked above it)
    parts.push(jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children:
      'Work on it in the message box below: send your thinking as you go. Hint and Set aside sit above the box.' }, 'dock'))
  } else if (p.status === 'open') {
    parts.push(jsx(Field, { label: 'Your thinking', value: text, onChange: setText, rows: 4,
      placeholder: 'Work it through: what do you notice, what applies, where you are stuck. Say when you have an answer.' }, 'f'))
    parts.push(jsxs('div', { className: 'flex flex-wrap items-center gap-2', children: [
      jsx(Btn, { type: 'button', disabled: busy || !text.trim(), onClick: () => post('/thinking', { text, hint: false }, () => setText('')), children: 'Send' }),
      jsx(Btn, { type: 'button', variant: 'outline', disabled: busy, onClick: () => post('/thinking', { text, hint: true }, () => setText('')), children: 'Hint' }),
      jsx('button', { type: 'button', disabled: busy, onClick: () => post('/dismiss', {}),
        className: 'ml-auto text-xs text-(--ui-text-tertiary) hover:text-(--ui-text-primary)', children: 'Set aside' })
    ] }, 'b'))
  } else if (p.result) {
    const o = OUTCOME[p.result.outcome] || { label: p.result.outcome, tone: 'var(--ui-text-tertiary)' }
    parts.push(jsxs('div', { className: 'flex flex-col gap-1', children: [
      jsx('div', { className: 'text-sm font-semibold', style: { color: o.tone }, children: o.label }),
      p.result.verdict && p.result.outcome !== 'dismissed' && jsx('div', { className: 'text-sm', children: jsx(Md, { text: p.result.verdict }) })
    ] }, 'v'))
    parts.push(jsxs('div', { className: 'flex flex-col gap-1 rounded-md px-3 py-2 text-sm',
      style: { background: 'color-mix(in srgb, var(--ui-stroke-secondary) 30%, transparent)' }, children: [
        jsx(Label, { children: 'Solution' }), jsx(Md, { text: p.result.model_solution })
      ] }, 'sol'))
    if (p.latest && p.lesson_open && p.paused) {
      parts.push(jsxs('div', { className: 'flex items-center gap-3', children: [
        jsx(Btn, { type: 'button', onClick: next, children: 'Next problem' }),
        jsx('span', { className: 'text-xs text-(--ui-text-tertiary)', children: 'Or ask anything about this one first.' })
      ] }, 'n'))
    }
  }
  return shell(parts)
}

// ---------- shared ----------
const PHASES = ['probe', 'plan', 'teach', 'done']
const PHASE_LABEL = { probe: 'Probe', plan: 'Plan', teach: 'Teach', practice: 'Practice', done: 'Done' }
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

function startIn(skill, topic) {
  const t = topic.trim()
  if (!t) return
  // A session belongs to its own chat: open a fresh one, then send the start command into it.
  if (typeof sdk.host.newChat === 'function') sdk.host.newChat()
  setTimeout(() => {
    const sent = sdk.host.composer.submit(null, `/learnloop:${skill} ${t}`)
    if (!sent) sdk.host.notify({ kind: 'warning', message: `Type /learnloop:${skill} ${t} in a chat to start.` })
  }, 400)
}
const startLesson = topic => startIn('study', topic)
const startPractice = topic => startIn('practice', topic)

function StartBox({ compact }) {
  const [topic, setTopic] = useState('')
  const Btn = sdk.Button || 'button'
  const In = sdk.Input || 'input'
  return jsxs('form', {
    className: cn('flex gap-2', compact ? 'flex-col' : 'items-center'),
    onSubmit: e => { e.preventDefault(); startLesson(topic); setTopic('') },
    children: [
      jsx(In, { value: topic, onChange: e => setTopic(e.target.value), placeholder: 'A topic to learn or practise',
        className: 'min-w-0 flex-1 text-sm' }),
      jsxs('div', { className: 'flex gap-2', children: [
        jsx(Btn, { type: 'submit', disabled: !topic.trim(), children: 'Start a lesson' }),
        jsx(Btn, { type: 'button', variant: 'outline', disabled: !topic.trim(),
          onClick: () => { startPractice(topic); setTopic('') }, children: 'Practise' })
      ] })
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


// Solid: the composer fades and shows the transcript through when scrolled up (10 Nov screenshot).
const DOCK_BG = { background: 'var(--ui-bg-elevated, var(--ui-bg-card, var(--background)))', borderRadius: 8 }

// ---------- practice dock (above the composer) ----------
// LearnHarness's practice dock: while a problem is open, the problem sits on the composer and the learner's
// messages are his thinking. Hermes lets plugins add a strip above the input (COMPOSER_AREAS.top), not replace it.
function PracticeDock({ ctx, sid, pr }) {
  const [open, setOpen] = useState(true)
  const [busy, setBusy] = useState(false)
  if (!pr || (!pr.open_problem && !pr.paused)) return null
  const Btn = sdk.Button || 'button'
  const say = line => {
    const sent = sdk.host.composer.submit(sid ?? null, line)
    if (!sent) sdk.host.notify({ kind: 'info', message: `Send "${line}" in this chat to continue.` })
  }
  const post = async (path, body) => {
    setBusy(true)
    try {
      const r = await ctx.rest(`/problem/${pr.open_problem.id}${path}`, { method: 'POST', body })
      say(r.line)
    } catch (e) {
      sdk.host.notify({ kind: 'warning', message: `learnloop: ${e && e.message ? e.message : e}` })
    } finally {
      setBusy(false)
    }
  }
  const small = 'text-xs text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
  if (!pr.open_problem) {
    return jsxs('div', { className: 'flex items-center gap-3 px-3 py-2 text-xs', style: DOCK_BG, children: [
      jsx(Btn, { type: 'button', onClick: () => say('Next problem'), children: 'Next problem' }),
      jsx('span', { className: 'text-(--ui-text-tertiary)', children: 'Or ask anything about the last one.' })
    ] })
  }
  return jsxs('div', { className: 'flex flex-col gap-1.5 px-3 py-2', style: DOCK_BG, children: [
    jsx(Style, {}, 'css'),
    jsxs('div', { className: 'flex items-center gap-3', children: [
      jsx('button', { type: 'button', onClick: () => setOpen(!open), className: 'flex items-center gap-1',
        children: jsx(Label, { children: open ? 'Problem ▾' : 'Problem ▸' }) }),
      jsx('span', { className: 'text-xs text-(--ui-text-tertiary)', children: 'Your messages are your thinking.' }),
      jsx('button', { type: 'button', disabled: busy, onClick: () => post('/thinking', { text: '', hint: true }),
        className: cn(small, 'ml-auto'), children: 'Hint' }),
      jsx('button', { type: 'button', disabled: busy, onClick: () => post('/dismiss', {}), className: small, children: 'Set aside' })
    ] }),
    open && jsx('div', { className: 'overflow-y-auto text-sm', style: { maxHeight: '30vh' },
      children: jsx(Md, { text: pr.open_problem.statement }) })
  ] })
}


// ---------- question dock (LearnHarness's question dock, above the composer) ----------
// The open question sits on the composer; the message box IS "Your thinking": Enter submits the answer.
// Hermes lets plugins add a strip above the input and rewrite a draft on send (COMPOSER_AREAS.middleware),
// not replace the input, so the dock holds the choices and confidence and the middleware turns the typed text
// into the answer. The middleware isn't told which chat it's in: it acts for the focused chat's open question.
const DOCK = { sid: null, q: null, choices: [], idk: false, confidence: '50', listeners: new Set() }
const dockSet = patch => { Object.assign(DOCK, patch); DOCK.listeners.forEach(f => f()) }
function useDock() {
  const [, bump] = useState(0)
  useEffect(() => { const f = () => bump(n => n + 1); DOCK.listeners.add(f); return () => DOCK.listeners.delete(f) }, [])
  return DOCK
}
// Where the plan map shows: off by default (pane only); on adds LearnHarness's placement, beside the open question.
const UI_KEY = 'learnloop.ui.v1'
const UI = { prefs: (() => { try { return JSON.parse(localStorage.getItem(UI_KEY) || '{}') } catch { return {} } })(), listeners: new Set() }
const uiGet = (k, dflt) => (k in UI.prefs ? UI.prefs[k] : dflt)
const uiSet = patch => {
  UI.prefs = { ...UI.prefs, ...patch }
  try { localStorage.setItem(UI_KEY, JSON.stringify(UI.prefs)) } catch { /* storage blocked */ }
  UI.listeners.forEach(f => f())
}
function useUi() {
  const [, bump] = useState(0)
  useEffect(() => { const f = () => bump(n => n + 1); UI.listeners.add(f); return () => UI.listeners.delete(f) }, [])
  return uiGet
}
const mapInDock = () => uiGet('mapInDock', false)

const dockArmed = () => !!(DOCK.q && DOCK.q.status === 'open' && !DOCK.q.submission)

function makeAnswerMiddleware(ctx) {
  return {
    handler: async draft => {
      if (!dockArmed()) return draft
      const typed = (draft && draft.text) || ''
      if (typed.trim().startsWith('/')) return draft  // slash commands (e.g. /learnloop stop) pass through
      const q = DOCK.q
      if (q.kind === 'mc' && !DOCK.idk && DOCK.choices.length === 0) {
        sdk.host.notify({ kind: 'info', message: "Pick an option (or I don't know) above the message box first." })
        return null
      }
      if (q.kind !== 'mc' && !DOCK.idk && !typed.trim()) {
        sdk.host.notify({ kind: 'info', message: 'Write your answer in the message box.' })
        return null
      }
      const thinking = typed === DOCK_EMPTY ? '' : typed
      const body = { dont_know: DOCK.idk, confidence: DOCK.idk ? null : Number(DOCK.confidence), thinking: '' }
      if (!DOCK.idk) Object.assign(body, q.kind === 'mc' ? { choices: DOCK.choices, thinking } : { text: thinking })
      else body.thinking = thinking
      try {
        const r = await ctx.rest(`/question/${q.id}/submit`, { method: 'POST', body })
        dockSet({ q: r.question, choices: [], idk: false })
        return { ...draft, text: r.line }
      } catch (e) {
        sdk.host.notify({ kind: 'warning', message: `learnloop: ${e && e.message ? e.message : e}` })
        return null
      }
    }
  }
}
const DOCK_EMPTY = '(no thinking written)'

function QuestionDock({ ctx, sid, qid, plan, goal }) {
  const d = useDock()
  useUi()
  const [mapOpen, setMapOpen] = useState(false)
  useEffect(() => {
    let live = true
    ctx.rest(`/question/${qid}`).then(q => {
      if (!live) return
      if (!DOCK.q || DOCK.q.id !== q.id) dockSet({ sid, q, choices: [], idk: false, confidence: '50' })
      else dockSet({ sid, q })
    }, () => {})
    return () => { live = false }
  }, [ctx, sid, qid])
  useEffect(() => () => { if (DOCK.q && DOCK.q.id === qid && !DOCK.q.submission) dockSet({ q: null }) }, [qid])
  const q = d.q && d.q.id === qid ? d.q : null
  if (q && q.submission) return jsx(DockResult, { q })
  if (!q || !dockArmed()) return null
  const toggle = i => dockSet({ idk: false, choices: q.multi ? (d.choices.includes(i) ? d.choices.filter(c => c !== i) : [...d.choices, i]) : [i] })
  const kind = q.qtype === 'predict' ? 'Prediction' : q.qtype === 'check' ? 'Check' : 'Question'
  const Btn = sdk.Button || 'button'
  const submit = async () => {
    const text = (await sdk.host.composer.getDraft(sid ?? null)) || ''
    const sent = sdk.host.composer.submit(sid ?? null, text.trim() ? text : DOCK_EMPTY)
    if (sent && text.trim()) sdk.host.composer.setDraft(sid ?? null, '')
  }
  const side = plan && mapInDock()
  const main = jsxs('div', { className: 'flex min-w-0 flex-1 flex-col gap-2', style: { display: 'flex', flexDirection: 'column', flex: '1 1 0', minWidth: 0 }, children: [
      jsx(Label, { children: kind }),
      jsx('div', { className: 'text-sm font-medium', children: jsx(Md, { text: q.prompt }) }),
      q.kind === 'mc' && jsxs('div', { className: 'flex flex-col gap-1.5', children: [
        q.multi && jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: 'More than one is right: select all that apply.' }),
        ...q.options.map((o, i) => jsx(Option, { i, text: o, multi: q.multi, selected: !d.idk && d.choices.includes(i), onClick: () => toggle(i) }, i)),
        jsx(Option, { i: -1, text: "I don't know", selected: d.idk, onClick: () => dockSet({ idk: !d.idk, choices: [] }) }, 'idk')
      ] }),
      q.kind !== 'mc' && jsxs('div', { className: 'flex items-center gap-3 text-xs text-(--ui-text-tertiary)', children: [
        jsx('span', { children: 'Write your answer in the message box below.' }),
        jsx('button', { type: 'button', onClick: () => dockSet({ idk: !d.idk }),
          className: cn('ml-auto hover:text-(--ui-text-primary)', d.idk && 'font-semibold text-(--ui-text-primary)'), children: "I don't know" })
      ] }),
      !d.idk && jsxs('div', { className: 'flex items-center gap-3', children: [
        jsx(Label, { children: 'Confidence' }),
        jsx('div', { className: 'min-w-0 flex-1', children: sdk.SegmentedControl
          ? jsx(sdk.SegmentedControl, { value: d.confidence, onChange: v => dockSet({ confidence: v }), sizing: 'equal',
            options: STOPS.map(s => ({ id: s, label: `${s}%` })) })
          : jsx('div', { className: 'flex gap-1', children: STOPS.map(s => jsx('button', { type: 'button', onClick: () => dockSet({ confidence: s }), children: `${s}%` }, s)) }) })
      ] }),
      jsxs('div', { className: 'flex items-center gap-2', children: [
        jsx('span', { className: 'text-xs text-(--ui-text-tertiary)', children:
          q.kind === 'mc' ? 'Your thinking goes in the message box below · Enter submits' : 'Enter submits' }),
        jsx(Btn, { type: 'button', className: 'ml-auto', onClick: submit, children: 'Submit answer' })
      ] })
    ] })
  // LearnHarness's plan marginalia: the map beside the open question, live, without a frame of its own
  return jsxs('div', { className: 'flex gap-3 overflow-y-auto px-3 pt-3 pb-1',
    style: { display: 'flex', alignItems: 'flex-start', gap: 12, maxHeight: '45vh', background: 'var(--ui-bg-elevated, var(--ui-bg-card, var(--background)))' }, children: [
      jsx(Style, {}, 'css'),
      main,
      side && jsx('div', { className: 'flex shrink-0 flex-col', style: { display: 'flex', flexDirection: 'column', flexShrink: 0, width: 'clamp(140px, 24%, 240px)' }, children: [
        jsx(PlanMap, { plan, thumb: true, bare: true, onOpen: () => setMapOpen(true) }, 'm'),
        jsx(PlanDialog, { plan, goal, open: mapOpen, onClose: () => setMapOpen(false) }, 'd')] })
    ] })
}

// The verdict, right at the input, until the next question arrives (the chat's card keeps the full record).
function DockResult({ q }) {
  const r = q.result
  const v = r ? (VERDICT[r.verdict] || VERDICT.wrong) : null
  const right = r && r.correct ? r.correct.map(i => `${LETTERS[i]}) ${q.options[i]}`).join(', ') : ''
  return jsxs('div', { className: 'flex flex-col gap-1 px-3 py-2 text-sm', style: DOCK_BG, children: [
    jsx(Style, {}, 'css'),
    v ? jsxs('div', { className: 'flex items-baseline gap-2', children: [
      jsx('span', { className: 'font-semibold', style: { color: v.tone }, children: v.label }),
      r.verdict !== 'correct' && right && jsx('span', { className: 'min-w-0 text-(--ui-text-secondary)', children: jsx(Md, { text: 'Correct: ' + right }) })
    ] }) : jsx('div', { className: 'text-(--ui-text-tertiary)', children: 'Answer sent: waiting for the verdict.' })
  ] })
}

function LearnDock({ ctx }) {
  useDock()
  const sid = sdk.useValue && sdk.host.state ? sdk.useValue(sdk.host.state.focusedStoredSessionId) : null
  const data = usePoll(ctx, sid ? `/lesson?session=${encodeURIComponent(sid)}` : null, 2500)
  const les = data && data.lesson
  // keep the last answer's verdict on show after grading, until the next question or another chat
  useEffect(() => { if (DOCK.q && DOCK.sid !== sid) dockSet({ q: null }) }, [sid])
  if (!les) return null
  if (les.phase === 'practice') return jsx(PracticeDock, { ctx, sid, pr: les.practice })
  if (les.open_question) return jsx(QuestionDock, { ctx, sid, qid: les.open_question.id, plan: les.plan, goal: les.goal }, les.open_question.id)
  if (DOCK.q && DOCK.q.submission && DOCK.sid === sid) return jsx(DockResult, { q: DOCK.q })
  return null
}


// ---------- plan map (our own drawing: progress first, readable at any size) ----------
// Mermaid scales the whole plan into the space it gets, so a narrow pane turns it to slivers. This lays the plan
// out top to bottom (rows = how many steps lead to it), draws a label-free thumbnail for the pane, and a
// readable full map in a dialog over the chat (or inline on the Learn page).
function layoutPlan(nodes, edges) {
  const ids = nodes.map(n => n.id), known = new Set(ids)
  const E = (edges || []).filter(([a, b]) => known.has(a) && known.has(b) && a !== b)
  const parents = new Map(ids.map(i => [i, []])), kids = new Map(ids.map(i => [i, []]))
  for (const [a, b] of E) { parents.get(b).push(a); kids.get(a).push(b) }
  const depth = new Map(ids.map(i => [i, 0]))
  for (let pass = 0; pass < ids.length; pass++) {           // longest path from a root; bounded, so a cycle can't hang
    let moved = false
    for (const [a, b] of E) if (depth.get(b) < depth.get(a) + 1) { depth.set(b, depth.get(a) + 1); moved = true }
    if (!moved) break
  }
  const rows = []
  ids.forEach(i => { const d = depth.get(i); (rows[d] = rows[d] || []).push(i) })
  const pos = new Map()
  const place = () => rows.forEach(r => r && r.forEach((id, k) => pos.set(id, k - (r.length - 1) / 2)))
  place()
  const bary = (id, nb) => { const ps = nb.get(id).filter(p => pos.has(p)); return ps.length ? ps.reduce((s, p) => s + pos.get(p), 0) / ps.length : pos.get(id) }
  for (let sweep = 0; sweep < 4; sweep++) {
    const nb = sweep % 2 ? kids : parents
    rows.forEach(r => r && r.sort((a, b) => bary(a, nb) - bary(b, nb)))
    place()
  }
  return { rows: rows.filter(Boolean), pos, depth, edges: E, parents }
}

const PLAN_TONE = {
  done: { fill: 'color-mix(in srgb, var(--ui-success, #2e7d32) 22%, transparent)', stroke: 'var(--ui-success, #2e7d32)' },
  current: { fill: 'color-mix(in srgb, var(--ui-warning, #f9a825) 30%, transparent)', stroke: 'var(--ui-warning, #f9a825)' },
  next: { fill: 'transparent', stroke: 'var(--ui-accent, #6b8afd)' },
  todo: { fill: 'transparent', stroke: 'var(--ui-stroke-secondary, #555)' }
}

function wrapTitle(t, width) {
  const words = String(t).split(/\s+/), lines = []
  let cur = ''
  for (const w of words) {
    if (cur && (cur + ' ' + w).length > width) { lines.push(cur); cur = w } else cur = cur ? cur + ' ' + w : w
  }
  if (cur) lines.push(cur)
  return lines.slice(0, 3).map((l, i, a) => i === 2 && lines.length > 3 ? l + '…' : l)
}

// The links are the agent's own `a --> b` lines; read them from the plan text when the backend doesn't send them
// (an older plugin host still running after an update).
function planEdges(plan) {
  if (plan.edges && plan.edges.length) return plan.edges
  const out = []
  for (const line of String(plan.mermaid || '').split('\n')) {
    const m = line.match(/^\s*([a-z0-9_-]+)\s*(?:\[[^\]]*\])?\s*-->\s*([a-z0-9_-]+)/)
    if (m) out.push([m[1], m[2]])
  }
  return out
}

function PlanMap({ plan, thumb = false, bare = false, onOpen }) {
  const L = useMemo(() => layoutPlan(plan.nodes, planEdges(plan)), [plan])
  const state = new Map(plan.nodes.map(n => [n.id, n.state]))
  const title = new Map(plan.nodes.map(n => [n.id, n.title]))
  // "next": steps still to do whose prerequisites are all reached: where the lesson can go from here
  const reached = id => state.get(id) === 'done' || state.get(id) === 'current'
  const tone = id => state.get(id) !== 'todo' ? state.get(id)
    : (L.parents.get(id).length ? L.parents.get(id).every(reached) : plan.nodes.some(n => n.state !== 'todo')) && plan.nodes.some(n => n.state !== 'todo') ? 'next' : 'todo'
  const W = thumb ? 26 : 176, GX = thumb ? 8 : 22, GY = thumb ? 10 : 34, LINE = 15
  const lines = new Map(plan.nodes.map(n => [n.id, thumb ? [] : wrapTitle(n.title, 25)]))
  const H = id => thumb ? 9 : lines.get(id).length * LINE + 14
  const rowH = L.rows.map(r => Math.max(...r.map(H)))
  const rowY = []; rowH.reduce((y, h, i) => { rowY[i] = y; return y + h + GY }, 0)
  const span = Math.max(...L.rows.map(r => r.length))
  const width = span * W + (span - 1) * GX, height = rowY[rowY.length - 1] + rowH[rowH.length - 1]
  const at = id => { const d = L.depth.get(id), k = L.rows.findIndex(r => r.includes(id))
    return { x: width / 2 + L.pos.get(id) * (W + GX) - W / 2, y: rowY[k] + (rowH[k] - H(id)) / 2, h: H(id), d } }
  const P = new Map(plan.nodes.map(n => [n.id, at(n.id)]))
  const pad = thumb ? 2 : 6
  const svg = jsxs('svg', {
    viewBox: `${-pad} ${-pad} ${width + 2 * pad} ${height + 2 * pad}`,
    width: thumb ? '100%' : width + 2 * pad, height: thumb ? '100%' : height + 2 * pad,
    preserveAspectRatio: 'xMidYMid meet', role: 'img', 'aria-label': 'Lesson map', style: { display: 'block' },
    children: [
      ...L.edges.map(([a, b]) => { const p = P.get(a), q = P.get(b)
        const x1 = p.x + W / 2, y1 = p.y + p.h, x2 = q.x + W / 2, y2 = q.y, my = (y1 + y2) / 2
        const lit = reached(a) && reached(b)
        return jsx('path', { d: `M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`, fill: 'none',
          style: { stroke: lit ? PLAN_TONE.done.stroke : 'var(--ui-stroke-secondary, #555)', strokeOpacity: lit ? 0.8 : 0.6, strokeWidth: thumb ? 1 : 1.25 } }, a + '>' + b) }),
      ...plan.nodes.map(n => { const p = P.get(n.id), t = PLAN_TONE[tone(n.id)]
        return jsxs('g', { children: [
          jsx('title', { children: title.get(n.id) }),
          jsx('rect', { x: p.x, y: p.y, width: W, height: p.h, rx: thumb ? 2 : 7,
            style: { fill: t.fill, stroke: t.stroke, strokeWidth: n.state === 'current' ? (thumb ? 1.5 : 2.5) : 1,
              strokeDasharray: tone(n.id) === 'next' && !thumb ? '4 3' : undefined } }),
          ...lines.get(n.id).map((l, i) => jsx('text', { x: p.x + W / 2, y: p.y + 7 + LINE * (i + 0.75), textAnchor: 'middle',
            style: { fill: n.state === 'todo' ? 'var(--ui-text-secondary)' : 'var(--ui-text-primary)', fontSize: 12,
              fontWeight: n.state === 'current' ? 600 : 400 }, children: l }, i))
        ] }, n.id) })
    ]
  })
  if (!thumb) return svg
  if (bare) {
    return jsxs('button', { type: 'button', onClick: onOpen, title: 'Open the lesson map',
      className: 'flex h-full flex-col gap-1 text-left opacity-80 hover:opacity-100', children: [
        jsx('div', { style: { height: Math.min(220, Math.max(90, L.rows.length * 20)), width: '100%' }, children: svg }),
        jsx('span', { className: 'text-xs text-(--ui-text-tertiary)', children: 'Open map' })] })
  }
  return jsxs('button', { type: 'button', onClick: onOpen, title: 'Open the lesson map',
    className: 'flex flex-col gap-1 rounded-md border border-(--ui-stroke-secondary) px-2 py-1.5 text-left hover:border-(--ui-stroke-primary)',
    children: [jsx('div', { style: { height: Math.min(120, Math.max(48, L.rows.length * 13)), width: '100%' }, children: svg }),
      jsx('span', { className: 'text-xs text-(--ui-text-tertiary)', children: 'Open map' })] })
}

function PlanLegend({ plan }) {
  const done = plan.nodes.filter(n => n.state === 'done').length
  const item = (k, label) => jsxs('span', { className: 'flex items-center gap-1', children: [
    jsx('span', { style: { display: 'inline-block', width: 10, height: 10, borderRadius: 3, background: PLAN_TONE[k].fill,
      border: `1.5px ${k === 'next' ? 'dashed' : 'solid'} ${PLAN_TONE[k].stroke}` } }), label] }, k)
  return jsxs('div', { className: 'flex items-center gap-3 text-xs text-(--ui-text-tertiary)', children: [
    item('done', 'Done'), item('current', 'Now'), item('next', 'Up next'), item('todo', 'Later'),
    jsx('span', { className: 'ml-auto', children: `${done} of ${plan.nodes.length} steps done` })] })
}

// The full map over the chat: the session stays where it is, Esc or a click outside closes it.
function PlanDialog({ plan, goal, open, onClose }) {
  useEffect(() => {
    if (!open || sdk.Dialog) return undefined
    const k = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [open, onClose])
  if (!open || !plan) return null
  const body = jsxs('div', { className: 'flex flex-col gap-3', style: { minWidth: 360 }, children: [
    jsx(PlanLegend, { plan }),
    jsx('div', { style: { maxHeight: '72vh', maxWidth: '86vw', overflow: 'auto' }, children: jsx(PlanMap, { plan }) })] })
  if (sdk.Dialog && sdk.DialogContent) {
    const Title = sdk.DialogTitle || 'div', Header = sdk.DialogHeader || 'div'
    return jsx(sdk.Dialog, { open: true, onOpenChange: v => { if (!v) onClose() }, children: jsxs(sdk.DialogContent, { fitContent: true, children: [
      jsx(Header, { children: jsx(Title, { children: goal ? `Lesson map · ${goal.length > 70 ? goal.slice(0, 70) + '…' : goal}` : 'Lesson map' }) }), body] }) })
  }
  return jsx('div', { onClick: onClose, style: { position: 'fixed', inset: 0, zIndex: 60, display: 'flex', alignItems: 'center',
    justifyContent: 'center', background: 'rgba(0,0,0,0.45)' }, children: jsxs('div', { onClick: e => e.stopPropagation(),
    style: { background: 'var(--ui-bg-elevated, var(--background))', border: '1px solid var(--ui-stroke-secondary)', borderRadius: 12, padding: 16 },
    children: [jsx('div', { className: 'text-sm font-semibold', style: { marginBottom: 8 }, children: 'Lesson map' }), body] }) })
}

// ---------- lesson pane (right of the chat) ----------
function LessonPane({ ctx }) {
  const [allSteps, setAllSteps] = useState(false)
  const [allFacts, setAllFacts] = useState(false)
  const [mapOpen, setMapOpen] = useState(false)
  useUi()
  const sid = sdk.useValue && sdk.host.state ? sdk.useValue(sdk.host.state.focusedStoredSessionId) : null
  const data = usePoll(ctx, sid ? `/lesson?session=${encodeURIComponent(sid)}` : null, 3000)
  const les = data && data.lesson
  const body = []
  if (!les) {
    body.push(jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children:
      'No lesson in this chat. Start one here, or type /learnloop:study <topic> in a chat.' }, 'e'))
    body.push(jsx(StartBox, { compact: true }, 's'))
  } else {
    body.push(jsx('div', { className: 'line-clamp-2 text-sm font-semibold leading-snug', title: les.goal, children: les.goal }, 'g'))
    if (les.practice) {
      const pr = les.practice
      const solved = pr.problems.filter(p => p.outcome === 'solved' || p.outcome === 'solvedWithHints').length
      body.push(jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children:
        `Practice · ${pr.problems.length} problems · ${solved} solved` + (les.phase === 'done' ? ' · ended' : pr.paused ? ' · paused' : '') }, 'ps'))
      if (pr.problems.length) {
        body.push(jsx('ol', { className: 'flex flex-col gap-1.5 text-sm', children: pr.problems.map((p, i) => jsxs('li', {
          className: 'flex flex-col gap-0.5', children: [
            jsx('div', { className: 'flex items-center gap-2 text-xs', children: [
              jsx('span', { className: 'font-medium', children: `${i + 1}.` }, 'n'),
              jsx('span', { style: { color: (OUTCOME[p.outcome] || {}).tone }, children: p.label }, 'l'),
              p.retest && jsx('span', { className: 'text-(--ui-text-tertiary)', children: '· retest' }, 'r')
            ] }),
            jsx('div', { className: 'line-clamp-3 text-xs text-(--ui-text-secondary)', children: jsx(Md, { text: p.statement }) })
          ] }, p.id)) }, 'pl'))
      }
      if (pr.material.length) {
        body.push(jsxs('div', { className: 'flex flex-col gap-1', children: [
          jsx(Label, { children: 'Practising' }),
          ...pr.material.map((m, i) => jsx('div', { className: 'text-xs', children: `• ${m}` }, i))
        ] }, 'm'))
      }
      return jsx('div', { className: 'flex h-full flex-col gap-3 overflow-y-auto p-3 text-(--ui-text-primary)', children: [jsx(Style, {}, 'css'), ...body] })
    }
    body.push(jsx(PhaseSteps, { phase: les.phase }, 'p'))
    const plan = les.plan
    const small = 'text-xs text-(--ui-text-tertiary) hover:text-(--ui-text-primary) self-start'
    if (plan) {
      const nodes = plan.nodes
      const idx = nodes.findIndex(n => n.state === 'current')
      const done = nodes.filter(n => n.state === 'done').length
      const current = idx >= 0 ? nodes[idx] : null
      const upcoming = nodes.filter((n, i) => n.state === 'todo' && i > idx).slice(0, 2)
      body.push(jsxs('div', { className: 'flex flex-col gap-1.5', children: [
        jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children:
          `Step ${Math.min(nodes.length, done + 1)} of ${nodes.length} · ${les.correct}/${les.answered} correct` }),
        jsx('div', { style: { height: 3, borderRadius: 2, background: 'color-mix(in srgb, var(--ui-stroke-secondary) 60%, transparent)' }, children:
          jsx('div', { style: { height: 3, borderRadius: 2, width: `${Math.round(100 * done / Math.max(1, nodes.length))}%`, background: 'var(--ui-accent)' } }) })
      ] }, 'st'))
      body.push(jsx(PlanMap, { plan, thumb: true, onOpen: () => setMapOpen(true) }, 'map'))
      if (HAS_DOCK) {
        body.push(jsxs('label', { className: 'flex items-center gap-2 text-xs text-(--ui-text-tertiary)', children: [
          jsx('input', { type: 'checkbox', checked: mapInDock(), onChange: e => uiSet({ mapInDock: e.target.checked }),
            style: { accentColor: 'var(--ui-accent)' } }),
          'Also show the map beside questions'] }, 'mapdock'))
      }
      body.push(jsx(PlanDialog, { plan, goal: les.goal, open: mapOpen, onClose: () => setMapOpen(false) }, 'mapd'))
      if (current) {
        body.push(jsxs('div', { className: 'flex flex-col gap-0.5', children: [
          jsx(Label, { children: 'Now' }), jsx('div', { className: 'text-sm font-medium leading-snug', children: current.title })] }, 'now'))
      }
      if (upcoming.length) {
        body.push(jsxs('div', { className: 'flex flex-col gap-0.5', children: [
          jsx(Label, { children: 'Next' }),
          ...upcoming.map(n => jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: n.title }, n.id))] }, 'next'))
      }
      body.push(jsx('button', { type: 'button', onClick: () => setAllSteps(!allSteps), className: small,
        children: allSteps ? 'Hide steps' : `All steps (${nodes.length})` }, 'all'))
      if (allSteps) {
        body.push(jsx('ol', { className: 'flex flex-col gap-0.5 text-xs', children: nodes.map(n => jsxs('li', {
          className: cn('flex gap-2', n.state === 'current' ? 'font-semibold' : n.state === 'todo' ? 'text-(--ui-text-tertiary)' : 'text-(--ui-text-secondary)'),
          children: [jsx('span', { className: 'w-3 shrink-0', style: n.state === 'done' ? { color: VERDICT.correct.tone } : undefined,
            children: STATE_MARK[n.state] }), n.title]
        }, n.id)) }, 'n'))
      }
    } else {
      body.push(jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: les.phase === 'probe'
        ? `Measuring what you already know · ${les.answered} answered. The plan appears once the probe has found where your understanding ends.`
        : `${les.answered} answered (${les.correct} correct)` }, 'pp'))
    }
    // the dock above the message box already shows the open question; only show it here without one
    if (les.open_question && !(HAS_DOCK && sdk.COMPOSER_AREAS.middleware)) {
      body.push(jsxs('div', { className: 'rounded-md border border-(--ui-stroke-secondary) px-2 py-1.5 text-xs', children: [
        jsx(Label, { children: 'Open question' }), jsx('div', { className: 'line-clamp-3', children: jsx(Md, { text: les.open_question.prompt }) })
      ] }, 'q'))
    }
    if (les.facts.length) {
      const shown = allFacts ? les.facts : les.facts.slice(0, 3)
      body.push(jsxs('div', { className: 'flex flex-col gap-0.5', children: [
        jsx(Label, { children: `Learned (${les.facts.length}${les.facts.length >= 12 ? '+' : ''})` }),
        ...shown.map((f, i) => jsx('div', { className: 'text-xs text-(--ui-text-secondary)', title: f.statement, children: f.name }, i)),
        les.facts.length > 3 && jsx('button', { type: 'button', onClick: () => setAllFacts(!allFacts), className: small,
          children: allFacts ? 'Show less' : `+${les.facts.length - 3} more` })
      ] }, 'f'))
    }
  }
  return jsx('div', { className: 'flex h-full flex-col gap-3 overflow-y-auto p-3 text-(--ui-text-primary)', children: [jsx(Style, {}, 'css'), ...body] })
}


// ---------- knowledge graph view ----------
// After LearnHarness's graph (components/graph-canvas.ts, AGPL-3.0): force layout with a depth pull
// (premises left of what they support: the Desktop page is wide), facts grouped into soft regions by the lesson or chat that taught them,
// zoom-gated labels, hover highlight, click for details. Re-implemented on one plain canvas: the catalog
// allows the SDK and React only, so no d3.
const HUES = [212, 152, 32, 282, 352, 92, 192, 252, 12, 322, 62, 122]

function hashStr(s) {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) }
  return h >>> 0
}

// Deterministic layered layout: same graph, same picture. Columns are depth (longest premise path), so every
// arrow runs left to right; within a column facts are ordered by lesson band, then by barycenter sweeps
// (fewer crossings), then relaxed toward their neighbours with a fixed minimum gap. Exported for tests.
export function layoutGraph(props, chains, opts = {}) {
  const n = props.length
  const idx = new Map(props.map((p, i) => [p.id, i]))
  const edges = []
  const seen = new Set()
  for (const c of chains) {
    const t = idx.get(c.conclusion)
    if (t === undefined) continue
    for (const pr of c.premises) {
      const s = idx.get(pr)
      if (s === undefined || s === t || seen.has(s + ':' + t)) continue
      seen.add(s + ':' + t); edges.push([s, t])
    }
  }
  const up = props.map(() => []), down = props.map(() => [])
  for (const [s, t] of edges) { up[t].push(s); down[s].push(t) }
  const depth = new Array(n).fill(-1)
  const visiting = new Uint8Array(n)
  const dfs = i => {
    if (depth[i] >= 0) return depth[i]
    if (visiting[i]) return 0  // a cycle can't happen (the store refuses them); stay safe anyway
    visiting[i] = 1
    let d = 0
    for (const s of up[i]) d = Math.max(d, dfs(s) + 1)
    visiting[i] = 0
    depth[i] = d
    return d
  }
  for (let i = 0; i < n; i++) dfs(i)
  // one band per label: two lessons on the same goal share a region
  // (an older backend sends no group fields: one band, never a crash)
  const label = p => p.group_label || p.group || 'Facts'
  const groups = [...new Set(props.map(label))]
  const gi = props.map(p => groups.indexOf(label(p)))
  const spacing = opts.spacing || 64, gap = opts.gap || 28, bandGap = opts.bandGap || 64
  const cols = []
  for (let i = 0; i < n; i++) (cols[depth[i]] = cols[depth[i]] || []).push(i)
  for (let d = 0; d < cols.length; d++) cols[d] = cols[d] || []
  const pos = new Float64Array(n)  // order key within a column
  const rank = () => cols.forEach(col => col.forEach((i, k) => { pos[i] = k }))
  for (const col of cols) col.sort((a, b) => gi[a] - gi[b] || hashStr(props[a].id) - hashStr(props[b].id))
  rank()
  const mean = (list, fallback) => list.length ? list.reduce((a, j) => a + pos[j], 0) / list.length : fallback
  for (let sweep = 0; sweep < 8; sweep++) {
    const forward = sweep % 2 === 0
    const order = forward ? cols : [...cols].reverse()
    for (const col of order) {
      const key = new Map(col.map(i => [i, mean(forward ? up[i] : down[i], pos[i])]))
      col.sort((a, b) => gi[a] - gi[b] || key.get(a) - key.get(b) || pos[a] - pos[b])
      col.forEach((i, k) => { pos[i] = k })
    }
  }
  // cross-axis coordinates: stack each column with gaps (bigger between bands), then relax toward neighbours
  const y = new Float64Array(n)
  const bandCount = groups.length
  const bandSize = new Array(bandCount).fill(0)
  for (const col of cols) {
    const c = new Array(bandCount).fill(0)
    for (const i of col) c[gi[i]]++
    c.forEach((v, g) => { bandSize[g] = Math.max(bandSize[g], v) })
  }
  const bandTop = []
  let acc = 0
  for (let g = 0; g < bandCount; g++) { bandTop[g] = acc; acc += Math.max(1, bandSize[g]) * gap + bandGap }
  for (const col of cols) {
    const c = new Array(bandCount).fill(0)
    for (const i of col) c[gi[i]]++
    const k = new Array(bandCount).fill(0)
    for (const i of col) {
      const g = gi[i]
      y[i] = bandTop[g] + (Math.max(1, bandSize[g]) - c[g]) * gap / 2 + k[g]++ * gap
    }
  }
  const settle = col => {  // keep order and minimum gap inside each band, shifting as little as possible
    for (let k = 1; k < col.length; k++) {
      const a = col[k - 1], b = col[k]
      const need = gi[a] === gi[b] ? gap : bandGap
      if (y[b] - y[a] < need) y[b] = y[a] + need
    }
    for (let k = col.length - 2; k >= 0; k--) {
      const a = col[k], b = col[k + 1]
      const need = gi[a] === gi[b] ? gap : bandGap
      if (y[b] - y[a] < need) y[a] = y[b] - need
    }
  }
  for (let it = 0; it < 12; it++) {
    for (const col of cols) {
      for (const i of col) {
        const nb = [...up[i], ...down[i]].filter(j => gi[j] === gi[i])
        if (nb.length) y[i] += (nb.reduce((a, j) => a + y[j], 0) / nb.length - y[i]) * 0.5
      }
      settle(col)
    }
  }
  const x = new Float64Array(n)
  for (let i = 0; i < n; i++) x[i] = depth[i] * spacing
  return { x, y, depth, edges, groups, gi }
}

// Live physics after LearnHarness's graph (d3-force semantics, re-implemented: the catalog allows the SDK and
// React only). Defaults are LearnHarness's own render settings (data/graph/render-settings.json). Exported for tests.
// groupSpacing is ours: LearnHarness keeps clusters apart through its own region layout; here every group gets
// its own slot (see groupAnchors) and this is the gap between slots.
export const PHYSICS_DEFAULTS = {
  charge: 364, linkDistance: 40, linkStrength: 1, gravity: 0.104, clusterPull: 0.033, velocityDecay: 0.4,
  depthMode: 'vertical', depthStrength: 0.8, depthSpacing: 91, groupSpacing: 160, regions: true, nodeSize: 5, labelZoom: 1.2
}

// Each group (lesson) gets its own slot, packed in rows, biggest first. Depth is measured inside the group, so
// one lesson's first facts no longer line up with every other lesson's on a shared strip. Exported for tests.
export function groupAnchors(seed, P) {
  const n = seed.x.length, G = seed.groups.length
  const cnt = new Array(G).fill(0), dmin = new Array(G).fill(Infinity), dmax = new Array(G).fill(-Infinity)
  for (let i = 0; i < n; i++) { const g = seed.gi[i]; cnt[g]++; dmin[g] = Math.min(dmin[g], seed.depth[i]); dmax[g] = Math.max(dmax[g], seed.depth[i]) }
  const local = new Float64Array(n), span = dmax.map((d, g) => cnt[g] ? d - dmin[g] : 0)
  for (let i = 0; i < n; i++) local[i] = seed.depth[i] - dmin[seed.gi[i]] - span[seed.gi[i]] / 2
  const ax = new Float64Array(G), ay = new Float64Array(G)
  if (G <= 1) return { ax, ay, local }
  const along = g => P.depthMode === 'off' ? 0 : span[g] * P.depthSpacing          // extent on the depth axis
  const across = g => Math.sqrt(cnt[g]) * (P.linkDistance + 30)                     // rough spread across it
  const size = g => Math.max(along(g), across(g), 220)  // never narrower than its label
  const order = [...Array(G).keys()].filter(g => cnt[g]).sort((a, b) => cnt[b] - cnt[a])
  const total = order.reduce((s, g) => s + (size(g) + P.groupSpacing) ** 2, 0)
  const rowMax = Math.max(size(order[0]) + P.groupSpacing, Math.sqrt(total) * 1.4)
  // shelf packing: row along the cross axis; depth axis is the row's height
  const placed = []
  let u = 0, v = 0, rowH = 0
  for (const g of order) {
    const w = size(g)
    if (u > 0 && u + w > rowMax) { u = 0; v += rowH + P.groupSpacing; rowH = 0 }
    placed.push([g, u + w / 2, v + size(g) / 2])
    u += w + P.groupSpacing; rowH = Math.max(rowH, size(g))
  }
  let ux = 0, uy = 0
  for (const [, a, b] of placed) { ux += a; uy += b }
  ux /= placed.length; uy /= placed.length
  for (const [g, a, b] of placed) { ax[g] = a - ux; ay[g] = b - uy }
  return { ax, ay, local }
}
const ALPHA_MIN = 0.001, ALPHA_DECAY = 1 - Math.pow(ALPHA_MIN, 1 / 300)

export function createSim(seed, settings) {
  const n = seed.x.length
  const S = { n, x: Float64Array.from(seed.x), y: Float64Array.from(seed.y), vx: new Float64Array(n), vy: new Float64Array(n),
    fx: new Float64Array(n).fill(NaN), fy: new Float64Array(n).fill(NaN), alpha: 1, alphaTarget: 0, settings }
  const degree = new Float64Array(n)
  for (const [a, b] of seed.edges) { degree[a]++; degree[b]++ }
  const groups = seed.groups.length
  let anchorKey = '', A = null
  const anchors = P => {
    const key = [P.depthMode, P.depthSpacing, P.groupSpacing, P.linkDistance].join()
    if (key !== anchorKey) { anchorKey = key; A = groupAnchors(seed, P) }
    return A
  }
  S.anchors = () => anchors(S.settings)
  S.tick = () => {
    const P = S.settings, alpha = (S.alpha += (S.alphaTarget - S.alpha) * ALPHA_DECAY)
    const { ax, ay, local } = anchors(P)
    const { x, y, vx, vy } = S
    // many-body repulsion (d3 forceManyBody, exact pairwise; fine at a few hundred facts)
    const k = -P.charge * alpha
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      let dx = x[j] - x[i], dy = y[j] - y[i], l = dx * dx + dy * dy
      if (l > 640000) continue
      if (l < 1) { dx = (i % 2 ? 1 : -1) * 0.5; dy = 0.5; l = 1 }
      const w = k / l
      vx[i] += dx * w; vy[i] += dy * w; vx[j] -= dx * w; vy[j] -= dy * w
    }
    // links (d3 forceLink: strength 1/min(degree), bias toward the less-connected end)
    for (const [a, b] of seed.edges) {
      let dx = x[b] + vx[b] - x[a] - vx[a], dy = y[b] + vy[b] - y[a] - vy[a]
      const l0 = Math.sqrt(dx * dx + dy * dy) || 1
      const str = P.linkStrength / Math.min(degree[a], degree[b])
      const l = ((l0 - P.linkDistance) / l0) * alpha * str
      dx *= l; dy *= l
      const bias = degree[a] / (degree[a] + degree[b])
      vx[b] -= dx * bias; vy[b] -= dy * bias; vx[a] += dx * (1 - bias); vy[a] += dy * (1 - bias)
    }
    // group pull, gravity (toward the group's slot), depth (inside the group)
    const cx = new Float64Array(groups), cy = new Float64Array(groups), cnt = new Float64Array(groups)
    for (let i = 0; i < n; i++) { cx[seed.gi[i]] += x[i]; cy[seed.gi[i]] += y[i]; cnt[seed.gi[i]]++ }
    for (let i = 0; i < n; i++) {
      const g = seed.gi[i]
      vx[i] += (cx[g] / cnt[g] - x[i]) * P.clusterPull * alpha
      vy[i] += (cy[g] / cnt[g] - y[i]) * P.clusterPull * alpha
      // d3 forceX/forceY toward the centre; with several groups, toward this group's slot
      if (P.depthMode !== 'horizontal') vx[i] += (ax[g] - x[i]) * P.gravity * alpha
      if (P.depthMode !== 'vertical') vy[i] += (ay[g] - y[i]) * P.gravity * alpha
      if (P.depthMode !== 'off') {
        const target = local[i] * P.depthSpacing
        if (P.depthMode === 'horizontal') vx[i] += (ax[g] + target - x[i]) * P.depthStrength * alpha
        else vy[i] += (ay[g] + target - y[i]) * P.depthStrength * alpha
      }
    }
    for (let i = 0; i < n; i++) {
      if (!Number.isNaN(S.fx[i])) { x[i] = S.fx[i]; y[i] = S.fy[i]; vx[i] = vy[i] = 0; continue }
      vx[i] *= 1 - P.velocityDecay; vy[i] *= 1 - P.velocityDecay
      x[i] += vx[i]; y[i] += vy[i]
    }
    return S.alpha
  }
  S.reheat = (a = 0.6) => { S.alpha = Math.max(S.alpha, a) }
  S.running = () => S.alpha >= ALPHA_MIN || S.alphaTarget > 0
  return S
}

const STORE_KEY = 'learnloop.graph.v2'  // v2: group slots + vertical depth; v1 positions no longer apply
function loadGraphPrefs() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY) || '{}') } catch { return {} }
}
function saveGraphPrefs(patch) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify({ ...loadGraphPrefs(), ...patch })) } catch { /* storage full or blocked */ }
}

const SLIDERS = [
  ['charge', 'Repel', 0, 1500, 1], ['linkDistance', 'Link distance', 10, 200, 1], ['linkStrength', 'Link strength', 0, 2, 0.05],
  ['gravity', 'Gravity', 0, 0.5, 0.005], ['clusterPull', 'Group pull', 0, 0.2, 0.002], ['velocityDecay', 'Friction', 0.05, 0.9, 0.01],
  ['depthStrength', 'Depth pull', 0, 1.5, 0.05], ['depthSpacing', 'Depth spacing', 20, 250, 1],
  ['groupSpacing', 'Group spacing', 0, 600, 5],
  ['nodeSize', 'Node size', 2, 12, 0.5], ['labelZoom', 'Names from zoom', 0.3, 4, 0.05]
]

function PhysicsPanel({ settings, onChange, onReset }) {
  const row = ([key, label, min, max, step]) => jsxs('label', { className: 'flex flex-col gap-0.5 text-xs', children: [
    jsxs('div', { className: 'flex justify-between', children: [jsx('span', { children: label }),
      jsx('span', { className: 'text-(--ui-text-tertiary)', children: String(Math.round(settings[key] * 1000) / 1000) })] }),
    jsx('input', { type: 'range', min, max, step, value: settings[key], onChange: e => onChange({ [key]: Number(e.target.value) }),
      style: { accentColor: 'var(--ui-accent)' } })
  ] }, key)
  return jsxs('div', { className: 'absolute left-2 top-2 flex w-56 flex-col gap-2 overflow-y-auto rounded-md border border-(--ui-stroke-secondary) p-3 shadow-lg',
    style: { maxHeight: 'calc(100% - 1rem)', background: 'var(--ui-bg-elevated, var(--ui-bg-card, var(--background)))' }, children: [
      jsx(Label, { children: 'Physics' }),
      jsxs('label', { className: 'flex items-center justify-between text-xs', children: [jsx('span', { children: 'Depth' }),
        jsx('select', { value: settings.depthMode, onChange: e => onChange({ depthMode: e.target.value }),
          className: 'rounded-md border border-(--ui-stroke-secondary) bg-transparent px-1 text-xs', children: [
            jsx('option', { value: 'vertical', children: 'top → bottom' }, 'v'),
            jsx('option', { value: 'horizontal', children: 'left → right' }, 'h'),
            jsx('option', { value: 'off', children: 'off (free)' }, 'o')] })] }),
      jsxs('label', { className: 'flex items-center justify-between text-xs', children: [jsx('span', { children: 'Group regions' }),
        jsx('input', { type: 'checkbox', checked: settings.regions !== false, onChange: e => onChange({ regions: e.target.checked }),
          style: { accentColor: 'var(--ui-accent)' } })] }),
      ...SLIDERS.map(row),
      jsx('button', { type: 'button', onClick: onReset, className: 'self-start text-xs text-(--ui-text-tertiary) hover:text-(--ui-text-primary)',
        children: 'Reset to defaults' })
    ] })
}

function GraphView({ graph, height = 600, onOpenLesson, onPractice }) {
  const wrap = useRef(null)
  const canvas = useRef(null)
  const props = (graph && graph.propositions) || []
  const chains = (graph && graph.chains) || []
  // re-seed only when the set of facts or links changes, not on every poll
  const sig = props.map(p => p.id).join(',') + '|' + chains.map(c => c.conclusion + ':' + c.premises.join('+')).join(',')
  const L = useMemo(() => layoutGraph(props, chains, { spacing: PHYSICS_DEFAULTS.depthSpacing }), [sig])
  const [settings, setSettings] = useState(() => ({ ...PHYSICS_DEFAULTS, ...(loadGraphPrefs().physics || {}) }))
  const [showPhysics, setShowPhysics] = useState(false)
  const sim = useMemo(() => {
    const saved = loadGraphPrefs().positions || {}
    const seed = { ...L, x: Float64Array.from(L.x), y: Float64Array.from(L.y) }
    const S0 = { ...PHYSICS_DEFAULTS, ...settings }
    const { ax, ay, local } = groupAnchors(L, S0)
    // start each fact in its group's slot: depth along the depth axis, the layered layout's order across it
    const G = L.groups.length, my = new Float64Array(G), mc = new Float64Array(G)
    props.forEach((p, i) => { my[L.gi[i]] += L.y[i]; mc[L.gi[i]]++ })
    let known = 0
    props.forEach((p, i) => {
      const g = L.gi[i], d = local[i] * S0.depthSpacing, c = L.y[i] - my[g] / mc[g]
      if (S0.depthMode === 'horizontal') { seed.x[i] = ax[g] + d; seed.y[i] = ay[g] + c }
      else { seed.x[i] = ax[g] + c; seed.y[i] = ay[g] + d }
      const pos = saved[p.id]
      if (pos) { seed.x[i] = pos[0]; seed.y[i] = pos[1]; known++ }
    })
    const S = createSim(seed, settings)
    S.alpha = known === props.length && known > 0 ? 0.05 : 0.8  // a saved layout only settles; a new one runs
    return S
  }, [L])
  sim.settings = settings
  const [sel, setSel] = useState(null)
  const [q, setQ] = useState('')
  const view = useRef({ k: 1, tx: 0, ty: 0, w: 0, h: 0, hover: -1, fitted: false })
  const dirty = useRef(true)
  const neighbours = useMemo(() => {
    const m = props.map(() => ({ up: new Set(), down: new Set() }))
    for (const [s, t] of L.edges) { m[t].up.add(s); m[s].down.add(t) }
    return m
  }, [L])
  const match = useMemo(() => {
    const t = q.trim().toLowerCase()
    return t ? props.map(p => (p.name + ' ' + p.statement + ' ' + p.group_label).toLowerCase().includes(t)) : null
  }, [q, graph])
  const selIdx = sel ? props.findIndex(p => p.id === sel) : -1

  const fit = useCallback(() => {
    const v = view.current
    if (!props.length || !v.w) return
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity
    for (let i = 0; i < props.length; i++) { x0 = Math.min(x0, sim.x[i]); x1 = Math.max(x1, sim.x[i]); y0 = Math.min(y0, sim.y[i]); y1 = Math.max(y1, sim.y[i]) }
    const pad = 50, padX = L.groups.length > 1 ? 150 : pad  // room for group names at the edges
    v.k = Math.min(2.5, Math.min((v.w - padX * 2) / Math.max(1, x1 - x0), (v.h - pad * 2) / Math.max(1, y1 - y0)))
    v.tx = v.w / 2 - ((x0 + x1) / 2) * v.k
    v.ty = v.h / 2 - ((y0 + y1) / 2) * v.k
    dirty.current = true
  }, [sim])
  const changeSettings = patch => {
    setSettings(prev => { const next = { ...prev, ...patch }; saveGraphPrefs({ physics: next }); return next })
    sim.reheat(0.5); dirty.current = true
  }
  const resetSettings = () => {
    saveGraphPrefs({ physics: {}, positions: {} })
    setSettings({ ...PHYSICS_DEFAULTS }); sim.reheat(1); view.current.refit = true
  }
  const savePositions = () => {
    const positions = { ...(loadGraphPrefs().positions || {}) }
    props.forEach((p, i) => { positions[p.id] = [Math.round(sim.x[i] * 10) / 10, Math.round(sim.y[i] * 10) / 10] })
    saveGraphPrefs({ positions })
  }

  // size + simulation/draw loop
  useEffect(() => {
    const c = canvas.current, w = wrap.current
    if (!c || !w) return undefined
    const ro = new ResizeObserver(() => {
      const r = w.getBoundingClientRect(), dpr = window.devicePixelRatio || 1
      c.width = Math.round(r.width * dpr); c.height = Math.round(height * dpr)
      c.style.width = r.width + 'px'; c.style.height = height + 'px'
      const v = view.current
      v.w = r.width; v.h = height
      dirty.current = true
    })
    ro.observe(w)
    let raf = 0, wasRunning = false, frames = 0
    const loop = () => {
      const v = view.current
      if (sim.running()) {
        sim.tick(); dirty.current = true; wasRunning = true; frames++
        // keep the picture in frame while a fresh layout unfolds
        if (v.w && (!v.fitted || v.refit) && frames % 6 === 0) fit()
      } else if (wasRunning) {
        wasRunning = false; savePositions()
        if (v.w && (!v.fitted || v.refit)) { fit(); v.fitted = true; v.refit = false }
      }
      if (v.w && !v.fitted && !sim.running()) { fit(); v.fitted = true }
      if (dirty.current) { dirty.current = false; drawRef.current() }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => { ro.disconnect(); cancelAnimationFrame(raf) }
  }, [sim, height])
  const drawRef = useRef(() => {})
  useEffect(() => { dirty.current = true }, [sel, match, settings])

  function draw() {
    const c = canvas.current
    if (!c) return
    const ctx = c.getContext('2d'), dpr = window.devicePixelRatio || 1, v = view.current
    const cs = getComputedStyle(wrap.current)
    const fg = cs.color || '#ddd'
    const font = cs.fontFamily || 'sans-serif'
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, v.w, v.h)
    const sx = i => sim.x[i] * v.k + v.tx, sy = i => sim.y[i] * v.k + v.ty
    const focus = v.hover >= 0 ? v.hover : selIdx
    const near = new Set()
    if (focus >= 0) { near.add(focus); neighbours[focus].up.forEach(j => near.add(j)); neighbours[focus].down.forEach(j => near.add(j)) }
    const lit = i => (match ? match[i] : true) && (focus < 0 || near.has(i))
    const hue = i => HUES[L.gi[i] % HUES.length]
    const r0 = settings.nodeSize * Math.min(1.6, Math.max(0.7, Math.sqrt(v.k)))
    // regions (after LearnHarness's): a soft disc around every fact and a wide round-capped stroke along every
    // link inside a group, in the group's colour, so each cluster reads as one patch (dilation 20 + blur 40)
    if (settings.regions !== false && L.groups.length > 1) {
      const rr = Math.max(18, 60 * v.k)
      ctx.globalAlpha = 1
      for (let i = 0; i < props.length; i++) {
        const g = ctx.createRadialGradient(sx(i), sy(i), 0, sx(i), sy(i), rr)
        g.addColorStop(0, `hsla(${hue(i)}, 60%, 55%, 0.16)`); g.addColorStop(0.45, `hsla(${hue(i)}, 60%, 55%, 0.08)`)
        g.addColorStop(1, `hsla(${hue(i)}, 60%, 55%, 0)`)
        ctx.fillStyle = g
        ctx.fillRect(sx(i) - rr, sy(i) - rr, rr * 2, rr * 2)
      }
      ctx.lineCap = 'round'; ctx.lineWidth = Math.max(10, 40 * v.k)
      for (const [s, t] of L.edges) {
        if (L.gi[s] !== L.gi[t]) continue
        ctx.strokeStyle = `hsla(${hue(s)}, 60%, 55%, 0.07)`
        ctx.beginPath(); ctx.moveTo(sx(s), sy(s)); ctx.lineTo(sx(t), sy(t)); ctx.stroke()
      }
      ctx.lineCap = 'butt'
    }
    // edges with arrowheads (premise -> conclusion)
    for (const [s, t] of L.edges) {
      const on = lit(s) && lit(t) && (focus < 0 || s === focus || t === focus)
      ctx.strokeStyle = fg
      ctx.globalAlpha = focus >= 0 || match ? (on ? 0.75 : 0.05) : 0.2
      ctx.lineWidth = on && focus >= 0 ? 1.6 : 1
      const x1 = sx(s), y1 = sy(s), x2 = sx(t), y2 = sy(t)
      const d = Math.hypot(x2 - x1, y2 - y1) || 1, ux = (x2 - x1) / d, uy = (y2 - y1) / d
      const ex = x2 - ux * (r0 + 2), ey = y2 - uy * (r0 + 2)
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(ex, ey); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(ex - ux * 6 - uy * 3, ey - uy * 6 + ux * 3); ctx.lineTo(ex - ux * 6 + uy * 3, ey - uy * 6 - ux * 3); ctx.closePath()
      ctx.fillStyle = fg; ctx.fill()
    }
    // nodes: size grows with how much a fact supports
    for (let i = 0; i < props.length; i++) {
      ctx.globalAlpha = lit(i) ? 1 : 0.12
      const r = r0 * (1 + Math.min(0.8, neighbours[i].down.size * 0.12)) * (i === focus ? 1.3 : 1)
      ctx.beginPath(); ctx.arc(sx(i), sy(i), r, 0, Math.PI * 2)
      ctx.fillStyle = `hsl(${hue(i)}, 65%, 60%)`; ctx.fill()
      if (i === selIdx) { ctx.lineWidth = 2; ctx.strokeStyle = fg; ctx.stroke() }
    }
    // labels: names when zoomed in (Names from zoom) or in focus; group names when zoomed out
    const showNames = v.k >= settings.labelZoom
    ctx.textBaseline = 'middle'
    for (let i = 0; i < props.length; i++) {
      const named = near.has(i) || (match && match[i]) || (showNames && lit(i))
      if (!named) continue
      ctx.globalAlpha = lit(i) ? (near.has(i) ? 1 : 0.8) : 0.15
      ctx.font = `${i === focus ? 600 : 400} 12px ${font}`
      ctx.fillStyle = fg
      ctx.fillText(props[i].name, sx(i) + r0 + 4, sy(i))
    }
    if (!showNames && focus < 0 && !match) {
      ctx.globalAlpha = 0.85
      ctx.font = `600 13px ${font}`
      ctx.textAlign = 'center'
      L.groups.forEach((g, k) => {
        let mx = 0, my = Infinity, c = 0
        for (let i = 0; i < props.length; i++) if (L.gi[i] === k) { mx += sx(i); my = Math.min(my, sy(i)); c++ }
        if (!c) return
        ctx.fillStyle = `hsl(${HUES[k % HUES.length]}, 60%, 70%)`
        const text = String(g).length > 48 ? String(g).slice(0, 47) + '…' : String(g)
        const half = ctx.measureText(text).width / 2 + 8
        ctx.fillText(text, Math.max(half, Math.min(v.w - half, mx / c)), Math.max(16, my - 22))
      })
      ctx.textAlign = 'start'
    }
    ctx.globalAlpha = 1
  }

  drawRef.current = draw  // the rAF loop always draws with this render's state (selection, search)

  // input: drag the background to pan, drag a fact to move it (the others follow), wheel to zoom, click to select
  const drag = useRef(null)
  const toWorld = ev => {
    const r = canvas.current.getBoundingClientRect(), v = view.current
    return [(ev.clientX - r.left - v.tx) / v.k, (ev.clientY - r.top - v.ty) / v.k]
  }
  const pick = (ev) => {
    const r = canvas.current.getBoundingClientRect(), v = view.current
    const mx = ev.clientX - r.left, my = ev.clientY - r.top
    let best = -1, bd = 12 * 12
    for (let i = 0; i < props.length; i++) {
      const dx = sim.x[i] * v.k + v.tx - mx, dy = sim.y[i] * v.k + v.ty - my, d = dx * dx + dy * dy
      if (d < bd) { bd = d; best = i }
    }
    return best
  }
  const onPointerDown = ev => {
    const node = pick(ev)
    drag.current = { x: ev.clientX, y: ev.clientY, moved: false, node }
    ev.currentTarget.setPointerCapture(ev.pointerId)
  }
  const onPointerMove = ev => {
    const v = view.current, d = drag.current
    if (d) {
      const dx = ev.clientX - d.x, dy = ev.clientY - d.y
      if (!d.moved && Math.abs(dx) + Math.abs(dy) > 3) {
        d.moved = true
        if (d.node >= 0) sim.alphaTarget = 0.3
      }
      if (!d.moved) return
      if (d.node >= 0) {
        const [wx, wy] = toWorld(ev)
        sim.fx[d.node] = wx; sim.fy[d.node] = wy; sim.reheat(0.3)
      } else {
        v.tx += dx; v.ty += dy; d.x = ev.clientX; d.y = ev.clientY
      }
      dirty.current = true
      return
    }
    const h = pick(ev)
    if (h !== v.hover) { v.hover = h; dirty.current = true; canvas.current.style.cursor = h >= 0 ? 'pointer' : 'grab' }
  }
  const onPointerUp = ev => {
    const d = drag.current
    drag.current = null
    if (!d) return
    if (d.node >= 0 && d.moved) { sim.fx[d.node] = NaN; sim.fy[d.node] = NaN; sim.alphaTarget = 0 }
    if (!d.moved) { const i = pick(ev); setSel(i >= 0 ? props[i].id : null) }
  }
  const onPointerLeave = () => { if (view.current.hover !== -1) { view.current.hover = -1; dirty.current = true } }
  useEffect(() => {
    const c = canvas.current
    if (!c) return undefined
    const onWheel = ev => {
      ev.preventDefault()
      const v = view.current, r = c.getBoundingClientRect()
      const mx = ev.clientX - r.left, my = ev.clientY - r.top
      const k = Math.max(0.1, Math.min(8, v.k * Math.exp(-ev.deltaY * 0.0015)))
      v.tx = mx - ((mx - v.tx) / v.k) * k; v.ty = my - ((my - v.ty) / v.k) * k; v.k = k
      dirty.current = true
    }
    c.addEventListener('wheel', onWheel, { passive: false })
    return () => c.removeEventListener('wheel', onWheel)
  }, [])

  const In = sdk.Input || 'input'
  const selected = selIdx >= 0 ? props[selIdx] : null
  const factButton = j => jsx('button', { type: 'button', onClick: () => setSel(props[j].id),
    className: 'block text-left text-xs hover:text-(--ui-text-primary)', children: '• ' + props[j].name }, props[j].id)
  const tool = (label, onClick, on) => jsx('button', { type: 'button', onClick,
    className: cn('text-xs hover:text-(--ui-text-primary)', on ? 'font-semibold text-(--ui-text-primary)' : 'text-(--ui-text-tertiary)'), children: label })
  return jsxs('div', { className: 'flex flex-col gap-2', children: [
    jsxs('div', { className: 'flex items-center gap-3', children: [
      jsx(In, { value: q, onChange: e => setQ(e.target.value), placeholder: 'Search your knowledge graph', className: 'min-w-0 flex-1 text-sm' }),
      tool('Physics', () => setShowPhysics(!showPhysics), showPhysics),
      tool('Shake', () => { sim.reheat(1); view.current.refit = true }),
      tool('Fit', fit)
    ] }),
    jsxs('div', { ref: wrap, className: 'relative overflow-hidden rounded-md border border-(--ui-stroke-secondary) text-(--ui-text-primary)', style: { height }, children: [
      jsx('canvas', { ref: canvas, onPointerDown, onPointerMove, onPointerUp, onPointerLeave, style: { touchAction: 'none', cursor: 'grab' } }),
      props.length === 0 && jsx('div', { className: 'absolute inset-0 flex items-center justify-center text-sm text-(--ui-text-tertiary)',
        children: 'Your graph fills up as lessons land facts.' }),
      showPhysics && jsx(PhysicsPanel, { settings, onChange: changeSettings, onReset: resetSettings }),
      selected && jsxs('div', { className: 'absolute right-2 top-2 flex w-72 flex-col gap-2 overflow-y-auto rounded-md border border-(--ui-stroke-secondary) p-3 text-sm shadow-lg',
        style: { maxHeight: 'calc(100% - 1rem)', background: 'var(--ui-bg-elevated, var(--ui-bg-card, var(--background)))' }, children: [
        jsxs('div', { className: 'flex items-start gap-2', children: [
          jsx('div', { className: 'flex-1 font-semibold leading-snug', children: selected.name }),
          jsx('button', { type: 'button', onClick: () => setSel(null), className: 'text-(--ui-text-tertiary) hover:text-(--ui-text-primary)', children: '×' })
        ] }),
        jsx('div', { className: 'text-(--ui-text-secondary)', children: jsx(Md, { text: selected.statement }) }),
        selected.session_id && onOpenLesson
          ? jsx('button', { type: 'button', onClick: () => onOpenLesson(selected.session_id),
              className: 'self-start text-xs text-(--ui-accent) hover:underline', children: 'From: ' + selected.group_label + ' ↗' })
          : selected.group_label && jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: 'From: ' + selected.group_label }),
        onPractice && jsx('button', { type: 'button', onClick: () => onPractice(selected.name),
          className: 'self-start rounded-md border border-(--ui-stroke-secondary) px-2 py-1 text-xs hover:border-(--ui-stroke-primary)',
          children: 'Practise this' }),
        neighbours[selIdx].up.size > 0 && jsxs('div', { children: [jsx(Label, { children: 'Built from' }), ...[...neighbours[selIdx].up].map(factButton)] }),
        neighbours[selIdx].down.size > 0 && jsxs('div', { children: [jsx(Label, { children: 'Supports' }), ...[...neighbours[selIdx].down].map(factButton)] })
      ] })
    ] }),
    jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children:
      'Arrows run from a fact to what it supports. Drag a fact to move it, drag the background to pan, scroll to zoom, click for details. Physics tunes the forces.' })
  ] })
}

// ---------- Learn page (sidebar) ----------

// A lesson on the Learn page: click to reopen its chat; lessons with a plan can show their full map here.
function LessonCard({ ctx, l, open }) {
  const [map, setMap] = useState(false)
  const data = usePoll(ctx, map ? `/lesson?session=${encodeURIComponent(l.session_id)}` : null, 10000)
  const plan = data && data.lesson && data.lesson.plan
  const small = 'text-xs text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'
  return jsxs('div', { className: 'flex flex-col gap-2 rounded-md border border-(--ui-stroke-secondary) px-3 py-2 hover:border-(--ui-stroke-primary)', children: [
    jsxs('div', { className: 'flex items-start gap-3', children: [
      jsxs('button', { type: 'button', onClick: () => open(l), className: 'flex min-w-0 flex-1 flex-col gap-0.5 text-left', children: [
        jsx('div', { className: 'text-sm font-medium', children: l.goal }),

        jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: [
            l.kind === 'practice' ? (l.phase === 'done' ? 'Practice · done' : 'Practice') : (PHASE_LABEL[l.phase] || l.phase),
            l.steps ? `${l.reached}/${l.steps} steps` : null,
            ...(l.kind === 'practice' ? [`${l.problems} problems (${l.solved} solved)`] : [`${l.answered} answered`, `${l.facts} facts`]),
            when(l.updated_at)
          ].filter(Boolean).join(' · ') })
      ] }),
      l.steps > 0 && jsx('button', { type: 'button', onClick: () => setMap(!map), className: small, children: map ? 'Hide map' : 'Map' })
    ] }),
    map && (plan ? jsxs('div', { className: 'flex flex-col gap-2', children: [jsx(PlanLegend, { plan }),
      jsx('div', { style: { overflow: 'auto', maxHeight: '70vh' }, children: jsx(PlanMap, { plan }) })] })
      : jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: 'Loading the map…' }))
  ] })
}

function LearnPage({ ctx }) {
  const data = usePoll(ctx, '/lessons', 5000)
  const graph = usePoll(ctx, '/graph', 15000)
  const [q, setQ] = useState('')
  const [mode, setMode] = useState('graph')
  const lessons = (data && data.lessons) || []
  const stats = data && data.stats
  const facts = ((graph && graph.propositions) || []).filter(p => !q.trim() ||
    (p.name + ' ' + p.statement).toLowerCase().includes(q.trim().toLowerCase()))
  const byId = new Map(((graph && graph.propositions) || []).map(p => [p.id, p.name]))
  const premisesOf = new Map()
  for (const c of (graph && graph.chains) || []) premisesOf.set(c.conclusion, [...(premisesOf.get(c.conclusion) || []), ...c.premises])
  const open = l => typeof sdk.host.openSession === 'function' ? sdk.host.openSession(l.session_id) : null
  const In = sdk.Input || 'input'
  return jsxs('div', { className: 'mx-auto flex h-full w-full flex-col gap-6 overflow-y-auto p-6 text-(--ui-text-primary)', style: { maxWidth: 1100 }, children: [
    jsx(Style, {}),
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
      ...lessons.map(l => jsx(LessonCard, { ctx, l, open }, l.id))
    ] }),
    jsxs('section', { className: 'flex flex-col gap-2', children: [
      jsxs('div', { className: 'flex items-center gap-3', children: [
        jsx(Label, { children: 'What you know' }),
        ...['graph', 'list'].map(m => jsx('button', { type: 'button', onClick: () => setMode(m),
          className: cn('text-xs', mode === m ? 'font-semibold text-(--ui-text-primary)' : 'text-(--ui-text-tertiary) hover:text-(--ui-text-primary)'),
          children: m === 'graph' ? 'Graph' : 'List' }, m))
      ] }),
      mode === 'graph'
        ? jsx(GraphView, { graph, onOpenLesson: sid => open({ session_id: sid }), onPractice: startPractice })
        : jsxs('div', { className: 'flex flex-col gap-2', children: [
            jsx(In, { value: q, onChange: e => setQ(e.target.value), placeholder: 'Search your knowledge graph', className: 'text-sm' }),
            ...facts.slice(0, 200).map(p => jsxs('div', { className: 'flex flex-col gap-0.5 border-b border-(--ui-stroke-secondary) py-2 text-sm', children: [
              jsx('div', { className: 'font-medium', children: p.name }),
              jsx('div', { className: 'text-(--ui-text-secondary)', children: jsx(Md, { text: p.statement }) }),
              premisesOf.has(p.id) && jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children:
                'from: ' + [...new Set(premisesOf.get(p.id))].map(id => byId.get(id)).filter(Boolean).join(', ') })
            ] }, p.id))
          ] })
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
    if (HAS_DOCK) {
      ctx.register({ id: 'learn-dock', area: sdk.COMPOSER_AREAS.top, render: () => jsx(LearnDock, { ctx }) })
      if (sdk.COMPOSER_AREAS.middleware) {
        ctx.register({ id: 'answer-middleware', area: sdk.COMPOSER_AREAS.middleware, data: makeAnswerMiddleware(ctx) })
      }
    }
    ctx.register({
      id: 'problem-card',
      area: sdk.TRANSCRIPT_DIRECTIVE_AREA,
      data: {
        name: 'learnloop-problem',
        render: ({ attrs, sessionId }) => jsx(ProblemCard, { ctx, id: attrs && attrs.id, sessionId })
      }
    })
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
