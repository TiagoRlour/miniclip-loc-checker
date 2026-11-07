# Localisation Release Checker (`loc_check.py`)

## Overview & Problem Framing
A releaser on Monday morning with 15 minutes doesn't need a raw line-by-line diff; they need a fast, high-signal **Ship / No-Ship** recommendation. 

I built a zero-dependency Python CLI tool that compares the live baseline `.plist` against a candidate release and categorizes findings into three actionable buckets:
- 🔴 **Blockers:** Issues that will crash the client, break dynamic tag parsing, or show missing text/keys in production.
- 🟡 **Warnings:** Suspicious changes (unupdated version metadata, discrepancies in game-rule numbers, or UI layout/overflow risks) that require a quick human check.
- 🟢 **Info / Fixes:** Safe additions or regressions from the previous version that were repaired in the candidate release.

## How to Run the Tool
Requires Python 3 (standard library only, zero external dependencies):

```bash
# 1. Default run (evaluates localisations_1_2_0.plist -> localisations_1_2_1.plist)
python loc_check.py

# 2. Edge-case & defensive test (missing en-US baseline, 5.0x text expansion, dropped keys)
python loc_check.py localisations_1_2_0.plist test_edge_cases.plist

# 3. Clean release test (verifies SAFE TO SHIP verdict when bugs are fixed)
python loc_check.py localisations_1_2_0.plist test_clean_release.plist
```

## Smallest Complete Version & Iterative Additions
- **Smallest Complete Version (Steps 1 & 2):** Parsed both `.plist` files using Python's built-in `plistlib` and checked for structural regressions using set operations: version metadata check, deleted UUID keys, dropped languages (e.g., Spanish disappearing), and empty strings (`""`).
- **Step 3 — Format Specifiers & Fix Detection:** Validated `printf`-style specifiers (`%[0-9]*[@udfs]`) and dangling `%` signs against `en-US`. By comparing both `1.2.0` and `1.2.1` against the `en-US` contract, the tool detects when a previously broken translation (like `fr` having `% ...` in `1.2.0`) is repaired in `1.2.1`, reporting it as a `[FIXED BUG]` rather than a risky change.
- **Step 4 — Custom Bracket Tag Validation (`X:[opt1/opt2]`):** Checks balanced square brackets (`[` vs `]`) and maps each tag identifier to its slash-separated option count (`{'A': 2, 'B': 3}`). Stored as an unordered dictionary so valid grammatical reordering in German (`de`) and Turkish (`tk`) does not trigger false alarms.
- **Step 5 — Game Economy Numbers & Layout Heuristics:** Extracts and normalizes numbers (handling European decimal commas `0,5` -> `0.5` and trailing zeros `4,0` -> `4.0`), catching `pt-BR` changing a `30`s penalty to `3`s and `jp` duplicating `4` instead of `1.0`. Also checks line-break counts (`\n`) and extreme character length expansion (>2.5x `en-US`).

## Key Assumptions
- **`en-US` is the source of truth:** Within any key, `en-US` defines the expected contract for format specifiers, dynamic bracket tags, game-rule numbers, and base line breaks.
- **Backwards compatibility of keys/languages:** Dropping an existing key or language between minor releases (`1.2.0` -> `1.2.1`) is assumed to be an accidental regression unless explicitly deprecated.
- **CI/CD & CLI workflow:** Releasers and engineers prefer a fast CLI tool that exits with non-zero status (`sys.exit(1)`) on blockers so it can double as an automated CI gate and a manual terminal check.

## Blind Spots (What This Tool Does Not Catch)
- **Semantic contradictions:** In `9bb069bc...` (`it`), the translator wrote *"fino a un massimo di 1,0"* ("up to a maximum of 1.0") instead of *"minimum of 1.0"*. Because the number `1,0` is present, deterministic regex checks pass.
- **Dropped or swapped `1` and `2` numerals (Number Filtering Trade-off):** To avoid false positives in languages like Turkish (`tk`) that naturally translate `"Rack 1 / Rack 2"` into ordinal words (`"İlk / İkinci"`), the number check filters out `1.0` and `2.0` from the required baseline list (`important_en_nums`). **Strength:** Eliminates false alarms on ordinal words while still catching if a larger number (like `30`) is mistakenly changed to `1` or `2` (since `30` will be missing), and catches `jp` changing the final `1.0` to `4` (since `4.0` appears twice). **Weakness:** If an English string contains *only* the number `1` or `2` (e.g., `"Wait 1 second"`) and a translator completely drops the number or swaps `1` for `2`, the tool will not flag it.
- **True pixel rendering overflow:** Character ratios (>2.5x) and `\n` counts are useful proxies, but real UI overflow depends on font metrics (especially CJK vs. Latin glyphs) and container dimensions.
- **Contextual grammar or tone errors:** Purely linguistic mistranslations that preserve tags, numbers, and length will pass deterministic checks.

## Scope Trade-offs & What I'd Build Next With Another Day

### Explicitly Chosen NOT to Do (Trade-offs)
- **No Web UI:** Deliberately built a fast, lightweight Command Line Interface (CLI) rather than a graphical web interface. For LiveOps releasers and automation pipelines, speed, scriptability, and zero friction matter more than UI polish.
- **Zero External Dependencies (`pip` free):** Avoided external third-party libraries, relying strictly on Python's standard library (`plistlib`, `re`, `sys`, `argparse`). This ensures any engineer or release manager can pull the repository and run the tool instantly without setting up virtual environments or installing packages.
- **No Mandatory LLM/API Calls:** Kept the standard execution deterministic and local. Forcing an internet connection or paid API keys for a release tool introduces network latency, non-determinism, and unnecessary friction.

### What I Would Build Next With Another Day (+1 Day Roadmap)
1. **Automated CI PR Commenter (`--format markdown/json`):** 
   - *What it is:* Add a CLI flag to export the validation report as a structured Markdown table or JSON payload.
   - *Why:* When integrated into GitHub Actions or GitLab CI, a failed check can automatically post a cleanly formatted comment directly onto the developer's Pull Request page, eliminating the need to inspect raw terminal logs.
2. **Allowlist / Ignore Mechanism (`.locignore`):** 
   - *What it is:* Support a local configuration file where the team can explicitly whitelist intentional changes (e.g., acknowledging that a specific key was deliberately deleted because a feature was deprecated).
   - *Why:* Prevents strict release pipelines from getting blocked by false alarms when a removal or schema shift is fully intentional.
3. **Optional AI Semantic Check (`--llm-check` Flag for New Keys):** 
   - *What it is:* Introduce an *optional*, opt-in flag that leverages an LLM to review newly added keys and cross-reference semantic meanings (such as catching the Italian *"massimo"* vs. *"minimum"* rule inversion).
   - *Why:* Combines the speed and reliability of local deterministic rules for routine checks with the deep linguistic understanding of AI when specifically requested for high-risk text.