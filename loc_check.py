import argparse
import plistlib
import re
import sys

#abre e converte o ficheiro plist num dic de python 
def load_plist(filepath):
  try:
    with open(filepath, "rb") as f:
      data = plistlib.load(f)
      if not isinstance(data, dict) or "localisations" not in data:
        print(
            f"Error: File '{filepath}' is missing the required 'localisations'"
            " dictionary."
        )
        sys.exit(1)
      return data
  except Exception as e:
    print(f"Error reading/parsing '{filepath}': {e}")
    sys.exit(1)

# extrai os placeholders bons e partidos
def extract_placeholders(text):
  valid = re.findall(r"%[0-9]*[@udfs]", text)
  broken = re.findall(r"%(?![0-9]*[@udfs])", text)
  return valid, broken

#usei dicionario pq a ordem nao importar quando usei as listas dava erros que nao eram problematicos
def extract_bracket_tags(text):
  unbalanced = text.count("[") != text.count("]")
  matches = re.findall(r"([A-Z]):\[([^\]]*)\]", text)
  tags_info = {}
  for tag_name, content in matches:
    options = content.split("/")
    tags_info[tag_name] = len(options)
  return tags_info, unbalanced

#extrai os numeros das frases e garanti que tudo ficasse em floats com pontos
def extract_numbers(text):
  clean_text = re.sub(r"[A-Z]:\[[^\]]*\]", "", text)
  raw_nums = re.findall(r"\d+(?:[.,]\d+)?", clean_text)
  return [float(n.replace(",", ".")) for n in raw_nums]


def count_linebreaks(text):
  return text.count("\n") + text.count("\\n")


