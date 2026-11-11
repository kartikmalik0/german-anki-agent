#!/usr/bin/env python3
"""
german_to_anki.py
Reads German words from a raw text file, asks Gemini for article / plural /
meaning / example, adds cards to Anki (via AnkiConnect), saves everything to a
backup file, and clears the raw file once everything succeeded.

Raw file format (one entry per line):
    Tisch
    gehen
    Tisch - table                      <- optional hint for Gemini
    Tisch | teacher said: exam word    <- note after "|" goes to Anki + backup
    # lines starting with # are ignored

Usage:
    export GEMINI_API_KEY="your-key"     (never write the key inside this file)
    python3 german_to_anki.py words.txt
    python3 german_to_anki.py words.txt --dry-run   # preview only: no Anki, no backup, no clearing
"""
import argparse
import csv
import html
import json
import os
import sys
import time
import urllib.request
from datetime import date

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

# ---- settings you may want to change ----
MODEL = "gemini-2.5-flash"             # check ai.google.dev for the current model name
FALLBACK_MODEL = "gemini-2.5-flash-lite"  # lighter model, used if the main one stays busy
DECK = "German Vocab"
NOTE_TYPE = "Basic"                    # needs fields "Front" and "Back"
BATCH_SIZE = 20
ANKI_URL = "http://127.0.0.1:8765"
BACKUP_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "vocab_backup.tsv"
)
# ------------------------------------------

BACKUP_COLS = [
    "article", "word", "plural", "part_of_speech",
    "english", "example_de", "example_en", "note", "added",
]


class Card(BaseModel):
    word: str          # the word without article, e.g. "Tisch"
    article: str       # "der" / "die" / "das" for nouns, otherwise ""
    part_of_speech: str
    plural: str        # nouns only, otherwise ""
    english: str
    example_de: str    # simple A2-B1 level sentence
    example_en: str


PROMPT = """You are a German teacher. For each entry below (it may contain a
German word, possibly with an English hint), return exactly one object per
entry, in the same order as the entries.
- Use the correct dictionary form (nouns singular, verbs infinitive).
- For nouns give the article (der/die/das) and plural form. For other word
  types leave article and plural empty.
- Give a short English meaning.
- Give one simple, natural example sentence (A2-B1 level) with an English translation.
Entries:
{entries}
"""


# ---------- helpers ----------

def merge_note(old, new):
    """Combine two notes without repeating the same text."""
    if not new:
        return old
    if not old:
        return new
    if new in old:
        return old
    return f"{old}; {new}"


def read_entries(path):
    """Returns a list of (entry, note). Duplicate entries are merged."""
    entries = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entry, _, note = line.partition("|")
            entry, note = entry.strip(), note.strip()
            if not entry:
                continue
            key = entry.lower()
            if key in entries:
                entries[key][1] = merge_note(entries[key][1], note)
            else:
                entries[key] = [entry, note]
    return [tuple(v) for v in entries.values()]


# ---------- backup file ----------

def load_backup():
    rows = {}
    if os.path.exists(BACKUP_FILE):
        with open(BACKUP_FILE, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f, delimiter="\t"):
                rows[row["word"].lower()] = row
    return rows


def save_backup(rows):
    tmp = BACKUP_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=BACKUP_COLS, delimiter="\t")
        w.writeheader()
        for r in rows.values():
            w.writerow({k: r.get(k, "") for k in BACKUP_COLS})
    os.replace(tmp, BACKUP_FILE)


def update_backup(rows, c, note):
    key = c.word.lower()
    if key in rows:
        rows[key]["note"] = merge_note(rows[key].get("note", ""), note)
    else:
        rows[key] = {
            "article": c.article, "word": c.word, "plural": c.plural,
            "part_of_speech": c.part_of_speech, "english": c.english,
            "example_de": c.example_de, "example_en": c.example_en,
            "note": note, "added": date.today().isoformat(),
        }


# ---------- Gemini ----------

