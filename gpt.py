from cleanup_text import cleanup_text, clean_text
from openai import OpenAI
from datetime import datetime
import platform
import re

# gets the api keys
def getKey():
    """Retrieves the OpenAI API key from a file."""
    try:
        with open("utils/key.txt", "r") as file:
            return file.readline().strip()
    except FileNotFoundError:
        print("File not found!")
    except PermissionError:
        print("You don't have permission to access this file.")
    except IOError as e:
        print(f"An I/O error occurred: {e}")

# makes the date that goes after WASHIGNTON
def get_body_date():
    today = datetime.today()
    month = today.strftime('%B') 
    short_month = today.strftime('%b')
    formatted_month = month if len(month) <= 5 else short_month + "."
    day_format = '%-d' if platform.system() != 'Windows' else '%#d'
    return f"{formatted_month} {today.strftime(day_format)}"

def format_grant_date(date_str):
    """Convert a date like '07222025' to '7 / 22 / 25'."""
    try:
        date = datetime.strptime(date_str, "%m%d%Y")
        return f"{date.month}/{date.day}/{str(date.year)[-2:]}"
    except Exception:
        return date_str  # fallback if the format is unexpected

def callApiWithGrant(client, grant):
    #TODO ADD ALL GRANT INFO FOR EACH

    def millions(amount):
        try:
            amt = float(amount)
            if amt >= 1_000_000:
                millions_value = amt / 1_000_000
                if millions_value.is_integer():
                    return f"${int(millions_value)} million"
                else:
                    return f"${millions_value:.1f} million"
            else:
                return f"${int(amt):,}"
        except:
            return "an unspecified amount"


    award_floor = millions(grant.get("AwardFloor", 0))
    award_ceiling = millions(grant.get("AwardCeiling", 0))
    total_funding = millions(grant.get("EstimatedTotalProgramFunding", 0))
    agency = grant.get("AgencyName", "N/A")
    opportunity_id = grant.get("OpportunityID", "N/A")
    opportunity_title = grant.get("OpportunityTitle", "N/A")
    close_date = grant.get("CloseDate", "N/A")
    expected_awards = grant.get("ExpectedNumberOfAwards", "an unspecified number")
    eligibility = grant.get("AdditionalInformationOnEligibility", "Eligibility details not specified.")
    description = grant.get("Description", "No description provided.")
    OpportunityNumber = grant.get("OpportunityNumber", "N/A")

    prompt =  f"""
    Create a news story of up to 300 words with a headline based on the following federal grant opportunity. Use the acronym of {agency} in the headline.

    Title: {opportunity_title}

    Issued by: {agency}

    The grant offers funding ranging from {award_floor} to {award_ceiling}, with an estimated total program funding of {total_funding}. The agency expects to make {expected_awards} award(s).

    Eligible applicants: {eligibility}

    Description: {description}

    Do not use the words “significant,” “forthcoming,” or “extensive.” Do not include a dateline or use the word “new” in front of “grant.” If the agency begins with “Department,” insert “U.S.” in front of it. Refer to millions using a single decimal point (e.g., $3.5 million). Use the acronym of {agency} in the headline instead of the full name of the agency.

    """

    try:
        # Generate main press release
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2500
        )
        result = response.choices[0].message.content.strip()
        parts = result.split('\n', 1)

        if len(parts) != 2:
            # TODO: ADD LOG MESSAGE HERE
            print(f"Headline Wasnt Parsed Right")
            return None, None, None 

        headline_raw = parts[0]
        body_raw = parts[1]

        today_date = get_body_date()
        story = f"WASHINGTON, {today_date} -- {body_raw.strip()}"
        close_date = format_grant_date(close_date)
        story += f"\n\nThe deadline for application is {close_date}. The funding opportunity number is {OpportunityNumber}"
        story += f"\n\n* * *\n\nView grant announcement here: https://www.grants.gov/search-results-detail/{opportunity_id}"

        # getting rid of stray input from gpt and turning all text into ASCII charectors for DB
        headline = clean_text(headline_raw)
        headline = cleanup_text(headline)

        story = clean_text(story)
        story = cleanup_text(story)
        
        return headline, story

    except Exception as e:
        print(f"OpenAI API error: {e}")
        return "NA", None, None 