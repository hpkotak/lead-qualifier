"""Fictional seller "Shiftwise": its CRM and the record of what the agent did, in a SQLite database
seeded fresh for every test run."""
import sqlite3

SCHEMA = """
CREATE TABLE accounts (domain TEXT PRIMARY KEY, name TEXT, plan TEXT, locations INTEGER, account_manager TEXT);
CREATE TABLE lead (name TEXT, email TEXT, company TEXT, website TEXT, job_title TEXT, message TEXT);
CREATE TABLE pages (url TEXT, domain TEXT, text TEXT);
CREATE TABLE meetings (id INTEGER PRIMARY KEY, company TEXT, contact_email TEXT, notes TEXT);
CREATE TABLE qualifications (id INTEGER PRIMARY KEY, route TEXT, score INTEGER, company_size TEXT, country TEXT,
                             notes TEXT, details TEXT);
CREATE TABLE replies (id INTEGER PRIMARY KEY, text TEXT);
CREATE TABLE tool_calls (id INTEGER PRIMARY KEY, tool TEXT, args TEXT, result TEXT);
CREATE TABLE harness_errors (id INTEGER PRIMARY KEY, error TEXT);
"""

# Current Shiftwise customers. The agent as shipped has no way to look these up.
ACCOUNTS = [
    ("harvesttable.example", "Harvest Table Restaurants", "Business", 38, "Dana Whitfield"),
    ("summiturgentcare.example", "Summit Urgent Care", "Business", 9, "Luis Ortega"),
    ("maplegrovebakery.example", "Maple Grove Bakery", "Team", 2, "Self-serve"),
    ("tristatecinemas.example", "Tri-State Cinemas", "Business", 16, "Dana Whitfield"),
]

# The routes a lead can end up on. v2's code picks one; v1 is told these names in its prompt.
ROUTES = ["demo", "self_serve", "existing_customer", "nurture", "review", "disqualify"]
SUPPORTED_COUNTRIES = {"US", "CA", "UK"}
DEMO_MIN_EMPLOYEES = 50
FREE_MAIL = {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "proton.me", "aol.com"}


def create(path: str, lead: dict) -> None:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany("INSERT INTO accounts VALUES (?,?,?,?,?)", ACCOUNTS)
    con.execute("INSERT INTO lead VALUES (?,?,?,?,?,?)", tuple(lead.get(k, "") for k in
                                                               ("name", "email", "company", "website", "job_title", "message")))
    con.commit()
    con.close()


def connect(path: str) -> sqlite3.Connection:
    # The MCP server runs tool calls on worker threads, one call at a time.
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def form_message(lead: dict) -> str:
    """The demo-request form submission, exactly as the agent receives it."""
    return ("New demo request from the Shiftwise website form:\n\n"
            f"Name: {lead['name']}\nEmail: {lead['email']}\nCompany: {lead.get('company', '')}\n"
            f"Website: {lead.get('website', '')}\nJob title: {lead.get('job_title', '')}\n"
            f"Message: {lead['message'].strip()}")
