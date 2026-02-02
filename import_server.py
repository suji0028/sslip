from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import mysql.connector
import re
from datetime import date, datetime
from urllib.parse import urlparse, parse_qs
from io import StringIO
import csv

# ================= DATABASE CONFIG =================

MAIN_DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "salary_slip"
}

# ================= UTIL =================

def json_safe(obj):
    if isinstance(obj, (date, datetime)):
        return obj.strftime("%Y-%m-%d")
    return obj

# ================= MULTIPART PARSER =================

def parse_multipart(self):
    content_type = self.headers.get("Content-Type", "")
    if "boundary=" not in content_type:
        raise Exception("Invalid multipart request")

    boundary = content_type.split("boundary=")[1].encode()
    length = int(self.headers.get("Content-Length", 0))
    body = self.rfile.read(length)

    parts = body.split(b"--" + boundary)
    files = {}

    for part in parts:
        if b"Content-Disposition" not in part:
            continue
        if b"\r\n\r\n" not in part:
            continue

        headers, content = part.split(b"\r\n\r\n", 1)
        content = content.rsplit(b"\r\n", 1)[0]

        m = re.search(
            b'name="([^"]+)"; filename="([^"]+)"',
            headers
        )
        if m:
            field = m.group(1).decode()
            filename = m.group(2).decode()
            files[field] = {
                "filename": filename,
                "content": content.decode("utf-8", errors="ignore")
            }

    return files

# ================= CSV PARSER =================

def parse_csv(content):
    reader = csv.DictReader(StringIO(content))
    employees = []

    for r in reader:
        pan_value = (
            r.get("pan_card")
            or r.get("pan_number")
            or r.get("pan")
            or r.get("PAN")
            or ""
        )

        employees.append({
            "full_name": r.get("full_name", "").strip(),
            "pan": pan_value.strip().upper(),
            "email": r.get("email", ""),
            "company": r.get("company", ""),
            "designation": r.get("designation", ""),
            "phone": r.get("phone", ""),
            "dob": r.get("dob"),
            "uan_no": r.get("uan_no", ""),
            "aadhar_no": r.get("aadhar_no", ""),
            "account_holder_name": r.get("account_holder_name", ""),
            "account_number": r.get("account_number", ""),
            "ifsc_code": r.get("ifsc_code", ""),
            "bank_name": r.get("bank_name", "")
        })

    return employees

# ================= SQL HELPERS =================

def detect_tables(sql):
    """
    Detect tables from INSERT statements that contain any PAN-like column
    """
    # Step 1: find all INSERT INTO table names
    raw_tables = re.findall(
        r"INSERT\s+INTO\s+[`\"]?([\w\.]+)[`\"]?",
        sql,
        re.IGNORECASE
    )

    tables = set(t.split(".")[-1] for t in raw_tables)

    valid_tables = []

    for table in tables:
        # Find column list for this table
        m = re.search(
            rf"INSERT\s+INTO\s+[`\"]?{table}[`\"]?\s*\((.*?)\)\s*VALUES",
            sql,
            re.IGNORECASE | re.DOTALL
        )

        if not m:
            continue

        columns = m.group(1).lower()

        # Accept ANY pan-like column
        if any(pan in columns for pan in [
            "pan",
            "pan_",
            "pan_number",
            "pan_card",
            "pancard"
        ]):
            valid_tables.append(table)

    return sorted(valid_tables)


def parse_row_values(row):
    values = []
    current = ""
    in_string = False

    i = 0
    while i < len(row):
        c = row[i]

        if c == "'" and not in_string:
            in_string = True
            current = ""
        elif c == "'" and in_string:
            in_string = False
            values.append(current)
        elif in_string:
            current += c
        elif row[i:i+4].upper() == "NULL":
            values.append(None)
            i += 3
        elif c.isdigit() and not in_string:
            num = c
            j = i + 1
            while j < len(row) and row[j].isdigit():
                num += row[j]
                j += 1
            values.append(num)
            i = j - 1
        i += 1

    return values


def fetch_from_import_db(payload):
    conn = mysql.connector.connect(
        host=payload["host"],
        user=payload["user"],
        password=payload["password"],
        database=payload["database"]
    )

    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            full_name,
            pan_card AS pan,
            email,
            company,
            designation,
            phone,
            dob,
            uan_no,
            aadhar_no,
            account_holder_name,
            account_number,
            ifsc_code,
            bank_name
        FROM employees
        WHERE pan_card IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows




def parse_sql_for_table(sql, table):
    employees = []

    pattern = re.compile(
        rf"INSERT\s+INTO\s+`?{table}`?\s*\((.*?)\)\s*VALUES\s*(.*?);",
        re.IGNORECASE | re.DOTALL
    )

    matches = pattern.findall(sql)

    for cols, values_block in matches:
        columns = [c.strip(" `") for c in cols.split(",")]
        rows = re.findall(r"\((.*?)\)", values_block, re.DOTALL)

        for row_vals in rows:
            values = parse_row_values(row_vals)

            # SAFETY: align length
            if len(values) != len(columns):
                continue

            row = dict(zip(columns, values))

            pan_value = (
                row.get("pan_card")
                or row.get("pan_number")
                or row.get("pan")
                or ""
            )


            employees.append({
                "full_name": row.get("full_name", "").strip(),
                "pan": pan_value.strip().upper(),
                "email": row.get("email", "").strip().lower(),
                "company": row.get("company", "").strip(),
                "designation": row.get("designation", "").strip(),
                "phone": row.get("phone"),
                "dob": row.get("dob"),
                "uan_no": row.get("uan_no", ""),
                "aadhar_no": row.get("aadhar_no", ""),
                "account_holder_name": row.get("account_holder_name", ""),
                "account_number": row.get("account_number", ""),
                "ifsc_code": row.get("ifsc_code", ""),
                "bank_name": row.get("bank_name", "")
            })

    return employees

