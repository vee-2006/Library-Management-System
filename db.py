
import os
import oracledb

def get_connection():
    return oracledb.connect(
        user=os.environ["ORACLE_USER"],
        password=os.environ["ORACLE_PASSWORD"],
        dsn="localhost:1521/FREEPDB1"
    )
