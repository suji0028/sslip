from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from weasyprint import HTML
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import tempfile
import json
import mysql.connector
import urllib.parse
import traceback
import smtplib
import uuid
from http import cookies
import hashlib
import csv
from io import StringIO


PROFESSIONAL_TAX = 200
PROVIDENT_FUND = 1800
SESSIONS = {}




SMTP_EMAIL = "sachingardhariya30146@gmail.com"
SMTP_PASS = "sjmo uzzf eqih kecd"

def safe_filename(text):
    return "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in text).strip()

def html_to_pdf(html_content, month, year, employee_name):
    safe_name = safe_filename(employee_name).replace(" ", "_")
    filename = f"{month}_{year}_{safe_name}.pdf"

    pdf_path = os.path.join(tempfile.gettempdir(), filename)

    HTML(string=html_content).write_pdf(pdf_path)
    return pdf_path


def render_salary_html(template_path, data):
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    for key, value in data.items():
        html = html.replace("{{ " + key + " }}", str(value))

    return html

def send_email_with_pdf(to_email, subject, body_text, pdf_path):
    msg = MIMEMultipart()
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body_text, "plain"))

    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "pdf")
        part.set_payload(f.read())

    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f'attachment; filename="{os.path.basename(pdf_path)}"'
    )

    msg.attach(part)

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(SMTP_EMAIL, SMTP_PASS)
    server.send_message(msg)
    server.quit()

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="salary_slip"
    )

def generate_salary_html(row, month, year):

    with open("templates/salary_slip.html", "r", encoding="utf-8") as f:
        html = f.read()

    # ---- Salary calculations (based on your DB structure) ----
    basic = row.get("basic", 0)
    hra = row.get("hra", 0)
    conveyance = 1600
    medical = 1250
    special = row.get("special_allowance", 0)
    incentive  = row.get("incentive", 0)
    gross_salary = basic + hra + conveyance + medical + special + incentive 

    pt = row.get("pro_tax", 200)
    pf = row.get("pf", 1800)
    esi = row.get("esi", 0)
    income_tax = row.get("income_tax", 0)
    other_deduction = row.get("other", 0)
    tds = row.get("tds", 0)

    total_deduction = pt + pf + esi + income_tax + other_deduction
    net_salary = row.get("final_salary", 0)

    replacements = {
        "month": month,
        "year": year,
        "monthYear": f"{month} {year}",

        "empId": row["employee_id"],
        "empName": row["full_name"],
        "empDesignation": row.get("designation", "-"),
        "workingDays": 30,
        "panNumber": row.get("pan_card", "-"),

        "basic": basic,
        "hra": hra,
        "conveyance": conveyance,
        "medicalAllowance": medical,
        "specialAllowance": special,
        "incentive": incentive,
        "grossSalary": gross_salary,

        "pt": pt,
        "pf": pf,
        "esi": esi,
        "incomeTax": income_tax,
        "otherDeduction": other_deduction,
        "tds": tds,
        "totalDeduction": total_deduction,

        "netSalary": net_salary
    }

    # 🔥 IMPORTANT: &key& replacement
    for k, v in replacements.items():
        html = html.replace(f"&{k}&", str(v))

    return html


def calculate_final_salary(
    salary,
    incentive=0,
    other=0,
    tds=0,
    esi=0,
    income_tax=0,
    pt_pf=2000
):
    CONVEYANCE = 1600
    MEDICAL = 1250
    EMPLOYER_PF = 1800
    GRATUITY_RATE = 0.0481

    basic = round(salary * 0.5)
    hra = round(basic * 0.4)
    gratuity = round(basic * GRATUITY_RATE)

    special = round(
        salary - (basic + hra + CONVEYANCE + MEDICAL + EMPLOYER_PF + gratuity)
    )

    gross = round(
        basic + hra + CONVEYANCE + MEDICAL + special + incentive
    )

    net_salary = (
        gross
        - pt_pf
        - esi
        - income_tax
        - tds
        - other
    )

    return net_salary


