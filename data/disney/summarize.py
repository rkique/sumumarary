import json
from openai import OpenAI
import pandas as pd
import os

# Read API key from file
with open("../openai.key", "r") as f:
    api_key = f.read().strip()

client = OpenAI(api_key=api_key)

LEVEL_FOLDER_PATH = "level_summaries"
TEXT_FOLDER_PATH = "text_summaries"

def level_summarization_prompt(count, lines, text):
    summarization_guide = f"""
    ***Summarization Guide***
    - Do not use any names of places or people.
    - Keep each summary under 12 words. 
    - Keep the sentence structure simple.
    - Do not use linking predicates, coordinating conjunctions, semicolons, or commas to combine clauses.
    - Even though summaries can be simple, they should form a cohesive narrative. 
    - Summaries can corefer.
    - Bad example (1 summary): 'A hacker learns reality is fake, escapes captivity, saves allies, and gains power.' 
    - Good example (1 summary): 'A hacker escapes his simulated reality.'
    - Good example (2 summaries): 'A hacker learns reality is fake, and escapes captivity. He gains power and saves allies.'
    """

    prompt = f"""
    Create exactly {count} one-line summaries from the following plot summary, summarizing {lines} lines each.  Do not number summaries. The summary should follow the summarization guide below. \n\n {summarization_guide} \n\n
    Here is the plot summary:\n{text}
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
        
    def summarize(self, count: int, lines: int) -> str:
        """Query OpenAI for summaries of specified count and length"""
        response = client.chat.completions.create(
            model= "gpt-5.2",
            messages=[
                {"role": "user", "content": level_summarization_prompt(count, lines, self.source_text)}
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
                range_str
            )
            self.levels -= 1
            num_summaries *= 2
        
        with open(f"{LEVEL_FOLDER_PATH}/{self.path}", "w") as f:
            json.dump(results, f, indent=2)

#From a complete text summaries folder, writes to complete the level summaries folder.
if __name__ == "__main__":
    disney_movies = list(range(50))
    for movie_title in disney_movies:
        try:
            summarizer = Summary(f"{movie_title}.txt", levels=5)
            summarizer.save_all_summaries()
            print(f"Summarized {movie_title}")
        except:
            print(f"Failed to summarize {movie_title}")