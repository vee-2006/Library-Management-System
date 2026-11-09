
import os
import hmac
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session
)
import oracledb
from db import get_connection

app = Flask(__name__)

# Demo configuration. Set your own values in PowerShell.
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "dev-only-change-this-secret-key"
)


def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)

    return wrapped_view


TABLES = {
    "AUTHOR": "AUTHOR",
    "BOOK": "BOOK",
    "BOOK_COPY": "BOOK_COPY",
    "BORROWING_TRANSACTION": "BORROWING_TRANSACTION",
    "BORROWS": "BORROWS",
    "CATEGORY": "CATEGORY",
    "DIGITAL_RESOURCE": "DIGITAL_RESOURCE",
    "EMPLOYEE": "EMPLOYEE",
    "FINE": "FINE",
    "MEMBER": "MEMBER",
    "NOTIFICATION": "NOTIFICATION",
    "PUBLISHER": "PUBLISHER",
    "RESERVATION": "RESERVATION",
    "REVIEWS": "REVIEWS",
    "WRITTEN_BY": "WRITTEN_BY",
}

ACTIVITIES = {
    "view": "View Library Tables",
    "add": "Add a Book",
    "update": "Update a Book",
    "delete": "Delete a Book",
    "reports": "Library Reports",
}

REPORTS = {
    "books_by_category": "Books by Category",
    "books_by_publisher": "Books by Publisher",
    "members": "Library Members",
    "transactions": "Borrowing Transactions",
    "fines": "Fine Records",
}


# ---------------- LOGIN AND LOGOUT ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("logged_in"):
        return redirect(url_for("index"))

    error = None

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        correct_username = os.environ.get(
            "LIBRARY_ADMIN_USERNAME", "librarian"
        )
        correct_password = os.environ.get(
            "LIBRARY_ADMIN_PASSWORD", "ChangeMe123!"
        )

        if (
            hmac.compare_digest(username, correct_username)
            and hmac.compare_digest(password, correct_password)
        ):
            session.clear()
            session["logged_in"] = True
            session["username"] = username
            return redirect(url_for("index"))

        error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- HELPER FUNCTIONS ----------------

def read_lobs(rows):
    """Read Oracle LOB values before closing the connection."""
    result = []

    for row in rows:
        new_row = []

        for value in row:
            if isinstance(value, oracledb.LOB):
                value = value.read()
            new_row.append(value)

        result.append(tuple(new_row))

    return result


def get_dropdown_data():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT publisher_id, name "
                "FROM publisher ORDER BY name"
            )
            publishers = cursor.fetchall()

            cursor.execute(
                "SELECT category_id, category_name "
                "FROM category ORDER BY category_name"
            )
            categories = cursor.fetchall()

    return publishers, categories


# ---------------- HOME PAGE AND LIBRARY DATA ----------------

