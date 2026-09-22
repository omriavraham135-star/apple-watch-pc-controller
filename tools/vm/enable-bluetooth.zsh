#!/bin/zsh
# Gives the macOS VM working Bluetooth, through a USB Bluetooth dongle passed
# into it from the host.
#
# Why: Xcode discovers an Apple Watch over Bluetooth as well as Wi-Fi. A VMware
# guest has no Bluetooth of its own, so without this Xcode never learns the
# watch exists, cannot register it to the signing team, and the watch app
# fails to install with "could not install at this time".
#
# macOS 12+ moved the Bluetooth stack into user space and refuses non-Apple
# controllers; Acidanthera's BlueToolFixup patches that. 2.7.2 is the first
# release with patches for macOS 26.
#
# Safe to run twice. Backs up the whole EFI folder first. Takes effect on the
# next restart.

set -euo pipefail

VERSION=2.7.2
SHA256=e1c1c55347526d031a8ae2fdd1f52efa3019161e497fb38e1cfa809752f8af21
OC=/Volumes/OPENCORE/EFI/OC
CONFIG=$OC/config.plist

[[ -f $CONFIG ]] || { echo "OpenCore is not mounted at /Volumes/OPENCORE — stopping."; exit 1; }
command -v python3 >/dev/null || { echo "python3 missing (it ships with Xcode) — stopping."; exit 1; }

backup=~/opencore-backup-$(date +%Y%m%d-%H%M%S)
cp -R /Volumes/OPENCORE/EFI "$backup"
echo "Backed up EFI to $backup"

work=$(mktemp -d)
curl -fsSL -o "$work/brcm.zip" \
  "https://github.com/acidanthera/BrcmPatchRAM/releases/download/$VERSION/BrcmPatchRAM-$VERSION-RELEASE.zip"
echo "$SHA256  $work/brcm.zip" | shasum -a 256 -c - >/dev/null \
  || { echo "Download checksum mismatch — stopping, nothing changed."; exit 1; }
unzip -q "$work/brcm.zip" -d "$work"

python3 - "$CONFIG" "$work/config.plist" <<'PY'
import plistlib, sys

src, dst = sys.argv[1], sys.argv[2]
with open(src, "rb") as f:
    p = plistlib.load(f)

kexts = p["Kernel"]["Add"]
if not any(k.get("BundlePath") == "BlueToolFixup.kext" for k in kexts):
    # Appended after Lilu, which it depends on.
    kexts.append({
        "Arch": "Any",
        "BundlePath": "BlueToolFixup.kext",
        "Comment": "Bluetooth for a USB dongle, so Xcode can find the watch",
        "Enabled": True,
        "ExecutablePath": "Contents/MacOS/BlueToolFixup",
        "MaxKernel": "",
        "MinKernel": "21.0.0",
        "PlistPath": "Contents/Info.plist",
    })

# BlueToolFixup requires these two on every macOS version since 2.7.0.
guid = "7C436110-AB2A-4BBB-A880-FE41995C9F82"
add = p["NVRAM"]["Add"].setdefault(guid, {})
add["bluetoothExternalDongleFailed"] = bytes(1)
add["bluetoothInternalControllerInfo"] = bytes(14)

delete = p["NVRAM"]["Delete"].setdefault(guid, [])
for key in ("bluetoothExternalDongleFailed", "bluetoothInternalControllerInfo"):
    if key not in delete:
        delete.append(key)

# Cheap CSR8510 dongles often share one hard-coded address, which bluetoothd
# rejects since macOS 12.4.
args = add.get("boot-args", "").split()
if "-btlfxallowanyaddr" not in args:
    args.append("-btlfxallowanyaddr")
add["boot-args"] = " ".join(args)

with open(dst, "wb") as f:
    plistlib.dump(p, f)
print("config.plist prepared")
PY

echo "Writing to the OpenCore volume (your Mac password may be asked):"
sudo rm -rf "$OC/Kexts/BlueToolFixup.kext"
sudo cp -R "$work/BlueToolFixup.kext" "$OC/Kexts/"
sudo cp "$work/config.plist" "$CONFIG"

python3 - "$CONFIG" <<'PY'
import plistlib, sys
p = plistlib.load(open(sys.argv[1], "rb"))
k = [x["BundlePath"] for x in p["Kernel"]["Add"]]
nv = p["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]
print("kexts:", ", ".join(k))
print("boot-args:", nv["boot-args"])
print("dongle vars:", "bluetoothExternalDongleFailed" in nv and "bluetoothInternalControllerInfo" in nv)
PY
ls -d "$OC/Kexts/BlueToolFixup.kext" >/dev/null && echo "DONE — restart the Mac."
