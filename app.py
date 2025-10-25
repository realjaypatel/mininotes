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
    # Show only orgs user owns or belongs to
    orgs = list(mongo.db.orgs.find({"$or": [{"owner": username}, {"users": username}]}))
    return render_template("orgs.html", orgs=orgs, username=username)


@app.route("/landing")
def landing():
    return render_template("landing.html")


# ---------- HELPER ----------
def has_org_access(org_name, username):
    org_data = mongo.db.orgs.find_one({"name": org_name})
    if not org_data:
        return False
    return username == org_data["owner"] or username in org_data.get("users", [])


# ---------- ORG ----------
@app.route("/<org>")
def view_org(org):
    if "username" not in session:
        return redirect(url_for("login"))
    username = session["username"]
    if not has_org_access(org, username):
        return "Access denied", 403

    spaces = list(mongo.db.spaces.find({"org": org}))
    return render_template("spaces.html", org=org, spaces=spaces)


@app.route("/<org>/create_space", methods=["POST"])
def create_space(org):
    if "username" not in session:
        return redirect(url_for("login"))
    username = session["username"]
    if not has_org_access(org, username):
        return "Access denied", 403

    name = request.form["name"]
    mongo.db.spaces.insert_one({"org": org, "name": name})
    return redirect(url_for("view_org", org=org))


# ---------- SPACE ----------
@app.route("/<org>/<space>")
def view_space(org, space):
    if "username" not in session:
        return redirect(url_for("login"))
    username = session["username"]
    if not has_org_access(org, username):
        return "Access denied", 403

    pages = mongo.db.pages.find({"org": org, "space": space})
    return render_template("pages.html", org=org, space=space, pages=pages)


@app.route("/<org>/<space>/new", methods=["GET", "POST"])
def new_page(org, space):
    if "username" not in session:
        return redirect(url_for("login"))
    username = session["username"]
    if not has_org_access(org, username):
        return "Access denied", 403

    if request.method == "POST":
        title = request.form["title"]
        content = request.form["content"]
        mongo.db.pages.insert_one({"org": org, "space": space, "title": title, "content": content})
        return redirect(url_for("view_space", org=org, space=space))
    return render_template("page_edit.html", org=org, space=space, action="New")


@app.route("/<org>/<space>/<page>")
def view_page(org, space, page):
    if "username" not in session:
        return redirect(url_for("login"))
    username = session["username"]
    if not has_org_access(org, username):
        return "Access denied", 403

    p = mongo.db.pages.find_one({"org": org, "space": space, "title": page})
    return render_template("page_view.html", org=org, space=space, page=p)


@app.route("/<org>/<space>/<page>/edit", methods=["GET", "POST"])
def edit_page(org, space, page):
    if "username" not in session:
        return redirect(url_for("login"))
    username = session["username"]
    if not has_org_access(org, username):
        return "Access denied", 403

    p = mongo.db.pages.find_one({"org": org, "space": space, "title": page})
    if request.method == "POST":
        mongo.db.pages.update_one({"_id": p["_id"]}, {"$set": {"content": request.form["content"]}})
        return redirect(url_for("view_page", org=org, space=space, page=page))
    return render_template("page_edit.html", org=org, space=space, page=p, action="Edit")


# ---------- ORG SEARCH ----------
@app.route("/<org>/search", methods=["GET", "POST"])
def org_search(org):
    if "username" not in session:
        return redirect(url_for("login"))
    username = session["username"]
    if not has_org_access(org, username):
        return "Access denied", 403

    query = request.args.get("q", "")
    results = []
    if query:
        results = list(mongo.db.pages.find({
            "org": org,
            "$or": [
                {"title": {"$regex": query, "$options": "i"}},
                {"content": {"$regex": query, "$options": "i"}}
            ]
        }))
    return render_template("org_search.html", org=org, query=query, results=results)


# ---------- ORG CREATE / EDIT ----------
@app.route("/org/new", methods=["GET", "POST"])
def new_org():
    if "username" not in session:
        return redirect(url_for("login"))
    
    if request.method == "POST":
        name = request.form["name"]
        users_str = request.form.get("users", "")
        users_list = [u.strip() for u in users_str.split(",") if u.strip()]
        mongo.db.orgs.insert_one({"name": name, "owner": session["username"], "users": users_list})
        return redirect(url_for("home"))
    
    return render_template("org_form.html", action="New", org=None)


@app.route("/org/<org_id>/edit", methods=["GET", "POST"])
def edit_org(org_id):
    if "username" not in session:
        return redirect(url_for("login"))

    org_data = mongo.db.orgs.find_one({"_id": ObjectId(org_id)})
    if not org_data:
        return "Organization not found", 404

    if request.method == "POST":
        new_name = request.form["name"]
        users_str = request.form.get("users", "")
        users_list = [u.strip() for u in users_str.split(",") if u.strip()]
        mongo.db.orgs.update_one(
            {"_id": org_data["_id"]},
            {"$set": {"name": new_name, "users": users_list}}
        )
        return redirect(url_for("home"))

    return render_template("org_form.html", action="Edit", org=org_data)


if __name__ == "__main__":
    app.run(debug=True)
