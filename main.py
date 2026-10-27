import requests
import csv
import io
import json
import os
import zipfile

# GitHub raw CSV URLs
RTK_URL = "https://raw.githubusercontent.com/cyphar/heisig-rtk-index/master/kanji/KANJI_INDEX.csv"
WORDS_URL = "https://raw.githubusercontent.com/quentin-moquay/japanese-words-frequency/master/resources/frequency_list.csv"
JMDICT_URL = "https://github.com/scriptin/jmdict-simplified/releases/download/3.6.2%2B20260824122934/jmdict-eng-common-3.6.2%2B20260824122934.json.zip"
JMDICT_CACHE = "jmdict-eng-common.json.zip"
PROGRESS_FILE = "rtk_progress.txt"

def download_csv(url):
    """Download a CSV file and return its text."""
    print(f"Downloading: {url}")
    r = requests.get(url)
    r.raise_for_status()
    return r.text

def load_translations():
    """Load English translations from a cached JMdict dictionary."""
    if not os.path.exists(JMDICT_CACHE):
        print(f"Downloading: {JMDICT_URL}")
        response = requests.get(JMDICT_URL)
        response.raise_for_status()
        with open(JMDICT_CACHE, "wb") as dictionary_file:
            dictionary_file.write(response.content)

    translations = {}
    with zipfile.ZipFile(JMDICT_CACHE) as archive:
        dictionary = json.loads(archive.read(archive.namelist()[0]))
    for entry in dictionary["words"]:
        words = [item["text"] for item in entry["kanji"]]
        words.extend(item["text"] for item in entry["kana"])
        meanings = [
            gloss["text"]
            for sense in entry["sense"]
            for gloss in sense["gloss"]
            if gloss["lang"] == "eng"
        ]
        for word in words:
            translations.setdefault(word, set()).update(meanings)
    return {word: "; ".join(sorted(meanings)) for word, meanings in translations.items()}

def load_rtk_kanji():
    """Load RTK kanji and map each kanji to its RTK index."""
    reader = csv.DictReader(io.StringIO(download_csv(RTK_URL)))
    return {
        row["kanji"].strip(): int(row["id_6th_ed"])
        for row in reader
        if row.get("kanji", "").strip() and row.get("id_6th_ed", "").isdigit()
    }

def load_words():
    """Load frequency-sorted Japanese words."""
    reader = csv.DictReader(io.StringIO(download_csv(WORDS_URL)))
    return [
        (
            row["Orthographe standard (dans les journaux)"].strip(),
            row.get("Lecture standard (en Hiragana)", "").strip(),
            int(row["Classement de fréquence"]),
        )
        for row in reader
        if row.get("Orthographe standard (dans les journaux)", "").strip()
        and row.get("Classement de fréquence", "").isdigit()
    ]

def filter_words(words, rtk_map, start_n, end_n):
    """Return words newly enabled by the RTK range from start_n to end_n."""
    allowed = []
    for entry in words:
        w = entry[0] if isinstance(entry, tuple) else entry
        if w == "#N/D" or not any('\u4e00' <= ch <= '\u9fff' for ch in w):
            continue
        highest_index = 0
        for ch in w:
            if not ('\u4e00' <= ch <= '\u9fff'):
                continue
            if ch not in rtk_map or rtk_map[ch] > end_n:
                break
            highest_index = max(highest_index, rtk_map[ch])
        else:
            if highest_index > start_n:
                allowed.append(entry)
    return allowed

def write_csv(words, translations, output_file):
    """Write filtered words, readings, and English translations to a CSV file."""
    with open(output_file, "w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        for entry in words:
            if isinstance(entry, tuple):
                word, hiragana, frequency_rank = entry
            else:
                word, hiragana, frequency_rank = entry, "", ""
            writer.writerow([word, hiragana, frequency_rank, translations.get(word, "")])

def load_start_n():
    """Load the previous end number, defaulting to zero on the first run."""
    try:
        with open(PROGRESS_FILE, encoding="utf-8") as progress_file:
            return max(0, int(progress_file.read().strip()))
    except (FileNotFoundError, ValueError):
        return 0

def read_end_kanji(rtk_map):
    """Read an RTK kanji and return its index."""
    while True:
        kanji = input("Enter the last RTK kanji you know: ").strip()
        if len(kanji) == 1 and kanji in rtk_map:
            return rtk_map[kanji]
        print("Please enter one kanji from the RTK index.")

def save_start_n(end_n):
    """Save the end number for the next run's starting point."""
    with open(PROGRESS_FILE, "w", encoding="utf-8") as progress_file:
        progress_file.write(str(end_n))

def main():
    start_n = load_start_n()
    rtk_map = load_rtk_kanji()
    print(f"Starting from RTK number {start_n}.")
    end_n = read_end_kanji(rtk_map)
    if end_n < start_n:
        print(f"That kanji is before the saved progress ({start_n}).")
        return

    words = load_words()
    translations = load_translations()

    filtered = filter_words(words, rtk_map, start_n, end_n)
    filtered.sort(key=lambda entry: entry[2])
    output_file = f"filtered_words_{start_n}_{end_n}.csv"
    write_csv(filtered, translations, output_file)
    save_start_n(end_n)

    print(f"Wrote {len(filtered)} words to {output_file}.")

if __name__ == "__main__":
    main()
