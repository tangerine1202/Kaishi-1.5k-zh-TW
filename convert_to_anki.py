#!/usr/bin/env python3
import csv
import re
import zipfile
import sqlite3
import tempfile
import json
from pathlib import Path
import zstandard as zstd
import genanki

# Define unique Model and Deck IDs distinct from the rich style version
MODEL_ID = 1781458743411
DECK_ID = 1781459085120

def to_ruby(text: str) -> str:
    if not text:
        return ""
    pattern = r"([^\s[\]<>]+)\[([^[\]]+)\]"
    return re.sub(pattern, r"<ruby>\1<rt>\2</rt></ruby>", text)

def read_varint(data, pos):
    val = 0
    shift = 0
    while True:
        b = data[pos]
        pos += 1
        val |= (b & 0x7f) << shift
        if not (b & 0x80):
            break
        shift += 7
    return val, pos

def decompress_anki21b(apkg_path, out_db_path):
    with zipfile.ZipFile(apkg_path, 'r') as zf:
        if 'collection.anki21b' in zf.namelist():
            data = zf.read('collection.anki21b')
            dctx = zstd.ZstdDecompressor()
            decompressed = dctx.decompress(data, max_output_size=100_000_000)
            with open(out_db_path, 'wb') as f:
                f.write(decompressed)
            return True
        elif 'collection.anki2' in zf.namelist():
            with open(out_db_path, 'wb') as f:
                f.write(zf.read('collection.anki2'))
            return True
    return False

def build_en_audio_map(db_path):
    conn = sqlite3.connect(db_path)
    conn.create_collation("unicase", lambda a, b: (a.lower() > b.lower()) - (a.lower() < b.lower()))
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    
    fields_list = []
    if 'fields' in tables:
        cursor.execute("SELECT ntid, name, ord FROM fields ORDER BY ntid, ord")
        ntid_fields = {}
        for ntid, name, ord_val in cursor.fetchall():
            if ntid not in ntid_fields:
                ntid_fields[ntid] = []
            ntid_fields[ntid].append(name)
        
        cursor.execute("SELECT id FROM notetypes WHERE name = 'Kaishi 1.5k'")
        ntid_row = cursor.fetchone()
        if ntid_row:
            target_ntid = ntid_row[0]
            fields_list = ntid_fields[target_ntid]
            
    if not fields_list:
        print("Could not retrieve fields list.")
        conn.close()
        return {}
        
    idx_word = fields_list.index('Word')
    idx_reading = fields_list.index('Word Reading')
    idx_word_audio = fields_list.index('Word Audio')
    idx_sentence_audio = fields_list.index('Sentence Audio')
    
    audio_map = {}
    cursor.execute("SELECT flds FROM notes WHERE mid = ?", (target_ntid,))
    notes_rows = cursor.fetchall()
    for r in notes_rows:
        flds = r[0].split('\x1f')
        if len(flds) > max(idx_word, idx_reading, idx_word_audio, idx_sentence_audio):
            w = flds[idx_word].strip()
            read = flds[idx_reading].strip()
            w_audio = flds[idx_word_audio].strip()
            s_audio = flds[idx_sentence_audio].strip()
            
            clean_read = re.split(r'[\s(（]', read)[0].strip()
            idx_sent = fields_list.index('Sentence')
            sent_clean = re.sub(r'<[^>]*>', '', flds[idx_sent]).strip()
            
            key = (w, clean_read)
            if key not in audio_map:
                audio_map[key] = []
            audio_map[key].append({
                'word_audio': w_audio,
                'sentence_audio': s_audio,
                'sentence_clean': sent_clean
            })
            
    conn.close()
    return audio_map

