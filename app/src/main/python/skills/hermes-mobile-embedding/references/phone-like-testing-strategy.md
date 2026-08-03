# Phone-like testing strategy (PC / GitHub / VM) — decision matrix

Session-tested (2026-08) mapping of "where do I test the app like it's on a
phone?" when the user has no Android Studio, no local emulator disk space
(1.5 GB too big for their PC), and keeps asking "PC pe to chalta hai, phone
pe chalega?".

## Three test tiers — use in this order

### Tier 1 — PC-local engine test (fastest, do FIRST)

`hermes_agent.py` + `hermes_gateway.py` are **pure Python**. The exact code
Chaquopy runs on-device runs on the PC. Smoke-test everything before any APK:

```bash
# gateway smoke test (REST + WS JSON-RPC + live LLM reply)
pip install websockets
python app/src/main/python/hermes_gateway.py   # background
curl http://127.0.0.1:9119/api/status          # {"status":"ok",...}
# then run scripts/test_gateway_ws.py — session.create → prompt.submit →
# message.start/delta/complete/done + real model reply
```

- Engine module test: `get_status()`, all 8 tools (`web_search`, `web_fetch`,
  `read/write/list_files`, `get_time`, `memory_get/set`), `process_chat()`.
- Proves: engine logic, gateway protocol, LLM connectivity, tool behavior —
  ~90% of what could break, with zero APK/phone cycle.
- User-facing demo: print the "Page 1 engine status" values live (Python ✅,
  Tools ✅, Model ✅) — instant hands-on proof.

### Tier 2 — GitHub Actions instrumented tests (the free "phone")

The `Instrumented Tests` job boots a real Android emulator (API 34 ATD) on
GitHub's runner, installs the APK, launches the app. This IS a phone-like run
and it's free — no local SDK, no disk space. Current state: PASS on latest
builds. It does NOT prove the Python engine chats on-device (Compose UI tests
only) — for that, either extend the instrumented tests or fall to Tier 3.

### Tier 3 — real device / local emulator (final proof)

Only needed when the UI layer specifically must be verified live.

## GCP N1 test-lab VM — CREATED and KVM confirmed (2026-08)

The N1 instance was actually created this session and **KVM works**:

```text
$ ssh hermes-test-lab 'ls -la /dev/kvm'   → crw-rw---- 1 root kvm ...  ✅
$ free -h                                  → 7.3 Gi total (6.8 free)
```

Working creation command (user's project, us-east1-b, no min-cpu-platform):

```bash
gcloud.cmd compute instances create hermes-test-lab \
  --project=project-78ba515a-5113-4559-b4e --zone=us-east1-b \
  --machine-type=n1-standard-2 \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB --boot-disk-type=pd-balanced \
  --enable-nested-virtualization
```

**Windows gcloud.cmd pitfalls (username has a space: "Mohd yousuf"):**
- Use `gcloud.cmd` (not the `gcloud` shell script) — the shim fails with
  `python.exe: can't open file ...gcloud.py` under git-bash.
- **Drop `--min-cpu-platform` entirely.** Multi-word values like
  `--min-cpu-platform="Intel Haswell"` break the .cmd wrapper on this machine
  (`'C:\Users\Mohd' is not recognized as an internal or external command`).
  Nested virtualization works WITHOUT it — GCP picks a compatible CPU.
- Git-bash `cmd //c script.cmd` invocation opens an interactive shell instead
  of running the script; run the gcloud.cmd binary directly from bash instead.
- After creation: SSH "Connection refused" for ~30–60 s while the VM boots —
  retry after 30 s, it comes up.
- 50 GB boot disk > 10 GB image triggers a "resize repartition manually"
  warning — harmless for an emulator test box (SDK + system image fit in the
  first 10 GB; resize later if needed).

## GCP VM CANNOT run an Android emulator (verified)

User's idea: "VM pe instance banao, wahi testing karo, GitHub ka kya kaam
fir?" — legitimate instinct, but the existing VM is the wrong shape:

```text
$ ssh vm 'ls /dev/kvm'                 → No such file or directory
$ ssh vm 'grep -oE "(vmx|svm)" /proc/cpuinfo' → (empty)
$ free -h                               → 1.9 Gi total (emulator wants 4+)
```

- e2-small (and all e2 family) has **no nested virtualization** → `/dev/kvm`
  absent → Android emulator won't boot (software emulation is unusably slow).
- To get KVM on GCP you need an **N1/N2 machine type created with
  `--enable-nested-virtualization`** (and enough RAM: n1-standard-2 = 7.5 GB).
  That's a NEW instance, not a tweak to the existing e2-small. **This was done —
  `hermes-test-lab` (n1-standard-2) now exists with KVM confirmed** (see the
  creation section above; it was booted, SDK install was in progress).
- The user has $300 GCP credits → a ~$70/mo n1-standard-2 test-lab VM is
  affordable for a few months if a dedicated emulator host is ever wanted.
  **Note: the user said the GCP trial VM expires ~day-19-of-the-month, so a
  new N1 test VM dies with the same trial — use it for the remaining window,
  don't over-invest.**
- Bottom line to tell the user: emulator testing belongs on GitHub Actions
  (free) or a dedicated KVM-enabled VM (now `hermes-test-lab`); the existing
  e2-small stays for services (LocalBridge/gateway/Telegram) and Python-engine
  tests only.

## GitHub vs VM — roles to explain to the user (new to infra)

When the user asks "GITHUB KA KYA KAAM HOTA FIR" (what's GitHub for, then?):

- **GitHub = code store + factory**: repo holds history; every push triggers
  CI that builds the APK, runs lint/ktlint/unit tests, and boots the free
  emulator. Release tab hosts downloadable APKs.
- **VM = always-on services + private test bed**: 24×7 engine/gateway/Telegram
  services, build/debug scratch space, cron. It is NOT where the app's
  phone-like UI test runs (no KVM).
- Both stay useful; they don't replace each other.

## User-facing verification habits (this user)

- "DOWNLOAD MAT ANDAR DEKH KUCH MASLA TO NAI" — verify downloaded APKs
  (zip validity, dex classes, permissions, bundled Python `.imy`) BEFORE
  telling the user they're ready.
- "PC PE TO SAB CHAL JATA HE BUT PHONE ME NAI CHALTA" — answer with APK zip
  proof (`libpython3.11.so`, `assets/chaquopy/*.imy`, APK size ~33→71 MB),
  not assertion.
- "ESA KUCH TOOL NAI HE KI APAN YAHI PER TEST KARE" — Tier 1 (PC-local)
  IS that tool; run it live in front of the user.
