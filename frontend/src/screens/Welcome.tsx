import { useMemo, useState } from 'react'

import { StewardMark } from '../components/StewardMark'
import type { Me } from '../types'

interface Step {
  eyebrow: string
  title: string
  body: string[]
}

/** What a new arrival is told, and in what order.
 *
 * Three steps for everyone, a fourth for the executor. The order is deliberate:
 * what this is, then the thing they will do first (ask for something), then the
 * thing they are most likely to be afraid of (someone else asking too). The
 * reassurance has to land *before* they meet a contested item, not after.
 */
function steps(estateName: string, isExecutor: boolean): Step[] {
  const shared: Step[] = [
    {
      eyebrow: 'Where you are',
      title: `This is ${estateName}.`,
      body: [
        `Everything from the house is being catalogued here, a piece at a time — a photograph, what it is, what sort of condition it's in.`,
        `Nothing has to be decided today. The list will still be here next week.`,
      ],
    },
    {
      eyebrow: 'Asking for something',
      title: 'If something matters to you, say so.',
      body: [
        `When you find a piece you'd like, you can put your name to it and say why. The why is the part that helps — "she wore it to my wedding" tells the family something the photograph can't.`,
        `Other people will be asking for things too. That's the point of doing it this way, not a problem with it.`,
      ],
    },
    {
      eyebrow: 'When two people ask',
      title: "Sometimes you'll both want the same thing.",
      body: [
        `It happens, and it isn't a fight. The piece gets marked as needing a talk, and Steward writes a note in the thread with what it knows — who asked, what each of you said, and a suggestion for a way through.`,
        `Nobody loses their claim by waiting. It just means the two of you talk before anything is settled.`,
      ],
    },
  ]

  if (!isExecutor) return shared

  return [
    ...shared,
    {
      eyebrow: 'Your part in it',
      title: "The final call is yours to record.",
      body: [
        `You're the executor here, so when something is contested, you're the one who writes down how it was settled — and later, where each piece goes: kept, given away, sold, or let go.`,
        `Steward will suggest and explain. It won't decide. That stays with you.`,
      ],
    },
  ]
}

/** The first thing a new member sees, once.
 *
 * On Ink, like the sign-in screen — DESIGN.md reserves the dark surface for
 * arrival moments, and this is the other one. Skippable from every step,
 * because some people would rather just go and look at the list.
 */
export function Welcome({ me, onDone }: { me: Me; onDone: () => void }) {
  const [at, setAt] = useState(0)

  const estateName = me.estate_name?.trim() || 'the estate'
  const sequence = useMemo(
    () => steps(estateName, me.role === 'executor'),
    [estateName, me.role],
  )

  const step = sequence[at]
  const last = at === sequence.length - 1

  return (
    <div className="welcome">
      <div className="welcome__panel">
        <header className="welcome__top">
          <StewardMark size={30} color="var(--on-ink)" />
          <button className="welcome__skip" type="button" onClick={onDone}>
            Skip, I'll figure it out
          </button>
        </header>

        <div className="welcome__body">
          <span className="eyebrow eyebrow--on-ink">{step.eyebrow}</span>
          <h1 className="welcome__title">{step.title}</h1>
          {step.body.map((paragraph) => (
            <p className="welcome__text" key={paragraph.slice(0, 24)}>
              {paragraph}
            </p>
          ))}
        </div>

        <footer className="welcome__foot">
          {/* A place-marker, not a progress bar — no percentage, no target. */}
          <ol className="welcome__marks" aria-label={`Step ${at + 1} of ${sequence.length}`}>
            {sequence.map((each, index) => (
              <li
                key={each.eyebrow}
                className={`welcome__mark-dot${index === at ? ' welcome__mark-dot--here' : ''}`}
                aria-hidden="true"
              />
            ))}
          </ol>

          <div className="welcome__actions">
            {at > 0 && (
              <button
                className="button button--ghost-ink"
                type="button"
                onClick={() => setAt((n) => n - 1)}
              >
                Back
              </button>
            )}
            <button
              className="button button--cream"
              type="button"
              onClick={() => (last ? onDone() : setAt((n) => n + 1))}
            >
              {last ? 'Take me to the inventory' : 'Go on'}
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
