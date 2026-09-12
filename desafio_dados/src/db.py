import psycopg
from pgvector.psycopg import register_vector
from pymongo import MongoClient
from pymongo.database import Database


def conectar_postgres(cfg: dict) -> psycopg.Connection:
    pg = cfg["postgres"]
    conn = psycopg.connect(
        host=pg["host"],
        port=pg["port"],
        dbname=pg["database"],
        user=pg["user"],
        password=pg["password"],
    )
    register_vector(conn)
    return conn


def conectar_mongo(cfg: dict) -> Database:
    mg = cfg["mongodb"]
    uri = f"mongodb://{mg['user']}:{mg['password']}@{mg['host']}:{mg['port']}/?authSource=admin"
    cliente = MongoClient(uri, serverSelectionTimeoutMS=5000)
    cliente.admin.command("ping")
    return cliente[mg["database"]]
