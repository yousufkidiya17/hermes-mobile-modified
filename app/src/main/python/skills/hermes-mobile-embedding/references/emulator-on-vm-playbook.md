# Android emulator on the GCP N1 test-lab VM — end-to-end playbook
Session-tested (2026-08): fully booted a headless emulator and ran the APK on
`hermes-test-lab` (n1-standard-2, `--enable-nested-virtualization`, us-east1-b).
This is Tier 3 (real phone-like run) — the ONLY way to prove "does the app +
on-device Python engine actually work" without a physical phone or local SDK.

## 1. OS prerequisites (once, on the fresh Ubuntu 22.04 VM)

```bash
sudo apt-get update -y
sudo apt-get install -y openjdk-17-jdk unzip wget   # Java 17 (emulator needs a JRE)
```

## 2. Android SDK + cmdline-tools

```bash
mkdir -p ~/android-sdk/cmdline-tools
wget -q https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -O /tmp/ct.zip
unzip -q /tmp/ct.zip -d ~/android-sdk/cmdline-tools
mv ~/android-sdk/cmdline-tools/cmdline-tools ~/android-sdk/cmdline-tools/latest
export ANDROID_HOME=~/android-sdk
yes | ~/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses > /tmp/licenses.log 2>&1
# big download (~2 GB): platform-tools + emulator + x86_64 system image
~/android-sdk/cmdline-tools/latest/bin/sdkmanager \
  "platform-tools" "emulator" "system-images;android-34;google_apis;x86_64"
```

## 3. Create the AVD

```bash
echo no | ~/android-sdk/cmdline-tools/latest/bin/avdmanager create avd \
  -n testavd -k "system-images;android-34;google_apis;x86_64" -d pixel_6
# run it from the VM in background with nohup so it survives the SSH session:
export ANDROID_HOME=~/android-sdk; export PATH=$PATH:~/android-sdk/platform-tools
nohup ~/android-sdk/emulator/emulator -avd testavd \
  -no-window -no-audio -no-boot-anim -gpu swiftshader_indirect -no-snapshot -accel auto \
  > /tmp/emulator.log 2>&1 &
```
- `-no-window -no-audio -no-boot-anim -gpu swiftshader_indirect` = headless (no GUI on VM).
- `-no-snapshot` avoids stale-state boot failures that bite CI (see instrumented-tests pitfall).
- Boot takes 3–5 min. Check: `adb shell getprop sys.boot_completed` → `1` when done.

## 4. KVM gotcha — /dev/kvm exists but emulator still refuses

First attempt fails even though `/dev/kvm` is present:
```
ERROR | x86_64 emulation currently requires hardware acceleration!
This user doesn't have permissions to use KVM (/dev/kvm).
```
The unprivileged user isn't in the `kvm` group. Perfect fix for a disposable test VM:
```bash
sudo usermod -aG kvm $USER
sudo chmod 666 /dev/kvm          # quick path; a long-lived box should rely on the group
ls -la /dev/kvm                 # → crw-rw-rw- root kvm
```
**You must open a NEW SSH session after `usermod`** for the group to take effect. Re-launch
the emulator and now `adb devices` shows `emulator-5554 device` — that's the phone-like device.

## 5. Install + open the APK

Copy the built APK to the VM, then:
```bash
adb install /tmp/app-debug.apk                       # expect "Success"
adb shell am start -n com.m57.hermescontrol/.MainActivity
sleep 10
adb shell "dumpsys activity activities | grep -i hermes | head"   # confirm topResumedActivity
```
- **scp pitfall:** a 71 MB APK over a slow link can truncate; the first attempt produced a
  47 MB file and `adb install` failed with `INSTALL_PARSE_FAILED_NOT_APK`. Always
  `ls -lh` the transferred file and confirm it matches the local size before installing.
- App debug = 71 MB (Chaquopy Python bundle) vs the ~33 MB pre-Chaquopy build.

## 6. Read the screen WITHOUT a vision model (KEY technique)

