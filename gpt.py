import re
import logging
import platform
from openai import OpenAI
from datetime import datetime
from cleanup_text import cleanup_text, clean_text, TNS_clean, clean_headline, suppress_dod_reference, strip_page_references

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
    # Surface the announcement URL so editors have a one-click path to the source (QA 06/13).
    opp_id = grant.get("OpportunityID", "")
    if opp_id:
        lines.append(f"Announcement URL: https://www.grants.gov/search-results-detail/{opp_id}")
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
    """Convert a date like '07202026' to 'July 20, 2026'."""
    # Handle empty or None strings
    if not date_str or date_str == "None":
        return "to be determined"

    try:
        date = datetime.strptime(date_str, "%m%d%Y")
        # No-leading-zero day, platform-specific like get_body_date: "July 20, 2026".
        day_format = '%-d' if platform.system() != 'Windows' else '%#d'
        return f"{date.strftime('%B')} {date.strftime(day_format)}, {date.year}"
    except Exception:
        return "to be determined"  # fallback for invalid dates

# Last-resort deadline recovery (QA 06/13, doc 1864800): when the structured close-date
# field is empty, the date may only exist in the announcement free text. Pull a date out
# of that text, but only when it sits right after a closing cue ("due by Aug. 31, 2026")
# so we don't grab a start date or some other unrelated date.
_DATE_IN_TEXT = re.compile(
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+"
    r"(\d{1,2}),?\s+(\d{4})", re.IGNORECASE,
)
_CLOSE_CUE = re.compile(r"clos|deadline|due|submit|application", re.IGNORECASE)

