# Grants.gov Daily Scraper and Story Generator

This project automates the process of downloading, parsing, and summarizing new federal grants posted on [Grants.gov](https://www.grants.gov). It filters grants by those posted **yesterday**, uses OpenAI's GPT API to generate news-style headlines and summaries, and either saves the results to a CSV file for review or inserts them into a MySQL database for production use. A log report is sent via email after each run.

---

## 🚀 Features

* Downloads the latest Grants.gov XML data dump.
* Filters for grants posted **yesterday** using `PostDate`.
* Generates press-release style headlines and stories using GPT.
* Supports two modes:

  * **Test mode (`-t`)**: Outputs stories to `grant_stories.csv`.
  * **Production mode (`-p`)**: Inserts stories into a database with metadata tags.
* Sends a summary email report with attached log.
* Tags each grant by applicant type, funding category, and funding type.

---

## 🖥️ Usage

```bash
# Test mode: Generate CSV for review
python main.py -t

# Production mode: Insert stories into DB
python main.py -p

# Run both modes
python main.py -p -t
```

---

## 📁 Project Structure

| File              | Purpose                                               |
| ----------------- | ----------------------------------------------------- |
| `main.py`         | Coordinates the full scraping and processing pipeline |
| `grants.py`       | Downloads, parses, and filters the Grants XML data    |
| `gpt.py`          | Builds GPT prompts and processes completions          |
| `email_utils.py`  | Sends summary report emails with logs                 |
| `db_functions.py` | Inserts tagged grant stories into the MySQL database  |
| `utils/key.txt`   | Stores OpenAI API key                                 |

---

## 🧰 Requirements

* Python 3.9+
* [`openai`](https://pypi.org/project/openai/)
* [`requests`](https://pypi.org/project/requests/)
* [`beautifulsoup4`](https://pypi.org/project/beautifulsoup4/)
* [`lxml`](https://pypi.org/project/lxml/) (optional but faster XML parsing)
* SMTP credentials (for sending reports)
* MySQL database with required schema

---

## 📝 Output

**Test Mode (`-t`)**

* `grant_stories.csv` with columns:

  * `Filename`
  * `Headline`
  * `Story Text`

**Production Mode (`-p`)**

* Inserts stories into MySQL with:

  * Applicant Type Tags
  * Funding Category Tags
  * Funding Instrument Type Tags

---

## 📞 Logging & Reporting

Each run generates a timestamped log file (e.g. `scrape_log.2025-08-05_09-00-00.log`). A summary email is automatically sent with the log file attached.

---

## ✍️ Author

Bailey Malota
*Last updated: August 5, 2025*
