import io
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
    return (datetime.now() - timedelta(days=1)).strftime("%m%d%Y")


# returns a list of dicts that contains all needed info for each grant
def parse_yesterdays_grants(file):
    ns = {"ns": "http://apply.grants.gov/system/OpportunityDetail-V1.0"}
    tree = ET.parse(file)
    root = tree.getroot()
    yesterday = get_yesterdays_date()
    grants = []

    for opp in root.findall("ns:OpportunitySynopsisDetail_1_0", ns):
        post_date = opp.find("ns:PostDate", ns)
        if post_date is not None and post_date.text == yesterday:
            grant_data = {
                "OpportunityID": opp.findtext("ns:OpportunityID", default="", namespaces=ns),
                "OpportunityNumber": opp.findtext("ns:OpportunityNumber", default="", namespaces=ns),
                "OpportunityTitle": opp.findtext("ns:OpportunityTitle", default="", namespaces=ns),
                "AgencyName": opp.findtext("ns:AgencyName", default="", namespaces=ns),
                "Description": opp.findtext("ns:Description", default="", namespaces=ns),
                "AwardCeiling": opp.findtext("ns:AwardCeiling", default="", namespaces=ns),
                "AwardFloor": opp.findtext("ns:AwardFloor", default="", namespaces=ns),
                "EstimatedTotalProgramFunding": opp.findtext("ns:EstimatedTotalProgramFunding", default="", namespaces=ns),
                "ExpectedNumberOfAwards": opp.findtext("ns:ExpectedNumberOfAwards", default="", namespaces=ns),
                "AdditionalInformationOnEligibility": opp.findtext("ns:AdditionalInformationOnEligibility", default="", namespaces=ns),
                "CloseDate": opp.findtext("ns:CloseDate", default="", namespaces=ns),
            }
            grants.append(grant_data)
    
    return grants


# gets the filename for an individual grant
def generate_filename(grant: dict):
    date = datetime.now().strftime("%y%m%d")
    return f"$H {date}-grants-{grant["OpportunityNumber"]}"
