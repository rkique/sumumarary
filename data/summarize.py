import json
from openai import OpenAI

# Read API key from file
with open("../openai.key", "r") as f:
    api_key = f.read().strip()

client = OpenAI(api_key=api_key)

LEVEL_FOLDER_PATH = "level_summaries"
TEXT_FOLDER_PATH = "text_summaries"

def level_summarization_prompt(count, lines, text):
    prompt = f"Create exactly {count} one-line summaries from the following plot summary. Do not use any names of places or people and keep the sentences simple. Each summary should summarize {lines} lines each, and not exceed 15 words. The summaries can refer to each other, and should form a cohesive narrative. \n\n Plot summary:\n{text}"
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
        
    def summarize(self, text, count, lines):
        """Query OpenAI for summaries of specified count and length"""
        response = client.chat.completions.create(
            model= "gpt-5.2",
            messages=[
                {"role": "user", "content": level_summarization_prompt(count, lines, text)}
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
                self.source_text, 
                num_summaries, 
                range_str
            )
            self.levels -= 1
            num_summaries *= 2
        
        with open(f"{LEVEL_FOLDER_PATH}/{self.path}", "w") as f:
            json.dump(results, f, indent=2)

if __name__ == "__main__":
    movie_titles = open("movie_titles.txt").read().splitlines()
    print(movie_titles)
    for movie_title in movie_titles:
        summarizer = Summary(f"{movie_title}.txt", levels=5)
        summarizer.save_all_summaries()
        print(f"[Summary] {movie_title}\n")
