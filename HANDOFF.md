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

### Apple ID — SOLVED. Do not undo any of this.
Xcode sign-in failed with "Verification Failed: An unknown error occurred" until
all three of these were in place. Each one alone was not enough.

1. **Mac identity** — `oc4vm/tools/windows/spoof.cmd macos.vmx` wrote an iMac19,2
   serial, board-id and MLB into the vmx. Before that the VM had no identity at
   all. (The script prints `'EM' is not recognized` errors — harmless; check the
   vmx, not the output.)
2. **Hide the hypervisor** — OC4VM's `cloak on`, run inside the guest:
   `sudo nvram 4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102:revpatch=sbvmm,asset,novmm`.
   Apple services refuse a machine that reports running under a VM. OpenCore's
   config leaves `revpatch` out of its NVRAM Delete list, so this persists.
3. **ROM = en0 MAC** — spoof generates a random ROM; Apple expects it to match the
   network interface. Set `efi.nvram.var.ROM = "%00%0C%29%2D%A7%F7"` to match
   `ethernet0.generatedAddress = "00:0c:29:2d:a7:f7"`.

**Do not move or copy the VM folder.** VMware regenerates the MAC when it thinks
a VM was copied; the ROM would then stop matching and sign-in would break again.

Backups of the vmx before each change: `macos.vmx.before-spoof`, `macos.vmx.before-rom`.

### Xcode
**Xcode 26.6 Universal**, not 27: Xcode 27 runs only on Apple silicon and the VM
is Intel. 26.6 needs macOS 26.2+ (the VM runs 26.7) and deploys to iOS 26.6,
which is what the iPhone runs. Do not update the iPhone or watch to 27 — Xcode 26
may refuse to install on them, and no Intel Mac can run Xcode 27.

The bundle identifier is `com.omriavraham.pcvolume`. A free Apple ID can only
sign identifiers no other developer has registered; the generic
`com.personal.pcvolume` risked a collision.

### Progress toward the device
- [x] Project cloned, generated with XcodeGen, open in Xcode inside the VM
- [x] Signing with the free Personal Team, both targets
- [x] **Built and installed on the physical iPhone** (Xcode: "Finished running
      PCVolumeApp on iPhone"). The iPhone app is only a carrier for the watch app.
- [ ] **Watch — BLOCKED on the free route.** The Watch app on the iPhone says
      "could not install at this time". With a free team, the watch must be
      registered by Xcode seeing it once, and Developer Mode on the watch only
      appears after that. Xcode never discovers the watch:
      `devicectl list devices` and `xctrace list devices` show only the iPhone,
      and the pairing daemon's log has no watch activity at all.

### What was tried for the watch (all done, none sufficient)
- VM network NAT → **Bridged** (Mac on the home LAN, same subnet as the watch).
  The MAC is unchanged, so the Apple ID fix still holds.
- **Bluetooth in the VM**: the host's spare CSR8510 USB dongle (Windows uses
  the Intel radio, so the CSR is otherwise idle) is passed in, and
  `tools/vm/enable-bluetooth.zsh` added BlueToolFixup 2.7.2 plus its NVRAM
  variables to OpenCore. macOS reports the controller as `State: On`.
  VMware does not auto-connect the dongle after a VM power cycle.
- Reset Location & Privacy on the iPhone and re-trusted, so the pairing that
  is supposed to discover the watch would run again with Bluetooth present.
- `tools/vm/watch-diagnose.zsh` reports each layer; it changes nothing.
- Untested suspects: the Mac is not signed into iCloud; the watch (SE, 2.4GHz)
  and the PC (5GHz) are on different bands of a mesh network.
- Apple acknowledges a watch-connection regression in Xcode 26.2+ that hits
  real Macs too (forum thread 813066). No report found of anyone deploying to a
  watch from a macOS VM.

### Recommended route: TestFlight (needs the paid program, $99/year)
The VM builds and uploads over the internet. No iPhone cable, no Xcode-to-watch
connection, no Developer Mode (Apple: TestFlight installs don't need it), and
builds last 90 days. Waiting on the user's decision. To do if yes: app icons for
both targets, `ITSAppUsesNonExemptEncryption = NO`, an App Store Connect record,
Archive → Distribute from the VM.

### USB passthrough is flaky, and why
The iPhone re-enumerates about 0.5 s after it is handed to the VM. If VMware
catches it again it stays for hours. About half the time the VMware USB
Arbitration Service connection breaks at that moment
(`USBArbLib: Received message size(1701667190) exceeds maxmium size(4096)`,
then `New set of 0 USB devices` for 15–55 s), and Windows takes the phone back.
Restarting the service did not help. The fix is to retry Connect until the menu
offers Disconnect.

### Host changes and backups from this session
- Wi-Fi band preference was changed for a test and **restored**
  (`RoamingPreferredBandType=0`, `WirelessMode=34`, as found).
- `D:\macos-vm\VM\opencore.iso.before-bt` — OpenCore before the Bluetooth
  change. Inside the guest, the EFI backup is at `~/opencore-backup-*`.

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

The VM has 8 vCPUs and 8 GB of RAM.

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
2. `macos-dl\` (18 GB) and `unlocker\` can be deleted.
3. The README's top block is a temporary VM helper; move it into docs when done.

---

## How this user works

Wants short, direct answers — pushes back on long explanations. Wants things
verified before being told to act, and said so explicitly after nearly being sent
into a multi-hour VM install with an unresolved unknown. Prefers being told what
was actually measured over what is assumed.
