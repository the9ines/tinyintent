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
/Users/oberfelder/projects/tinyintent/
/Users/oberfelder/projects/tinyintent/
    1 /Users/oberfelder/projects/tinyintent/
    2 ├── PRD.md
    3 ├── README.md
    4 ├── claude.md
    5 ├── pyproject.toml
    6 ├── Makefile
    7 ├── models.yaml
    8 ├── launchd/
    9 │   └── com.tinyintent.tinyrpc.sample.plist
   10 ├── bridge/
   11 │   ├── tinyrpc.py
   12 │   ├── api_routes.py
   13 │   ├── security.py
   14 │   ├── gen_client.py
   15 │   ├── router_client.py
   16 │   ├── errors.py
   17 │   ├── resolve.py
   18 │   └── logs/
   19 │       ├── audit.py
   20 │       ├── sanitize.py
   21 │       └── util.py
   22 ├── data/
   23 │   ├── episodes/
   24 │   │   ├── __init__.py
   25 │   │   ├── logger.py
   26 │   │   ├── flush.py
   27 │   │   └── schema.py
   28 │   └── datasets/
   29 ├── helpers/
   30 │   ├── sdk.py
   31 │   ├── manifest.py
   32 │   ├── registry.py
   33 │   ├── sandbox.py
   34 │   ├── executor.py
   35 │   ├── registry.yaml
   36 │   ├── bot_guard/
   37 │   │   ├── helper.yaml
   38 │   │   ├── input.schema.json
   39 │   │   ├── output.schema.json
   40 │   │   └── main.js
   41 │   └── log_tailer/
   42 │       ├── helper.yaml
   43 │       ├── input.schema.json
   44 │       ├── output.schema.json
   45 │       └── main.js
   46 ├── router/
   47 │   ├── train_router.swift
   48 │   ├── eval_router.swift
   49 │   ├── SmallIntent.mlmodel
   50 │   ├── TinyIntent.mlmodel
   51 │   ├── runner/
   52 │   │   └── run_router.swift
   53 │   └── data/
   54 │       ├── intents.tsv
   55 │       └── intents_test.tsv
   56 ├── scripts/
   57 │   ├── rotate_secret.sh
   58 │   ├── print_urls_and_secret.sh
   59 │   ├── export_episodes.py
   60 │   ├── promote_model.py
   61 │   ├── autopilot.py
   62 │   └── ...
   63 ├── tests/
   64 │   ├── bridge/
   65 │   ├── helpers/
   66 │   ├── router/
   67 │   ├── integration/
   68 │   ├── health.sh
   69 │   ├── auth.sh
   70 │   ├── routes.smoke.sh
   71 │   ├── router_smoke.sh
   72 │   └── helpers_smoke.sh



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