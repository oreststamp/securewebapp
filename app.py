from flask import Flask, request, render_template, redirect
import pyodbc
import struct
import random
import string
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

app = Flask(__name__)

SERVER = "sql-securewebapp-dev-ostamp.database.windows.net"
DATABASE = "sqldb-securewebapp-dev"
KEY_VAULT_URL = "https://kv-securewebapp-dev-os2.vault.azure.net/"

def get_connection():
    credential = DefaultAzureCredential()
    token_bytes = credential.get_token("https://database.windows.net/.default").token.encode("utf-16-le")
    token_struct = struct.pack(f'<I{len(token_bytes)}s', len(token_bytes), token_bytes)
    conn_str = f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={SERVER};DATABASE={DATABASE}"
    SQL_COPT_SS_ACCESS_TOKEN = 1256
    conn = pyodbc.connect(conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})
    return conn

def generate_code(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/shorten", methods=["POST"])
def shorten():
    original_url = request.form.get("url")
    if not original_url:
        return render_template("index.html", error="Please enter a URL.")
    try:
        conn = get_connection()
        cursor = conn.cursor()
        code = generate_code()
        cursor.execute("INSERT INTO Urls (ShortCode, OriginalUrl) VALUES (?, ?)", code, original_url)
        conn.commit()
        short_url = request.host_url + code
        return render_template("index.html", short_url=short_url)
    except Exception as e:
        return render_template("index.html", error=f"Error: {str(e)}")

@app.route("/<code>")
def redirect_to_url(code):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT OriginalUrl FROM Urls WHERE ShortCode = ?", code)
        row = cursor.fetchone()
        if row:
            cursor.execute("UPDATE Urls SET ClickCount = ClickCount + 1 WHERE ShortCode = ?", code)
            conn.commit()
            return redirect(row[0])
        else:
            return "Short URL not found", 404
    except Exception as e:
        return f"Error: {str(e)}", 500

@app.route("/stats")
def stats():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ShortCode, OriginalUrl, ClickCount, CreatedAt FROM Urls ORDER BY CreatedAt DESC")
        columns = [column[0] for column in cursor.description]
        urls = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return render_template("stats.html", urls=urls)
    except Exception as e:
        return f"Error loading stats: {str(e)}", 500

@app.route("/dbcheck")
def dbcheck():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT GETDATE()")
        row = cursor.fetchone()
        return f"Connected successfully! DB server time: {row[0]}"
    except Exception as e:
        return f"Connection failed: {str(e)}", 500

@app.route("/secretcheck")
def secretcheck():
    try:
        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
        secret = client.get_secret("demo-api-key")
        return f"Key Vault access successful! Secret value: {secret.value}"
    except Exception as e:
        return f"Key Vault access failed: {str(e)}", 500

if __name__ == "__main__":
    app.run()