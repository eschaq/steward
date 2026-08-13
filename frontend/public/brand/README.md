# Brand imagery

Drop the Ideogram renders here. Vite serves `public/` at the site root, so a file
at `public/brand/hero-gable-portrait.jpg` is referenced in code as
`/brand/hero-gable-portrait.jpg`.

Expected files:

| File                          | Aspect | Used by                                  |
| ----------------------------- | ------ | ---------------------------------------- |
| `hero-gable-portrait.jpg`     | 9:16   | sign-in on phone / narrow viewports      |
| `hero-gable-landscape.jpg`    | 16:9   | sign-in on desktop / wide viewports      |

Both are rendered through a CSS duotone (grayscale base + clay-to-ink colour
layer), so the source file's own colour barely survives — what matters is tonal
separation, texture, and where the light falls. See frontend/README.md.

Keep each under ~300 KB; they load before anyone can sign in.
