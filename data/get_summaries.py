import requests
import os
from bs4 import BeautifulSoup
import pandas as pd
import wikipedia
import re
import json
import pandas as pd

# Read the disney_titles.csv with movie names and URLs
df_disney = pd.read_csv('disney/disney_titles.csv')

plots_enhanced = {}

def write_plots(movies: pd.DataFrame):
    for index, row in movies.iterrows():
        wiki_movie = row['wiki_movie']
        try:
            search_results = wikipedia.search(wiki_movie)
            if not search_results:
                print(f"✗ No search results for: {wiki_movie}")
                continue
            
            # Try the first result
            page = wikipedia.page(search_results[0], auto_suggest=False)
            
            # Get the page content
            content = page.content
            
            # Extract the Plot section
            plot_match = re.search(r'== Plot ==\n(.*?)(?===|\Z)', content, re.DOTALL)
            
            if plot_match:
                plot_text = plot_match.group(1).strip()
                plots_enhanced[index] = plot_text
                print(f"✓ {index + 1}: {wiki_movie} (Found as: {page.title})")
                print(f"  Preview: {plot_text[:80]}...\n")
                with open(f'{index + 1}.txt', 'w', encoding='utf-8') as plot_file:
                    plot_file.write(plot_text)
            
        except Exception as e:
            print(f"[Error] {index + 1} - could not find {wiki_movie}: {type(e).__name__}\n")


def fetch_movie_posters(movies, output_dir='photos'):
    """
    Fetch the main poster/image for each movie from Wikipedia and save to photos directory.
    Scrapes the infobox-image from the Wikipedia page directly.
    
    Args:
        movies: DataFrame with 'title' and 'url' columns
        output_dir: Directory to save images
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Set up a session with proper headers
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    })
    
    for index, row in movies.iterrows():
        movie = row['title']
        page_url = row['url']
        
        try:
            response = session.get(page_url, timeout=15)
            if response.status_code != 200:
                print(f"✗ Failed to fetch page for {movie}: HTTP {response.status_code}")
                continue
            soup = BeautifulSoup(response.text, 'html.parser')
            infobox_image = soup.find(class_='infobox-image')
            if not infobox_image:
                infobox = soup.find(class_='infobox')
                if infobox:
                    img = infobox.find('img')
                    if img:
                        infobox_image = img.parent
            
            if infobox_image:
                img_tag = infobox_image.find('img')
                if img_tag and img_tag.get('src'):
                    img_src = img_tag['src']
                    if img_src.startswith('//'):
                        img_src = 'https:' + img_src
                    elif img_src.startswith('/'):
                        img_src = 'https://en.wikipedia.org' + img_src
            
                    if '/thumb/' in img_src:
                        parts = img_src.split('/thumb/')
                        if len(parts) == 2:
                            base = parts[0]
                            rest = parts[1]
                            rest_parts = rest.rsplit('/', 1)
                            if len(rest_parts) == 2:
                                img_src = base + '/' + rest_parts[0]
                    
                    img_response = session.get(img_src, timeout=15)
                    if img_response.status_code == 200:
                        ext = img_src.split('.')[-1].split('?')[0].lower()
                        if ext not in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']:
                            ext = 'jpg'
                        filename = f"{index + 1}.{ext}"
                        filepath = os.path.join(output_dir, filename)
                        
                        with open(filepath, 'wb') as f:
                            f.write(img_response.content)
                        print(f"✓ {index + 1}: {movie} → {filename}")
                    else:
                        print(f"✗ Failed to download image for: {movie} (HTTP {img_response.status_code})")
                else:
                    print(f"✗ No img tag found in infobox for: {movie}")
            else:
                print(f"✗ No infobox-image found for: {movie}")
                    
        except Exception as e:
            print(f"[Error] {index + 1} - {movie}: {type(e).__name__} - {e}")

# Fetch posters for the disney movies
#fetch_movie_posters(df_disney, output_dir='movies/photos')

#write plots for the disney movies
write_plots(df_disney)