def extract_referenced_media(en_apkg_path, referenced_filenames, dest_dir):
    with zipfile.ZipFile(en_apkg_path, 'r') as zf:
        if 'media' not in zf.namelist():
            print("No media file in English APKG.")
            return []
        media_data = zf.read('media')
        if media_data.startswith(b'\x28\xb5\x2f\xfd'):
            dctx = zstd.ZstdDecompressor()
            media_bytes = dctx.decompress(media_data, max_output_size=100_000_000)
        else:
            media_bytes = media_data
            
        filename_to_idx = {}
        entry_idx = 0
        pos = 0
        n = len(media_bytes)
        while pos < n:
            tag, pos = read_varint(media_bytes, pos)
            if tag == 0:
                break
            wire_type = tag & 0x07
            field_num = tag >> 3
            if wire_type == 2:
                length, pos = read_varint(media_bytes, pos)
                val = media_bytes[pos:pos+length]
                pos += length
                if field_num == 1:
                    inner_pos = 0
                    inner_len = len(val)
                    fn = None
                    while inner_pos < inner_len:
                        inner_tag, inner_pos = read_varint(val, inner_pos)
                        inner_wire = inner_tag & 0x07
                        inner_field = inner_tag >> 3
                        if inner_wire == 2 and inner_field == 1:
                            str_len, inner_pos = read_varint(val, inner_pos)
                            fn = val[inner_pos:inner_pos+str_len].decode('utf-8')
                            inner_pos += str_len
                        elif inner_wire == 2:
                            l, inner_pos = read_varint(val, inner_pos)
                            inner_pos += l
                        else:
                            _, inner_pos = read_varint(val, inner_pos)
                    if fn:
                        filename_to_idx[fn] = str(entry_idx)
                    entry_idx += 1
            elif wire_type == 0:
                _, pos = read_varint(media_bytes, pos)
            else:
                pass

        extracted_paths = []
        for fn in referenced_filenames:
            if fn in filename_to_idx:
                zip_member = filename_to_idx[fn]
                dest_path = dest_dir / fn
                try:
                    with zf.open(zip_member) as source_file:
                        file_data = source_file.read()
                    if file_data.startswith(b'\x28\xb5\x2f\xfd'):
                        dctx = zstd.ZstdDecompressor()
                        file_data = dctx.decompress(file_data, max_output_size=100_000_000)
                    with open(dest_path, 'wb') as target_file:
                        target_file.write(file_data)
                    extracted_paths.append(str(dest_path))
                except Exception as e:
                    print(f"Failed to extract {fn}: {e}")
            else:
                print(f"Warning: {fn} not found in media mapping.")
        return extracted_paths

# Simpler, minimal CSS style
css_style = """
.card {
  font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
  font-size: 22px;
  color: #333333;
  background-color: #ffffff;
  text-align: center;
  margin: 20px;
}

.nightMode .card {
  color: #e0e0e0;
  background-color: #121212;
}

/* Ruby Furigana */
ruby {
  ruby-position: over;
}
rt {
  font-size: 0.5em;
  color: #666666;
}
.nightMode rt {
  color: #999999;
}

/* Word Displays */
.word-front, .word-back {
  font-size: 44px;
  font-weight: bold;
}

.reading {
  font-size: 23px;
  color: #666666;
  margin-top: 5px;
}
.nightMode .reading {
  color: #999999;
}

.pitch {
  margin: 5px 0;
}

.meaning {
  font-size: 25px;
  color: #c0392b;
  margin: 15px 0;
  font-weight: bold;
}
.nightMode .meaning {
  color: #e74c3c;
}

.meaning-front {
  font-size: 30px;
  font-weight: bold;
}

/* Metadata Row */
.meta-row {
  font-size: 15px;
  color: #777777;
  margin: 8px 0;
}
.nightMode .meta-row {
  color: #aaaaaa;
}
.badge {
  margin: 0 4px;
}

/* Sentences */
.sentence-front {
  font-size: 21px;
  color: #444444;
  margin-top: 15px;
  line-height: 1.5;
}
.nightMode .sentence-front {
  color: #cccccc;
}

.sentence-section {
  margin-top: 20px;
  text-align: center;
}

.sentence-jp, .sentence-jp-back {
  font-size: 22px;
  line-height: 1.6;
}

.sentence-zh, .sentence-zh-back {
  font-size: 17px;
  color: #666666;
  margin-top: 5px;
}
.nightMode .sentence-zh, .nightMode .sentence-zh-back {
  color: #999999;
}

.sentence-zh-front {
  font-size: 24px;
}

.word-hint {
  font-size: 16px;
  color: #777777;
  margin-top: 15px;
}
.nightMode .word-hint {
  color: #aaaaaa;
}

/* Notes Section */
.notes-section {
  font-size: 16px;
  color: #666666;
  text-align: left;
  max-width: 500px;
  margin: 15px auto 0 auto;
  border-left: 2px solid #cccccc;
  padding-left: 10px;
}
.nightMode .notes-section {
  border-left-color: #444444;
  color: #999999;
}

.notes-header {
  font-weight: bold;
  font-size: 14px;
  color: #888888;
  margin-bottom: 2px;
}

.divider {
  border: 0;
  height: 1px;
  background-color: #eeeeee;
  margin: 15px 0;
}
.nightMode .divider {
  background-color: #2c2c2c;
}

b, strong {
  color: #2980b9;
}
.nightMode b, .nightMode strong {
  color: #3498db;
}

/* Type Answer Styling */
#typeans, #ankiweb-type-input {
  font-family: inherit;
  font-size: 20px;
  padding: 8px 12px;
  max-width: 500px;
  width: 90%;
  border: 1px solid #ccc;
  border-radius: 6px;
  margin: 15px auto;
  box-sizing: border-box;
  text-align: center;
  display: block;
}
.nightMode #typeans, .nightMode #ankiweb-type-input {
  background-color: #222;
  color: #fff;
  border-color: #444;
}
code#typeans {
  background: transparent;
  border: none;
  font-family: inherit;
  font-size: 20px;
  text-align: center;
  display: block;
}
.typeGood {
  color: #2ecc71;
  background-color: rgba(46, 204, 113, 0.1);
  padding: 2px 4px;
  border-radius: 3px;
}
.typeBad {
  color: #e74c3c;
  background-color: rgba(231, 76, 60, 0.1);
  text-decoration: line-through;
  padding: 2px 4px;
  border-radius: 3px;
}
.typeMissed {
  color: #3498db;
  background-color: rgba(52, 152, 219, 0.1);
  padding: 2px 4px;
  border-radius: 3px;
  font-weight: bold;
}
"""

