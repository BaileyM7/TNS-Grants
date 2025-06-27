import yaml
import logging
import mysql.connector
from datetime import datetime

def get_db_connection(yml_path="configs/db_config.yml"):
    with open(yml_path, "r") as yml_file:
        config = yaml.load(yml_file, Loader=yaml.FullLoader)
    return mysql.connector.connect(
        host=config["host"],
        user=config["user"],
        password=config["password"],
        database=config["database"]
    )

def insert_story(filename, headline, body, a_id, sponsor_blob):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check for duplicate filename
        check_sql = "SELECT COUNT(*) FROM story WHERE filename = %s"
        cursor.execute(check_sql, (filename,))
        if cursor.fetchone()[0] > 0:
            logging.info(f"Duplicate filename, skipping: {filename}")
            return False

        # Insert into story
        insert_sql = """
        INSERT INTO story
        (filename, uname, source, by_line, headline, story_txt, editor, invoice_tag,
         date_sent, sent_to, wire_to, nexis_sent, factiva_sent,
         status, content_date, last_action, orig_txt)
        VALUES (%s, %s, %s, %s, %s, %s, '', '', NOW(), '', '', NULL, NULL, %s, %s, SYSDATE(), %s)
        """
        today_str = datetime.now().strftime('%Y-%m-%d')
        cursor.execute(insert_sql, (
            filename,
            "T55-Bailey-Proj",
            a_id,
            "Bailey Malota",
            headline,
            body,
            'D',
            today_str,
            sponsor_blob
        ))

        # Get story ID s_id
        s_id = cursor.lastrowid

        # Insert state tags into story_tag
        tag_insert_sql = "INSERT INTO story_tag (id, tag_id) VALUES (%s, %s)"
        for state_abbr, tag_id in openai_api.found_ids.items():
            cursor.execute(tag_insert_sql, (s_id, tag_id))
            logging.debug(f"Inserted tag for state {state_abbr} (tag_id={tag_id})")

        conn.commit()
        logging.info(f"Inserted story and {len(openai_api.found_ids)} tag(s): {filename}")
        return s_id
    except Exception as err:
        logging.error(f"DB insert failed: {err}")
        return None
    finally:
        if conn:
            conn.close()