# ================= HTTP HANDLER =================

class ImportHandler(BaseHTTPRequestHandler):

    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=json_safe).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def do_POST(self):

        # ================= DB TO DB IMPORT =================
        if self.path == "/import_from_db":
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))

                # fetch employees from IMPORT DB
                import_employees = fetch_from_import_db(payload)

                # fetch PANs from MAIN DB
                conn = mysql.connector.connect(**MAIN_DB_CONFIG)
                cur = conn.cursor()
                cur.execute("SELECT pan_card FROM employees WHERE pan_card IS NOT NULL")
                existing_pans = {
                    r[0].strip().upper()
                    for r in cur.fetchall()
                    if r[0]
                }
                cur.close()
                conn.close()

                new_employees = []
                existing_employees = []

                for emp in import_employees:
                    pan = (emp.get("pan") or "").strip().upper()

                    if pan in existing_pans:
                        emp["exists"] = True
                        existing_employees.append(emp)
                    else:
                        emp["exists"] = False
                        new_employees.append(emp)

                return self.send_json({
                    "new": new_employees,
                    "existing": existing_employees
                })

            except mysql.connector.Error as e:
                return self.send_json({"error": str(e)}, 200)

            except Exception as e:
                return self.send_json({"error": str(e)}, 500)

        # ================= FILE IMPORT =================
        if self.path.startswith("/import_employees_file"):
            try:
                query = parse_qs(urlparse(self.path).query)
                table = query.get("table", [None])[0]

                files = parse_multipart(self)
                if "file" not in files:
                    return self.send_json({"error": "No file uploaded"}, 400)

                file = files["file"]
                filename = file["filename"]
                content = file["content"]

                # CSV
                if filename.endswith(".csv"):
                    employees = parse_csv(content)

                # SQL
                elif filename.endswith(".sql"):
                    if not table:
                        tables = detect_tables(content)
                        return self.send_json({"tables": tables})

                    employees = parse_sql_for_table(content, table)

                else:
                    return self.send_json({"error": "Only CSV or SQL allowed"}, 400)

                # Remove empty PAN
                employees = [e for e in employees if e["pan"]]

                # Compare with MAIN DB
                conn = mysql.connector.connect(**MAIN_DB_CONFIG)
                cur = conn.cursor()
                cur.execute("SELECT pan_card FROM employees WHERE pan_card IS NOT NULL")
                existing_pans = {
                    r[0].strip().upper()
                    for r in cur.fetchall()
                    if r[0] and r[0].strip()
                }
                cur.close()
                conn.close()

                new_employees = []
                existing_employees = []

                for e in employees:
                    pan = e["pan"].strip().upper()

                    if pan in existing_pans:
                        e["exists"] = True
                        existing_employees.append(e)
                    else:
                        e["exists"] = False
                        new_employees.append(e)

                return self.send_json({
                    "new": new_employees,
                    "existing": existing_employees
                })


            except Exception as e:
                return self.send_json({"error": str(e)}, 500)

        # ================= ADD EMPLOYEE =================
        if self.path.startswith("/add_employee"):
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))

            conn = mysql.connector.connect(**MAIN_DB_CONFIG)
            cur = conn.cursor()

            cur.execute(
                "SELECT id FROM employees WHERE pan_card=%s",
                (data["pan"],)
            )
            if cur.fetchone():
                cur.close()
                conn.close()
                return self.send_json({
                    "success": False,
                    "message": "Employee already exists"
                })

            cur.execute("""
                INSERT INTO employees
                (full_name, pan_card, email, company, designation, phone, dob,
                 uan_no, aadhar_no, account_holder_name, account_number,
                 ifsc_code, bank_name, active)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)
            """, (
                data["full_name"],
                data["pan"],
                data["email"],
                data["company"],
                data["designation"],
                data["phone"],
                data["dob"],
                data["uan_no"],
                data["aadhar_no"],
                data["account_holder_name"],
                data["account_number"],
                data["ifsc_code"],
                data["bank_name"]
            ))

            conn.commit()
            cur.close()
            conn.close()

            return self.send_json({
                "success": True,
                "message": "Employee added successfully"
            })

        return self.send_json({"error": "Invalid endpoint"}, 404)
    

    def do_GET(self):
        if self.path == "/fetch_employees":
            try:
                conn = mysql.connector.connect(**MAIN_DB_CONFIG)
                cur = conn.cursor()
                cur.execute("""
                    SELECT
                        id,
                        full_name,
                        designation,
                        email,
                        company,
                        pan_card
                    FROM employees
                    ORDER BY id DESC
                """)
                rows = cur.fetchall()
                cur.close()
                conn.close()

                return self.send_json({"data": rows})

            except Exception as e:
                return self.send_json({"error": str(e)}, 500)


# ================= SERVER START =================

if __name__ == "__main__":
    print("🚀 Import Server running at http://127.0.0.1:8001")
    HTTPServer(("0.0.0.0", 8001), ImportHandler).serve_forever()


