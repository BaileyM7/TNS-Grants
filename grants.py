import os
import io
import logging
import zipfile
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

BASE_URL = "https://www.grants.gov/xml-extract"

# gets yesterdays xml file of the grants DB
def get_yesterday_zip_url():
    response = requests.get(BASE_URL)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    yesterday = datetime.now().strftime("GrantsDBExtract%Y%m%dv2.zip")

    # Find the anchor tag with yesterday's zip filename
    for a in soup.find_all("a"):
        if a.text.strip() == yesterday:
            return a['href']
    
    logging.info("Yerterdays xml file not found")
    raise Exception(f"No file found for {yesterday}")

# downloads the xml of the grants DB
def download_and_extract_zip(zip_url):
    print(f"Downloading: {zip_url}")
    response = requests.get(zip_url)
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        z.extractall()
        return z.namelist()[0]

# getting yesterdays date for getting yesterdays posted grants
def get_yesterdays_date():
    """Returns yesterday's date as MMDDYYYY string"""
    return (datetime.now() - timedelta(days=3)).strftime("%m%d%Y")

# returns the full child agency name (used it name gets truncated due to being to long)
def get_full_child_agency_name(agency_code):

    # dictionary of known issue agencies that are too long
    agency_name_patches = {
    "HHS-SAMHS-SAMHSA": "Substance Abuse and Mental Health Services Administration"
    }

    if agency_code in agency_name_patches:
        return agency_name_patches[agency_code]
    else:
        return None

# returns a list of dicts that contains all needed info for each grant
def parse_yesterdays_grants(file):
    ns = {"ns": "http://apply.grants.gov/system/OpportunityDetail-V1.0"}
    tree = ET.parse(file)
    root = tree.getroot()
    yesterday = get_yesterdays_date()
    grants = []
    
    try: 
        # looks through every grant in the file
        for opp in root.findall("ns:OpportunitySynopsisDetail_1_0", ns):
            post_date = opp.find("ns:PostDate", ns)

            # if the grant was posted yesterday, then it grabs its data
            if post_date is not None and post_date.text == yesterday:

                # creates a dict holding all needed info for a grant
                grant_data = {
                    "OpportunityID": opp.findtext("ns:OpportunityID", default="", namespaces=ns),
                    "OpportunityNumber": opp.findtext("ns:OpportunityNumber", default="", namespaces=ns),
                    "OpportunityTitle": opp.findtext("ns:OpportunityTitle", default="", namespaces=ns),
                    "AgencyCode": opp.findtext("ns:AgencyCode", default="", namespaces=ns),
                    "AgencyName": opp.findtext("ns:AgencyName", default="", namespaces=ns),
                    "Description": opp.findtext("ns:Description", default="", namespaces=ns),
                    "AwardCeiling": opp.findtext("ns:AwardCeiling", default="", namespaces=ns),
                    "AwardFloor": opp.findtext("ns:AwardFloor", default="", namespaces=ns),
                    "EstimatedTotalProgramFunding": opp.findtext("ns:EstimatedTotalProgramFunding", default="", namespaces=ns),
                    "ExpectedNumberOfAwards": opp.findtext("ns:ExpectedNumberOfAwards", default="", namespaces=ns),
                    "AdditionalInformationOnEligibility": opp.findtext("ns:AdditionalInformationOnEligibility", default="", namespaces=ns),
                    "CloseDate": opp.findtext("ns:CloseDate", default="", namespaces=ns),
                    "EligibleApplicants": [e.text for e in opp.findall("ns:EligibleApplicants", ns)],
                    "CategoryOfFundingActivity": [c.text for c in opp.findall("ns:CategoryOfFundingActivity", ns)],
                    "FundingInstrumentType": opp.findtext("ns:FundingInstrumentType", default="", namespaces=ns),
                }
                
                if len(grant_data["AgencyName"]) == 50 and get_full_child_agency_name(grant_data["AgencyCode"]):
                    grant_data["AgencyName"] = get_full_child_agency_name(grant_data["AgencyCode"])

                grants.append(grant_data)
            
    except Exception as e:
        logging.info("Hit error when parsing grants {e}")

    # print(grants)
    # returns a list of dictionaries containing info from all the grants
    return grants

# gets the filename for an individual grant
def generate_filename(grant: dict):
    date = datetime.now().strftime("%y%m%d")
    return f"$H {date}-grants-{grant["OpportunityNumber"]}"

# deletes the file
def delete_file(file_path):
    # Deletes the given file from the filesystem.
    try:
        os.remove(file_path)
        print(f"Deleted file: {file_path}")
    except OSError as e:
        print(f"Error deleting file {file_path}: {e}")

# returns the proper tagging for applicants tags for story insert
def get_applicants_tags(grant):
    tags = []

    # all the categories from the xml file transformed into TNS table equivilants
    applicant_types = {
        "99": 54,
        "00": 35,   
        "01": 32,  
        "02": 32,  
        "04": 33,   
        "05": 37,   
        "06": 36,   
        "07": 34,   
        "08": 46,   
        "11": 34,   
        "12": 43,   
        "13": 42,   
        "20": 36,  
        "21": 56,   
        "22": 44,
        "23": 45,   
        "25": 56,   
    }

    # adding every tag found to to the tags array
    for applicant in grant["EligibleApplicants"]:
        # add corresponding tag
        if applicant in applicant_types:
            tags.append(applicant_types[applicant])
        # if the tagt isnt found, just add "other"
        else:
            tags.append(applicant_types["25"])
    
    return tags

# gets the funding catergory tagging for the story insert
def get_funding_category_tags(grant):
    # list of found tags
    tags = []

    # categories with their corresponding story id tags
    """
    Current Unknowns: (what should I do with these????)
        "AR": "Arts",
        "RA": "Recovery Act",
    """
    table = {
        "ACA": 121,
        "AG": 120,
        "BC": 2,
        "CD": 122,
        "CP": 123,
        "DPR": 7,
        "ED": 9,
        "ELT": 124,
        "EN": 11,
        "ENV": 12,
        "FN": 125,
        "HL": 15,
        "HO": 64,
        "HU": 127,
        "ISS": 25,
        "IS": 128,
        "LJL": 17,
        "NR": 129,
        "RD": 130,
        "ST": 24,
        "T": 65,
        "O": 56
    } 

    # adding every tag
    for category in grant["CategoryOfFundingActivity"]:
        # if found as a category, add it
        if category in table:
            tags.append(table[category])
        # if its not found, add as other
        else: 
            tags.append(table["O"])

    # returns an array of tags for each grant to be inserted
    return tags

# gets the funding category and correlates it to the TNS table story instert tagging
def get_funding_type(grant):

    category = {
    "G": 62,   # Grant
    "CA": 59,  # Cooperative Agreement
    "O": 61, # Other — Maybe an award?
}
    # if in table, return its corresponding TNS tag match
    if grant["FundingInstrumentType"] in category:
        return category[grant["FundingInstrumentType"]]
    # if not in table, return award
    else:
        return 61
