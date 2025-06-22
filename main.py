from grants import get_yesterday_zip_url, get_yesterdays_date, download_and_extract_zip, parse_yesterdays_grants, generate_filename
from gpt import callApiWithGrant,  getKey, OpenAI
from db_functions import insert_story, get_db_connection
import pprint
import csv

client = OpenAI(api_key=getKey())

if __name__ == "__main__":
    zip_url = get_yesterday_zip_url()
    file = download_and_extract_zip(zip_url)
    grants = parse_yesterdays_grants(file)

    output_path = "grant_stories.csv"
    with open(output_path, "w", newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Filename", "Headline", "Story Text"])  # header row

        for grant in grants:
            filename = generate_filename(grant)
            headline, story = callApiWithGrant(client, grant)

            if headline and story:
                writer.writerow([filename, headline, story])



