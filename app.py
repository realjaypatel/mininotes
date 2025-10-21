from flask import Flask, render_template, request, redirect, session, url_for
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"

# MongoDB connection
client = MongoClient("mongodb+srv://user:user@cluster0.u3fdtma.mongodb.net/md")
db = client.md
users_col = db.users
books_col = db.books

# -------------------
# ROUTES
# -------------------

@app.route("/")
def home():
    if 'user' in session:
        user = session['user']
        # Fetch only the user's books
        books = list(books_col.find({"user": user}))
        all_pages = []
        for book in books:
            for page in book.get("pages", []):
                all_pages.append({
                    "title": page["title"],
                    "icon": page.get("icon", "📄"),
                    "book_title": book["title"],
                    "book_id": str(book["_id"]),
                    "page_id": page["id"]
                })
        return render_template("home.html", books=books, all_pages=all_pages)
    else:
        # Non-logged-in users see public landing page
        return render_template("public_home.html")

# -------------------
# REGISTER / LOGIN
# -------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        if users_col.find_one({"username": username}):
            return "User already exists"
        users_col.insert_one({"username": username, "password": password})
        session['user'] = username
        return redirect(url_for('home'))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = users_col.find_one({"username": username})
        if user and check_password_hash(user["password"], password):
            session['user'] = username
            return redirect(url_for('home'))
        else:
            return "Invalid credentials"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop('user', None)
    return redirect(url_for('home'))

# -------------------
# BOOKS & PAGES
# -------------------

@app.route("/book/new", methods=["GET", "POST"])
def new_book():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method == "POST":
        title = request.form["title"]
        books_col.insert_one({
            "title": title,
            "user": session['user'],
            "pages": []
        })
        return redirect(url_for('home'))
    return render_template("new_book.html")

@app.route("/book/<book_id>")
def view_book(book_id):
    book = books_col.find_one({"_id": ObjectId(book_id)})
    return render_template("view_book.html", book=book)

@app.route("/book/<book_id>/page/new", methods=["GET", "POST"])
def new_page(book_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    book = books_col.find_one({"_id": ObjectId(book_id)})
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        icon = request.form.get("icon", "📄")
        page_id = str(ObjectId())
        page = {"id": page_id, "title": title, "content": content, "icon": icon}
        books_col.update_one({"_id": ObjectId(book_id)}, {"$push": {"pages": page}})
        return redirect(url_for('view_book', book_id=book_id))
    return render_template("new_page.html", book=book)

@app.route("/book/<book_id>/page/<page_id>", methods=["GET", "POST"])
def view_page(book_id, page_id):
    book = books_col.find_one({"_id": ObjectId(book_id)})
    page = next((p for p in book.get("pages", []) if p["id"] == page_id), None)
    if request.method == "POST":
        page["title"] = request.form["title"]
        page["content"] = request.form["content"]
        page["icon"] = request.form.get("icon", "📄")
        # Save back
        books_col.update_one({"_id": ObjectId(book_id)}, {"$set": {"pages": book["pages"]}})
        return redirect(url_for('view_page', book_id=book_id, page_id=page_id))
    return render_template("view_page.html", book=book, page=page)

# -------------------
# RUN APP
# -------------------

if __name__ == "__main__":
    app.run(debug=True)