def render_home(
    activity="view",
    table="BOOK",
    message=None,
    search="",
    report="",
    category_id="",
    publisher_id="",
):
    records = []
    columns = []
    report_records = []
    report_columns = []
    publishers = []
    categories = []
    error = None

    try:
        publishers, categories = get_dropdown_data()

        with get_connection() as connection:
            with connection.cursor() as cursor:

                # View and search library tables
                if activity == "view" and table in TABLES:
                    if table == "BOOK" and search.strip():
                        if search.strip().isdigit():
                            cursor.execute(
                                """
                                SELECT *
                                FROM BOOK
                                WHERE book_id = :book_id
                                   OR LOWER(title) LIKE :search_text
                                ORDER BY book_id
                                FETCH FIRST 100 ROWS ONLY
                                """,
                                {
                                    "book_id": int(search.strip()),
                                    "search_text":
                                        f"%{search.strip().lower()}%",
                                },
                            )
                        else:
                            cursor.execute(
                                """
                                SELECT *
                                FROM BOOK
                                WHERE LOWER(title) LIKE :search_text
                                ORDER BY book_id
                                FETCH FIRST 100 ROWS ONLY
                                """,
                                {
                                    "search_text":
                                        f"%{search.strip().lower()}%"
                                },
                            )
                    else:
                        cursor.execute(
                            f"SELECT * FROM {TABLES[table]} "
                            "FETCH FIRST 100 ROWS ONLY"
                        )

                    columns = [
                        item[0] for item in cursor.description
                    ]
                    records = read_lobs(cursor.fetchall())

                # Library reports
                elif activity == "reports" and report in REPORTS:
                    report_sql = {
                        "books_by_category": """
                            SELECT c.category_id,
                                   c.category_name,
                                   COUNT(b.book_id) AS book_count
                            FROM category c
                            LEFT JOIN book b
                                ON b.category_id = c.category_id
                            GROUP BY c.category_id, c.category_name
                            ORDER BY c.category_name
                        """,

                        "books_by_publisher": """
                            SELECT p.publisher_id,
                                   p.name,
                                   COUNT(b.book_id) AS book_count
                            FROM publisher p
                            LEFT JOIN book b
                                ON b.publisher_id = p.publisher_id
                            GROUP BY p.publisher_id, p.name
                            ORDER BY p.name
                        """,

                        "members": """
                            SELECT * FROM member
                            FETCH FIRST 100 ROWS ONLY
                        """,

                        "transactions": """
                            SELECT * FROM borrowing_transaction
                            FETCH FIRST 100 ROWS ONLY
                        """,

                        "fines": """
                            SELECT * FROM fine
                            FETCH FIRST 100 ROWS ONLY
                        """,
                    }

                    cursor.execute(report_sql[report])

                    report_columns = [
                        item[0] for item in cursor.description
                    ]
                    report_records = read_lobs(cursor.fetchall())

                # Book recommendations by category and publisher
                elif activity == "recommendations" and category_id:
                    sql = """
                        SELECT b.book_id,
                               b.title,
                               b.edition,
                               b.publication_year,
                               b.total_copies,
                               c.category_name,
                               p.name
                        FROM book b
                        LEFT JOIN category c
                            ON c.category_id = b.category_id
                        LEFT JOIN publisher p
                            ON p.publisher_id = b.publisher_id
                        WHERE b.category_id = :category_id
                    """

                    params = {
                        "category_id": int(category_id)
                    }

                    if publisher_id:
                        sql += " AND b.publisher_id = :publisher_id"
                        params["publisher_id"] = int(publisher_id)

                    sql += " ORDER BY b.title"

                    cursor.execute(sql, params)

                    report_columns = [
                        item[0] for item in cursor.description
                    ]
                    report_records = read_lobs(cursor.fetchall())

    except Exception as exc:
        error = str(exc)

    return render_template(
        "index.html",
        activity=activity,
        activities=ACTIVITIES,
        tables=TABLES,
        table=table,
        records=records,
        columns=columns,
        message=message,
        error=error,
        search=search,
        report=report,
        reports=REPORTS,
        report_records=report_records,
        report_columns=report_columns,
        publishers=publishers,
        categories=categories,
        category_id=category_id,
        publisher_id=publisher_id,
    )


# ---------------- VIEW LIBRARY ----------------

@app.route("/")
@login_required
def index():
    activity = request.args.get("activity", "view")
    table = request.args.get("table", "BOOK")
    message = request.args.get("message")
    search = request.args.get("search", "")
    report = request.args.get("report", "")
    category_id = request.args.get("category_id", "")
    publisher_id = request.args.get("publisher_id", "")

    if activity not in ACTIVITIES and activity != "recommendations":
        activity = "view"

    return render_home(
        activity=activity,
        table=table,
        message=message,
        search=search,
        report=report,
        category_id=category_id,
        publisher_id=publisher_id,
    )


# ---------------- ADD BOOK ----------------

