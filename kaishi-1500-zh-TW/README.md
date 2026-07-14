# Kaishi 1.5k Anki Deck Generator (zh-TW)

This repository contains tools to convert the **Kaishi 1500** Japanese vocabulary dataset (Traditional Chinese / zh-TW edition) into a highly optimized, clean, distraction-free Anki flashcard deck (`.apkg` format).

## Deck Included

The generated Anki deck is ready to import:
- **[Kaishi 1.5k (zh-TW, 3 types).apkg](./Kaishi%201.5k%20(zh-TW,%203%20types).apkg)**: Clean, plain text alignment centered without shadows or container styling for a distraction-free experience.

It fully supports **Dark Mode** natively based on device preferences.

---

## Card Types

Each note generates three distinct cards to build complete language competence:

1. **Recognition (Japanese → Chinese)**: Read the Kanji/sentence context and recall the meaning and reading.
2. **Recall (Chinese → Japanese)**: Look at the Traditional Chinese meaning and target sentence translation, then recall the Kanji and reading.
3. **Reverse Translation (Chinese Sentence → Japanese Sentence)**: Based on the method from Kazuma's book *"最強的外國語習得法"*, translate the Chinese example sentence back into the full Japanese sentence from memory.

---

## Repository Structure

- [kaishi-1500.tsv](./kaishi-1500.tsv): The raw source vocabulary and example sentence dataset.
- [convert_to_anki.py](./convert_to_anki.py): Script to generate the Anki deck.

---

## How to Regenerate Deck

`convert_to_anki.py` extracts word/sentence audio from the official English **Kaishi 1.5k** deck, so first place `Kaishi-1.5k-en.apkg` in this directory (not tracked in git due to its size).

Ensure you have [uv](https://github.com/astral-sh/uv) installed, then run:

```bash
# Set up virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install genanki zstandard

# Generate the deck
python convert_to_anki.py
```
