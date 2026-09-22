# Orb — vendored

Source copied from [metasidd/Orb](https://github.com/metasidd/Orb) at commit
`8c5dda85e55638893f37657b56558968c3e11409` (tag `0.2`), MIT licensed. The
licence is kept alongside, unmodified.

## Why it is vendored rather than a package dependency

The package declares `.watchOS(.v10)` support, but it does not compile for
watchOS. `ParticlesView.swift` is built on `UIGraphicsImageRenderer` and
SpriteKit's `SpriteView`, and neither exists on that platform:

```
ParticlesView.swift:115  cannot find 'UIGraphicsImageRenderer' in scope
ParticlesView.swift:150  'init(scene:transition:…)' is unavailable in watchOS
```

Only that one file is affected; the other five are clean. Rather than drop the
library, the five that compile are vendored and the particle layer is left out.

## What changed

- `ParticlesView.swift` is not included.
- `OrbView.swift` no longer renders the particle overlay. The `showParticles`
  flag remains on `OrbConfiguration` so the type still matches upstream, but it
  has no effect here.

Nothing else was touched. The gradients, the counter-rotating glows, the wavy
blobs, the inner rim and the layered shadow — everything that gives the orb its
depth — are upstream's, unaltered.

Particles were a subtle extra at this size, and SpriteKit would have cost
battery on a watch, so their absence is close to invisible.

## Re-syncing

Compare against upstream at the tag above before pulling anything in, and
re-check that no new file reaches for UIKit.
