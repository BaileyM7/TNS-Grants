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

def insert_story(filename, headline, body, applicants_tags, category_tags, funding_tag, a_id = 51):
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
         status, content_date, last_action)
        VALUES (%s, %s, %s, %s, %s, %s, '', '', NOW(), '', '', NULL, NULL, %s, %s, SYSDATE())
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
        ))

        # Get story ID s_id
        s_id = cursor.lastrowid

        # Insert tags for applicants_tags
        tag_insert_sql = "INSERT INTO story_tag (id, tag_id) VALUES (%s, %s)"
        for tag in applicants_tags:
            cursor.execute(tag_insert_sql, (s_id, tag))
            logging.debug(f"Inserted tag for Grant applicants_tag (tag_id={tag})")

        # Insert tags for category_tags
        tag_insert_sql = "INSERT INTO story_tag (id, tag_id) VALUES (%s, %s)"
        for tag in category_tags:
            cursor.execute(tag_insert_sql, (s_id, tag))
            logging.debug(f"Inserted tag for Grant tag_insert_sql (tag_id={tag})")

        # Insert tag for funding_tag
        tag_insert_sql = "INSERT INTO story_tag (id, tag_id) VALUES (%s, %s)"
        cursor.execute(tag_insert_sql, (s_id, funding_tag))
        logging.debug(f"Inserted tag for Grant funding_tag (tag_id={funding_tag})")

        conn.commit()
        logging.info(f"Inserted Grant with filename: {filename}")
        return s_id

    except Exception as err:
        logging.error(f"DB insert failed: {err}")
        return None

    finally:
        if conn:
            conn.close()