from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "supersecret"

# -------------------------
# In-memory "database"
# -------------------------
users = {}  # username: password

# Each book has: title, categories: {category_name: [pages]}
books = {}
# Page structure: {"id": int, "title": str, "content": str, "book_id": int, "category": str}
next_page_id = 1
next_book_id = 1

# -------------------------
# Authentication
# -------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username in users:
            return "User already exists!"
        users[username] = password
        session["user"] = username
        return redirect(url_for("home"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username in users and users[username] == password:
            session["user"] = username
            return redirect(url_for("home"))
        return "Invalid credentials!"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# -------------------------
# Home & Books
# -------------------------
@app.route("/")
def home():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("home.html", books=books)

@app.route("/book/new", methods=["GET", "POST"])
def new_book():
    global next_book_id
    if "user" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        title = request.form["title"]
        # For simplicity, each new book starts with a default category
        books[next_book_id] = {"title": title, "categories": {"General": []}}
        next_book_id += 1
        return redirect(url_for("home"))
    return render_template("new_book.html")

@app.route("/book/<int:book_id>")
def view_book(book_id):
    if "user" not in session:
        return redirect(url_for("login"))
    book = books.get(book_id)
    if not book:
        return "Book not found!"
    return render_template("view_book.html", book=book, book_id=book_id)

# -------------------------
# Pages
# -------------------------
@app.route("/book/<int:book_id>/page/new", methods=["GET", "POST"])
def new_page(book_id):
    global next_page_id
    if "user" not in session:
        return redirect(url_for("login"))
    book = books.get(book_id)
    if not book:
        return "Book not found!"
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        category = request.form.get("category", "General")
        page = {"id": next_page_id, "title": title, "content": content, "book_id": book_id, "category": category}
        next_page_id += 1
        # Add page to category
        if category not in book["categories"]:
            book["categories"][category] = []
        book["categories"][category].append(page)
        return redirect(url_for("view_book", book_id=book_id))
    return render_template("new_page.html", book_id=book_id, book=book)

@app.route("/book/<int:book_id>/page/<int:page_id>")
def view_page(book_id, page_id):
    if "user" not in session:
        return redirect(url_for("login"))
    book = books.get(book_id)
    if not book:
        return "Book not found!"
    for category_pages in book["categories"].values():
        for page in category_pages:
            if page["id"] == page_id:
                return render_template("view_page.html", page=page, book_id=book_id)
    return "Page not found!"

@app.route("/book/<int:book_id>/page/<int:page_id>/edit", methods=["GET", "POST"])
def edit_page(book_id, page_id):
    if "user" not in session:
        return redirect(url_for("login"))
    book = books.get(book_id)
    if not book:
        return "Book not found!"
    page_to_edit = None
    for category_pages in book["categories"].values():
        for page in category_pages:
            if page["id"] == page_id:
                page_to_edit = page
                break
    if not page_to_edit:
        return "Page not found!"
    if request.method == "POST":
        page_to_edit["title"] = request.form["title"]
        page_to_edit["content"] = request.form["content"]
        return redirect(url_for("view_page", book_id=book_id, page_id=page_id))
    return render_template("new_page.html", page=page_to_edit, book_id=book_id, book=book)

# -------------------------
# Run App
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)
