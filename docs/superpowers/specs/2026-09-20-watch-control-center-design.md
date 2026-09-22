# Watch Control Center — Design

**Date:** 2026-09-20
**Status:** Approved, in implementation

## Goal

Grow the app from a single-purpose volume remote into a four-page control
centre for the PC, and rebuild the visual language so it reads as a native
Apple Watch app rather than a web page in a watch frame.

## Structure

Four full-screen pages, navigated by horizontal swipe. Each page owns one
concern and stays uncluttered. This mirrors the `TabView(.page)` pattern
Apple uses for Now Playing and Workout.

| Page | Contents |
|---|---|
| 1. Voice | The Orb (tap to dictate), volume slider, Digital Crown controls volume |
| 2. Power | Lock, Sleep, Restart, Shutdown |
| 3. Stats | CPU, memory, disk — live rings |
| 4. Actions | User-defined buttons loaded from `actions.json` |

## The Orb

The current Orb is a circle with a static gradient. The replacement is built
from four layers:

1. Two translucent gradient layers counter-rotating at different speeds,
   producing organic fluid motion rather than a spinning disc.
2. A specular highlight that drifts across the surface.
3. A blurred aura that breathes on its own cycle.
4. A rim light that picks up the state colour.

State is expressed through **motion as well as colour**:

| State | Colour | Motion |
|---|---|---|
| idle | deep blue / indigo | slow breathing, ~4s cycle |
| listening | cyan | pulses with audio level |
| thinking | violet | accelerated rotation |
| success | green | single bloom, then settles to idle |
| error | red/orange | short shake, then settles to idle |

## Server

Three new modules beside the existing `volume_controller.py`, each with one
responsibility:

- `power_controller.py` — lock, sleep, restart, shutdown
- `system_stats.py` — CPU, memory, disk percentages via `psutil`
- `actions.py` — loads `actions.json`, runs entries **by id**

New endpoints:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/power` | `{action: lock\|sleep\|restart\|shutdown}` |
| `GET` | `/api/stats` | CPU / memory / disk percentages |
| `GET` | `/api/actions` | List available actions (id + label + icon) |
| `POST` | `/api/actions/{id}` | Run one action by id |

The existing volume endpoints are unchanged.

### CPU temperature is out of scope

Windows does not expose CPU temperature without administrator rights and
additional software; `psutil.sensors_temperatures()` is unavailable on this
platform and the WMI thermal zone returns access denied. Disk usage takes the
third slot instead.

## Security

Two properties matter, because this server binds `0.0.0.0` and now reaches
beyond volume:

1. **Actions run by id only.** The client sends an id that must already exist
   in `actions.json`. A command string received from the network is never
   executed. This keeps the actions page from becoming a remote shell.
2. **Destructive power actions require a deliberate gesture.** Restart and
   shutdown need a 1.5 second press-and-hold in the UI. Lock and sleep are a
   single tap, being harmless and reversible.

Authentication is deliberately **not** part of this change. The server remains
LAN-only and unauthenticated, exactly as it is today. If the server is ever
exposed beyond the LAN, a token becomes mandatory before that happens — this is
recorded as a follow-up, not silently assumed.

## Delivery order

1. Server modules and endpoints, with tests. Verifiable immediately over HTTP.
2. Browser dashboard rebuilt as a faithful four-page watch simulator. This is
   the surface where the design is reviewed and approved.
3. SwiftUI port of the approved design, ready for the first Mac that becomes
   available.

## Testing

- `actions.py` — the whitelist logic is security-relevant and gets unit tests
  covering unknown ids, malformed config, and a missing config file.
- `system_stats.py` — shape and bounds of the returned values.
- `power_controller.py` — the command mapping is tested without executing it;
  execution is behind a boundary the tests substitute.
- `nlp_parser.py` — currently untested. Existing behaviour gets characterisation
  tests before anything nearby changes.

## Known defects fixed along the way

These were found while reading the existing code and would block the app once
it reaches a watch:

- `project.yml` embeds the watch app in `Watch/`; Xcode 26 requires `PlugIns/`,
  and installation fails otherwise.
- The watch target has no `NSAllowsLocalNetworking`, so watchOS blocks the
  cleartext LAN request the app depends on.
- `ContentView.swift` sends a volume POST on every `volumeValue` change while
  also assigning `volumeValue` from the server response, forming an echo loop;
  the slider additionally posts on its own.
- `ContentView.swift` reaches the dictation UI through
  `WKExtension.shared().visibleInterfaceController`, deprecated and liable to
  return nil in a pure SwiftUI app on watchOS 10.