def extract_close_date_from_text(text):
    """Return MMDDYYYY for a date within ~60 chars after a closing cue, else ''."""
    if not text:
        return ""
    months = {  # abbrev prefix -> month number
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    for m in _DATE_IN_TEXT.finditer(text):
        window = text[max(0, m.start() - 60):m.start()]
        if _CLOSE_CUE.search(window):
            mon = months[m.group(1)[:3].lower()]
            return f"{mon:02d}{int(m.group(2)):02d}{m.group(3)}"
    return ""

# TNS rule (BM): a grant whose application window closes within a week is stale news by
# the time the story runs, so it is dropped rather than loaded.
MIN_DAYS_TO_DEADLINE = 7

# resolves the application deadline: structured CloseDate, then the forecast's estimated
# close date, then a last-resort scrape of the announcement free text.
def resolve_close_date(grant):
    """Return the grant's deadline as MMDDYYYY, or '' when no deadline can be found."""
    close_date = grant.get("CloseDate", "")

    # For forecasted grants, use EstimatedSynopsisCloseDate if CloseDate is empty
    if grant.get("IsForecasted", False) and (not close_date or close_date == "None"):
        close_date = grant.get("EstimatedSynopsisCloseDate", "")

    # Last resort: pull the deadline out of the announcement text (QA 06/13, doc 1864800).
    if not close_date or close_date == "None":
        close_date = extract_close_date_from_text(grant.get("Description"))

    return close_date or ""

# returns True if the grant's deadline is fewer than MIN_DAYS_TO_DEADLINE days away
def deadline_too_soon(grant):
    """True when the deadline is under a week out (or already past).

    A grant with no resolvable deadline is kept: the story prints "to be determined"
    rather than a bad date, and dropping it would lose legitimate open-ended grants.
    """
    close_date = resolve_close_date(grant)
    if not close_date:
        return False

    try:
        deadline = datetime.strptime(close_date, "%m%d%Y").date()
    except ValueError:
        return False  # unparseable date -> same fallback as a missing one

    return (deadline - datetime.today().date()).days < MIN_DAYS_TO_DEADLINE

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

# Grants.gov often tacks an internal office code onto the child agency name
# ("Administration for Children and Families - ACYF/CB") or names a headquarters
# ("NASA Headquarters"). TNS wants the plain agency in the lede (QA 07/14), so drop
# both before the name is ever shown to GPT.
def normalize_child_agency_name(name):
    """Strip a trailing '- OFFICECODE' suffix and a trailing 'Headquarters'."""
    if not name:
        return name
    # Drop a trailing " - CODE" office suffix. Only an all-caps/code-like token is
    # removed (e.g. "- ACYF/CB", "- OJP"); a descriptive tail like "- GOM Region"
    # contains lowercase letters and is left intact.
    name = re.sub(r"\s*[-–—]\s*[A-Z0-9][A-Z0-9&/.\-]*\s*$", "", name)
    # "NASA Headquarters" -> "NASA": a headquarters is not a distinct child agency.
    name = re.sub(r"\s+Headquarters\s*$", "", name, flags=re.IGNORECASE)
    return name.strip()

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

    # Drop office-code suffixes and "Headquarters" so the lede names the plain agency
    # ("Administration for Children and Families", "NASA") -- QA 07/14.
    agency = normalize_child_agency_name(agency)

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
    close_date = resolve_close_date(grant)

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
        # TNS rule (06/16): NASA is the one agency that is never spelled out, so the
        # "spell out the parent agency" instruction has to be suppressed for it.
        if acronym == "NASA":
            first_paragraph_prompt = f"""
        - the parent agency as "NASA" -- never spell out "National Aeronautics and Space Administration"
        - the exact agency name: {agency}
        """
        else:
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
- Describe the agency's action using EXACTLY ONE of these five approved phrases and no other verb: "invites proposals," "opens funding," "accepts applications," "seeks proposals," or "seeks applications." Choose the phrase that best fits the grant (e.g. a research or construction grant "seeks proposals"; a scholarship or fellowship "accepts applications"). You may follow the phrase with "for" and the purpose (e.g. "seeks proposals for..."). Use the phrase in the present tense exactly as written -- do NOT add the auxiliary "is" or "are" (write "accepts applications," never "is accepting applications"), and do NOT substitute a synonym ("solicits," "offers," "provides," "requests," "announces," "grants," "awards," "funded," etc. are all disallowed)
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
- Spell out the parent agency from its acronym. If it begins with "Department", prepend "U.S." (e.g., "U.S. Department of Energy"). The one exception is NASA: always write "NASA" and never spell out "National Aeronautics and Space Administration", in the headline or the story.
- Use the **exact agency name** "{agency}" when referring to the child agency. Do **not** substitute it with a different bureau or inferred entity, and do **not** append a parenthetical acronym or office code after it (write "Administration for Children and Families," never "Administration for Children and Families (ACF)" or "... - ACYF/CB").
- Refer to dollar amounts in millions with a single decimal point if applicable (e.g., "$2.5 million").
- If the grant title or any phrase in the details is written in ALL CAPITAL LETTERS, rewrite it in standard title case in both the headline and the story (e.g., "PROGRAM FOR INVESTMENT IN MICROENTREPRENEURS" becomes "Program for Investment in Microentrepreneurs"). Keep genuine acronyms and abbreviations capitalized (e.g., NASA, PRIME, FY, U.S.).
- Do not reference or name any presidential administration or attribute the program to one (never write "the Biden Administration," "the Trump Administration," or "the administration's commitment to ..."). Report only the agency and the opportunity.
- Do not editorialize or end with a call to action. Never encourage, invite, or urge anyone to apply, prepare, or submit; never write that applicants are "encouraged to" do something, that an agency "looks forward to receiving" proposals, or that readers should "join" the agency's mission. Simply report the facts of the opportunity and stop.
- Do not use the words “significant,” “forthcoming,” “extensive,” or “new”.
- Do not include a dateline.
- Do not mention deadlines
- Do not refer the reader to a page, section, or attachment for information (never write phrases like "see page X," "on pages 2 to 3," or "of the announcement package"). State eligibility and other details directly; if a detail is only available as a page reference, omit it.
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
        # A concrete date is a real deadline even for a forecast; only call it
        # "estimated" when the forecast gives no specific date (QA doc 1869503).
        has_specific_date = close_date != "to be determined"
        deadline_label = "deadline" if (has_specific_date or not is_forecasted) else "estimated deadline"
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

        # drop any "see page X of the announcement package" sentence (QA 06/13)
        story = strip_page_references(story)

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