def check_files(old_data, new_data):
  blockers = []
  warnings = []
  infos = []

  # 1. Version metadata check
  old_ver = old_data.get("version")
  new_ver = new_data.get("version")
  if old_ver == new_ver:
    warnings.append(
        f"[METADATA] Version string was not updated (still '{new_ver}')."
    )
  else:
    infos.append(f"[METADATA] Version updated from {old_ver} to {new_ver}.")

  old_locs = old_data.get("localisations", {})
  new_locs = new_data.get("localisations", {})

  old_keys = set(old_locs.keys())
  new_keys = set(new_locs.keys())

  # 2. Key coverage check
  removed_keys = old_keys - new_keys
  for k in sorted(removed_keys):
    en_preview = (
        old_locs[k].get("en-US", "")
        if isinstance(old_locs.get(k), dict)
        else ""
    )
    en_preview = en_preview.replace("\n", " ")
    blockers.append(
        f"[KEY REMOVED] Key '{k}' ('{en_preview}') existed in baseline and was"
        " deleted!"
    )

  added_keys = new_keys - old_keys
  for k in sorted(added_keys):
    infos.append(f"[KEY ADDED] New key added: '{k}'")

  # 3. Per-key and per-language checks
  for key, lang_dict in new_locs.items():
    if not isinstance(lang_dict, dict):
      blockers.append(
          f"[SCHEMA ERROR] Key '{key[:8]}...' does not contain a valid language"
          " dictionary!"
      )
      continue

    if "en-US" not in lang_dict or not str(lang_dict.get("en-US", "")).strip():
      blockers.append(
          f"[MISSING BASELINE] Key '{key[:8]}...' is missing the base 'en-US'"
          " reference string!"
      )
      continue

    en_text = lang_dict["en-US"]
    en_valid_ph, _ = extract_placeholders(en_text)
    en_tags, _ = extract_bracket_tags(en_text)
    en_nums = extract_numbers(en_text)
    en_newlines = count_linebreaks(en_text)

    if key in old_locs and isinstance(old_locs[key], dict):
      old_langs = set(old_locs[key].keys())
      new_langs = set(lang_dict.keys())

      missing_langs = old_langs - new_langs
      for lang in sorted(missing_langs):
        blockers.append(
            f"[MISSING LANG] Key '{key[:8]}...': Language '{lang}' existed in"
            " baseline but was dropped!"
        )

    for lang, text in lang_dict.items():
      # 3a. Empty string check
      if not isinstance(text, str) or text.strip() == "":
        blockers.append(
            f"[EMPTY TEXT] Key '{key[:8]}...' [{lang}]: Translation is"
            " completely empty!"
        )
        continue

      # 3b. Format specifiers (%u, %@, etc.)
      valid_ph, broken_ph = extract_placeholders(text)
      if broken_ph or valid_ph != en_valid_ph:
        blockers.append(
            f"[PLACEHOLDER BROKEN] Key '{key[:8]}...' [{lang}]: Expected"
            f" {en_valid_ph}, found valid={valid_ph}, broken={broken_ph} in"
            f" '{text}'"
        )
      else:
        if (
            key in old_locs
            and isinstance(old_locs[key], dict)
            and lang in old_locs[key]
        ):
          old_text = old_locs[key][lang]
          if isinstance(old_text, str):
            old_valid_ph, old_broken_ph = extract_placeholders(old_text)
            if old_broken_ph or old_valid_ph != en_valid_ph:
              infos.append(
                  f"[FIXED BUG] Key '{key[:8]}...' [{lang}]: Placeholder"
                  f" fixed! Was '{old_text}' -> Now '{text}'."
              )

      # 3c. Dynamic bracket tags (A:[op1/op2])
      tags, unbalanced = extract_bracket_tags(text)
      if unbalanced:
        blockers.append(
            f"[SYNTAX ERROR] Key '{key[:8]}...' [{lang}]: Unbalanced square"
            f" brackets '[' or ']' in '{text}'"
        )
      elif tags != en_tags:
        blockers.append(
            f"[TAG MISMATCH] Key '{key[:8]}...' [{lang}]: Dynamic tags differ"
            f" from en-US! Expected {en_tags}, found {tags}."
        )

      if lang == "en-US":
        continue

      # 3d. Game rule / economy numbers check
      nums = extract_numbers(text)
      important_en_nums = [n for n in en_nums if n not in (1.0, 2.0)]
      en_counts = {n: important_en_nums.count(n) for n in set(important_en_nums)}
      tr_counts = {n: nums.count(n) for n in set(important_en_nums)}

      if en_counts != tr_counts:
        warnings.append(
            f"[NUMBER MISMATCH] Key '{key[:8]}...' [{lang}]: Numbers in text"
            f" ({nums}) do not match en-US baseline ({en_nums})."
        )

      # 3e. Line breaks & length overflow heuristics
      newlines = count_linebreaks(text)
      if en_newlines > 0 and newlines == 0:
        warnings.append(
            f"[UI OVERFLOW RISK] Key '{key[:8]}...' [{lang}]: Base en-US has"
            f" {en_newlines} line breaks (\\n), but translation has 0!"
        )
      elif abs(newlines - en_newlines) >= 2:
        warnings.append(
            f"[LAYOUT WARNING] Key '{key[:8]}...' [{lang}]: Line break count"
            f" ({newlines}) differs significantly from en-US ({en_newlines})."
        )

      if len(en_text) > 0 and len(text) > len(en_text) * 2.5:
        warnings.append(
            f"[LENGTH OVERFLOW] Key '{key[:8]}...' [{lang}]: Translation is"
            f" {len(text)/len(en_text):.1f}x longer than en-US ({len(text)} vs"
            f" {len(en_text)} chars)."
        )

  return blockers, warnings, infos


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
      description="Localisation Release Readiness Checker (.plist)"
  )
  parser.add_argument(
      "baseline",
      nargs="?",
      default="localisations_1_2_0.plist",
      help="Baseline plist file (live in production)",
  )
  parser.add_argument(
      "candidate",
      nargs="?",
      default="localisations_1_2_1.plist",
      help="Candidate plist file (new release)",
  )
  args = parser.parse_args()

  old_data = load_plist(args.baseline)
  new_data = load_plist(args.candidate)

  blockers, warnings, infos = check_files(old_data, new_data)

  verdict = (
      "❌ DO NOT SHIP (Blockers detected)"
      if blockers
      else "✅ SAFE TO SHIP (Review warnings if any)"
  )
  print("\n========================================================")
  print(f"RELEASE VERDICT: {verdict}")
  print(f"Comparing: {args.baseline} -> {args.candidate}")
  print(
      f"Summary: {len(blockers)} Blockers | {len(warnings)} Warnings |"
      f" {len(infos)} Infos"
  )
  print("========================================================\n")

  for b in blockers:
    print("🔴", b)
  if blockers:
    print()

  for w in warnings:
    print("🟡", w)
  if warnings:
    print()

  for i in infos:
    print("🟢", i)

  sys.exit(1 if blockers else 0)