@app.route("/add-book", methods=["POST"])
@login_required
def add_book():
    try:
        book_id = int(request.form["book_id"])
        title = request.form["title"].strip()
        edition = request.form.get("edition", "").strip() or None
        publication_year = (
            request.form.get("publication_year", "").strip() or None
        )
        total_copies = (
            request.form.get("total_copies", "").strip() or None
        )
        publisher_id = (
            request.form.get("publisher_id", "").strip() or None
        )
        category_id = (
            request.form.get("category_id", "").strip() or None
        )

        if not title:
            raise ValueError("Book title is required.")

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO book
                        (book_id, title, edition, publication_year,
                         total_copies, publisher_id, category_id)
                    VALUES
                        (:book_id, :title, :edition, :publication_year,
                         :total_copies, :publisher_id, :category_id)
                    """,
                    {
                        "book_id": book_id,
                        "title": title,
                        "edition": edition,
                        "publication_year": (
                            int(publication_year)
                            if publication_year else None
                        ),
                        "total_copies": (
                            int(total_copies)
                            if total_copies else None
                        ),
                        "publisher_id": (
                            int(publisher_id)
                            if publisher_id else None
                        ),
                        "category_id": (
                            int(category_id)
                            if category_id else None
                        ),
                    },
                )

            connection.commit()

        message = f'Book "{title}" added successfully.'

    except ValueError as exc:
        message = str(exc)

    except oracledb.IntegrityError as exc:
        if "ORA-00001" in str(exc):
            message = (
                "That Book ID already exists. Please use a different ID."
            )
        elif "ORA-02291" in str(exc):
            message = "Please choose a valid publisher and category."
        else:
            message = f"Database constraint error: {exc}"

    except Exception as exc:
        message = f"Could not add the book: {exc}"

    return redirect(
        url_for("index", activity="add", message=message)
    )


# ---------------- UPDATE BOOK ----------------

@app.route("/update-book", methods=["POST"])
@login_required
def update_book():
    try:
        book_id = int(request.form["book_id"])
        title = request.form["title"].strip()
        edition = request.form.get("edition", "").strip() or None
        publication_year = (
            request.form.get("publication_year", "").strip() or None
        )
        total_copies = (
            request.form.get("total_copies", "").strip() or None
        )
        publisher_id = (
            request.form.get("publisher_id", "").strip() or None
        )
        category_id = (
            request.form.get("category_id", "").strip() or None
        )

        if not title:
            raise ValueError("Book title is required.")

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE book
                    SET title = :title,
                        edition = :edition,
                        publication_year = :publication_year,
                        total_copies = :total_copies,
                        publisher_id = :publisher_id,
                        category_id = :category_id
                    WHERE book_id = :book_id
                    """,
                    {
                        "book_id": book_id,
                        "title": title,
                        "edition": edition,
                        "publication_year": (
                            int(publication_year)
                            if publication_year else None
                        ),
                        "total_copies": (
                            int(total_copies)
                            if total_copies else None
                        ),
                        "publisher_id": (
                            int(publisher_id)
                            if publisher_id else None
                        ),
                        "category_id": (
                            int(category_id)
                            if category_id else None
                        ),
                    },
                )

                updated = cursor.rowcount

            connection.commit()

        if updated:
            message = f"Book ID {book_id} updated successfully."
        else:
            message = f"No book found with ID {book_id}."

    except ValueError as exc:
        message = str(exc)

    except oracledb.IntegrityError as exc:
        message = f"Database constraint error: {exc}"

    except Exception as exc:
        message = f"Could not update the book: {exc}"

    return redirect(
        url_for("index", activity="update", message=message)
    )


# ---------------- DELETE BOOK ----------------

@app.route("/delete-book", methods=["POST"])
@login_required
def delete_book():
    try:
        book_id = int(request.form["book_id"])

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT title FROM book WHERE book_id = :book_id",
                    {"book_id": book_id},
                )
                book = cursor.fetchone()

                if not book:
                    message = f"No book found with ID {book_id}."

                else:
                    dependencies = [
                        ("DIGITAL_RESOURCE", "book_id"),
                        ("RESERVATION", "book_id"),
                        ("REVIEWS", "book_id"),
                        ("WRITTEN_BY", "book_id"),
                    ]

                    linked = False

                    for table_name, column_name in dependencies:
                        cursor.execute(
                            f"SELECT COUNT(*) FROM {table_name} "
                            f"WHERE {column_name} = :book_id",
                            {"book_id": book_id},
                        )

                        if cursor.fetchone()[0] > 0:
                            linked = True
                            break

                    if linked:
                        message = (
                            "This book is linked to other library records "
                            "and cannot be deleted until those links are "
                            "removed."
                        )

                    else:
                        cursor.execute(
                            "DELETE FROM book WHERE book_id = :book_id",
                            {"book_id": book_id},
                        )

                        connection.commit()

                        message = (
                            f'Book "{book[0]}" deleted successfully.'
                        )

    except ValueError:
        message = "Please enter a valid Book ID."

    except oracledb.IntegrityError:
        message = (
            "This book is linked to other records and cannot be deleted."
        )

    except Exception as exc:
        message = f"Could not delete the book: {exc}"

    return redirect(
        url_for("index", activity="delete", message=message)
    )


if __name__ == "__main__":
    app.run(debug=True)








