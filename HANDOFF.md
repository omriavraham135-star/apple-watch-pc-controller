# Handoff — where this project stands

Written 2026-09-22. Read this first; it is the current state, not history.

---

## What the project is

Control a Windows PC from an Apple Watch. Hebrew voice commands for volume,
plus power, machine vitals and user-defined shortcuts.

**Repo:** `github.com/omriavraham135-star/apple-watch-pc-controller`
Local: `D:\project\apple-watch-pc-controller`, branch `main`, remote name `star`.

> The older repo under `omrigalavraham` is abandoned — that account is locked by
> a GitHub billing issue that blocks all Actions runs. Pushing to `origin` now
> fails with 403. Use `git push star main`.

---

## Current state — what works

| Part | State |
|---|---|
| Python server | Done. 86 tests pass. |
| Browser dashboard | Done. 49 browser tests pass. |
| watchOS app | **Compiles and runs.** Verified by screenshots from a simulator in CI. |
| CI | Green. Builds on macos-15, then boots a watch simulator and captures all four pages. |

### The four pages
Voice (particle orb + volume + Digital Crown), Power (lock/sleep/restart/shutdown),
Stats (CPU/memory/disk rings), Actions (shortcuts that light up when their app is open).

### Verified visually
`docs/screenshots/` holds captures from the watch simulator. The layout was
measured and fixed — power tiles were running off the bottom of a 41mm screen.

---

## Where we are right now — the only thing in progress

Getting the app onto a physical watch. That needs macOS, and the user has no
Mac, so a macOS VM is being built on their Windows machine.

### Done
- VMware Workstation Pro **25H2** installed at `D:\VMware\`
- Hyper-V and VBS disabled and verified off (`HypervisorPresent: False`, `VBS: 0`)
- macOS **Tahoe** installed in the VM at `D:\macos-vm\VM\macos.vmx`
- Windows Defender exclusion added for the VM folder

### Blocked on, right now
**Apple ID will not sign in inside the VM.** Apple rejects App Store sign-in from
virtual machines that lack a valid hardware serial. The user had just reported
this and had not yet said what the error message was.

**The planned workaround, not yet tried:**
1. Skip sign-in during macOS setup ("Set Up Later")
2. Download Xcode directly from `developer.apple.com` rather than the App Store —
   a web login works where App Store sign-in does not
3. Add the Apple ID inside Xcode (Settings → Accounts) for signing — a different
   auth path that usually succeeds in a VM

If that fails, the next lever is generating valid SMBIOS data with OpenCore's
GenSMBIOS so the VM presents a plausible serial.

### Remaining after that
1. Install Xcode in the VM
2. Pass the iPhone through to the VM over USB (VM → Removable Devices)
3. Open `watch_pc_controller/`, run `xcodegen generate`, open the project, press Run
4. The watch app installs via the iPhone, which must be paired to the watch

**A free Apple ID signs for 7 days.** Re-running Run in the VM each week is the
ongoing cost; this is why the VM was chosen over borrowing a Mac.

---

## The VM, assembled

`D:\macos-vm\`

```
VM\                    the working VM — macos.vmx, disks, OpenCore
oc4vm\                 OC4VM 3.0.1, AMD template (source of VM\)
recoveryos\            recoveryOS 1.0.3 + the Tahoe recovery VMDK
qemu\qemu-img.exe      used to convert the recovery image
macos-dl\              18GB InstallAssistant.pkg — NOT USED, can be deleted
unlocker\              NOT USED, OC4VM replaces it
```

Two things were downloaded before the right method was found, and are dead
weight: the 18GB `InstallAssistant.pkg` and the VMware Unlocker. Converting that
pkg into bootable media needs macOS, which was the whole problem; OC4VM plus an
Apple recovery image sidesteps it entirely.

### Why this combination
OC4VM ships an AMD template whose `.vmx` already carries the CPUID masks that
AMD needs — no hand-editing. The machine was checked against its requirements
before starting: AVX, AVX2, F16C and RDRAND are all present on the Ryzen 5800X.

---

## The machine

```
CPU     AMD Ryzen 7 5800X, 8 cores / 16 threads
RAM     16 GB   (VM has 8 GB; only ~1 GB was free during install)
Disks   both SSD; project on D:
Watch   watchOS 26  → needs a current Xcode, which is why Tahoe was chosen
```

The VM has 4 vCPUs. Raising it to 8 was suggested and not yet done — it needs
the VM powered off (VM → Settings → Processors).

---

## How to verify anything

```bash
# server
py -m pytest tests/ -q

# browser tests need the server running first
py -m uvicorn watch_pc_controller.server:app --host 0.0.0.0 --port 8000
node --test tests/browser/test_dashboard_nav.mjs
node --test tests/browser/test_hold_guard.mjs

# the watch app — CI only; there is no Swift toolchain on Windows
git push star main    # then watch the run
gh run list --repo omriavraham135-star/apple-watch-pc-controller
```

The browser tests drive a real Chrome over CDP with no npm dependency
(`tests/browser/cdp.mjs`). They read pixels back from the orb canvas and measure
the hold guard's geometry, because "loaded without errors" proves nothing about
whether something looks right.

`tests/mock_server.py` stands in for the PC on macOS CI, where pycaw cannot run.

---

## Things that will bite you

**The watch app cannot be compiled locally.** No Swift toolchain on Windows. CI
is the only compiler. Four separate failures were found this way, three of them
undiscoverable without a Mac.

**The Orb library is vendored, not a package.** `metasidd/Orb` declares watchOS
support but does not compile there — its particle layer uses UIKit and SpriteKit.
Five of its six files are copied into `apple_watch_app/Orb/` with the particle
layer removed. See `apple_watch_app/Orb/README.md`.

**The dashboard's scroll axis is forced LTR.** The page is RTL, and an RTL scroll
container reports `scrollLeft` as 0 → −N, which silently clamped every page
change. Do not "fix" the `direction: ltr` on `.pages`.

**Hebrew prepositions attach to the following word.** The parser handles fused
forms (`בחמישים`, `לשמונים`) and matches verbs as whole words — `שים` hides
inside `חמישים`. There are tests for both; do not loosen them.

**The demo watch must never send anything.** The dashboard shows two watches; the
right one runs the whole interface including the shutdown guard and sends no
requests. A test spies on `fetch` to prove it.

---

## Known open items

1. **The server has no authentication.** It binds `0.0.0.0`. Anyone on the home
   network can change the volume or shut the machine down. Raised several times,
   never addressed. Actions are at least run by id only — a command string from
   the network is never executed.
2. VM vCPU count could go from 4 to 8.
3. `macos-dl\` (18 GB) and `unlocker\` can be deleted.

---

## How this user works

Wants short, direct answers — pushes back on long explanations. Wants things
verified before being told to act, and said so explicitly after nearly being sent
into a multi-hour VM install with an unresolved unknown. Prefers being told what
was actually measured over what is assumed.