The free/aux vision model in this setup can't see local screenshots (image inputs not
supported / "unknown variant image_url"). Do NOT block on `browser_vision`/`vision_analyze`.
Instead read the composable tree — it's the ground truth for what's on screen:
```bash
adb shell uiautomator dump /sdcard/ui.xml
adb shell cat /sdcard/ui.xml | grep -oE 'text="[^"]*"' | grep -vE 'text=""'
# and get a tap target's exact bounds:
adb shell cat /sdcard/ui.xml | grep -oE '<node[^>]*text="Auth Login"[^>]*bounds="[^"]*"'
# tap center of a bounds box [x1,y1][x2,y2]:
adb shell "input tap ((x1+x2)/2) ((y1+y2)/2)"
```
- Screenshots still useful to deliver: `adb exec-out screencap -p > file.png`, pull to PC,
  attach as MEDIA: so the USER sees it (even if the model can't).
- `text` fetching concatenates (typed chars append to the existing value); to replace a field:
  `input keyevent --longpress KEYCODE_A` (select all) then `KEYCODE_DEL`, then `input text "..."`.

## 7. Confirming the gateway is actually listening on-device

The emulator is Linux under the hood — you can inspect sockets from adb:
```bash
adb shell "ss -tlnp" | grep 9119
# LISTEN  127.0.0.1:9119   (uid 10192)  == the app's uid → on-device gateway is UP
```
Proof that Python's `hermes_gateway.py` bound 9119 inside the Android sandbox. Combined with
`adb logcat -d | grep EngineManager` → `"Gateway started on port 9119"` / `"Engine ready"`,
this is the whole on-device chain confirmed without a real phone.

**Reading the `Engine ready: Python null, 1 tools` line (diagnostic):** this log
(`status.get("tools").toString()` / `status.get("python")`) can print `Python null`
and `1 tools` on-device even when the engine is healthy — it's an artifact of how the
Kotlin side formats the Chaquopy `PyObject` (a `java.util.List` prints as `[web_search, ...]`,
and feeding that through `trim('[',']')` + `split(", ")` can miscount). The REAL on-device
health check is: (1) `adb shell "ss -tlnp" | grep 9119` shows LISTEN with the app uid, and
(2) driving the gateway from the host (section 10) returns a live `message.complete` reply.
Trust those over the pretty-printed count. If only ONE tool shows while the PC run shows 8,
and chat still replies, it's a formatting artifact, not missing tools.

## 8. Emulator "System UI isn't responding" ANR dialog (slow 2-CPU box)

On n1-standard-2 (2 vCPU) the launcher/systemUI can ANR during boot. `uiautomator dump` then
shows three texts: `System UI isn't responding` / `Close app` / `Wait`. Tap **Wait** at its
bounds center (`[70,1300][1010,1426]` → `input tap 540 1363`) — NOT the ANR's "Close". Landing
screen then appears with the real app. This is an environment slowness, not an app bug.

## 9. Drive the CHAT screen: tap the Send button, don't rely on Enter

When testing the Chat UI headlessly, typing the message then pressing Enter
(`input keyevent 66`) fills the field but **does NOT send it** — the text stays
in the input. To actually dispatch a message you must tap the Send button:
```bash
# find the Send button (it's a View with content-desc="Send", not an EditText)
adb shell cat /sdcard/ui.xml | grep -oE '<node[^>]*content-desc="Send"[^>]*bounds="[^"]*"'
# [949,1266][1012,1329] → tap its center
adb shell "input tap 980 1297"
```
Sequence that worked end-to-end (user msg "hello2" → assistant "Hi there! 👋"):
```bash
adb shell "input tap 540 2143"          # focus message field
sleep 2
adb shell "input text hello2"           # type (lowercase — no spaces via this method)
sleep 1
adb shell "input tap 980 1297"          # tap Send (NOT keyevent 66)
sleep 12                                # model call over network takes ~10s
adb shell "uiautomator dump /sdcard/ui.xml" | grep -oE 'text="[^"]*"'
```
Check logcat for the WS health line to distinguish \"connected but idle\" from a real
failure. `HermesWsClient: WebSocket opened` = connected; a *repeated*
`WebSocket connection appears unhealthy (no frames received for > 60s)` with `ss -tlnp`
showing 9119 LISTEN means the gateway is up but the prompt was never actually submitted
(usually the Enter-vs-Send issue above), not a gateway crash.

## 10. Test the ON-DEVICE gateway from the host (no emulator GUI needed)

Even though the gateway binds `127.0.0.1:9119` inside the emulator, you can drive it from
the PC to prove the full WS JSON-RPC chain (session.create → prompt.submit → reply) against
the exact process the app uses:

```bash
# (a) emulator → VM loopback: expose emulator's :9119 as VM's :19119
adb forward tcp:19119 tcp:9119
adb forward --list          # emulator-5554 tcp:19119 tcp:9119
# (b) VM → PC: SSH local forward PC:19121 → VM:127.0.0.1:19119
ssh -N -L 19121:127.0.0.1:19119 user@VM
# (c) from the PC, connect websockets to ws://127.0.0.1:19121/api/ws?token=hermes-mobile-token
#     expect gateway.ready → session.create → prompt.submit("Reply OK") → message.complete "OK"
```
- `adb reverse tcp:9119 tcp:9119` often fails with `cannot bind listener: Address already
  in use` on this VM; prefer `adb forward` (host→guest direction) + SSH `-L` instead.
- **websockets library version trap on the VM host:** Ubuntu's `python3-websockets` is the
  old 10.x legacy API and crashes on Python 3.10 with
  `TypeError: As of 3.10, the *loop* parameter was removed from Lock()`.
  Don't fight it on the VM — run the ws client from the PC (which has `websockets>=12`)
  through the SSH `-L` tunnel in step (b).
- If `adb reverse` is needed, remote all first: `adb reverse --remove-all`.

## Also useful afterwards
- Kill/relaunch emulator: `pkill -f "emulator -avd"` then re-nohup (a plain re-launch while the
  old one lingers gives "no emulators found").
- Logcat for engine init: `adb logcat -d | grep -iE "EngineManager|Gateway|Python"`.

The emulator runs watchably slow on 2 vCPU — expect 1–2 min app starts and occasional
launcher ANRs, but it is fully usable for UI-level integration verification.