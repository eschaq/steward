import { Composition } from 'remotion'

import { Closing, Opening, Positioning, Problem, Stack } from './Cards'
import { LOWER_THIRDS, LowerThird } from './LowerThird'
import './index.css'

const FPS = 30
const W = 1920
const H = 1080

/**
 * One composition per card, so each renders to its own file and drops into the
 * DaVinci timeline independently — the demo's live footage is the spine, and
 * these are placed against it rather than pre-assembled into a cut.
 *
 * Durations are generous. A viewer should finish reading and then have a beat
 * before the cut, which is the pacing the brand asks for; the editor can always
 * trim, and cannot invent frames that were never rendered.
 */
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="opening" component={Opening} durationInFrames={5 * FPS} fps={FPS} width={W} height={H} />
      <Composition id="problem" component={Problem} durationInFrames={5 * FPS} fps={FPS} width={W} height={H} />
      <Composition id="positioning" component={Positioning} durationInFrames={7 * FPS} fps={FPS} width={W} height={H} />
      <Composition id="stack" component={Stack} durationInFrames={5 * FPS} fps={FPS} width={W} height={H} />
      <Composition id="closing" component={Closing} durationInFrames={7 * FPS} fps={FPS} width={W} height={H} />

      {LOWER_THIRDS.map(({ id, text }) => (
        <Composition
          key={id}
          id={id}
          component={LowerThird}
          durationInFrames={5 * FPS}
          fps={FPS}
          width={W}
          height={H}
          defaultProps={{ text }}
        />
      ))}
    </>
  )
}