# HTML Card Templates
front_template_1 = """
<div class="word-front">{{Word}}</div>
{{#Sentence}}
<hr class="divider">
<div class="sentence-front">{{Sentence}}</div>
{{/Sentence}}
"""

back_template_1 = """
<div class="word-back">{{WordFurigana}}</div>
<div class="reading">{{Reading}}</div>
{{#PitchAccent}}<div class="pitch">{{PitchAccent}}</div>{{/PitchAccent}}


<div class="meta-row">
  <span class="badge">[{{POS}}]</span>
</div>

<hr class="divider">

<div class="meaning">{{Meaning}}</div>

{{#SentenceFurigana}}
<div class="sentence-section">
  <div class="sentence-jp">{{SentenceFurigana}}</div>
  <div class="sentence-zh">{{SentenceMeaning}}</div>
</div>
{{/SentenceFurigana}}

{{#Notes}}
<div class="notes-section">
  <div class="notes-header">Notes</div>
  <div>{{Notes}}</div>
</div>
{{/Notes}}
{{WordAudio}}
{{SentenceAudio}}
"""

front_template_2 = """
<div class="meaning-front">{{Meaning}}</div>
{{#SentenceMeaning}}
<hr class="divider">
<div class="sentence-zh">{{SentenceMeaning}}</div>
{{/SentenceMeaning}}
"""

back_template_2 = """
<div class="word-back">{{WordFurigana}}</div>
<div class="reading">{{Reading}}</div>
{{#PitchAccent}}<div class="pitch">{{PitchAccent}}</div>{{/PitchAccent}}

<div class="meta-row">
  <span class="badge">[{{POS}}]</span>
</div>

<hr class="divider">

<div class="meaning">{{Meaning}}</div>

{{#SentenceFurigana}}
<div class="sentence-section">
  <div class="sentence-jp">{{SentenceFurigana}}</div>
  <div class="sentence-zh">{{SentenceMeaning}}</div>
</div>
{{/SentenceFurigana}}

{{#Notes}}
<div class="notes-section">
  <div class="notes-header">Notes</div>
  <div>{{Notes}}</div>
</div>
{{/Notes}}
{{WordAudio}}
{{SentenceAudio}}
"""

