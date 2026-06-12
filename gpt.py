import re
import logging
import platform
from openai import OpenAI
from datetime import datetime
from cleanup_text import cleanup_text, clean_text, TNS_clean, clean_headline, suppress_dod_reference

# Raw parent acronyms (from AgencyCode) that TNS writes differently in headlines.
# Agencies not listed here are used as-is. Extend as new agencies appear.
ACRONYM_OVERRIDES = {
    "USDOT": "DOT",   # QA: "It's just DOT."
    "USDOJ": "DOJ",   # QA: "It's just DOJ."
    "ED": "DE",       # QA: Dept. of Education is "DE"; "DOE" means Dept. of Energy.
}

# builds the orig_txt audit value: every scraped grant field + the exact GPT prompt
def build_original_text(grant, prompt):
    """orig_txt = a labeled dump of every scraped grant field, then the GPT prompt."""
    lines = ["=== ORIGINAL GRANT DATA (scraped from Grants.gov) ==="]
    for key, value in grant.items():
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value if v is not None)
        lines.append(f"{key}: {value}")
    lines.append("")
    lines.append("=== GPT PROMPT ===")
    lines.append(prompt)
    return cleanup_text("\n".join(lines))  # ASCII-safe for the TNS DB

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
    # Handle empty or None strings
    if not date_str or date_str == "None":
        return "to be determined"

    try:
        date = datetime.strptime(date_str, "%m%d%Y")
        return f"{date.month}/{date.day}/{str(date.year)[-2:]}"
    except Exception:
        return "to be determined"  # fallback for invalid dates

# gets the parent govenrment agency to put into report
def get_parent_agency_abbreviation(agency_code):
    """
    Extracts the parent agency abbreviation from an AgencyCode.
    Example: 'DOI-BLM' -> 'DOI', 'ED' -> 'ED'
    """
    if not agency_code:
        return None
    # A dash-less code (e.g. 'ED') is itself the parent acronym.
    return agency_code.split('-')[0]

# DoD service branches are written as "U.S. Army"/"U.S. Navy"/"U.S. Air Force" and
# never alongside a "Department of Defense"/"DOD" reference (TNS editor rule). Note:
# defense-wide agencies (DARPA, DLA, etc.) are NOT branches and keep their DOD framing.
def get_service_branch(agency_name):
    """Return the branch label if the agency name identifies a service branch, else None.
    Order matters: 'air force' is checked before the broader keywords."""
    name = (agency_name or "").lower()
    if "air force" in name:
        return "U.S. Air Force"
    if "navy" in name or "naval" in name:
        return "U.S. Navy"
    if "army" in name:
        return "U.S. Army"
    return None

