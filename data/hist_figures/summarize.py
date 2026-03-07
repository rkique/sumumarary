import json
from openai import OpenAI
import pandas as pd
import os
import re

# Read API key from file
with open("../../openai.key", "r") as f:
    api_key = f.read().strip()

client = OpenAI(api_key=api_key)

LEVEL_FOLDER_PATH = "level_summaries"
TEXT_FOLDER_PATH = "text_summaries"

def level_summarization_prompt(count, lines, text, is_most_specific=False):
    summarization_guide = f"""
    ***Summarization Guide***
 - Do not use any names of people or places.
    - Refer to unique events, achievements, or characteristics from their life.
    - The summary should uniquely identify the historical figure to someone with great knowledge of history.
    - Keep summaries under 16 words.
    - Try to keep the sentence structure simple.
    - Do not use linking predicates, coordinating conjunctions, semicolons, or commas to combine clauses.
    - Avoid multiple modifiers. When in doubt, simply omit supplementary material.
    - However, each summary should comprise a "nugget" of information.
    - Summaries can corefer.
    - Even though each summary should be simple, they should form a cohesive biography of the person.
   - Good example (1 sentence summary for Einstein): He published four groundbreaking papers in a single miraculous year while working as a patent clerk.
   - Good example (2 sentence summary for Einstein): He published four groundbreaking papers in a single miraculous year while working as a patent clerk. He fled his homeland when fascists rose to power and warned a foreign president about a devastating new weapon.
   - Do not use unfamiliar word combinations.
   - Bad example (1 sentence summary): He formulated a new epistemological framework for natural philosophy. Because "epistemological framework for natural philosophy" is too academic for players.
   - Good example (1 sentence summary): He revolutionized physics by reimagining the relationship between space and time. This describes the achievement without naming the person.
    """

    if is_most_specific:
        summarization_guide += """
    - IMPORTANT: At this level of detail, take sentences and phrases directly from the source document as much as possible. Preserve the original wording rather than paraphrasing.
    """

    prompt = f"""
    Create exactly {count} one-line summaries from the following biography of a historical figure, summarizing {lines} lines each.  Do not number summaries. The summary should follow the summarization guide below. \n\n {summarization_guide} \n\n
    Here is the biography: \n{text}
    """

    return prompt

class Summary:
    # Read source document
    def read_document(self, path: str) -> tuple[str, int]:
        with open(f"{TEXT_FOLDER_PATH}/{path}", "r") as f:
            source_text = f.read()
            line_count = source_text.count('.')  # Count periods
            return source_text, line_count

    def __init__(self, path: str, levels: int = 5):
        self.path = path
        self.levels = levels
        self.source_text, self.total_lines = self.read_document(path)

    def summarize(self, count: int, lines: int, is_most_specific: bool = False) -> str:
        """Query OpenAI for summaries of specified count and length"""
        response = client.chat.completions.create(
            model= "gpt-5.2",
            messages=[
                {"role": "user", "content": level_summarization_prompt(count, lines, self.source_text, is_most_specific)}
            ]
        )
        return response.choices[0].message.content

    def save_all_summaries(self):
        # Generate summaries for each level based on hierarchical subdivision
        line_count = self.total_lines
        results = {}
        num_summaries = 1
        while self.levels > 0 and line_count > 0:
            lines_per_summary = max(1, line_count // num_summaries)
            range_str = f"{lines_per_summary} lines" if num_summaries == 1 else f"{lines_per_summary}-{lines_per_summary * 2} lines each"
            results[f"level_{self.levels}"] = self.summarize(
                num_summaries,
                range_str,
                is_most_specific=(self.levels == 1)
            )
            self.levels -= 1
            num_summaries *= 2

        with open(f"{LEVEL_FOLDER_PATH}/{self.path}", "w") as f:
            json.dump(results, f, indent=2)


def slugify_filename(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


#From a complete text summaries folder, writes to complete the level summaries folder.
if __name__ == "__main__":
    os.makedirs(LEVEL_FOLDER_PATH, exist_ok=True)
    figures_df = pd.read_csv("hist_figures_titles.csv")

    for _, row in figures_df.iterrows():
        person = str(row.get("person", "")).strip()
        wiki_person = str(row.get("wiki_person", "")).strip()
        output_stem = slugify_filename(wiki_person or person)
        source_file = f"{output_stem}.txt"

        if not os.path.exists(os.path.join(TEXT_FOLDER_PATH, source_file)):
            print(f"Skipped {person or output_stem}: source file not found ({source_file})")
            continue

        try:
            summarizer = Summary(source_file, levels=5)
            summarizer.path = f"{output_stem}.txt"
            summarizer.save_all_summaries()
            print(f"Summarized {person or output_stem}")
        except Exception as exc:
            print(f"Failed to summarize {person or output_stem}: {exc}")
