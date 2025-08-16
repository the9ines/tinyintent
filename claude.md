# 🧠 TinyIntent v2 – Claude Agent Context

TinyIntent is a Mac-first, local-only AI platform for routing and executing personal assistant tasks—like managing crypto bots—using CoreML, Ollama, and sandboxed helpers.

---

## 🔒 Key Rules

- **No cloud inference.** All models run locally via Ollama.
- **Router must be ANE-accelerated.** SmallIntent.mlmodel runs via CoreML on macOS.
- **Helpers are sandboxed.** All `act` tasks must go through schema-validated helpers.
- **Critical actions require two-step approval.** (e.g., closing crypto positions)
- **Emergency flow is limited and fully audited.**
- **Claude does not run the system.** You are only used as a senior architect to help improve it when needed.

---

## 🧪 Core Make Targets

```bash
make router-train      # Train the SmallIntent model
make router-eval       # Evaluate the trained model (latency/accuracy)
make learn             # Mine episodes, retrain router, promote if valid
make doctor            # Show model/hardware readiness
make bridgesrv         # Start the Bridge API service
📂 Key File Structure
tinyintent/
├─ PRD.md                  ← Full product spec (Claude, read this first)
├─ README.md               ← Setup instructions for human devs
├─ claude.md               ← This file (Claude config)
├─ models.yaml             ← Ollama roles config (small/medium/large)
├─ Makefile                ← Entry point for build/test/train
├─ launchd/
│  └─ com.tinyintent.tinyrpc.sample.plist
├─ bridge/                 ← FastAPI bridge + routing server
│  ├─ tinyrpc.py
│  ├─ resolve.py
│  └─ logs/
├─ data/
│  ├─ episodes/            ← Logged requests + SQLite db
│  └─ datasets/            ← Training data for router
├─ helpers/
│  ├─ registry.yaml        ← List of allowed helpers
│  ├─ sdk.py               ← Launch/sandbox helpers
│  └─ <helper_id>/         ← Each helper with manifest
├─ router/
│  ├─ runner/              ← CLI runner for SmallIntent
│  ├─ SmallIntent.mlmodel  ← CoreML router model (macOS)
│  ├─ TinyIntent.mlmodel   ← Future iOS model
│  └─ data/                ← intents.tsv etc.
├─ scripts/
│  ├─ rotate_secret.sh
│  ├─ print_urls_and_secret.sh
│  └─ ...
└─ tests/
   ├─ health.sh
   ├─ auth.sh
   └─ routes.smoke.sh
🧠 What You’re Expected to Help With
Claude, you're used for:
Improving Python bridge routing logic
Drafting router training code (Swift + CreateML)
Improving helper manifest schemas
Refactoring APIs and CLI ergonomics
Reviewing intent training data structure
Making robust automation scripts (Makefile, shell)
You do not handle UI, iOS, or devops tasks unless asked.
🗂️ Always start with
Read PRD.md before taking any action.