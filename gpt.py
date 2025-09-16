import re
import logging
import platform
from openai import OpenAI
from datetime import datetime
from cleanup_text import cleanup_text, clean_text, TNS_clean

# gets the api keys
def getKey():
    """Retrieves the OpenAI API key from a file."""
    try:
        with open("utils/key.txt", "r") as file:
            return file.readline().strip()
    except FileNotFoundError:
        logging.info("File not found!")
    except PermissionError:
        logging.info("You don't have permission to access this file.")
    except IOError as e:
        logging.info(f"An I/O error occurred: {e}")

# makes the date that goes after "WASHINGTON --"
def get_body_date():
    today = datetime.today()
    month = today.strftime('%B') 
    short_month = today.strftime('%b')
    formatted_month = month if len(month) <= 5 else short_month + "."

    # Special case for September
    if month == "September":
        formatted_month = "Sept."

    day_format = '%-d' if platform.system() != 'Windows' else '%#d'
    return f"{formatted_month} {today.strftime(day_format)}"

# turns grant date into a TNS approved format
def format_grant_date(date_str):
    """Convert a date like '07222025' to '7/22/25'."""
    try:
        date = datetime.strptime(date_str, "%m%d%Y")
        return f"{date.month}/{date.day}/{str(date.year)[-2:]}"
    except Exception:
        return date_str  # fallback if the format is unexpected

# gets the parent govenrment agency to put into report
def get_parent_agency_abbreviation(agency_code):
    """
    Extracts the parent agency abbreviation from an AgencyCode.
    Example: 'DOI-BLM' -> 'DOI'
    """
    if not agency_code or '-' not in agency_code:
        return None
    return agency_code.split('-')[0]

# calls GPT to summarize grant info
def callApiWithGrant(client, grant):
    # converts dollar amount into TNS specified format
    def millions(amount):
        try:
            amt = float(amount)
            if amt >= 1_000_000:
                millions_value = amt / 1_000_000
                return f"${int(millions_value)} million" if millions_value.is_integer() else f"${millions_value:.1f} million"
            elif amt >= 0:
                return f"${int(amt):,}"
        except:
            pass
        return None  # Return None if formatting fails

    # Get attributes from grant
    agency = grant.get("AgencyName")
    opportunity_id = grant.get("OpportunityID")
    opportunity_title = grant.get("OpportunityTitle")
    OpportunityNumber = grant.get("OpportunityNumber")
    AgencyCode = grant.get("AgencyCode")

    # checking to see if agency is all caps (if so make only first letter capitalized)
    if agency.isupper():
        agency = agency.title()

    # Required fields — return None if missing
    if not all([agency, opportunity_id, opportunity_title, OpportunityNumber, AgencyCode]):
        return None, None

    # Optional fields
    award_floor_val = grant.get("AwardFloor")
    award_ceiling_val = grant.get("AwardCeiling")
    total_funding_val = grant.get("EstimatedTotalProgramFunding")
    expected_awards = grant.get("ExpectedNumberOfAwards", 1)
    eligibility = grant.get("AdditionalInformationOnEligibility")
    description = grant.get("Description")
    close_date = grant.get("CloseDate", "No close date provided.")

    # Format amounts
    award_floor = millions(award_floor_val)
    award_ceiling = millions(award_ceiling_val)
    total_funding = millions(total_funding_val)

    # Estimate total funding if missing but ceiling is available
    if total_funding is None and award_ceiling_val is not None:
        try:
            total_funding_est = expected_awards * float(award_ceiling_val)
            total_funding = millions(total_funding_est)
        except:
            total_funding = None

    # Get acronym from agency code
    acronym = get_parent_agency_abbreviation(AgencyCode)

    # DOS -> The State Department
    if acronym == "DOS":
        acronym = "State Departement"
    
    # Build the details block conditionally (I found this gave more consistant GPT outputs)
    details = f"- Title: {opportunity_title}\n"

    try:
        floor_val = float(award_floor_val)
    except:
        floor_val = None

    if floor_val and award_ceiling:
        details += f"- Award range: {award_floor} to {award_ceiling}\n"
    elif floor_val and floor_val > 0:
        details += f"- Award floor: {award_floor}\n"
    elif award_ceiling:
        details += f"- Award ceiling: {award_ceiling}\n"
        if total_funding:
            details += f"- Estimated total funding: {total_funding}\n"
        if expected_awards:
            details += f"- Expected number of awards: {expected_awards}\n"
        if eligibility:
            details += f"- Eligible applicants: {eligibility}\n"
        if description:
            details += f"- Description: {description}\n"

    # commenting out so that gpt doesnt use close date
    
    # readable_close = datetime.strptime(close_date, "%m%d%Y").strftime("%B %d, %Y")
    # details += f"- Application deadline: {readable_close}\n"

    # Construct final prompt

    # making headline prompt and first paragraph modular based off of whether the child and parent agencuy are the same
    if acronym:
        headline_prompt = f"Use the acronym of the parent agency '{acronym}' in the headline (not the full name), you can also mention the child agency '{agency}'. If the agency represented by the acroynm and the child agency are the same, only mention the child agency."
        first_paragraph_prompt = f"""
        - the fully spelled-out parent agency (based on the acronym {acronym})
        - the exact child agency name: {agency}
        """
    else:
        headline_prompt = f"Create and use an acronym based on the full agency name '{agency}' in the headline (not the full name)."
        first_paragraph_prompt = f"- the exact agency name: {agency}"

    prompt = f"""
Write a news story of up to 300 words with a headline based on the following federal grant opportunity.
{headline_prompt}

The headline should:
- Avoid any introductory phrases like “Funding Alert,” “Grant Notice,” or “Breaking:”
- Be clear, descriptive, and written in a professional journalistic tone
- Focus on the agency and the purpose or target of the grant

In the first paragraph, naturally introduce the grant by identifying:
{first_paragraph_prompt}

For example: "The U.S. Department of State, through its Bureau of Educational and Cultural Affairs, has announced..."

Do not use a rigid structure like "X agency issued the following grant." Instead, write in the style of a professional news brief.

Use the following details in the article:
{details}
Guidelines:
- Spell out the parent agency from its acronym. If it begins with "Department", prepend "U.S." (e.g., "U.S. Department of Energy").
- Use the **exact agency name** "{agency}" when referring to the child agency. Do **not** substitute it with a different bureau or inferred entity.
- Refer to dollar amounts in millions with a single decimal point if applicable (e.g., "$2.5 million").
- Do not use the words “significant,” “forthcoming,” “extensive,” or “new”.
- Do not include a dateline.
- Do not mention deadlines
""".strip()
    
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
            logging.info(f"Headline Wasnt Parsed Right")
            return None, None 

        # getting both the headline and body
        headline_raw = parts[0]
        body_raw = parts[1]

        today_date = get_body_date()
        story = f"WASHINGTON, {today_date} -- {body_raw.strip()}"
        close_date = format_grant_date(close_date)
        story += f"\n\nThe deadline for application is {close_date}. The funding opportunity number is {OpportunityNumber}."
        story += f"\n\n* * *\n\nView grant announcement here: https://www.grants.gov/search-results-detail/{opportunity_id}"

        # getting rid of stray input from gpt and turning all text into ASCII charectors for DB
        headline = clean_text(headline_raw)
        headline = cleanup_text(headline)

        story = clean_text(story)
        story = cleanup_text(story)
        
        # cleaning text via TNS editors instructions
        headline = TNS_clean(headline)
        story = TNS_clean(story)
        
        return headline, story

    except Exception as e:
        logging.info(f"OpenAI API error: {e}")
        return None, None 