# client = MongoClient("mongodb+srv://user:user@cluster0.u3fdtma.mongodb.net/md")

from flask import Flask, render_template, request, redirect, url_for, session
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"

app.config["MONGO_URI"] = "mongodb+srv://user:user@cluster0.u3fdtma.mongodb.net/md1"
mongo = PyMongo(app)

# ---------- AUTH ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        if mongo.db.users.find_one({"username": username}):
            return "User exists!"
        mongo.db.users.insert_one({"username": username, "password": password})
        session["username"] = username
        return redirect(url_for("home"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        user = mongo.db.users.find_one({"username": username})
        if user and check_password_hash(user["password"], request.form["password"]):
            session["username"] = username
            return redirect(url_for("home"))
        return "Invalid credentials"
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("landing"))


# ---------- LANDING ----------
@app.route("/")
def home():
    if "username" not in session:
        return redirect(url_for("landing"))

    username = session["username"]
    orgs = mongo.db.orgs.find({"owner": username})
    return render_template("orgs.html", orgs=orgs, username=username)


@app.route("/landing")
def landing():
    return render_template("landing.html")


@app.route("/create_org", methods=["POST"])
def create_org():
    if "username" not in session:
        return redirect(url_for("login"))
    name = request.form["name"]
    mongo.db.orgs.insert_one({"name": name, "owner": session["username"]})
    return redirect(url_for("home"))


# ---------- ORG ----------
@app.route("/<org>")
def view_org(org):
    if "username" not in session:
        return redirect(url_for("login"))
    spaces = mongo.db.spaces.find({"org": org})
    spaces = list(mongo.db.spaces.find({"org": org}))
    return render_template("spaces.html", org=org, spaces=spaces)


@app.route("/<org>/create_space", methods=["POST"])
def create_space(org):
    name = request.form["name"]
    mongo.db.spaces.insert_one({"org": org, "name": name})
    return redirect(url_for("view_org", org=org))


# ---------- SPACE ----------
@app.route("/<org>/<space>")
def view_space(org, space):
    pages = mongo.db.pages.find({"org": org, "space": space})
    return render_template("pages.html", org=org, space=space, pages=pages)


@app.route("/<org>/<space>/new", methods=["GET", "POST"])
def new_page(org, space):
    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        mongo.db.pages.insert_one({"org": org, "space": space, "title": title, "content": content})
        return redirect(url_for("view_space", org=org, space=space))
    return render_template("page_edit.html", org=org, space=space, action="New")


@app.route("/<org>/<space>/<page>")
def view_page(org, space, page):
    p = mongo.db.pages.find_one({"org": org, "space": space, "title": page})
    return render_template("page_view.html", org=org, space=space, page=p)


@app.route("/<org>/<space>/<page>/edit", methods=["GET", "POST"])
def edit_page(org, space, page):
    p = mongo.db.pages.find_one({"org": org, "space": space, "title": page})
    if request.method == "POST":
        mongo.db.pages.update_one({"_id": p["_id"]}, {"$set": {"content": request.form["content"]}})
        return redirect(url_for("view_page", org=org, space=space, page=page))
    return render_template("page_edit.html", org=org, space=space, page=p, action="Edit")


@app.route("/<org>/search", methods=["GET", "POST"])
def org_search(org):
    query = request.args.get("q", "")
    results = []

    if query:
        # Search only inside this org
        results = list(mongo.db.pages.find({
            "org": org,
            "$or": [
                {"title": {"$regex": query, "$options": "i"}},
                {"content": {"$regex": query, "$options": "i"}}
            ]
        }))

    return render_template("org_search.html", org=org, query=query, results=results)

if __name__ == "__main__":
    app.run(debug=True)
