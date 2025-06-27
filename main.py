import sys
import csv
import getopt
import pprint
import logging
import datetime
from email_utils import send_summary_email
from gpt import callApiWithGrant,  getKey, OpenAI
from db_functions import insert_story, get_db_connection
from grants import get_yesterday_zip_url, get_yesterdays_date, download_and_extract_zip, parse_yesterdays_grants, generate_filename, delete_file
"""
Author: Bailey Malota
Last Updated: Jun 26 2025
"""
# getting the api key
client = OpenAI(api_key=getKey())

# setting up the Logging functionality
logfile = f"scrape_log.{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
    datefmt="%m-%d %H:%M:%S",
    filename=logfile,
    filemode="w"
)

# more logging setup
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("%(name)-12s: %(levelname)-8s %(message)s")
console.setFormatter(formatter)
logging.getLogger("").addHandler(console)

# main runner
def main(argv):
    # setting up email summary variable
    start_time = datetime.now()
    processed = 0
    test_run = False
    production_run = False
    output_path = "grant_stories.csv"

    # gettings options
    try:
        opts, args = getopt.getopt(argv, "pt")
    except getopt.GetoptError:
        print("Usage: -p -t")
        sys.exit(1)

    # settings get opt variables
    for opt, _ in opts:
        if opt == "-p":
            production_run = True
        elif opt == "-t":
            test_run = True
    
    # grabs zip file, downloads it, and gets all yesterdays grants
    logging.info("Starting run")
    zip_url = get_yesterday_zip_url()
    file = download_and_extract_zip(zip_url)
    grants = parse_yesterdays_grants(file)

    # delete the file after parsing it
    delete_file(file)

    # if test run, sent it to csv file to look at
    if test_run:
        with open(output_path, "w", newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Filename", "Headline", "Story Text"])  # header row

            for grant in grants:
                filename = generate_filename(grant)
                headline, story = callApiWithGrant(client, grant)
                
                # if callApiWithGrant didnt return None, then write row
                if headline and story:
                    writer.writerow([filename, headline, story])

        # ends the run after putting it into csv
        return
    
    # inserts into the story coder if this is running in production
    if production_run:
        #setting up db connection
        get_db_connection()

        # parsing through each grant
        for grant in grants:
            filename = generate_filename(grant)
            headline, story = callApiWithGrant(client, grant)

            # inserting story if valid input and non-duplicatge filename
            if headline and story:
                insert_story(filename, headline, story, "TODO")
                pass