class Server(BaseHTTPRequestHandler):

    PUBLIC_ROUTES = {"/login", "/logout", "/check_login", "/fetch_employees"}

    def send_headers(self):
        origin = self.headers.get("Origin")
        if origin :
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Credentials", "true")


    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, default=float).encode())


    def do_OPTIONS(self):
        self.send_response(200)
        self.send_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        return
    
    def get_logged_in_user(self):
        if "Cookie" not in self.headers:
            return None

        cookie = cookies.SimpleCookie(self.headers["Cookie"])
        if "session_id" not in cookie:
            return None

        session_id = cookie["session_id"].value
        return SESSIONS.get(session_id)


    def export_salary_csv(self, query):
        month = query.get("month", [""])[0]
        year = int(query.get("year", [0])[0])

        db = get_db()
        cur = db.cursor(dictionary=True)

        cur.execute("""
            SELECT
                e.full_name,
                e.designation,
                e.email,
                s.ctc,
                s.incentive,
                s.other,
                s.esi,
                s.income_tax,
                s.tds,
                s.final_salary
            FROM salary_records s
            JOIN employees e ON e.id = s.employee_id
            WHERE s.month = %s
              AND s.year = %s
              AND s.status = 'Paid'
            ORDER BY e.full_name
        """, (month, year))

        rows = cur.fetchall()

        if not rows:
            cur.close()
            db.close()

            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "message": "No paid salary data found for this month"
            }).encode())
            return

        

        output = StringIO()
        writer = csv.writer(output)

        writer.writerow([
            "Employee Name",
            "Designation",
            "Email",
            "CTC",
            "Incentive",
            "Other",
            "ESI",
            "Income Tax",
            "TDS",
            "Final Salary"
        ])

        for r in rows:
            writer.writerow([
                r["full_name"],
                r["designation"],
                r["email"],
                r["ctc"],
                r["incentive"],
                r["other"],
                r["esi"],
                r["income_tax"],
                r["tds"],
                r["final_salary"]
            ])

        filename = f"{month}_{year}.csv"

        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="{filename}"'
        )
        self.send_headers()
        self.end_headers()

        self.wfile.write(output.getvalue().encode("utf-8"))

    def get_financial_records(self, query):
        year = int(query.get("year", ["0"])[0])
        employee_id = query.get("employee_id", ["ALL"])[0]
        next_year = year + 1

        db = get_db()
        cur = db.cursor(dictionary=True)

        sql = """
        SELECT 
            e.id AS employee_id,
            e.full_name,
            sr.month,
            sr.month_index,
            sr.year,
            sr.final_salary,
            sr.ctc
        FROM salary_records sr
        JOIN employees e ON e.id = sr.employee_id
        WHERE (
            (sr.year = %s AND sr.month_index BETWEEN 4 AND 12)
            OR
            (sr.year = %s AND sr.month_index BETWEEN 1 AND 3)
        )
        """

        params = [year, next_year]

        if employee_id != "ALL":
            sql += " AND e.id = %s"
            params.append(employee_id)

        cur.execute(sql, params)
        rows = cur.fetchall()

        cur.close()
        db.close()

        self.send_json({"data": rows})

        

    # ---------- POST ----------
    def do_POST(self):
        db=None
        cur=None
        try:
            parsed = urlparse(self.path)
            path = parsed.path         

            if path not in self.PUBLIC_ROUTES:
                user = self.get_logged_in_user()
                if not user:
                    self.send_response(401)
                    self.end_headers()
                    return   

            if path == "/upload_logo":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)

                os.makedirs("images", exist_ok=True)

                filename = "brand_logo.png"
                save_path = os.path.join("images", filename)

                with open(save_path, "wb") as f:
                        f.write(body)

                logo_path = f"http://localhost:8000/images/{filename}"

                db = get_db()
                cur = db.cursor()

                cur.execute("""
                        INSERT INTO site_settings (setting_key, setting_value)
                        VALUES ('brand_logo', %s)
                        ON DUPLICATE KEY UPDATE setting_value=%s
                    """, (logo_path, logo_path))

                db.commit()

                self.send_json({
                        "success": True,
                        "brand_logo": logo_path
                    })
                return


            if path in ("/add_salary", "/update_salary", "/save_bulk_salary", "/send_salary_email","/save_site_settings"):
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length))
            else:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                data = urllib.parse.parse_qs(body)


            db = get_db()
            cur = db.cursor()
            
           
