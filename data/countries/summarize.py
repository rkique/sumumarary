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
 - Do not use any names of places or people.
    - Refer to unique events in history.
    - The summary should uniquely identify the country to someone with great geographic knowledge.
    - Keep summaries under 16 words.
    - Try to keep the sentence structure simple.
    - Do not use linking predicates, coordinating conjunctions, semicolons, or commas to combine clauses. 
    - Avoid multiple modifiers. When in doubt, simply omit supplementary material.
    - However, each summary should comprise a "nugget" of information.
    - Summaries can corefer.
    - Even though each summary should be simple, they should form a cohesive history of the place.
   - Good example (1 sentence summary for Panama): It built an interoceanic canal after secession from a larger union."
   - Good example (2 sentence summary for Panama): It built an interoceanic canal across a narrow land bridge. It endured dictatorship and foreign invasion before democratic recovery.
   - Do not use unfamiliar word combinations.
   - Bad example (1 sentence summary from level 5 for Palau):
    An eighteenth century packet shipwreck sparked sustained foreign trading contact. Because a packet ship is not well-known to players.
   - Good example (1 sentence summary from level 5 for Palau) "After an East India Company ship crashed in the 18th century, British traders became regular visitors". This mentions relevant entities without pinning down the geographic location.
    """

    if is_most_specific:
        summarization_guide += """
    - IMPORTANT: At this level of detail, take sentences and phrases directly from the source document as much as possible. Preserve the original wording rather than paraphrasing.
    """

    prompt = f"""
    Create exactly {count} one-line summaries from the following history of a country, summarizing {lines} lines each.  Do not number summaries. The summary should follow the summarization guide below. \n\n {summarization_guide} \n\n
    Here is the history of the country: \n{text}
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
    countries_df = pd.read_csv("countries_titles.csv")

    for _, row in countries_df.iterrows():
        country = str(row.get("country", "")).strip()
        wiki_country = str(row.get("wiki_country", "")).strip()
        output_stem = slugify_filename(wiki_country or country)
        source_file = f"{output_stem}.txt"

        if not os.path.exists(os.path.join(TEXT_FOLDER_PATH, source_file)):
            print(f"Skipped {country or output_stem}: source file not found ({source_file})")
            continue

        try:
            summarizer = Summary(source_file, levels=5)
            summarizer.path = f"{output_stem}.txt"
            summarizer.save_all_summaries()
            print(f"Summarized {country or output_stem}")
        except Exception as exc:
            print(f"Failed to summarize {country or output_stem}: {exc}")