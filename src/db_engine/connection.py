import os
import psycopg2

from dotenv import load_dotenv #type:ignore

load_dotenv()


def get_connection(database_name: str):

    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=database_name,
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )