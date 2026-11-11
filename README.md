# German Words to Anki

You write German words in a text file.
Run one command.
Cards appear in Anki with the article (der/die/das), plural, meaning and an example sentence.

No typing cards by hand.

---

## What you need

- A laptop with Ubuntu
- Internet
- 15 minutes for the first setup

---

## SETUP (do this only once)

### Step 1: Install Anki

1. Go to https://apps.ankiweb.net
2. Download Anki for Linux and install it.
3. Open Anki once to make sure it works.

### Step 2: Add the AnkiConnect helper to Anki

1. In Anki click **Tools** then **Add-ons** then **Get Add-ons**.
2. Type this code: `2055492159`
3. Click OK.
4. Close Anki and open it again.

### Step 3: Get a free Gemini key

1. Go to https://aistudio.google.com
2. Log in with your Google account.
3. Click **Get API key** and create a key.
4. Copy the key.

**Keep the key secret.** Never write it inside a file. Never send it to anyone.

### Step 4: Open the terminal in this folder

Open a terminal and type:

```
cd ~/Desktop/german-anki-agent
```

(Use the real path of the folder where this README is.)

### Step 5: Install the tools (copy and paste one line at a time)

```
sudo apt install python3-full python3-venv
python3 -m venv venv
source venv/bin/activate
pip install google-genai pydantic
```

You will see `(venv)` at the start of the line. That is good.

### Step 6: Save your key so you never type it again

Replace `PASTE-YOUR-KEY-HERE` with your real key:

```
echo 'export GEMINI_API_KEY="PASTE-YOUR-KEY-HERE"' >> ~/.bashrc
```

Now **close the terminal and open a new one**.

Setup is done.

---

## HOW TO USE (every time)

### 1. Write your words in `words.txt`

One word on each line:

```
Tisch
gehen
Apfel
```

You can add your own note after a `|` sign:

```
Tisch | teacher said this is in the exam
Mutter | page 42 in my book
```

Other rules:

- A line starting with `#` is ignored.
- An English hint helps Gemini: `Bahnhof - train station`

### 2. Open Anki

Anki **must be open** when you run the script.

### 3. Open the terminal and run

```
cd ~/Desktop/german-anki-agent
source venv/bin/activate
python3 german_to_anki.py words.txt
```

### 4. Done

- Your cards are in the Anki deck called **German Vocab**.
- All your words are saved in `vocab_backup.tsv` (open it with LibreOffice or any text editor).
- `words.txt` is now empty, ready for your next words.

---

## Want to test first?

Add `--dry-run` at the end. It shows the result but saves nothing and clears nothing.

```
python3 german_to_anki.py words.txt --dry-run
```

---

## Good to know

- Same word again? No second card is made.
- Same word again with a new note? The note is added to the old card.
- If something fails, your `words.txt` is **not** cleared. Just run it again.
- Gemini can make a mistake sometimes, especially with rare words. Quickly check the card.

---

## Problems and fixes

**"externally-managed-environment"**
You forgot the virtual environment. Run `source venv/bin/activate` first.

**"Set GEMINI_API_KEY first"**
The key is missing. Do Step 6 again, then open a new terminal.

**"Connection refused" or an error about 127.0.0.1:8765**
Anki is not open, or AnkiConnect is not installed. Open Anki and check Step 2.

**"503 UNAVAILABLE" or "Gemini busy"**
Google is busy. The script tries again by itself. If it still fails, wait a few minutes and run again.

**"429" error**
You used the free limit. Wait a bit and try again, or use fewer words.

**"model not found"**
Google renamed the model. Open `german_to_anki.py`, look at the top for `MODEL` and `FALLBACK_MODEL`, and put in the current names from https://ai.google.dev

---

## Files in this folder

- `german_to_anki.py` : the program
- `words.txt` : you write new words here
- `vocab_backup.tsv` : a safe copy of all your words (made by the program)
- `venv/` : the tools folder, do not touch it
- `README.md` : this help file