# strips a leading "Dept. of the Army --" style prefix, leaving the command/office
def get_branch_office(agency_name):
    """'Dept of the Army -- Materiel Command' -> 'Materiel Command'.
    Returns '' when the name is just the branch with no specific office."""
    office = re.sub(
        r"^\s*(?:U\.S\.\s+)?(?:Department|Dept\.?)\s+of\s+the\s+(?:Army|Navy|Air Force)\s*",
        "", agency_name or "", flags=re.IGNORECASE,
    )
    office = office.strip(" -–—:|")
    return "" if office.lower() in ("", "army", "navy", "air force") else office

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
        return None, None, None

    # Optional fields
    award_floor_val = grant.get("AwardFloor")
    award_ceiling_val = grant.get("AwardCeiling")
    total_funding_val = grant.get("EstimatedTotalProgramFunding")
    expected_awards = grant.get("ExpectedNumberOfAwards", 1)
    eligibility = grant.get("AdditionalInformationOnEligibility")
    description = grant.get("Description")
    is_forecasted = grant.get("IsForecasted", False)
    close_date = grant.get("CloseDate", "")

    # For forecasted grants, use EstimatedSynopsisCloseDate if CloseDate is empty
    if is_forecasted and (not close_date or close_date == "None"):
        close_date = grant.get("EstimatedSynopsisCloseDate", "")

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
    raw_acronym = get_parent_agency_abbreviation(AgencyCode)

    # Strip redundant parent-acronym prefix when XML embeds it in AgencyName
    # (e.g. "DOC National Oceanic..." -> "National Oceanic...")
    if raw_acronym and agency.startswith(f"{raw_acronym} "):
        agency = agency[len(raw_acronym) + 1:]

    # State Department (and its missions/bureaus): headline shows only the parent "State Dept."
    is_state_dept = raw_acronym == "DOS"

    # Apply TNS headline acronym conventions (e.g. USDOT -> DOT, USDOJ -> DOJ)
    acronym = ACRONYM_OVERRIDES.get(raw_acronym, raw_acronym)

    # DoD service branches (Army/Navy/Air Force) drop the DOD framing entirely and
    # lead with the branch + its command. Only DOD-parented grants are considered.
    service_branch = get_service_branch(agency) if raw_acronym == "DOD" else None
    branch_office = get_branch_office(agency) if service_branch else ""
    if service_branch:
        # Downstream "exact agency name" becomes the clean branch form, e.g.
        # "U.S. Army Materiel Command" -- never "Dept of the Army -- ...".
        agency = f"{service_branch} {branch_office}".strip() if branch_office else service_branch

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
    if is_state_dept:
        # State Department grants: only the parent "State Dept." belongs in the headline.
        headline_prompt = (
            'Begin the headline with "State Dept." Do not mention any bureau, mission, '
            "or child agency in the headline."
        )
        first_paragraph_prompt = "- the agency, referred to as the State Dept. (the U.S. Department of State)"
    elif service_branch:
        # Army/Navy/Air Force: lead with the branch (+ its command) and never
        # reference the Department of Defense anywhere in the story (TNS rule).
        if branch_office:
            headline_prompt = (
                f'Begin the headline with "{service_branch}," then name its specific '
                f'command "{branch_office}." '
            )
        else:
            headline_prompt = f'Begin the headline with "{service_branch}." '
        headline_prompt += (
            'Do not mention the Department of Defense, "DOD," or "DoD" anywhere in the '
            "headline or story."
        )
        first_paragraph_prompt = (
            f"- the agency as the {service_branch}"
            + (f", through its {branch_office}" if branch_office else "")
        )
    elif acronym:
        # GPT tends to abbreviate "Department of Education" as DOE, but DOE is the
        # Department of Energy. TNS wants "DE" for Education, so call it out explicitly.
        ed_note = ""
        if acronym == "DE":
            ed_note = (
                " Note: 'DE' is the U.S. Department of Education; always use 'DE' and never "
                "'DOE' or 'ED'. ('DOE' refers to the Department of Energy.)"
            )
        headline_prompt = (
            f"Begin the headline with the parent agency acronym '{acronym}' (not the full name). "
            f"You may also mention the agency '{agency}'. If '{acronym}' and '{agency}' refer to "
            f"the same entity, mention only '{agency}'.{ed_note}"
        )
        first_paragraph_prompt = f"""
        - the fully spelled-out parent agency (based on the acronym {acronym})
        - the exact agency name: {agency}
        """
    else:
        headline_prompt = (
            f"Begin the headline with an acronym you create from the full agency name "
            f"'{agency}' (not the full name)."
        )
        first_paragraph_prompt = f"- the exact agency name: {agency}"

    prompt = f"""
Write a news story of up to 300 words with a headline based on the following federal grant opportunity.
{headline_prompt}

The headline should:
- Start with the agency name or acronym (the agency must be the first thing in the headline)
- Use a simple present-tense active verb for the agency's action (e.g. "seeks," "accepts applications for," "opens funding for," "invites proposals for") so the opportunity reads as currently open. Do NOT use the auxiliary "is" or "are" before an "-ing" verb -- write "accepts applications for," never "is accepting applications for." Do not use verbs that imply the funding is already distributed or the opportunity has closed (e.g. "grants," "awards," "awarded," "funded," "gave")
- Avoid any introductory phrases like “Funding Alert,” “Grant Notice,” or “Breaking:”
- Be clear, descriptive, and written in a professional journalistic tone
- Focus on the agency and the purpose or target of the grant
- Not contain parentheses
- Not use possessive apostrophes on agency names (write "USDA Rural Utilities Service," not "USDA's Rural Utilities Service")
- Write acronyms without periods (write "DOE," not "D.O.E.")

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

    # build the orig_txt audit trail (raw scraped grant data + the exact prompt)
    orig_txt = build_original_text(grant, prompt)

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
            return None, None, None

        # getting both the headline and body
        headline_raw = parts[0]
        body_raw = parts[1]

        today_date = get_body_date()
        story = f"WASHINGTON, {today_date} -- {body_raw.strip()}"
        close_date = format_grant_date(close_date)
        deadline_label = "estimated deadline" if is_forecasted else "deadline"
        story += f"\n\nThe {deadline_label} for application is {close_date}. The funding opportunity number is {OpportunityNumber}."
        story += f"\n\n* * *\n\nView grant announcement here: https://www.grants.gov/search-results-detail/{opportunity_id}"

        # getting rid of stray input from gpt and turning all text into ASCII charectors for DB
        headline = clean_text(headline_raw)
        headline = cleanup_text(headline)

        story = clean_text(story)
        story = cleanup_text(story)
        
        # cleaning text via TNS editors instructions
        headline = TNS_clean(headline)
        story = TNS_clean(story)

        # enforce TNS headline-only conventions deterministically (no periods in
        # acronyms, no parentheses, no possessives, "State Dept.", ED not DOE, etc.)
        headline = clean_headline(headline, expected_acronym=acronym)

        # Army/Navy/Air Force: strip any lingering DOD reference, replacing it with the
        # branch (belt-and-suspenders behind the prompt's "do not mention DOD" instruction).
        if service_branch:
            headline = suppress_dod_reference(headline, service_branch)
            story = suppress_dod_reference(story, service_branch)

        return headline, story, orig_txt

    except Exception as e:
        logging.info(f"OpenAI API error: {e}")
        return None, None, None