front_template_3 = """
{{#SentenceMeaning}}
<div class="sentence-zh-front">{{SentenceMeaning}}</div>
{{/SentenceMeaning}}
<div class="word-hint">Keyword: {{Word}} ({{Reading}})</div>

<!-- Native typing (hidden on AnkiWeb) -->
{{type:SentenceClean}}

<!-- Fallback input for AnkiWeb -->
<div id="ankiweb-type-container" style="display: none;">
  <input id="ankiweb-type-input" type="text" placeholder="Type the Japanese sentence..." autocomplete="off" autofocus>
</div>

<script>
  (function() {
    sessionStorage.removeItem('ankiTypedAnswer');
    setTimeout(function() {
      var nativeInput = document.getElementById('typeans');
      if (nativeInput) {
        nativeInput.addEventListener('input', function(e) {
          sessionStorage.setItem('ankiTypedAnswer', e.target.value);
        });
      } else {
        var fallbackContainer = document.getElementById('ankiweb-type-container');
        if (fallbackContainer) {
          fallbackContainer.style.display = 'block';
          var fallbackInput = document.getElementById('ankiweb-type-input');
          fallbackInput.addEventListener('input', function(e) {
            sessionStorage.setItem('ankiTypedAnswer', e.target.value);
          });
          fallbackInput.focus();
        }
      }
    }, 150);
  })();
</script>
"""

back_template_3 = """
<div id="type-result-container">
  {{type:SentenceClean}}
</div>

<div id="correct-sentence-raw" style="display: none;">{{SentenceClean}}</div>

{{#SentenceFurigana}}
<div class="sentence-section">
  <div class="sentence-jp-back">{{SentenceFurigana}}</div>
  <div class="sentence-zh-back">{{SentenceMeaning}}</div>
</div>
{{/SentenceFurigana}}

<hr class="divider">

<div class="word-back">{{WordFurigana}}</div>
<div class="reading">{{Reading}}</div>
{{#PitchAccent}}<div class="pitch">{{PitchAccent}}</div>{{/PitchAccent}}

<div class="meta-row">
  <span class="badge">[{{POS}}]</span>
</div>
<div class="meaning">{{Meaning}}</div>

{{#Notes}}
<div class="notes-section">
  <div class="notes-header">Notes</div>
  <div>{{Notes}}</div>
</div>
{{/Notes}}
{{WordAudio}}
{{SentenceAudio}}

<script>
  (function() {
    function escapeHtml(str) {
      if (!str) return '';
      return str.replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
    }

    function getDiffHtml(typed, correct) {
      if (!typed) {
        return '<span style="color: #9b59b6; font-style: italic;">(no answer typed)</span>';
      }
      if (typed === correct) {
        return '<span class="typeGood">' + escapeHtml(typed) + '</span>';
      }
      
      var html = '';
      var len = Math.max(typed.length, correct.length);
      for (var i = 0; i < len; i++) {
        var tChar = typed[i] || '';
        var cChar = correct[i] || '';
        if (tChar === cChar) {
          html += '<span class="typeGood">' + escapeHtml(tChar) + '</span>';
        } else {
          if (tChar) {
            html += '<span class="typeBad">' + escapeHtml(tChar) + '</span>';
          }
          if (cChar) {
            html += '<span class="typeMissed">' + escapeHtml(cChar) + '</span>';
          }
        }
      }
      return html;
    }

    var resultContainer = document.getElementById('type-result-container');
    var nativeResult = resultContainer ? resultContainer.querySelector('code, #typeans') : null;
    
    if (!nativeResult || nativeResult.innerText.trim() === "") {
      var typedVal = sessionStorage.getItem('ankiTypedAnswer') || '';
      var correctVal = document.getElementById('correct-sentence-raw').innerText.trim();
      
      if (resultContainer) {
        resultContainer.innerHTML = '<code id="typeans">' + getDiffHtml(typedVal, correctVal) + '</code>';
      }
    }
  })();
</script>
"""