def call_gemini(client, model, entries):
    return client.models.generate_content(
        model=model,
        contents=PROMPT.format(entries="\n".join(f"- {e}" for e in entries)),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[Card],
            temperature=0.2,
        ),
    )


def enrich(client, entries):
    waits = [5, 15, 30, 60]
    models = [MODEL] * 3 + [FALLBACK_MODEL] * 2
    for attempt, model in enumerate(models):
        try:
            resp = call_gemini(client, model, entries)
        except errors.ServerError:          # 503 overloaded, 500, etc.
            wait = waits[min(attempt, len(waits) - 1)]
            print(f"  Gemini busy ({model}), retrying in {wait}s...")
            time.sleep(wait)
            continue
        cards = resp.parsed or []
        if len(cards) == len(entries):
            return cards
        print(f"  Gemini returned {len(cards)} cards for {len(entries)} words, retrying...")
    sys.exit("Gemini is still unavailable or inconsistent. "
             "Nothing was cleared from your raw file; just run again later.")


# ---------- Anki ----------

def anki(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(ANKI_URL, payload, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data["result"]


def note_html(note):
    return f"<br><br><b>Note:</b> {html.escape(note)}"


def to_note(c, note):
    # Front: bare word (so you must recall the gender). Back: everything else.
    back = f"<b>{html.escape((c.article + ' ' + c.word).strip())}</b>"
    if c.plural:
        back += f"<br>Plural: {html.escape(c.plural)}"
    back += f"<br>{html.escape(c.english)} <i>({html.escape(c.part_of_speech)})</i>"
    back += f"<br><br>{html.escape(c.example_de)}<br><i>{html.escape(c.example_en)}</i>"
    if note:
        back += note_html(note)
    return {
        "deckName": DECK,
        "modelName": NOTE_TYPE,
        "fields": {"Front": c.word, "Back": back},
        "options": {"allowDuplicate": False},
        "tags": ["german", "auto"],
    }


def append_note_to_existing(word, note):
    """Word already in Anki: add the new note to the existing card's back."""
    safe = word.replace('"', '\\"')
    ids = anki("findNotes", query=f'deck:"{DECK}" "Front:{safe}"')
    for nid in ids:
        info = anki("notesInfo", notes=[nid])[0]
        back = info["fields"]["Back"]["value"]
        if html.escape(note) in back:
            continue
        anki("updateNoteFields",
             note={"id": nid, "fields": {"Back": back + note_html(note)}})


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("Set GEMINI_API_KEY first.")
    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(api_version="v1beta"),
    )

    entries = read_entries(args.file)
    if not entries:
        print("No words in the file. Nothing to do.")
        return
    print(f"{len(entries)} words to process")

    backup = load_backup()
    if not args.dry_run:
        anki("createDeck", deck=DECK)

    added = existing = 0
    for i in range(0, len(entries), BATCH_SIZE):
        batch = entries[i:i + BATCH_SIZE]
        cards = enrich(client, [e for e, _ in batch])
        notes = [n for _, n in batch]

        for c, n in zip(cards, notes):
            extra = f" | note: {n}" if n else ""
            print(f"  {c.article} {c.word} | pl. {c.plural} | {c.english}{extra}")
        if args.dry_run:
            continue

        results = anki("addNotes", notes=[to_note(c, n) for c, n in zip(cards, notes)])
        for c, n, r in zip(cards, notes, results):
            if r is None:           # already in Anki
                existing += 1
                if n:
                    append_note_to_existing(c.word, n)
            else:
                added += 1
            update_backup(backup, c, n)
        save_backup(backup)

    if args.dry_run:
        print("Dry run finished. Nothing was saved or cleared.")
        return

    # Everything succeeded: clear the raw file.
    open(args.file, "w", encoding="utf-8").close()
    print(f"Done. Added {added} new cards, {existing} were already in Anki.")
    print(f"Backup: {BACKUP_FILE}")
    print(f"Cleared: {args.file}")


if __name__ == "__main__":
    main()