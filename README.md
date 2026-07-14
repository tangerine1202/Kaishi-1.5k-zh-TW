# Kaishi 1.5k zh-TW

Tools to convert the **Kaishi 1500** Japanese vocabulary dataset into a PDF (via Typst) and into Anki flashcard decks (`.apkg`), including a Traditional Chinese (zh-TW) edition.

## Contents

- [kaishi-1500.tsv](kaishi-1500.tsv): the raw source vocabulary and example sentence dataset.
- [kaishi-1500.apkg](kaishi-1500.apkg) / [kaishi-1500-simple.apkg](kaishi-1500-simple.apkg): pre-built English Anki decks.
- [Kaishi 1.5k (zh-TW, 3 types).apkg](Kaishi%201.5k%20(zh-TW,%203%20types).apkg): pre-built Traditional Chinese Anki deck.

## PDF

Convert the dataset to PDF using Typst:

```bash
uv run convert_kaishi.py
# if the font is not found, you can add the font path to the command
typst compile --font-path=/Users/<user>/Library/Fonts kaishi-1500.typ
```

## zh-TW Anki Deck

[Kaishi 1.5k (zh-TW, 3 types).apkg](Kaishi%201.5k%20(zh-TW,%203%20types).apkg) is a clean, distraction-free deck built from the same dataset, with plain text alignment (no shadows or container styling). It fully supports **Dark Mode** natively based on device preferences.

### Card Types

Each note generates three distinct cards to build complete language competence:

1. **Recognition (Japanese → Chinese)**: Read the Kanji/sentence context and recall the meaning and reading.
2. **Recall (Chinese → Japanese)**: Look at the Traditional Chinese meaning and target sentence translation, then recall the Kanji and reading.
3. **Reverse Translation (Chinese Sentence → Japanese Sentence)**: Based on the method from Kazuma's book *"最強的外國語習得法"*, translate the Chinese example sentence back into the full Japanese sentence from memory.

### How to Regenerate

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
