# Live tests to run

Things the automated tests and headless runs can't cover. Run them in Hermes Desktop under the `learnloop-test` profile, tick them off, note what happened.

- [ ] **Background research arrives mid-lesson.** During a lesson, ask about something niche or fast-moving (a library version, a detail from a recent paper). Expect: "let me verify… while we continue", teaching carries on, the brief lands as a new message and is woven in with a source. If a question is open when it lands, it must stay open (not graded as your answer). Headless runs can't show this: a one-shot CLI run waits for the sub-agent and gets the result inline.
- [ ] **Practice dock end to end.** Work one problem through the dock: thinking in the message box, Hint, a wrong claim, the conclusion, Next problem.
- [ ] **Question dock.** During a lesson: the open question appears above the message box; picking an option and pressing Enter with thinking typed submits it; Enter with nothing picked is refused with a note; the verdict shows at once in the dock and in the chat card; a side message after answering goes through as normal chat.
- [ ] **Lesson map.** In a lesson with a plan: the pane shows a small map thumbnail; clicking it opens the full map in a dialog over the chat (Esc or clicking outside closes it, the chat is untouched); on the Learn page, a lesson's *Map* toggle shows the same map inline. Done steps green, the current step amber, steps available next dashed.
- [ ] **Graph groups.** On the Learn page with two or more lessons: each lesson sits in its own area with a tinted region and its name; Physics → *Group spacing* moves them apart or together, *Group regions* turns the tint off, *Depth* switches top → bottom / left → right; Reset restores it.
- [ ] **Graph physics on a fresh profile.** Positions and settings persist across a restart; Reset restores defaults.
