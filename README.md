# Grants.gov Daily Scraper and Story Generator

This project automates the process of downloading, parsing, and processing federal grants posted on [Grants.gov](https://www.grants.gov). It scrapes grant listings posted **yesterday**, generates news-style headlines and summaries using OpenAI's GPT API, and either exports the results to a CSV file for review or inserts them into a MySQL database with proper tagging for production use.

## Features

- Downloads the most recent Grants.gov XML data file.
- Extracts grants posted on the previous day.
- Uses OpenAI to generate a headline and news-style article for each grant.
- Supports both test and production modes:
  - **Test mode (`-t`)**: Outputs results to a CSV file (`grant_stories.csv`) for manual review.
  - **Production mode (`-p`)**: Inserts records into a database with tags for applicant type, funding category, and funding type.
- Sends a summary email with a log file after each run.

## Command-Line Usage

```bash
python main.py -t        # Test run: outputs to CSV
python main.py -p        # Production run: inserts into DB
python main.py -p -t     # Runs both modes
```

## Dependencies

-   Python 3.9+

-   [openai](https://pypi.org/project/openai/)

-   [beautifulsoup4](https://pypi.org/project/beautifulsoup4/)

-   [requests](https://pypi.org/project/requests/)

-   [lxml](https://pypi.org/project/lxml/) (optional, but recommended for faster XML parsing)

-   A valid OpenAI API key stored in `utils/key.txt`

-   MySQL database and `db_functions.py` for DB connectivity

-   SMTP credentials for sending email reports

## File Structure


-   `main.py` --- Orchestrates the full workflow.

-   `grants.py` --- Handles XML download, parsing, and tagging.

-   `gpt.py` --- Handles GPT prompt construction and API calls.

-   `email_utils.py` --- Sends summary email with log attachment.

-   `db_functions.py` --- Handles database inserts (not included here).

-   `utils/key.txt` --- Contains your OpenAI API key.

## Output


In test mode:

-   Outputs a CSV file with columns: `Filename`, `Headline`, `Story Text`.

In production mode:

-   Inserts generated stories into a database with proper tagging.

-   Tagging includes:

    -   Applicant types

    -   Funding categories

    -   Funding instrument type (Grant, Cooperative Agreement, etc.)

## Logging and Reporting


Each run generates a timestamped log file (e.g., `scrape_log.2025-06-30_12-00-00.log`) and sends a summary email with the log attached.

## Notes

-   The scraper filters grants based on their `PostDate`, checking only those posted **yesterday**.

-   GPT-generated headlines and summaries follow strict editorial guidelines to ensure clarity, professionalism, and consistency with TNS formatting.

## Author

Bailey Malota\
*Last updated: June 30, 2025*