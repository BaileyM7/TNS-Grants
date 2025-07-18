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

        # Insert tags for applicants_tags, category_tags, and funding_tag
        all_tags = set(applicants_tags + category_tags + [funding_tag])

        status = 'D'

        # if grant is a procurement contract, send to box 4
        if 61 in all_tags:
            status = 'E'

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
            "T70-Bailey-Gran",
            a_id,
            "Bailey Malota",
            headline,
            body,
            status,
            today_str,
        ))

        # Get story ID s_id
        s_id = cursor.lastrowid

        try:
            for tag in all_tags:
                cursor.execute("INSERT INTO story_tag (id, tag_id) VALUES (%s, %s)", (s_id, tag))
        except mysql.connector.Error as e:
            logging.warning(f"Some tags failed to insert for s_id={s_id}: {e}")

        conn.commit()
        logging.info(f"Inserted Grant with filename: {filename}")
        return s_id

    except Exception as err:
        logging.error(f"DB insert failed: {err}")
        return None

    finally:
        if conn:
            conn.close()