# 🔹 SAVE
            if path == "/save_employee":
                cur.execute("""
                    INSERT INTO employees (
                        full_name,
                        designation,
                        email,
                        phone,
                        dob,
                        active,
                        company,
                        uan_no,
                        aadhar_no,
                        pan_card,
                        account_holder_name,
                        account_number,
                        ifsc_code,
                        bank_name
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    data["fullName"][0],
                    data["designation"][0],
                    data["email"][0],
                    data["number"][0],
                    data["dob"][0] or None,
                    int(data["active"][0]),
                    data["companyName"][0],
                    data["uanNumber"][0],
                    data["aadharNumber"][0],
                    data["panNumber"][0],
                    data["accountHolderName"][0],
                    data["accountNumber"][0],
                    data["ifscCode"][0],
                    data["bankName"][0]
                ))

                db.commit()
                self.send_json({
                    "status": "success",
                    "message": "Employee saved successfully"
                })
                return
            
            elif path == "/login":
                email = data.get("email", [""])[0]
                password = data.get("password", [""])[0]

                if not email or not password:
                    self.send_json({
                        "success": False,
                        "message": "Email and password required"
                    })
                    return

                password_hash = hashlib.sha256(password.encode()).hexdigest()

                db = get_db()
                cur = db.cursor(dictionary=True)

                cur.execute("""
                    SELECT id, name, role
                    FROM users
                    WHERE email=%s
                    AND password_hash=%s
                    AND active=1
                """, (email, password_hash))

                user = cur.fetchone()
                cur.close()
                db.close()

                if not user:
                    self.send_json({
                        "success": False,
                        "message": "Invalid credentials"
                    })
                    return

                # 🔐 Create session
                session_id = str(uuid.uuid4())
                SESSIONS[session_id] = user

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header(
                    "Set-Cookie",
                    f"session_id={session_id}; HttpOnly; Path=/"
                )
                self.send_headers() 

                self.end_headers()

                self.wfile.write(json.dumps({
                    "success": True,
                    "user": user
                }).encode())
                return
            
            elif path == "/update_credentials":
                user = self.get_logged_in_user()
                if not user:
                    self.send_json({
                        "success": False,
                        "message": "Not authenticated"
                    }, 401)
                    return

                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length))

                current_password = data.get("current_password", "")
                new_password = data.get("new_password", "")
                confirm_password = data.get("confirm_password", "")

                if not current_password or not new_password or not confirm_password:
                    self.send_json({
                        "success": False,
                        "message": "All password fields are required"
                    })
                    return

                if new_password != confirm_password:
                    self.send_json({
                        "success": False,
                        "message": "New password and confirm password do not match"
                    })
                    return

                current_hash = hashlib.sha256(current_password.encode()).hexdigest()
                new_hash = hashlib.sha256(new_password.encode()).hexdigest()

                db = get_db()
                cur = db.cursor()

                # ✅ Verify current password
                cur.execute("""
                    SELECT id FROM users
                    WHERE id = %s AND password_hash = %s AND active = 1
                """, (user["id"], current_hash))

                if not cur.fetchone():
                    cur.close()
                    db.close()
                    self.send_json({
                        "success": False,
                        "message": "Current password is incorrect"
                    })
                    return

                # ✅ Update password
                cur.execute("""
                    UPDATE users
                    SET password_hash = %s
                    WHERE id = %s
                """, (new_hash, user["id"]))

                db.commit()
                cur.close()
                db.close()

                self.send_json({
                    "success": True,
                    "message": "Password updated successfully"
                })
                return


            elif path == "/save_bulk_salary":
                pf = PROVIDENT_FUND
                pt_pf = PROFESSIONAL_TAX + pf

                rows = data

                for r in rows:

                    month_index = [
                        "January","February","March","April","May","June",
                        "July","August","September","October","November","December"
                    ].index(r["month"]) + 1

                    salary = float(r.get("ctc") or 0)
                    incentive = float(r.get("incentive") or 0)
                    other = float(r.get("other") or 0)
                    tds = float(r.get("tds") or 0)
                    esi = float(r.get("esi") or 0)
                    income_tax = float(r.get("income_tax") or 0)


                    # ✅ CALCULATE FIRST (IMPORTANT)
                    final_salary = calculate_final_salary(
                        salary=salary,
                        incentive=incentive,
                        other=other,
                        tds=tds,
                        esi=esi,
                        income_tax=income_tax,
                        pt_pf=pt_pf
                    )

                    

                    basic = round(salary * 0.5)
                    hra = round(basic * 0.4)

                    special = max(
                        0,
                        salary - (basic + hra + 1600 + 1250 + 1800 + round(basic * 0.0481))
                    )

                    # 🔍 CHECK EXISTING
                    cur.execute("""
                        SELECT id FROM salary_records
                        WHERE employee_id=%s AND month=%s AND year=%s
                    """, (r["employee_id"], r["month"], r["year"]))

                    existing = cur.fetchone()

                    if existing:
                        # 🔁 UPDATE
                        cur.execute("""
                            UPDATE salary_records
                            SET 
                                ctc=%s,
                                basic=%s,
                                hra=%s,
                                special_allowance=%s,
                                pf=%s,
                                pro_tax=%s,
                                incentive=%s,
                                other=%s,
                                esi=%s,
                                income_tax=%s,
                                final_salary=%s,
                                status='Paid'
                            WHERE id=%s
                        """, (
                            salary,
                            basic,
                            hra,
                            special,
                            pf,
                            PROFESSIONAL_TAX,
                            incentive,
                            other,
                            esi,
                            income_tax,
                            final_salary,
                            existing[0]
                        ))

                    else:
                        # ➕ INSERT
                        cur.execute("""
                            INSERT INTO salary_records (
                                employee_id, month, year, month_index,
                                ctc, basic, hra, special_allowance,
                                pf, pro_tax,
                                incentive, other, esi, income_tax,
                                tds, final_salary, status
                            )
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Paid')
                        """, (
                            r["employee_id"],
                            r["month"],
                            r["year"],
                            month_index,
                            salary,
                            basic,
                            hra,
                            special,
                            pf,
                            PROFESSIONAL_TAX,
                            incentive,
                            other,
                            esi,
                            income_tax,
                            tds,
                            final_salary
                        ))


                db.commit()
                self.send_json({"success": True})
                return

            
            # 🔹 UPDATE
            elif path == "/update_employee":
                cur.execute("""
                    UPDATE employees SET
                        full_name=%s,
                        designation=%s,
                        email=%s,
                        phone=%s,
                        dob=%s,
                        active=%s,
                        company=%s,
                        uan_no=%s,
                        aadhar_no=%s,
                        pan_card=%s,
                        account_holder_name=%s,
                        account_number=%s,
                        ifsc_code=%s,
                        bank_name=%s
                    WHERE id=%s
                """, (
                    data["fullName"][0],
                    data["designation"][0],
                    data["email"][0],
                    data["number"][0],
                    data["dob"][0] or None,
                    int(data["active"][0]),
                    data["companyName"][0],
                    data["uanNumber"][0],
                    data["aadharNumber"][0],
                    data["panNumber"][0],
                    data["accountHolderName"][0],
                    data["accountNumber"][0],
                    data["ifscCode"][0],
                    data["bankName"][0],
                    int(data["id"][0])
                ))

                db.commit()
                self.send_json({
                    "status": "success",
                    "message": "Employee updated successfully"
                })
                return

            
            # 🔹 DELETE
            elif path == "/delete_employee":
                cur.execute(
                    "UPDATE employees SET active = 0 WHERE id = %s",
                    (int(data["id"][0]),)
                )
                db.commit()
                self.send_json({
                    "status": "success",
                    "message": "Employee deactivated successfully"
                })
                return

            elif path == "/send_salary_email":

                month = data["month"]
                year = int(data["year"])
                employee_id = int(data["employee_id"])

                db = get_db()
                cur = db.cursor(dictionary=True)

                base_query = """
                    SELECT 
                        e.id AS employee_id,
                        e.full_name,
                        e.email,
                        e.company,
                        e.designation,
                        e.pan_card,
                        s.*
                    FROM salary_records s
                    JOIN employees e ON e.id = s.employee_id
                    WHERE s.month=%s
                    AND s.year=%s
                    AND s.status='Paid'
                """

                params = [month, year]

                if employee_id != -1:
                    base_query += " AND e.id=%s"
                    params.append(employee_id)

                cur.execute(base_query, params)
                rows = cur.fetchall()

                if not rows:
                    self.send_json({
                        "success": False,
                        "message": "No paid salaries found"
                    })

                    cur.close()
                    db.close()

                    return

                sent_count = 0

                for r in rows:
                    if not r["email"]:
                        continue

                    # 1️⃣ Generate HTML from template
                    html = generate_salary_html(r, month, year)

                    # 2️⃣ Convert HTML → PDF
                    pdf_path = html_to_pdf(
                        html,
                        month,  
                        year,
                        r["full_name"]
                    )


                    # 3️⃣ Send email with PDF attachment
                    send_email_with_pdf(
                        to_email=r["email"],
                        subject=f"Salary Slip - {month} {year}",
                        body_text="Please find the attachment.",
                        pdf_path=pdf_path
                    )

                    sent_count += 1

                self.send_json({
                    "success": True,
                    "message": f"Salary emails sent ({sent_count} employees)"
                })
                return
            
            elif path == "/save_site_settings":
                try:
                    settings = {
                        "edit_pt_pf": int(data.get("edit_pt_pf", 0)),
                        "edit_esi": int(data.get("edit_esi", 0)),
                        "edit_income_tax": int(data.get("edit_income_tax", 0))
                    }

                    for key, value in settings.items():
                        cur.execute("""
                            INSERT INTO site_settings (setting_key, setting_value)
                            VALUES (%s, %s)
                            ON DUPLICATE KEY UPDATE setting_value = %s
                        """, (key, value, value))

                    db.commit()

                    self.send_json({"success": True})

                except Exception as e:
                    print("❌ save_site_settings error:", e)
                    self.send_json({"success": False, "error": str(e)})
                return


            elif path == "/logout":
                if "Cookie" in self.headers:
                    cookie = cookies.SimpleCookie(self.headers["Cookie"])
                    if "session_id" in cookie:
                        sid = cookie["session_id"].value
                        SESSIONS.pop(sid, None)

                self.send_response(200)
                self.send_header(
                    "Set-Cookie",
                    "session_id=; expires=Thu, 01 Jan 1970 00:00:00 GMT; Path=/"
                )
                self.end_headers()
                return
            
            else:
                self.send_json({"error": "Invalid POST route"}, 404)
                return

        except Exception as e:
            traceback.print_exc()
            self.send_json({"status": "error", "message": str(e)}, 500)

        finally:
            if cur:
                cur.close()
            if db:
                db.close()


       


    # ---------- GET ----------
    def do_GET(self):
        path = urlparse(self.path).path
        parsed = urlparse(self.path)

        if path not in self.PUBLIC_ROUTES:
            user = self.get_logged_in_user()
            if not user:
                self.send_response(401)
                self.end_headers()
                return
        try:

            if path.startswith("/images/"):
                file_path = path.lstrip("/")

                if os.path.exists(file_path):
                    self.send_response(200)

                    if file_path.endswith(".png"):
                        self.send_header("Content-Type", "image/png")
                    elif file_path.endswith(".jpg") or file_path.endswith(".jpeg"):
                        self.send_header("Content-Type", "image/jpeg")
                    elif file_path.endswith(".svg"):
                        self.send_header("Content-Type", "image/svg+xml")
                    else:
                        self.send_header("Content-Type", "application/octet-stream")

                    self.end_headers()

                    with open(file_path, "rb") as f:
                        self.wfile.write(f.read())
                    return
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
            
            if path == "/fetch_employees":
                db = get_db()
                cur = db.cursor()

                cur.execute("""
                    SELECT
                        id,
                        COALESCE(full_name,''),
                        COALESCE(designation,''),
                        COALESCE(email,''),
                        active,
                        COALESCE(company,''),
                        COALESCE(pan_card,''),
                        COALESCE(phone,''),
                        COALESCE(dob,''),
                        COALESCE(uan_no,''),
                        COALESCE(aadhar_no,''),
                        COALESCE(account_holder_name,''),
                        COALESCE(account_number,''),
                        COALESCE(ifsc_code,''),
                        COALESCE(bank_name,'')
                    FROM employees
                    ORDER BY id DESC
                """)

                rows = cur.fetchall()
                cur.close()
                db.close()

                data = []
                for r in rows:
                   data.append([
                        r[0],  # id
                        r[1],  # full name
                        r[2],  # designation
                        r[3],  # email
                        "Active" if r[4] == 1 else "Inactive",
                        r[5],  # company
                        r[6],  # pan
                        r[7],  # phone
                        r[8],  # dob
                        r[9],  # uan
                        r[10], # aadhar
                        r[11], # account holder
                        r[12], # account number
                        r[13], # ifsc
                        r[14], # bank
                        f"""
                        <button onclick='editEmployee({r[0]})'>Edit</button>
                        <button onclick='deleteEmployee({r[0]})'
                                style='margin-left:5px;color:red;'>Delete</button>
                        """
                    ])


                self.send_json({"data": data})
                return
            
            

            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)

            if parsed.path == "/getCompanies":
                db = None
                cur = None
                try:
                    db = get_db()
                    cur = db.cursor(dictionary=True)

                    cur.execute("""
                        SELECT DISTINCT company
                        FROM employees
                        WHERE active = 1
                        AND company IS NOT NULL
                        AND company != ''
                        ORDER BY company
                    """)


                    companies = cur.fetchall()
                    self.send_json({"data": companies})

                except Exception as e:
                    self.send_json({"data": [], "error": str(e)}, 500)

                finally:
                    if cur:
                        cur.close()
                    if db:
                        db.close()
                return

            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/financial-records":
                return self.get_financial_records(query)
            
            if parsed.path == "/export_salary_csv":
                return self.export_salary_csv(query)

            
            if parsed.path == "/fetch_salary":
                month = qs["month"][0]
                year = qs["year"][0]

                db = get_db()
                cur = db.cursor(dictionary=True)

                cur.execute("""
                SELECT e.id employee_id, e.full_name, e.company, e.email,
                    s.*
                FROM salary_records s
                JOIN employees e ON e.id = s.employee_id
                WHERE s.id IN (
                    SELECT MAX(id)
                    FROM salary_records
                    GROUP BY employee_id
                )
                AND s.month=%s AND s.year=%s
                """, (month, year))

                rows = cur.fetchall()
                cur.close()
                db.close()

                self.send_json({"data": rows})
                return

            elif parsed.path == "/get_last_salary":
                emp_id = int(qs["employee_id"][0])
                month = qs["month"][0]
                year = int(qs["year"][0])

                month_index = [
                    "January","February","March","April","May","June",
                    "July","August","September","October","November","December"
                ].index(month) + 1

                db = get_db()
                cur = db.cursor(dictionary=True)

                cur.execute("""
                    SELECT 
                        e.full_name,
                        e.company,
                        e.email,

                        s.ctc,
                        s.incentive,
                        s.other,
                        s.tds,
                        s.pro_tax,
                        s.pf,
                        s.esi,
                        s.final_salary,
                        s.status,
                        s.month,
                        s.month_index,
                        s.year
                    FROM salary_records s
                    JOIN employees e ON e.id = s.employee_id
                    WHERE s.employee_id = %s
                    AND (
                            s.year < %s
                        OR (s.year = %s AND s.month_index < %s)
                    )

                    ORDER BY s.year DESC, s.month_index DESC
                    LIMIT 1
                """, (emp_id, year, year, month_index))

                row = cur.fetchone()
                cur.close()
                db.close()

                if row:
                    self.send_json({
                        "exists": True,
                        "status": row["status"],
                        "salary": row
                    })
                else:
                    self.send_json({
                        "exists": False
                    })

                return

            elif parsed.path == "/get_paid_employees":
                month = qs["month"][0]
                year = int(qs["year"][0])

                db = get_db()
                cur = db.cursor(dictionary=True)

                cur.execute("""
                    SELECT DISTINCT
                        e.id,
                        e.full_name,
                        e.email
                    FROM salary_records s
                    JOIN employees e ON e.id = s.employee_id
                    WHERE s.month = %s
                    AND s.year = %s
                    AND s.status = 'Paid'
                    AND e.active = 1
                    ORDER BY e.full_name
                """, (month, year))

                rows = cur.fetchall()
                cur.close()
                db.close()

                self.send_json({"data": rows})
                return


            elif parsed.path == "/get_active_employees":
                db = None
                cur = None
                try:
                    db = get_db()
                    cur = db.cursor(dictionary=True)

                    cur.execute("""
                        SELECT 
                            id,
                            full_name,
                            company
                        FROM employees
                        WHERE active = 1
                        ORDER BY full_name
                    """)

                    rows = cur.fetchall()
                    self.send_json({"data": rows})

                except Exception as e:
                    self.send_json({"data": [], "error": str(e)}, 500)

                finally:
                    if cur:
                        cur.close()
                    if db:
                        db.close()
                return


            elif parsed.path == "/get_employees_without_salary":
                month = qs["month"][0]
                year = qs["year"][0]

                db = get_db()
                cur = db.cursor(dictionary=True)

                cur.execute("""
                    SELECT e.id, e.full_name
                    FROM employees e
                    WHERE e.active = 1
                    AND NOT EXISTS (
                        SELECT 1
                        FROM salary_records s
                        WHERE s.employee_id = e.id
                        AND s.month = %s
                        AND s.year = %s
                    )
                """, (month, year))

                rows = cur.fetchall()
                cur.close()
                db.close()

                self.send_json(rows)
                return


            elif parsed.path == "/get_employee_basic":
                emp_id = qs["employee_id"][0]

                db = get_db()
                cur = db.cursor(dictionary=True)

                cur.execute("""
                SELECT id, full_name, email, company
                FROM employees
                WHERE id = %s
                """, (emp_id,))

                row = cur.fetchone()
                cur.close()
                db.close()

                self.send_json(row)
                return

            elif parsed.path == "/fetch_salary_overview":
                month = qs["month"][0]
                year = int(qs["year"][0])

                db = get_db()
                cur = db.cursor(dictionary=True)

                cur.execute("""
                    SELECT
                        e.id AS employee_id,
                        e.full_name,
                        e.company,
                        e.email,
                        e.active,
                        s.pf,
                        s.pro_tax,
                        s.esi,
                        s.incentive,
                        s.other,
                        s.income_tax,
                        s.tds,
                        s.ctc,
                        s.final_salary,
                        s.status,

                        IF(s.id IS NULL, 1, 0) AS is_new
                    FROM employees e
                    LEFT JOIN salary_records s
                        ON s.employee_id = e.id
                    AND s.month = %s
                    AND s.year = %s
                    ORDER BY e.id DESC
                """, (month, year))

                rows = cur.fetchall()
                cur.close()
                db.close()

                data = []
                for r in rows:
                    data.append({
                        "employee_id": r["employee_id"],
                        "full_name": r["full_name"],
                        "company": r["company"],
                        "email": r["email"],
                        "active": r["active"],
                        "pf": r["pf"] or 0,
                        "pro_tax": r["pro_tax"] or 0,
                        "esi": r["esi"] or 0,
                        "incentive": r["incentive"] or 0,
                        "other": r["other"] or 0,
                        "income_tax": r["income_tax"] or 0,
                        "tds": r["tds"] or 0,
                        "ctc": r["ctc"] or 0,
                        "final_salary": r["final_salary"] or 0,
                        "status": r["status"] or "Unpaid",
                        "is_new": r["is_new"]
                    })

                self.send_json({ "data": data })
                return

            elif path == "/get_site_settings":
                db = get_db()
                cur = db.cursor(dictionary=True)

                cur.execute("SELECT setting_key, setting_value FROM site_settings")
                rows = cur.fetchall()

                cur.close()
                db.close()

                settings = {
                    r["setting_key"]: str(r["setting_value"])
                    for r in rows
                }

                self.send_json(settings)
                return

            elif path == "/check_login":
                user = self.get_logged_in_user()
                if not user:
                    self.send_json({"logged_in": False})
                else:
                    self.send_json({"logged_in": True, "user": user})
                return



        except Exception as e:
            self.send_json({"data": [], "error": str(e)}, 500)


if __name__ == "__main__":
    print("✅ Server running at http://localhost:8000")
    ThreadingHTTPServer(("localhost", 8000), Server).serve_forever()