def main():
    repo_dir = Path(__file__).resolve().parent
    tsv_path = repo_dir / "kaishi-1500.tsv"
    out_apkg_path = repo_dir / "Kaishi 1.5k (zh-TW, 3 types).apkg"
    en_apkg_path = repo_dir / "Kaishi-1.5k-en.apkg"

    if not tsv_path.exists():
        print(f"Error: {tsv_path} does not exist.")
        return

    # Check if English APKG exists
    if not en_apkg_path.exists():
        print(f"Error: {en_apkg_path} does not exist. Please place Kaishi-1.5k-en.apkg in the same directory.")
        return

    # Decompress English DB and build audio map
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        db_path = tmpdir_path / "collection.anki2"
        print("Extracting and decompressing English APKG database...")
        if not decompress_anki21b(en_apkg_path, db_path):
            print("Failed to decompress database from English APKG.")
            return
            
        audio_map = build_en_audio_map(db_path)
        print(f"Loaded {len(audio_map)} entries from English audio map.")

        # Define Model
        model = genanki.Model(
            MODEL_ID,
            'Kaishi 1.5k Model (zh-TW, 3 types)',
            fields=[
                {'name': 'Word'},
                {'name': 'Reading'},
                {'name': 'Meaning'},
                {'name': 'WordFurigana'},
                {'name': 'Sentence'},
                {'name': 'SentenceClean'},
                {'name': 'SentenceMeaning'},
                {'name': 'SentenceFurigana'},
                {'name': 'Notes'},
                {'name': 'PitchAccent'},
                {'name': 'POS'},
                {'name': 'Frequency'},
                {'name': 'WordAudio'},
                {'name': 'SentenceAudio'},
            ],
            templates=[
                {
                    'name': 'Recognition',
                    'qfmt': front_template_1,
                    'afmt': back_template_1,
                },
                {
                    'name': 'Recall',
                    'qfmt': front_template_2,
                    'afmt': back_template_2,
                },
                {
                    'name': 'Reverse Translation (逆翻譯)',
                    'qfmt': front_template_3,
                    'afmt': back_template_3,
                },
            ],
            css=css_style
        )

        deck = genanki.Deck(
            DECK_ID,
            'Kaishi 1.5k (zh-TW, 3 types)'
        )

        print("Parsing TSV and converting furigana patterns...")
        count = 0
        referenced_media_files = set()
        notes_data = []

        with open(tsv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\t")
            for row in reader:
                if not row or len(row) < 12:
                    continue
                
                # Fields matching Kaishi 1500 TSV columns
                word = row[0].strip()
                reading = row[1].strip()
                meaning = row[2].strip()
                word_furigana = to_ruby(row[3].strip())
                sentence = row[4].strip()
                # Clean up known typo in raw data
                sentence = sentence.replace('<b素晴らしい< b="">チャンスだ。</b素晴らしい<>', 'チャンスだ。')
                sentence_clean = re.sub(r'<[^>]*>', '', sentence)
                sentence_meaning = row[5].strip()
                sentence_furigana = to_ruby(row[6].strip())
                notes = row[7].strip()
                pitch_accent = row[8].strip()
                frequency = row[10].strip()
                pos = row[11].strip()

                # Get audio using robust match to handle duplicates
                clean_read = re.split(r'[\s(（]', reading)[0].strip()
                candidates = audio_map.get((word, clean_read))
                word_audio = ""
                sentence_audio = ""
                if candidates:
                    if len(candidates) == 1:
                        best_cand = candidates[0]
                    else:
                        best_cand = None
                        best_overlap = -1
                        for cand in candidates:
                            overlap = len(set(sentence_clean) & set(cand['sentence_clean']))
                            if overlap > best_overlap:
                                best_overlap = overlap
                                best_cand = cand
                    if best_cand:
                        word_audio = best_cand['word_audio']
                        sentence_audio = best_cand['sentence_audio']
                    
                    # Parse filenames to extract them later
                    for tag in (word_audio, sentence_audio):
                        if tag and tag.startswith('[sound:') and tag.endswith(']'):
                            fn = tag.replace('[sound:', '').replace(']', '').strip()
                            if fn:
                                referenced_media_files.add(fn)

                notes_data.append((
                    word, reading, meaning, word_furigana, sentence, sentence_clean,
                    sentence_meaning, sentence_furigana, notes, pitch_accent, pos, frequency,
                    word_audio, sentence_audio
                ))

        print(f"Extracting {len(referenced_media_files)} referenced media files from English APKG...")
        media_temp_dir = tmpdir_path / "media_extracted"
        media_temp_dir.mkdir(parents=True, exist_ok=True)
        media_paths = extract_referenced_media(en_apkg_path, referenced_media_files, media_temp_dir)
        print(f"Extracted {len(media_paths)} files successfully.")

        # Create Genanki notes using stable GUID matching original 12 fields
        for row in notes_data:
            guid = genanki.guid_for(*row[:12])
            note = genanki.Note(
                model=model,
                fields=list(row),
                guid=guid
            )
            deck.add_note(note)
            count += 1

        print(f"Saving {count} notes to Anki Deck (.apkg)...")
        package = genanki.Package(deck)
        package.media_files = media_paths
        package.write_to_file(str(out_apkg_path))
        print(f"Successfully generated {out_apkg_path}")

if __name__ == "__main__":
    main()
