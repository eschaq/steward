import { Link } from 'react-router-dom'

import type { Message } from '../types'

function when(iso: string): string {
  const date = new Date(iso)
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function titleCase(value: string): string {
  return value.replace(/\b[a-z]/g, (c) => c.toUpperCase())
}

/** One message. Steward's own posts get a distinct treatment — sage-tinted,
 * with the mark beside the name — but not a loud one: this is a family's feed
 * and the agent is a participant in it, not a system notification. */
function Entry({
  message,
  prominent,
  showItem,
}: {
  message: Message
  prominent?: boolean
  /** On the estate feed: name the item this is about and link to it. Off in the
   * per-item thread, where the item is the page you are already on. */
  showItem?: boolean
}) {
  const kind = message.is_agent ? 'agent' : 'human'
  return (
    <article
      className={`msg msg--${kind}${prominent ? ' msg--prominent' : ''}`}
      aria-label={`${message.author_name}, ${when(message.created_at)}`}
    >
      <header className="msg__head">
        <span className="msg__who">{message.author_name}</span>
        {prominent && <span className="tag tag--contested">A way through</span>}
        <span className="msg__when">{when(message.created_at)}</span>
      </header>

      {showItem &&
        (message.item_id ? (
          <Link className="msg__about" to={`/items/${message.item_id}`}>
            About the {titleCase(message.item_category ?? 'item').toLowerCase()} →
          </Link>
        ) : (
          // Stated rather than left blank: item_id is nullable by design, and a
          // general post is a different kind of thing, not a missing link.
          <span className="msg__about msg__about--general">About the estate</span>
        ))}

      {/* Agent copy is written with paragraph breaks; keep them. */}
      {message.text.split('\n\n').map((para, i) => (
        <p className="msg__text" key={i}>
          {para}
        </p>
      ))}
    </article>
  )
}

export function MessageThread({
  messages,
  /** The mediation post on a contested item — lifted, not buried in the feed. */
  prominentId,
  showItems,
  empty = 'Nothing said about this one yet.',
}: {
  messages: Message[]
  prominentId?: string | null
  showItems?: boolean
  empty?: string
}) {
  if (messages.length === 0) {
    return <div className="empty">{empty}</div>
  }

  return (
    <div className="thread">
      {messages.map((message) => (
        <Entry
          key={message.id}
          message={message}
          prominent={message.id === prominentId}
          showItem={showItems}
        />
      ))}
    </div>
  )
}
