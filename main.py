import os
import sys
import csv
import getopt
import pprint
import logging
from datetime import datetime
from email_utils import send_summary_email
from cleanup_text import missing_approved_keyword
from gpt import callApiWithGrant,  getKey, OpenAI, deadline_too_soon, MIN_DAYS_TO_DEADLINE
from db_functions import insert_story, get_db_connection
from grants import get_yesterday_zip_url, get_yesterdays_date, download_and_extract_zip, parse_yesterdays_grants, generate_filename, delete_file, get_applicants_tags, get_funding_category_tags, get_funding_type, is_sole_source, is_test_agency

# comment written to the story.comments field for sole-source grants
SOLE_SOURCE_COMMENT = "BM: This grant is a sole-source grant."

# comment flagging a headline whose action verb isn't one of the approved phrases
# (see cleanup_text.missing_approved_keyword) so an editor can fix it by hand
KEYWORD_ISSUE_COMMENT = "BM keyword issue"


# assembles the story.comments field from every editor flag that applies to a grant
def build_comments(grant, headline):
    """Join all applicable editor-flag comments into the story.comments string."""
    parts = []
    if is_sole_source(grant):
        parts.append(SOLE_SOURCE_COMMENT)
    if headline and missing_approved_keyword(headline):
        parts.append(KEYWORD_ISSUE_COMMENT)
    return " ".join(parts)


# drops grants that should never reach GPT or the story coder: agencies' test records,
# and grants whose application window closes too soon to be worth running.
def filter_grants(grants):
    """Return (grants_to_load, dropped_count), logging why each drop happened."""
    kept = []
    dropped = 0

    for grant in grants:
        number = grant.get("OpportunityNumber", "")

        # agencies push dummy records ("IV&V Test Agency") through the daily extract
        if is_test_agency(grant):
            logging.info(f"Skipping test-agency grant {number}: {grant.get('AgencyName')}")
            dropped += 1
            continue

        # a deadline under a week out is stale news by the time the story runs
        if deadline_too_soon(grant):
            logging.info(f"Skipping grant {number}: deadline is under {MIN_DAYS_TO_DEADLINE} days away")
            dropped += 1
            continue

        kept.append(grant)

    return kept, dropped

"""
Author: Bailey Malota
Last Updated: Jun 30 2025
"""

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


# getting the api key
client = OpenAI(api_key=getKey())

# main runner
def main(argv):
    # setting up email summary variable
    start_time = datetime.now()
    processed = 0
    skipped = 0
    dups = 0
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

    # drop test-agency records and grants closing too soon, before any GPT calls
    grants, dropped = filter_grants(grants)
    skipped += dropped
    logging.info(f"{len(grants)} grants to load, {dropped} filtered out")

    # if test run, sent it to csv file to look at
    if test_run:
        logging.info("TEST run")
        with open(output_path, "w", newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Filename", "Headline", "Story Text", "Original Text", "Comments"])  # header row

            for grant in grants:
                filename = generate_filename(grant)
                headline, story, orig_txt = callApiWithGrant(client, grant)
                comments = build_comments(grant, headline)

                # if callApiWithGrant didnt return None, then write row
                if headline and story:
                    writer.writerow([filename, headline, story, orig_txt, comments])
                    processed += 1
    
    # inserts into the story coder if this is running in production
    if production_run:
        logging.info("PRODUCTION run")

        #setting up db connection
        get_db_connection()

        # parsing through each grant
        for grant in grants:
            # running all grant functions to get data and tags for each grant
            filename = generate_filename(grant)
            headline, story, orig_txt = callApiWithGrant(client, grant)
            applicants_tags = get_applicants_tags(grant)
            category_tags = get_funding_category_tags(grant)
            funding_tag = get_funding_type(grant)
            comments = build_comments(grant, headline)

            # inserting story if valid input and non-duplicatge filename
            if headline and story:

                if insert_story(filename, headline, story, orig_txt, applicants_tags, category_tags, funding_tag, comments) is False:
                    dups += 1
                else:
                    processed += 1

            elif not headline or not story:
                skipped += 1
            
    # formatting the summary email to be sent
    end_time = datetime.now()
    elapsed = str(end_time - start_time).split('.')[0]

    summary = f"""
    Load Version 1.2.0 01/8/2026

    Passed Parameters: {' -t' if test_run else ''} {' -p' if production_run else ''}

    Grants Loaded: {processed}
    Grants Skipped: {skipped}
    Duplicates Found: {dups}

    Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}
    End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
    Elapsed Time: {elapsed}  
    """
    
    logging.info(summary)
    logging.shutdown()
    send_summary_email(summary, logfile)

    # runs main the the args
if __name__ == "__main__":
    main(sys.argv[1:])